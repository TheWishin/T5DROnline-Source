"""Frame analysis for the smoke suite (Pillow only).

stats()        cheap numbers per dumped frame: mean, spread, black/white share,
               and how much it differs from the previous frame (frozen screens)
classify()     black / white / flat / content
hud_score()    is the fight HUD (both health bars) on screen?
spike_score()  how much of the playfield is covered by one big smooth shape
fight_check()  both, for one 1280x720 frame

How the fight heuristics were validated (2026-10-17, see docs/SMOKE.md):
  * hud_score: the two health bars are 2D UI drawn at fixed pixels. Over 684
    QA screenshots (12 stages, every mode) it was >= 0.89 on all 195 fight
    frames and < 0.5 on every other screen (title, menus, character select,
    VS splash, loading, results, attract cut scenes).
  * spike_score: broken SPU skinning draws the fighters as "spikes" -- huge
    smoothly shaded triangles that reach across the screen. Measured as the
    largest 4-connected area of smooth 16x16 blocks (luma std < 2.5, not
    dark) in the playfield below the HUD, as a share of the playfield. The
    two real broken-skinning screenshots from before patch 0002 score 0.106
    and 0.300; 200+ good fight frames across 12 stages score <= 0.060 (the
    worst: a dusk stage with a smooth sea), median 0.004 -- except the
    marble practice stage (smooth bright floor): 0.047-0.082, median 0.055.
    The check uses the median over a test's fight frames against
    SPIKE_LIMIT = 0.09. The margin to 0.106 is thin; per-stage reference
    statistics would be the next step if it ever misfires.
  * Not covered: fighters that are simply missing (no negative sample
    exists -- with job chains off, PS3_NO_JOBCHAIN=1, the game never
    reaches the title, which the boot checks catch).
"""
import math
import os
import struct

THUMB = (32, 18)          # for frame-to-frame differences
STAT = (160, 90)          # for the per-frame numbers
SIZE = (1280, 720)        # the title renders 720p; other sizes are scaled first

HUD_MIN = 0.85            # share of health-bar columns that must look like a bar
SPIKE_LIMIT = 0.09        # median spike_score over the fight frames
PLAYFIELD = (200, 680)    # rows below the HUD and above the bottom edge


def _pil():
    from PIL import Image, ImageChops, ImageMath, ImageStat
    return Image, ImageChops, ImageMath, ImageStat


def _floats(im):
    """Pixel values of a mode 'F' image."""
    return struct.unpack(f"{im.width * im.height}f", im.tobytes())


def load(path):
    Image = _pil()[0]
    im = Image.open(path)
    im.load()
    return im.convert("RGB")


def save_thumb(im, path, size=(640, 360), quality=75):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    im.resize(size).save(path, quality=quality)


def stats(im, prev_thumb=None):
    """(record, thumb). record: mean (0-255 luma), std, black/white share (0-1),
    rgb mean, diff_prev (mean abs luma difference to the previous frame's
    thumb, 0-255; None for the first)."""
    Image, ImageChops, _, ImageStat = _pil()
    small = im.resize(STAT, Image.BILINEAR)
    lum = small.convert("L")
    hist = lum.histogram()
    n = float(sum(hist)) or 1.0
    st = ImageStat.Stat(lum)
    rgb = ImageStat.Stat(small).mean
    thumb = lum.resize(THUMB, Image.BILINEAR)
    diff = None
    if prev_thumb is not None:
        diff = ImageStat.Stat(ImageChops.difference(thumb, prev_thumb)).mean[0]
    rec = {
        "mean": round(st.mean[0], 1),
        "std": round(st.stddev[0], 1),
        "black": round(sum(hist[:17]) / n, 3),
        "white": round(sum(hist[240:]) / n, 3),
        "rgb": [round(c, 1) for c in rgb],
        "diff_prev": None if diff is None else round(diff, 2),
    }
    return rec, thumb


def classify(rec):
    """'black', 'white', 'flat' (one colour, e.g. a cleared but undrawn
    frame), 'content', or 'missing' for no frame."""
    if not rec:
        return "missing"
    if rec["black"] >= 0.98:
        return "black"
    if rec["white"] >= 0.98:
        return "white"
    if rec["std"] < 3.0:
        return "flat"
    return "content"


