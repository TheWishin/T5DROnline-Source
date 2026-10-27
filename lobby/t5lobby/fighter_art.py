"""The fighters' pictures in the launcher's character select, read from the player's own built game (never shipped).

The game's select screen shows a full-figure render of the fighter under each side's cursor ("chr_<code>_p1_in" /
"_p2_in" in its layout). They are entries 1475-1528 of the game's data table in T55DATA1.BIN (the table and its coding:
rank_art.py), one per fighter in the game's id order (docs/DIRECTFIGHT.md "Character ids"; a fighter that faces the
other way on the P2 side has a second, mirrored render right after its first):

* an entry is packed a second time, with the game's own LZ: a flag byte whose bits 0..6 say, low bit first, what the
  next seven items are -- 1 a byte as it is, 0 a copy of 2 bytes: length = byte0 >> 3 (0 = 32), distance =
  (byte0 & 7) << 8 | byte1 (0 = 2048) bytes back;
* unpacked it is an NTP3 file (rank_art.py) with one picture: DXT5, 1008 x 1080, alpha around the figure.

Of each render the launcher keeps a square around the head and shoulders (BOX: hand-placed for the pinned game
version, BUILD GAME checks it) and writes it as a PNG into <output folder>\\cache\\fighters (made on the first use
after BUILD GAME, made again when a file is missing). Nothing of the game is in the repository: only these entry
numbers, the squares and the decoding. Without the files (no build, a failed read) the grid shows the name tiles.

    python -m t5lobby.fighter_art --out <the launcher's output folder, e.g. native>
"""
import argparse
import json
import os
import struct
import sys
import threading
import zlib

from . import rank_art as ra

FORMAT = 1                     # bump when what is written changes (the folder is made again)
TEX_W, TEX_H = 1008, 1080
# the P1-side render of each game id 0..35 (Paul .. Jinpachi)
RENDERS = (1475, 1477, 1479, 1480, 1482, 1483, 1484, 1485, 1486, 1487, 1489, 1490, 1491, 1492, 1494, 1496, 1498,
           1500, 1502, 1504, 1505, 1507, 1509, 1510, 1511, 1513, 1514, 1515, 1516, 1518, 1520, 1522, 1523, 1525,
           1526, 1528)
# (left, top, side) of the head-and-shoulders square in the render, multiples of 4 (DXT blocks)
BOX = ((336, 0, 388), (360, 0, 388), (224, 0, 388), (456, 0, 388), (300, 48, 400), (268, 0, 388), (328, 0, 388),
       (300, 0, 388), (244, 0, 388), (372, 0, 388), (288, 0, 388), (312, 0, 388), (380, 112, 520), (136, 0, 400),
       (376, 0, 388), (352, 0, 388), (388, 0, 388), (276, 0, 388), (252, 0, 388), (264, 0, 388), (308, 0, 388),
       (264, 0, 388), (280, 0, 420), (416, 0, 388), (180, 32, 400), (468, 0, 388), (320, 0, 388), (252, 0, 388),
       (368, 0, 388), (320, 0, 400), (232, 0, 400), (184, 0, 400), (304, 0, 388), (380, 0, 388), (328, 0, 388),
       (332, 0, 388))
COUNT = len(RENDERS)
SIZE = 128                     # the stored pictures (smaller sizes are made from them on demand)


class ArtError(ra.ArtError):
    pass


def _write(path, data):
    """As rank_art._write, with the thread in the temporary name (the UI's thread and a test may both write)."""
    tmp = f"{path}.{os.getpid()}.{threading.get_ident()}.tmp"
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, path)


# ---------------------------------------------------------------------------------------------- the game's files
def lz_unpack(src, need=None):
    """The game's LZ (see above). `need`: stop once that many bytes are out (the rest is not needed)."""
    out = bytearray()
    i, n = 0, len(src)
    while i < n:
        flags = src[i]
        i += 1
        for b in range(7):
            if i >= n:
                break
            if flags >> b & 1:
                out.append(src[i])
                i += 1
                continue
            if i + 1 >= n:
                raise ArtError("a packed picture is cut off")
            b0, b1 = src[i], src[i + 1]
            i += 2
            length = b0 >> 3 or 32
            dist = ((b0 & 7) << 8 | b1) or 2048
            start = len(out) - dist
            if start < 0:
                out += bytes(min(length, -start))           # (before the start: zeros)
                length -= min(length, -start)
                start = len(out) - dist
            if dist >= length:
                out += out[start:start + length]
            else:
                for k in range(length):                     # (overlapping: a repeated pattern)
                    out.append(out[start + k])
        if need and len(out) >= need:
            break
    return out


