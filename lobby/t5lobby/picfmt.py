"""Profile pictures (docs/ONLINE.md "Profile picture"): the one picture format the lobby takes, and the launcher's
picture work. Standard library only (zlib): the launcher's Python and the server have nothing else.

The format is a strict subset of PNG: 8-bit RGB, not interlaced, the chunks IHDR, IDAT..., IEND and nothing else --
no text, no time, no colour profile, no EXIF, no palette, no alpha, nothing after IEND. `clean()` is the only way a
picture gets onto the server or onto a player's screen: it unpacks the pixels (bounded: a small file cannot unpack to
more than width x height says) and packs them again with `encode()`, so what is stored and shown is always this
module's own bytes of the pixels alone. `encode()` is deterministic: the launcher and the server make the same file
from the same pixels.

The launcher half: `read_ppm` (the game's backbuffer picture), `portrait` (crop and shrink to the profile's size),
`fit` (the largest version of the pixels that stays under the byte limit).
"""
import struct
import zlib

MAX_W, MAX_H = 240, 320         # the profile's picture: at most this many pixels ...
MIN_W, MIN_H = 48, 64           # ... and at least this many
MAX_BYTES = 200_000             # one picture, as a file
SIGNATURE = b"\x89PNG\r\n\x1a\n"


class PicError(ValueError):
    """Not a picture of the format above (the text says what; English, for logs and tests)."""


def _chunk(kind, data):
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)


def _paeth(a, b, c):
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    return b if pb <= pc else c


def _filters(row, prev):
    """The five PNG filters of one row of RGB bytes (prev: the row above, zeros for the first)."""
    left = b"\0\0\0" + row[:-3]
    upleft = b"\0\0\0" + prev[:-3]
    yield 0, row
    yield 1, bytes((x - a) & 255 for x, a in zip(row, left))
    yield 2, bytes((x - b) & 255 for x, b in zip(row, prev))
    yield 3, bytes((x - ((a + b) >> 1)) & 255 for x, a, b in zip(row, left, prev))
    yield 4, bytes((x - _paeth(a, b, c)) & 255 for x, a, b, c in zip(row, left, prev, upleft))


def _cost(line):
    """PNG's usual heuristic: the sum of the bytes read as signed (small differences pack best)."""
    return sum(v if v < 128 else 256 - v for v in line)


def encode(w, h, rgb):
    """Pixels (w * h * 3 bytes, rows from the top) -> the PNG file. Always the same bytes for the same pixels."""
    if not (isinstance(w, int) and isinstance(h, int) and w > 0 and h > 0 and len(rgb) == w * h * 3):
        raise PicError("pixels do not match the size")
    stride = w * 3
    prev = bytes(stride)
    out = bytearray()
    for y in range(h):
        row = bytes(rgb[y * stride:(y + 1) * stride])
        best = None
        for kind, line in _filters(row, prev):
            c = _cost(line)
            if best is None or c < best[0]:
                best = (c, kind, line)
        out.append(best[1])
        out += best[2]
        prev = row
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    return SIGNATURE + _chunk(b"IHDR", ihdr) + _chunk(b"IDAT", zlib.compress(bytes(out), 9)) + _chunk(b"IEND", b"")


def decode(data, max_w=MAX_W, max_h=MAX_H, max_bytes=MAX_BYTES, min_w=MIN_W, min_h=MIN_H):
    """The PNG file -> (w, h, rgb). Refuses (PicError) everything that is not the strict format: another chunk,
    another pixel format, a size outside the limits, bytes after IEND, a wrong checksum, packed data that is not
    exactly the pixels."""
    if not isinstance(data, (bytes, bytearray)):
        raise PicError("not bytes")
    data = bytes(data)
    if len(data) > max_bytes:
        raise PicError("too big")
    if data[:8] != SIGNATURE:
        raise PicError("not a PNG file")
    pos, chunks = 8, []
    while True:
        if pos + 12 > len(data):
            raise PicError("cut short")
        n, kind = struct.unpack(">I4s", data[pos:pos + 8])
        if n > len(data) - pos - 12:
            raise PicError("cut short")
        body = data[pos + 8:pos + 8 + n]
        if struct.unpack(">I", data[pos + 8 + n:pos + 12 + n])[0] != zlib.crc32(kind + body) & 0xFFFFFFFF:
            raise PicError("damaged")
        chunks.append((kind, body))
        pos += 12 + n
        if kind == b"IEND":
            break
        if len(chunks) > 4096:
            raise PicError("too many parts")
    if pos != len(data):
        raise PicError("bytes after the picture")
    kinds = [k for k, _ in chunks]
    if len(kinds) < 3 or kinds[0] != b"IHDR" or kinds[-1] != b"IEND" or any(k != b"IDAT" for k in kinds[1:-1]) \
            or chunks[-1][1]:
        raise PicError("only the picture itself is allowed in the file")
    if len(chunks[0][1]) != 13:
        raise PicError("bad header")
    w, h, depth, colour, comp, filt, lace = struct.unpack(">IIBBBBB", chunks[0][1])
    if (depth, colour, comp, filt, lace) != (8, 2, 0, 0, 0):
        raise PicError("8-bit RGB without interlacing only")
    if not (min_w <= w <= max_w and min_h <= h <= max_h):
        raise PicError("size outside the limits")
    stride = w * 3
    want = h * (stride + 1)
    z = zlib.decompressobj()
    try:
        raw = z.decompress(b"".join(b for k, b in chunks[1:-1]), want + 1)
    except zlib.error:
        raise PicError("damaged pixels") from None
    if len(raw) != want or not z.eof or z.unused_data or z.unconsumed_tail:
        raise PicError("the packed data is not exactly the pixels")
    out = bytearray(w * h * 3)
    prev = bytes(stride)
    for y in range(h):
        base = y * (stride + 1)
        kind = raw[base]
        line = raw[base + 1:base + 1 + stride]
        if kind == 0:
            row = bytearray(line)
        elif kind == 1:
            row = bytearray(line)
            for i in range(3, stride):
                row[i] = (row[i] + row[i - 3]) & 255
        elif kind == 2:
            row = bytearray((x + b) & 255 for x, b in zip(line, prev))
        elif kind == 3:
            row = bytearray(line)
            for i in range(stride):
                a = row[i - 3] if i >= 3 else 0
                row[i] = (row[i] + ((a + prev[i]) >> 1)) & 255
        elif kind == 4:
            row = bytearray(line)
            for i in range(stride):
                a = row[i - 3] if i >= 3 else 0
                c = prev[i - 3] if i >= 3 else 0
                row[i] = (row[i] + _paeth(a, prev[i], c)) & 255
        else:
            raise PicError("unknown row filter")
        out[y * stride:(y + 1) * stride] = row
        prev = bytes(row)
    return w, h, bytes(out)


