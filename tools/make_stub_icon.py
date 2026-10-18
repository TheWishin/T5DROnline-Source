#!/usr/bin/env python3
"""Make launcher/stub/t5dr_bmp.ico from launcher/stub/t5dr.ico: the usual icon layout of a Windows
program -- small sizes as uncompressed bitmaps, the 256x256 image as PNG.

    python tools/make_stub_icon.py            (needs Pillow; run once, the result is committed)

t5dr.ico holds seven PNG images. A PNG is compressed data, so the resource section of the stub
(T5DR Online.exe) measures an entropy of 7.7 of 8, which looks like packed code to a scanner's model.
The bitmap frames bring it down to the range of ordinary programs. Same pictures, no resampling.
"""
import io
import os
import struct
import sys

HERE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "launcher", "stub")
KEEP_BMP = (16, 24, 32, 48, 64)      # 128 is left out: Windows scales the 256 image for it


def dib(img):
    """An icon image as the DIB the .ico format stores: BITMAPINFOHEADER (height doubled), 32-bit BGRA
    rows bottom-up, then the 1-bit AND mask (all zero: the alpha channel does the work)."""
    w, h = img.size
    px = img.convert("RGBA").tobytes()
    rows = [px[y * w * 4:(y + 1) * w * 4] for y in range(h)][::-1]
    bgra = b"".join(bytes(v for i in range(0, len(r), 4) for v in (r[i + 2], r[i + 1], r[i], r[i + 3])) for r in rows)
    mask = bytes(((w + 31) // 32 * 4) * h)
    head = struct.pack("<IiiHHIIiiII", 40, w, h * 2, 1, 32, 0, len(bgra) + len(mask), 0, 0, 0, 0)
    return head + bgra + mask


def main():
    try:
        from PIL import Image
    except ImportError:
        sys.exit("Pillow is needed to regenerate the icon (pip install --user pillow)")
    src = open(os.path.join(HERE, "t5dr.ico"), "rb").read()
    count = struct.unpack_from("<HHH", src, 0)[2]
    frames = []
    for i in range(count):
        w, h, _, _, _, _, size, off = struct.unpack_from("<BBBBHHII", src, 6 + 16 * i)
        w, h = w or 256, h or 256
        blob = src[off:off + size]
        if w == 256:
            frames.append((w, h, blob))                  # the PNG as it is
        elif w in KEEP_BMP:
            frames.append((w, h, dib(Image.open(io.BytesIO(blob)))))
    frames.sort(key=lambda f: f[0])
    out = struct.pack("<HHH", 0, 1, len(frames))
    off = 6 + 16 * len(frames)
    for w, h, blob in frames:
        out += struct.pack("<BBBBHHII", w % 256, h % 256, 0, 0, 1, 32, len(blob), off)
        off += len(blob)
    out += b"".join(f[2] for f in frames)
    with open(os.path.join(HERE, "t5dr_bmp.ico"), "wb") as f:
        f.write(out)
    print(f"t5dr_bmp.ico: {len(out):,} bytes, sizes {[f[0] for f in frames]} (t5dr.ico: {len(src):,} bytes)")


if __name__ == "__main__":
    main()