def render_dxt(elf, data, gid, rows=TEX_H):
    """The DXT5 data of fighter `gid`'s render, its first `rows` pixel rows at least."""
    if not 0 <= gid < COUNT:
        raise ArtError("no such fighter")
    packed = ra.read_entry(elf, data, RENDERS[gid])
    head = 0x10 + 0x50
    nt = lz_unpack(packed, need=head + ((rows + 3) // 4) * (TEX_W // 4) * 16 + 16)
    if nt[:4] != b"NTP3" or len(nt) < 0x30:
        raise ArtError("the render is not a picture")
    dsize, = struct.unpack_from(">I", nt, 0x18)
    hsize, = struct.unpack_from(">H", nt, 0x1C)
    w, h = struct.unpack_from(">HH", nt, 0x24)
    if nt[0x23] != 2 or (w, h) != (TEX_W, TEX_H):
        raise ArtError("the render has another size or format (another version of the game?)")
    return bytes(nt[0x10 + hsize:0x10 + hsize + dsize])


def dxt5_square(data, w, x0, y0, side):
    """RGBA of the side x side square at (x0, y0) of a DXT5 picture `w` pixels wide (all multiples of 4)."""
    bw = w // 4
    out = bytearray(side * side * 4)
    stride = side * 4
    for by in range(y0 // 4, (y0 + side) // 4):
        for bx in range(x0 // 4, (x0 + side) // 4):
            p = (by * bw + bx) * 16
            blk = ra.dxt5_rgba(data[p:p + 16], 4, 4)
            for py in range(4):
                q = (by * 4 + py - y0) * stride + (bx * 4 - x0) * 4
                out[q:q + 16] = blk[py * 16:py * 16 + 16]
    return out


def portrait(elf, data, gid, size=SIZE):
    """RGBA bytes of fighter `gid`'s head-and-shoulders picture, size x size."""
    x0, y0, side = BOX[gid]
    dxt = render_dxt(elf, data, gid, rows=y0 + side)
    rgba = dxt5_square(dxt, TEX_W, x0, y0, side)
    return ra.scale_rgba(rgba, side, side, size, size)


# ---------------------------------------------------------------------------------------------- the cache folder
def folder_for(out_dir):
    return os.path.join(out_dir, "cache", "fighters")


def face_path(folder, gid, size=None):
    return os.path.join(folder, f"face_{gid:02d}.png" if size is None else f"face_{gid:02d}_{size}.png")


def is_ready(folder):
    try:
        with open(os.path.join(folder, "fighters.json"), encoding="utf-8") as f:
            info = json.load(f)
    except (OSError, ValueError):
        return False
    return (isinstance(info, dict) and info.get("format") == FORMAT and info.get("count") == COUNT
            and all(os.path.isfile(face_path(folder, g)) for g in range(COUNT)))


def extract(out_dir, folder=None, log=None):
    """Read every fighter's picture from the install's game files into the cache folder. -> the folder. ArtError
    when the files are not there or not the game's."""
    folder = folder or folder_for(out_dir)
    src = ra.find_sources(out_dir)
    if not src:
        raise ArtError("the game is not unpacked yet (BUILD GAME)")
    os.makedirs(folder, exist_ok=True)
    for gid in range(COUNT):
        if not os.path.isfile(face_path(folder, gid)):
            _write(face_path(folder, gid), ra.png_bytes(portrait(*src, gid), SIZE, SIZE))
    _write(os.path.join(folder, "fighters.json"),
              json.dumps({"format": FORMAT, "count": COUNT, "size": SIZE, "entries": [RENDERS[0], RENDERS[-1]]})
              .encode("utf-8"))
    if log:
        log(f"fighter pictures: {COUNT} read from the game's data into {folder}")
    return folder


def ensure_size(folder, size):
    """The pictures at `size` pixels in the folder, made from the stored ones if missing."""
    for gid in range(COUNT):
        p = face_path(folder, gid, size)
        if size == SIZE or os.path.isfile(p):
            continue
        with open(face_path(folder, gid), "rb") as f:
            w, h, rgba = ra.png_rgba(f.read())
        _write(p, ra.png_bytes(ra.scale_rgba(rgba, w, h, size, size), size, size))


# ---------------------------------------------------------------------------------------------- for the UI
class Faces:
    """The pictures for one Tk interpreter (as rank_art.Art): made in a thread, PhotoImages on first use."""

    def __init__(self):
        self.folder = os.environ.get("T5_FIGHTER_ART") or None
        self.sizes = set()
        self.images = {}              # (gid, size) -> PhotoImage
        self.listeners = []           # called on the Tk thread when pictures became available
        self.lock = threading.Lock()
        self.busy = False
        self.wanted = set()           # sizes asked for, not made yet
        self.wanted_lock = threading.Lock()
        self.failed = None            # why the last try did not work (logged once)

    def set_folder(self, folder):
        if os.environ.get("T5_FIGHTER_ART"):
            return                    # (tests, screenshots: a fixed folder)
        if folder != self.folder:
            self.folder, self.images, self.sizes = folder, {}, set()

    def has(self, size):
        return size in self.sizes and bool(self.folder) and is_ready(self.folder)

    def image(self, master, gid, size):
        """A PhotoImage of fighter `gid` at `size` pixels, or None (no pictures, not made yet)."""
        if gid is None or not 0 <= gid < COUNT or size not in self.sizes or not self.folder:
            return None
        key = (gid, size)
        img = self.images.get(key)
        if img is None:
            import tkinter as tk
            try:
                img = tk.PhotoImage(master=master, file=face_path(self.folder, gid, None if size == SIZE else size))
            except (tk.TclError, OSError):
                return None
            self.images[key] = img
        return img

    def prepare(self, sizes, out_dir=None, after=None, log=None):
        """In a thread: read the pictures when the folder lacks them (and the game is built), make `sizes`; then
        after(0, callback) on the Tk thread -> the listeners. A request while the thread runs is not dropped: the
        thread makes its sizes too (the grid and the profile picture ask at the same time; 1.1.5 lost one)."""
        with self.wanted_lock:
            self.wanted.update(int(s) for s in sizes if s and s > 0)
            if self.busy:
                return
            self.busy = True

        def work():
            while True:
                with self.wanted_lock:
                    todo = sorted(self.wanted)
                    self.wanted.clear()
                    if not todo:
                        self.busy = False
                        return
                ok = False
                try:
                    with self.lock:
                        if self.folder and not is_ready(self.folder) and out_dir and ra.find_sources(out_dir):
                            extract(out_dir, self.folder, log=log)
                        if self.folder and is_ready(self.folder):
                            for s in todo:
                                ensure_size(self.folder, s)
                            ok = True
                except (ra.ArtError, OSError, ValueError, zlib.error, struct.error, IndexError) as e:
                    if log and str(e) != self.failed:
                        log(f"fighter pictures: not read ({e}); the character select shows the names")
                    self.failed = str(e)
                if not ok:
                    with self.wanted_lock:
                        self.wanted.clear()
                        self.busy = False
                    return
                if after:
                    try:
                        after(0, lambda done=todo: self._done(done))   # a widget's after(ms, func); 1.1.5: after(func)
                    except Exception:   # noqa: BLE001 -- the window is gone (RuntimeError, TclError)
                        pass
        threading.Thread(target=work, name="fighter-art", daemon=True).start()

    def _done(self, sizes):
        self.sizes.update(sizes)
        for fn in list(self.listeners):
            try:
                fn()
            except Exception:   # noqa: BLE001 -- a listener must not stop the others
                pass

    def prepare_now(self, sizes):
        """The same without a thread, from a ready folder (tests, screenshots)."""
        with self.lock:
            if not (self.folder and is_ready(self.folder)):
                return
            sizes = sorted({int(s) for s in sizes})
            for s in sizes:
                ensure_size(self.folder, s)
        self._done(sizes)


FACES = Faces()


def main(argv=None):
    ap = argparse.ArgumentParser(description="Read the fighters' pictures into the launcher's cache folder.")
    ap.add_argument("--out", required=True, help="the launcher's output folder (the one BUILD GAME unpacked into)")
    ap.add_argument("--folder", help="where to write (default <out>\\cache\\fighters)")
    ap.add_argument("--sizes", type=int, nargs="*", default=[])
    a = ap.parse_args(argv)
    try:
        folder = extract(a.out, a.folder, log=print)
        for s in a.sizes:
            ensure_size(folder, s)
    except (ra.ArtError, OSError) as e:
        print(f"fighter pictures: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