def clean(data, max_bytes=MAX_BYTES, **limits):
    """A picture somebody sent -> this module's own file of its pixels (and nothing else), or PicError."""
    w, h, rgb = decode(data, max_bytes=max_bytes, **limits)
    out = encode(w, h, rgb)
    if len(out) > max_bytes:
        raise PicError("too big")
    return out


# ----------------------------------------------------------------------------- the launcher's picture work
def read_ppm(data):
    """A binary PPM (P6, 8 bits; the game's backbuffer picture) -> (w, h, rgb)."""
    if data[:2] != b"P6":
        raise PicError("not a PPM picture")
    pos, vals = 2, []
    while len(vals) < 3:
        while pos < len(data) and data[pos:pos + 1].isspace():
            pos += 1
        if data[pos:pos + 1] == b"#":
            while pos < len(data) and data[pos:pos + 1] != b"\n":
                pos += 1
            continue
        start = pos
        while pos < len(data) and data[pos:pos + 1].isdigit():
            pos += 1
        if start == pos:
            raise PicError("bad PPM header")
        vals.append(int(data[start:pos]))
    pos += 1
    w, h, mx = vals
    if mx != 255 or w <= 0 or h <= 0 or w * h > 64_000_000 or len(data) - pos < w * h * 3:
        raise PicError("bad PPM picture")
    return w, h, bytes(data[pos:pos + w * h * 3])


def portrait(w, h, rgb, out_w=MAX_W, out_h=MAX_H, centre=0.5, rough=False):
    """The upright middle part of a wide picture, shrunk to out_w x out_h (each pixel the average of the source
    pixels it covers; `rough`: one source pixel each, fast, for a look at what a frame shows). `centre`: where the
    part's middle is, 0..1 of the width. -> (out_w, out_h, rgb)."""
    cw = min(w, max(1, (h * out_w) // out_h))
    ch = min(h, max(1, (cw * out_h) // out_w))
    x0 = max(0, min(w - cw, int(w * centre - cw / 2)))
    y0 = (h - ch) // 2
    xs = [x0 + (i * cw) // out_w for i in range(out_w + 1)]
    ys = [y0 + (j * ch) // out_h for j in range(out_h + 1)]
    out = bytearray(out_w * out_h * 3)
    if rough:
        o = 0
        for j in range(out_h):
            base = ys[j] * w * 3
            for i in range(out_w):
                p = base + xs[i] * 3
                out[o:o + 3] = rgb[p:p + 3]
                o += 3
        return out_w, out_h, bytes(out)
    o = 0
    for j in range(out_h):
        ya, yb = ys[j], max(ys[j] + 1, ys[j + 1])
        rows = [rgb[(y * w) * 3:(y * w + w) * 3] for y in range(ya, min(yb, h))]
        for i in range(out_w):
            xa, xb = xs[i], max(xs[i] + 1, xs[i + 1])
            r = g = b = 0
            for row in rows:
                seg = row[xa * 3:xb * 3]
                r += sum(seg[0::3])
                g += sum(seg[1::3])
                b += sum(seg[2::3])
            n = len(rows) * (xb - xa) or 1
            out[o], out[o + 1], out[o + 2] = r // n, g // n, b // n
            o += 3
    return out_w, out_h, bytes(out)


def fit(w, h, rgb, max_bytes=MAX_BYTES):
    """The PNG of the pixels under max_bytes: as they are, else with the lowest colour bits dropped (2, 3, 4 bits:
    the file packs better, the picture stays the same size). PicError if even that is too big."""
    for bits in (0, 2, 3, 4):
        if bits:
            mask = (0xFF << bits) & 0xFF
            half = 1 << (bits - 1)
            px = bytes(min(255, (v & mask) | half) for v in rgb)
        else:
            px = rgb
        data = encode(w, h, px)
        if len(data) <= max_bytes:
            return data
    raise PicError("too big")


def detail(w, h, rgb):
    """How much there is to see in the pixels: the mean difference between neighbours (0 = one flat colour; a
    black loading frame or a white flash scores near 0). The capture drops such frames."""
    step = max(1, (w * h) // 20000)
    total = n = 0
    for i in range(3, w * h * 3 - 3, 3 * step):
        total += abs(rgb[i] - rgb[i - 3]) + abs(rgb[i + 1] - rgb[i - 2]) + abs(rgb[i + 2] - rgb[i - 1])
        n += 1
    return total / max(1, n)
