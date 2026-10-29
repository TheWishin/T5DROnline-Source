"""The game's own rank plates in the launcher, read from the player's game files (never shipped with it).

Tekken 5 DR's online lobby shows a player's rank as a plate ("Beginner", "9th kyu" ... "Lone Wolf" ... "Tekken Lord"),
one per rank in the game's rank order (ranks.RANKS). Their English pictures are textures 30-66 (192 x 96, DXT5) of
the online lobby's layout TK5OL_onlinebattle_i18n, entry 2344 of the game's data table in T55DATA1.BIN:

* the table: EBOOT 0x10053FB0, 2,345 entries of {sector, stored, size, sum, flag, key, ptr} (u32, big-endian);
  the entry is `stored` bytes at sector * 0x800 of T55DATA1.BIN;
* XOR-coded per 32-bit word with key, 5 * key + 3, ... (the key restarts every 0x800 bytes), the words' sum (little-
  endian) must be `sum`; zlib-packed when stored != size (src/directfight/costume_logic.h t55_decode, the same code);
* a pack {u32 count, {u32 offset, u32 size} x count} (little-endian): [0] the layout ("SWG\\0", the name at +8),
  [1] the textures (a pack of NTP3 files), [2] more layout data;
* an NTP3 file: "NTP3", then at +0x10 a picture header (big-endian): +0x18 data size, +0x1C header size, +0x23
  format (2 = DXT5), +0x24 width, +0x26 height; the pixels follow the header (0x10 + header size).

Nothing of the game is in the repository: only these offsets and the decoding. extract() writes the plates as PNGs
into a cache folder of the player's install (<output folder>\\cache\\ranks, next to the unpacked game), the launcher
shows them from there; without it (before BUILD GAME, a failed read) the UI draws its own text badges.

    python -m t5lobby.rank_art --out <the launcher's output folder, e.g. native>
"""
import argparse
import array
import json
import os
import struct
import sys
import threading
import zlib

FORMAT = 1                      # bump when what is written changes (the folder is made again)
TOC_VA = 0x10053FB0
TOC_LEN = 2345
ENTRY = 2344                    # TK5OL_onlinebattle_i18n (English pictures)
LAYOUT_NAME = b"TK5OL_onlinebattle_i18n"
TEX_FIRST = 30                  # the plates: textures 30 .. 66, ranks.RANKS order
TEX_W, TEX_H = 192, 96
COUNT = 37
MAX_STORED = 64 << 20
DATA_REL = (os.path.join("game", "pkg", "USRDIR", "T55DATA1.BIN"),
            os.path.join("game", "vfs", "dev_hdd0", "game", "NPUB30009", "USRDIR", "T55DATA1.BIN"))
ELF_REL = os.path.join("game", "EBOOT.elf")


class ArtError(Exception):
    pass


# ---------------------------------------------------------------------------------------------- the game's files
def elf_read(path, va, n):
    """`n` bytes at virtual address `va` of a big-endian ELF64 (the decrypted EBOOT)."""
    with open(path, "rb") as f:
        hdr = f.read(64)
        if hdr[:4] != b"\x7fELF" or hdr[4] != 2 or hdr[5] != 2:
            raise ArtError("not the game's program (EBOOT.elf)")
        phoff, = struct.unpack(">Q", hdr[0x20:0x28])
        phent, phnum = struct.unpack(">HH", hdr[0x36:0x3A])
        f.seek(phoff)
        table = f.read(phent * phnum)
        for i in range(phnum):
            p_type, _flags, off, vaddr, _pa, filesz, _memsz, _al = struct.unpack(
                ">IIQQQQQQ", table[i * phent:i * phent + 56])
            if p_type == 1 and vaddr <= va and va + n <= vaddr + filesz:
                f.seek(off + va - vaddr)
                data = f.read(n)
                if len(data) == n:
                    return data
    raise ArtError("the game's data table is not in its program")


