"""The game's own announcer, "Get ready for the next battle!", for the Online tab's notification sound -- read from
the player's own game files when it is needed, never shipped with the launcher and never written to disk.

The line is a sample of the announcer's sound bank, entry 11 of the game's data table in T55DATA1.BIN (the table and
its coding: rank_art.py, CLAUDE.md "Data format"):

* the bank (big-endian): "00 02 01 00", 0, the bank id (2), the sample count (21), the data offset, the data size,
  then at +0x20 one offset per sample to its 0xC0-byte record;
* a record: "vag\\0", ..., +0x14 the sample's size, +0x18 its offset in the data, +0xBC the sample rate (u32);
* a sample is PlayStation ADPCM (VAG): 16-byte frames {shift | filter << 4, flags, 14 bytes = 28 four-bit samples};
  flag bit 0 ends the sample.

Sample 1 of bank 2 is the line (found by comparing the bank's 21 samples with spoken phrases: samples 1 and 9 are two
takes of it, sample 0 is "Welcome to the King of Iron Fist Tournament"); its size and SHA-256 below make sure no
other sound is ever played (another release of the game, other data -> None, and notify.py rings its own chime).

    python -m t5lobby.announcer --out <the launcher's output folder, e.g. native> [--wav FILE] [--play]
"""
import argparse
import functools
import hashlib
import io
import os
import struct
import sys
import wave

from . import rank_art

ENTRY = 11                        # the announcer's bank in the data table
BANK_ID = 2
BANK_COUNT = 21
SAMPLE = 1                        # "Get ready for the next battle!"
SAMPLE_RATE = 18000
SAMPLE_SIZE = 17744               # bytes of ADPCM
SAMPLE_SHA256 = "4f7d1b013fe870402f05a996da276b29029cb68c89e70b5d22348f32a3c60855"
RECORD = 0xC0
PEAK = 0.45                       # of full scale: the game's own level is ~1.0, the chime's 0.30 (notify.py)

COEF = ((0, 0), (60, 0), (115, -52), (98, -55), (122, -60))


class VoiceError(Exception):
    pass


def adpcm_decode(data):
    """PlayStation ADPCM (VAG) -> list of 16-bit samples; stops after the frame with the end flag."""
    out = []
    s1 = s2 = 0
    for f in range(0, len(data) - 15, 16):
        head, flags = data[f], data[f + 1]
        shift, flt = head & 0x0F, (head >> 4) & 0x0F
        if shift > 12:
            shift = 9
        c1, c2 = COEF[flt] if flt < len(COEF) else COEF[0]
        for j in range(28):
            b = data[f + 2 + (j >> 1)]
            n = (b >> 4) if j & 1 else (b & 0x0F)
            if n >= 8:
                n -= 16
            v = ((n << 12) >> shift) + ((s1 * c1 + s2 * c2) >> 6)
            v = -32768 if v < -32768 else 32767 if v > 32767 else v
            s2, s1 = s1, v
            out.append(v)
        if flags & 1:
            break
    return out


def bank_sample(bank, index):
    """(ADPCM bytes, rate) of sample `index` of a decoded sound bank."""
    if len(bank) < 0x20 or bank[:4] != b"\x00\x02\x01\x00":
        raise VoiceError("not the announcer's sound bank")
    bank_id, count, data_off, data_size = struct.unpack_from(">4I", bank, 8)
    if bank_id != BANK_ID or count != BANK_COUNT or not 0 <= index < count:
        raise VoiceError("not the announcer's sound bank")
    if 0x20 + 4 * count > len(bank) or data_off + data_size > len(bank):
        raise VoiceError("the sound bank is cut off")
    rec, = struct.unpack_from(">I", bank, 0x20 + 4 * index)
    if rec + RECORD > len(bank) or bank[rec:rec + 4] != b"vag\0":
        raise VoiceError("the sample has no record")
    size, off = struct.unpack_from(">II", bank, rec + 0x14)
    rate, = struct.unpack_from(">I", bank, rec + 0xBC)
    if off + size > data_size:
        raise VoiceError("the sample is cut off")
    return bank[data_off + off:data_off + off + size], rate


def wav_bytes(samples, rate, peak=PEAK):
    """16-bit mono WAV image, the level brought to `peak` of full scale."""
    top = max((abs(v) for v in samples), default=0) or 1
    scale = peak * 32767 / top
    frames = struct.pack("<%dh" % len(samples), *(int(round(v * scale)) for v in samples))
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(frames)
    return out.getvalue()


def voice_from(elf, data):
    """The line as a WAV image from the game's program and T55DATA1.BIN. Raises VoiceError."""
    try:
        bank = rank_art.read_entry(elf, data, ENTRY)
    except rank_art.ArtError as e:
        raise VoiceError(str(e)) from None
    adpcm, rate = bank_sample(bank, SAMPLE)
    if rate != SAMPLE_RATE or len(adpcm) != SAMPLE_SIZE or hashlib.sha256(adpcm).hexdigest() != SAMPLE_SHA256:
        raise VoiceError("not the line this launcher knows (another release of the game?)")
    return wav_bytes(adpcm_decode(adpcm), rate)


@functools.lru_cache(maxsize=4)
def _cached(elf, data, stamp):
    try:
        return voice_from(elf, data)
    except (VoiceError, OSError, ValueError, struct.error):
        return None


def next_battle_wav(out_dir):
    """The announcer's "Get ready for the next battle!" as a WAV image (bytes), or None: no unpacked game in
    `out_dir`, a European program, other or damaged data. Read once per game files (kept in memory)."""
    if not out_dir:
        return None
    try:
        src = rank_art.find_sources(out_dir)
        if src is None:
            return None
        elf, data = src
        stamp = tuple((os.path.getsize(p), os.path.getmtime(p)) for p in src)
    except OSError:
        return None
    return _cached(elf, data, stamp)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", required=True, help="the launcher's output folder (with game\\EBOOT.elf)")
    ap.add_argument("--wav", help="also write the line to this file (it is the game's sound: keep it to yourself)")
    ap.add_argument("--play", action="store_true", help="play it")
    a = ap.parse_args(argv)
    src = rank_art.find_sources(a.out)
    if src is None:
        print("no unpacked US game in", a.out)
        return 1
    try:
        wav = voice_from(*src)
    except VoiceError as e:
        print("not available:", e)
        return 1
    print("announcer line: %d bytes of WAV" % len(wav))
    if a.wav:
        with open(a.wav, "wb") as f:
            f.write(wav)
    if a.play:
        import winsound
        winsound.PlaySound(wav, winsound.SND_MEMORY)
    return 0


if __name__ == "__main__":
    sys.exit(main())