def describe(rec):
    if not rec:
        return "no frame"
    s = (f"{classify(rec)} mean={rec['mean']} std={rec['std']} black={rec['black']:.0%} "
         f"white={rec['white']:.0%}")
    if rec.get("diff_prev") is not None:
        s += f" diff={rec['diff_prev']}"
    return s


def _to720(im):
    if im.size != SIZE:
        im = im.resize(SIZE)
    return im


def hud_score(im):
    """Share of sampled columns of both health bars that look like a bar:
    rows 62 and 70 teal (health) or red (damage), row 74 the dark border."""
    im = _to720(im)
    px = im.load()
    good = tot = 0
    for x0, x1 in ((90, 560), (725, 1195)):
        for x in range(x0, x1, 8):
            tot += 1
            ok = True
            for y in (62, 70):
                r, g, b = px[x, y][:3]
                teal = g > 90 and g > r + 50 and b > r + 30
                red = r > 40 and r > g + 30 and r > b + 30
                ok = ok and (teal or red)
            r2, g2, b2 = px[x, 74][:3]
            if ok and max(r2, g2, b2) < 30:
                good += 1
    return good / tot


def smooth_blocks(im, rows=PLAYFIELD, block=16, std_max=2.5, mean_min=40):
    """Grid (list of rows of bools) of smooth, not-dark blocks."""
    Image, _, ImageMath, _ = _pil()
    im = _to720(im)
    lum = im.convert("L").crop((0, rows[0], SIZE[0], rows[1])).convert("F")
    if hasattr(ImageMath, "lambda_eval"):
        sq = ImageMath.lambda_eval(lambda a: a["a"] * a["a"], a=lum)
    else:                                            # Pillow < 10.3
        sq = ImageMath.eval("a*a", a=lum)
    w, h = lum.width // block, lum.height // block
    m = _floats(lum.resize((w, h), Image.BOX))
    m2 = _floats(sq.resize((w, h), Image.BOX))
    grid = []
    for j in range(h):
        row = []
        for i in range(w):
            a, b = m[j * w + i], m2[j * w + i]
            row.append(math.sqrt(max(0.0, b - a * a)) < std_max and a > mean_min)
        grid.append(row)
    return grid


def largest_component(grid):
    """Size of the largest 4-connected True area, as a share of the grid."""
    h = len(grid)
    w = len(grid[0]) if h else 0
    if not w:
        return 0.0
    seen = [[False] * w for _ in range(h)]
    best = 0
    for j in range(h):
        for i in range(w):
            if grid[j][i] and not seen[j][i]:
                seen[j][i] = True
                stack, n = [(j, i)], 0
                while stack:
                    a, b = stack.pop()
                    n += 1
                    for u, v in ((a + 1, b), (a - 1, b), (a, b + 1), (a, b - 1)):
                        if 0 <= u < h and 0 <= v < w and grid[u][v] and not seen[u][v]:
                            seen[u][v] = True
                            stack.append((u, v))
                best = max(best, n)
    return best / float(w * h)


def spike_score(im):
    return largest_component(smooth_blocks(im))


def fight_check(im):
    """{'hud': 0-1, 'spikes': 0-1, 'is_fight': bool}. is_fight says the frame
    shows the fight HUD; the spike verdict is made over several frames by
    checks.py (fighters_verdict)."""
    hud = hud_score(im)
    return {"hud": round(hud, 3), "spikes": round(spike_score(im), 4), "is_fight": hud >= HUD_MIN}


def fighters_verdict(scores, limit=SPIKE_LIMIT):
    """(ok, median, max) over the spike scores of a test's fight frames."""
    if not scores:
        return None, None, None
    s = sorted(scores)
    n = len(s)
    med = s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2
    return med < limit, round(med, 4), round(s[-1], 4)


def frozen(diffs, eps=0.3):
    """True if every frame-to-frame difference in `diffs` (consecutive dumps,
    0-255 luma) is below eps: the picture did not change at all."""
    d = [x for x in diffs if x is not None]
    return bool(d) and max(d) < eps