def t55_decode(raw, key):
    """The XOR coding of a T55DATA entry -> (decoded bytes, the sum of its words)."""
    n = len(raw)
    stream = bytearray(0x800)
    k = key & 0xFFFFFFFF
    for i in range(0, 0x800, 4):
        stream[i:i + 4] = k.to_bytes(4, "little")
        k = (5 * k + 3) & 0xFFFFFFFF
    full = n // 0x800 * 0x800
    ks = int.from_bytes(stream, "little")
    out = bytearray(n)
    for o in range(0, full, 0x800):           # a big integer XOR per 2 KB block
        out[o:o + 0x800] = (int.from_bytes(raw[o:o + 0x800], "little") ^ ks).to_bytes(0x800, "little")
    tail = n - full
    if tail:
        out[full:] = bytes(a ^ b for a, b in zip(raw[full:], stream[:tail]))
    words = array.array("I")
    words.frombytes(bytes(out[:n // 4 * 4]))
    if sys.byteorder != "little":
        words.byteswap()
    return bytes(out), sum(words) & 0xFFFFFFFF


def read_entry(elf, data, index=ENTRY):
    sector, stored, size, total, _flag, key, _ptr = struct.unpack(">7I", elf_read(elf, TOC_VA + 28 * index, 28))
    if not (0 < stored <= MAX_STORED and 0 < size <= 4 * MAX_STORED):
        raise ArtError("the layout's entry is not one")
    with open(data, "rb") as f:
        f.seek(sector * 0x800)
        raw = f.read(stored)
    if len(raw) != stored:
        raise ArtError("the game's data file is too short")
    out, s = t55_decode(raw, key)
    if s != total:
        raise ArtError("the layout does not match its checksum")
    if stored != size:
        try:
            out = zlib.decompress(out)
        except zlib.error:
            raise ArtError("the layout does not inflate") from None
        if len(out) != size:
            raise ArtError("the layout has the wrong size")
    return out


def pack_items(d, base=0, end=None):
    end = len(d) if end is None else end
    if end - base < 4:
        raise ArtError("a pack is cut off")
    n, = struct.unpack_from("<I", d, base)
    if not 0 < n < 4096 or base + 4 + 8 * n > end:
        raise ArtError("a pack has no table")
    out = []
    for i in range(n):
        off, size = struct.unpack_from("<II", d, base + 4 + 8 * i)
        if off + size > end - base:
            raise ArtError("a pack's part is cut off")
        out.append((base + off, size))
    return out


def plates_dxt(layout):
    """The 37 plates' DXT5 data from the decoded layout."""
    parts = pack_items(layout)
    if len(parts) < 2:
        raise ArtError("the layout has no textures")
    o, n = parts[0]
    if layout[o:o + 4] != b"SWG\0" or layout[o + 8:o + 8 + len(LAYOUT_NAME) + 1] != LAYOUT_NAME + b"\0":
        raise ArtError("not the online lobby's layout")
    to, tn = parts[1]
    texs = pack_items(layout, to, to + tn)
    if len(texs) < TEX_FIRST + COUNT:
        raise ArtError("the layout has too few textures")
    out = []
    for i in range(COUNT):
        o, n = texs[TEX_FIRST + i]
        h = layout[o:o + 0x30]
        if len(h) < 0x30 or h[:4] != b"NTP3":
            raise ArtError(f"texture {TEX_FIRST + i} is not one")
        dsize, = struct.unpack_from(">I", h, 0x18)
        hsize, = struct.unpack_from(">H", h, 0x1C)
        fmt = h[0x23]
        w, ht = struct.unpack_from(">HH", h, 0x24)
        if (w, ht, fmt) != (TEX_W, TEX_H, 2) or dsize != w * ht or 0x10 + hsize + dsize > n:
            raise ArtError(f"texture {TEX_FIRST + i} is not a rank plate")
        start = o + 0x10 + hsize
        out.append(layout[start:start + dsize])
    return out


# ---------------------------------------------------------------------------------------------- pictures
def dxt5_rgba(data, w, h):
    """RGBA bytes of DXT5 (BC3) blocks."""
    out = bytearray(w * h * 4)
    p = 0
    stride = w * 4
    for by in range(0, h, 4):
        for bx in range(0, w, 4):
            a0, a1 = data[p], data[p + 1]
            abits = int.from_bytes(data[p + 2:p + 8], "little")
            if a0 > a1:
                al = (a0, a1, (6 * a0 + a1) // 7, (5 * a0 + 2 * a1) // 7, (4 * a0 + 3 * a1) // 7,
                      (3 * a0 + 4 * a1) // 7, (2 * a0 + 5 * a1) // 7, (a0 + 6 * a1) // 7)
            else:
                al = (a0, a1, (4 * a0 + a1) // 5, (3 * a0 + 2 * a1) // 5, (2 * a0 + 3 * a1) // 5,
                      (a0 + 4 * a1) // 5, 0, 255)
            c0 = data[p + 8] | data[p + 9] << 8
            c1 = data[p + 10] | data[p + 11] << 8
            bits = int.from_bytes(data[p + 12:p + 16], "little")
            r0, g0, b0 = (c0 >> 11) * 255 // 31, (c0 >> 5 & 63) * 255 // 63, (c0 & 31) * 255 // 31
            r1, g1, b1 = (c1 >> 11) * 255 // 31, (c1 >> 5 & 63) * 255 // 63, (c1 & 31) * 255 // 31
            cols = ((r0, g0, b0), (r1, g1, b1),
                    ((2 * r0 + r1) // 3, (2 * g0 + g1) // 3, (2 * b0 + b1) // 3),
                    ((r0 + 2 * r1) // 3, (g0 + 2 * g1) // 3, (b0 + 2 * b1) // 3))
            p += 16
            for py in range(4):
                q = (by + py) * stride + bx * 4
                for px in range(4):
                    i = py * 4 + px
                    r, g, b = cols[bits >> (2 * i) & 3]
                    out[q] = r
                    out[q + 1] = g
                    out[q + 2] = b
                    out[q + 3] = al[abits >> (3 * i) & 7]
                    q += 4
    return out


def scale_rgba(rgba, w, h, nw, nh):
    """Area-average downscale (premultiplied alpha) to nw x nh."""
    def weights(n_in, n_out):
        f = n_in / n_out
        res = []
        for o in range(n_out):
            a, b = o * f, (o + 1) * f
            taps = []
            i = int(a)
            while i < b and i < n_in:
                wgt = min(b, i + 1) - max(a, i)
                if wgt > 1e-9:
                    taps.append((i, wgt / f))
                i += 1
            res.append(taps)
        return res
    wx, wy = weights(w, nw), weights(h, nh)
    rows = []
    for y in range(h):
        base = y * w * 4
        src = rgba[base:base + w * 4]
        a = src[3::4]
        pr = [src[4 * i] * a[i] for i in range(w)]
        pg = [src[4 * i + 1] * a[i] for i in range(w)]
        pb = [src[4 * i + 2] * a[i] for i in range(w)]
        row = []
        for taps in wx:
            row.append((sum(pr[i] * k for i, k in taps), sum(pg[i] * k for i, k in taps),
                        sum(pb[i] * k for i, k in taps), sum(a[i] * k for i, k in taps)))
        rows.append(row)
    out = bytearray(nw * nh * 4)
    q = 0
    for taps in wy:
        for x in range(nw):
            r = g = b = al = 0.0
            for y, k in taps:
                c = rows[y][x]
                r += c[0] * k
                g += c[1] * k
                b += c[2] * k
                al += c[3] * k
            if al > 0.5:
                out[q] = min(255, int(r / al + 0.5))
                out[q + 1] = min(255, int(g / al + 0.5))
                out[q + 2] = min(255, int(b / al + 0.5))
                out[q + 3] = min(255, int(al + 0.5))
            q += 4
    return out


def png_bytes(rgba, w, h):
    raw = bytearray()
    for y in range(h):
        raw.append(0)
        raw += rgba[y * w * 4:(y + 1) * w * 4]

    def chunk(tag, data):
        c = tag + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(bytes(raw), 9)) + chunk(b"IEND", b""))


def png_rgba(data):
    """RGBA bytes of a PNG this module wrote (8-bit RGBA, filter 0) -> (w, h, rgba)."""
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ArtError("not a PNG")
    p, w, h, idat = 8, 0, 0, b""
    while p + 8 <= len(data):
        n, tag = struct.unpack(">I4s", data[p:p + 8])
        body = data[p + 8:p + 8 + n]
        if tag == b"IHDR":
            w, h, depth, ctype = struct.unpack(">IIBB", body[:10])
            if depth != 8 or ctype != 6:
                raise ArtError("not an RGBA PNG")
        elif tag == b"IDAT":
            idat += body
        p += 12 + n
    raw = zlib.decompress(idat)
    out = bytearray()
    for y in range(h):
        line = raw[y * (w * 4 + 1):(y + 1) * (w * 4 + 1)]
        if line[:1] != b"\0":
            raise ArtError("a filtered PNG")
        out += line[1:]
    return w, h, out


# ---------------------------------------------------------------------------------------------- the cache folder
def folder_for(out_dir):
    return os.path.join(out_dir, "cache", "ranks")


# 1.1.9: the European releases are other builds of the game (src/platform/t5_game.h): their data table is elsewhere in
# the program and numbered differently (NPEA00019 v01.00: one entry fewer before the fighter renders, no online lobby
# layout), so the offsets above would read other pictures. Told by the ELF header's e_entry; the UI then draws its
# own badges and names.
OTHER_PROGRAMS = {0x356980: "NPEA00019 v01.00", 0x457898: "NPEA00019 v02.00"}


def other_program(elf):
    """The name of a known other program than NPUB30009 v01.00 in the ELF at `elf`, or None."""
    try:
        with open(elf, "rb") as f:
            hdr = f.read(0x20)
    except OSError:
        return None
    return OTHER_PROGRAMS.get(struct.unpack_from(">Q", hdr, 0x18)[0]) if len(hdr) == 0x20 else None


def find_sources(out_dir):
    """(EBOOT.elf, T55DATA1.BIN) of an install's output folder, or None (also for a European program)."""
    elf = os.path.join(out_dir, ELF_REL)
    if not os.path.isfile(elf) or other_program(elf):
        return None
    for rel in DATA_REL:
        p = os.path.join(out_dir, rel)
        if os.path.isfile(p):
            return elf, p
    return None


def _write(path, data):
    tmp = f"{path}.{os.getpid()}.tmp"
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, path)


def plate_path(folder, tier, height=None):
    return os.path.join(folder, f"rank_{tier:02d}.png" if height is None else f"rank_{tier:02d}_h{height}.png")


def is_ready(folder):
    try:
        with open(os.path.join(folder, "ranks.json"), encoding="utf-8") as f:
            info = json.load(f)
    except (OSError, ValueError):
        return False
    return (isinstance(info, dict) and info.get("format") == FORMAT and info.get("count") == COUNT
            and all(os.path.isfile(plate_path(folder, i)) for i in range(COUNT)))


def extract(out_dir, folder=None, log=None):
    """Read the plates from the install's game files into the cache folder. -> the folder. ArtError when the
    files are not there or not the game's."""
    folder = folder or folder_for(out_dir)
    src = find_sources(out_dir)
    if not src:
        raise ArtError("the game is not unpacked yet (BUILD GAME)")
    layout = read_entry(*src)
    dxts = plates_dxt(layout)
    os.makedirs(folder, exist_ok=True)
    for i, d in enumerate(dxts):
        _write(plate_path(folder, i), png_bytes(dxt5_rgba(d, TEX_W, TEX_H), TEX_W, TEX_H))
    _write(os.path.join(folder, "ranks.json"),
           json.dumps({"format": FORMAT, "count": COUNT, "w": TEX_W, "h": TEX_H, "entry": ENTRY,
                       "textures": [TEX_FIRST, TEX_FIRST + COUNT - 1]}).encode("utf-8"))
    if log:
        log(f"rank plates: {COUNT} read from the game's data into {folder}")
    return folder


def ensure_height(folder, height):
    """The plates at `height` pixels (width twice that) in the folder, made from the full-size ones if missing."""
    for i in range(COUNT):
        p = plate_path(folder, i, height)
        if os.path.isfile(p):
            continue
        with open(plate_path(folder, i), "rb") as f:
            w, h, rgba = png_rgba(f.read())
        nw = max(1, int(round(w * height / h)))
        _write(p, png_bytes(scale_rgba(rgba, w, h, nw, height), nw, height))


# ---------------------------------------------------------------------------------------------- for the UI
class Art:
    """The plates for one Tk interpreter: folder set by the launcher, PhotoImages made on first use (cached)."""

    def __init__(self):
        self.folder = os.environ.get("T5_RANK_ART") or None
        self.ready = bool(self.folder and is_ready(self.folder))
        self.heights = set()          # heights made (or checked) in the folder
        self.images = {}              # (tier, height) -> PhotoImage
        self.listeners = []           # called (on the Tk thread) when the plates became available
        self.lock = threading.Lock()

    def set_folder(self, folder):
        if os.environ.get("T5_RANK_ART"):
            return                    # (tests, screenshots: a fixed folder)
        if folder != self.folder:
            self.folder, self.images, self.heights = folder, {}, set()
        self.ready = bool(folder and is_ready(folder))

    def available(self):
        return self.ready

    def has(self, height):
        """The plates can be shown at `height` pixels now."""
        return self.ready and height in self.heights

    def image(self, master, tier, height):
        """A PhotoImage of the plate of `tier` at `height` pixels, or None (no plates, not made yet)."""
        if not self.ready or tier is None or not 0 <= tier < COUNT:
            return None
        key = (tier, height)
        img = self.images.get(key)
        if img is None:
            if height not in self.heights:
                return None           # prepare() makes them off the Tk thread
            import tkinter as tk
            try:
                img = tk.PhotoImage(master=master, file=plate_path(self.folder, tier, height))
            except (tk.TclError, OSError):
                return None
            self.images[key] = img
        return img

    def prepare(self, heights, out_dir=None, after=None, log=None):
        """In a thread: extract the plates when the folder has none (and the game files are there), make the
        `heights`; then after(0, callback) on the Tk thread (a widget's after) -> notify the listeners."""
        heights = sorted(set(int(h) for h in heights if h and h > 0))

        def work():
            ok = False
            try:
                with self.lock:
                    if not self.folder or not is_ready(self.folder):
                        if out_dir and self.folder and find_sources(out_dir):
                            extract(out_dir, self.folder, log=log)
                    if self.folder and is_ready(self.folder):
                        for h in heights:
                            ensure_height(self.folder, h)
                        ok = True
            except (ArtError, OSError, ValueError, zlib.error) as e:
                if log:
                    log(f"rank plates: not read ({e}); the launcher draws its own badges")
            if ok and after:
                try:
                    after(0, lambda: self._done(heights))       # a widget's after(ms, func): after(func) failed in 1.1.5
                except Exception:   # noqa: BLE001 -- the window is gone (RuntimeError, TclError)
                    pass
        threading.Thread(target=work, name="rank-art", daemon=True).start()

    def _done(self, heights):
        self.ready = True
        self.heights.update(heights)
        for fn in list(self.listeners):
            try:
                fn()
            except Exception:   # noqa: BLE001 -- a listener must not stop the others (a window closed meanwhile)
                pass

    def prepare_now(self, heights):
        """The same without a thread (tests, screenshots)."""
        if self.folder and is_ready(self.folder):
            heights = sorted({int(h) for h in heights})
            for h in heights:
                ensure_height(self.folder, h)
            self._done(heights)


ART = Art()


def main(argv=None):
    ap = argparse.ArgumentParser(description="Read the game's rank plates into the launcher's cache folder.")
    ap.add_argument("--out", required=True, help="the launcher's output folder (the one BUILD GAME unpacked into)")
    ap.add_argument("--folder", help="where to write (default <out>\\cache\\ranks)")
    ap.add_argument("--heights", type=int, nargs="*", default=[])
    a = ap.parse_args(argv)
    try:
        folder = extract(a.out, a.folder, log=print)
        for h in a.heights:
            ensure_height(folder, h)
    except (ArtError, OSError) as e:
        print(f"rank plates: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
