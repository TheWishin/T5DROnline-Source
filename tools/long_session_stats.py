"""Long-session numbers per time window (1.2.3 long-session work, docs/RENDER_PERF.md "Long sessions"):
a game's PS3_LATENCY_LOG (with PS3_LATENCY_WATCH=1008F01C:4,1008F070:4), optionally the press times a tapper wrote
(JSON lines {"ns": perf_counter_ns}) with the netplay frame logs (T5_NET_LOG) of that game, and a tools/screen_watch.c
file (what reached the screen).

    python tools/long_session_stats.py <lat.log> [--win 300] [--presses presses.jsonl --frames frames1.log]
                                       [--screen screen.txt]

Per window: frames (F), F->X (translation), X->P (present queue), P->D (to the display, DXGI stats),
frame-time p50/p99 from successive P, hitches > 50 ms; presses: press->first F with the hold
counter = 1 and that flip's display time, delivery count; screen: dark frames (mean < 0.5x both neighbours).
"""
import argparse, bisect, json, statistics


def pct(v, p):
    if not v:
        return float("nan")
    v = sorted(v)
    return v[min(len(v) - 1, int(len(v) * p / 100))]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("log")
    ap.add_argument("--win", type=float, default=300)
    ap.add_argument("--presses")
    ap.add_argument("--screen")
    ap.add_argument("--consume", default="1008F01C")
    ap.add_argument("--frames", nargs="*", default=[], help="netplay frame logs (T5_NET_LOG) of the presses' game")
    a = ap.parse_args()
    freq = 10_000_000
    watch = []
    F, X, P, D, Nl = [], {}, {}, {}, []
    with open(a.log, errors="replace") as f:
        for line in f:
            if line.startswith("# qpc_frequency="):
                freq = int(line.split("=")[1]); continue
            if line.startswith("# watch"):
                for w in line.split()[2:]:
                    ad, l = w.split(":"); watch.append((int(ad, 16), int(l, 16)))
                continue
            p = line.split()
            if len(p) < 3:
                continue
            k = p[0]
            try:
                if k == "F":
                    F.append((int(p[1]), int(p[2]), p[3:]))
                elif k == "X":
                    X.setdefault(int(p[2]), int(p[1]))
                elif k == "P":
                    if len(p) >= 6 and p[5] not in ("0",):
                        continue
                    P.setdefault(int(p[2]), (int(p[1]), int(p[4]) if len(p) > 4 else -1))
                elif k == "N":
                    Nl.append((int(p[1]), int(p[2])))
                elif k == "D":
                    # D qpc pc present_refresh sync_refresh sync_qpc  -> display = sync_qpc + (pr - sr) * period
                    D[int(p[2])] = (int(p[3]), int(p[4]), int(p[5]))
            except (ValueError, IndexError):
                pass
    ms = 1000.0 / freq
    # display period from successive D sync points
    syncs = sorted(set((v[1], v[2]) for v in D.values()))
    per = None
    if len(syncs) > 10:
        d = [(syncs[i + 1][1] - syncs[i][1]) / (syncs[i + 1][0] - syncs[i][0])
             for i in range(len(syncs) - 1) if syncs[i + 1][0] > syncs[i][0]]
        per = statistics.median(d) if d else None

    def disp_of(seq):
        pp = P.get(seq)
        if not pp or per is None:
            return None
        dd = D.get(pp[1])
        if not dd:
            return None
        return dd[2] + (dd[0] - dd[1]) * per

    ci = None
    off = 0
    for ad, l in watch:
        if ad <= int(a.consume, 16) < ad + l:
            ci = off + (int(a.consume, 16) - ad) // 4
        off += l // 4
    t0 = F[0][0] if F else 0
    rows = {}
    for fq, seq, words in F:
        w = int((fq - t0) * ms / 1000 / a.win)
        r = rows.setdefault(w, dict(ft=[], fx=[], xp=[], pd=[], n=0, lat=[], taps=0, got=0, dark=0, scr=0))
        r["n"] += 1
    # the walker numbers its own flips: pair F with X by order in time
    xs = sorted(X.items(), key=lambda kv: kv[1])
    xq = [v for _, v in xs]
    pi = None
    off = 0
    for ad, l in watch:
        if ad <= 0x1008F070 < ad + l:
            pi = off + (0x1008F070 - ad) // 4
        off += l // 4
    def fighting(words):
        try:
            return pi is None or int(words[pi], 16) == 17
        except (IndexError, ValueError):
            return False
    prevf = None
    for fq, seq, words in F:
        if not fighting(words):
            prevf = None
            continue
        if prevf is not None:
            rows[int((fq - t0) * ms / 1000 / a.win)]["ft"].append((fq - prevf) * ms)
        prevf = fq
        k = bisect.bisect_left(xq, fq)
        if k >= len(xs):
            continue
        s, xt = xs[k]
        r = rows[int((fq - t0) * ms / 1000 / a.win)]
        r["fx"].append((xt - fq) * ms)
        if s in P:
            r["xp"].append((P[s][0] - xt) * ms)
            dq = disp_of(s)
            if dq:
                r["pd"].append((dq - P[s][0]) * ms)
    if a.presses and a.frames:
        # sessions: frame numbers restart; segment both the N events and the I lines where the frame drops
        def segs(pairs):
            out, cur, last = [], [], None
            for x in pairs:
                if last is not None and x[-1] < last - 50:
                    out.append(cur); cur = []
                cur.append(x); last = x[-1]
            if cur: out.append(cur)
            return out
        ilines = []
        for fp in a.frames:
            for line in open(fp, errors="replace"):
                q = line.split()
                if len(q) >= 3 and q[1] == "I":
                    try: ilines.append((int(q[2][:4], 16), int(q[0])))
                    except ValueError: pass
        nseg = segs(Nl)
        iseg = segs(ilines)
        n_by_seg = [dict((fr, qq) for qq, fr in sg) for sg in nseg]
        press_frames = []   # (seg, frame) of frames whose P1 input has SQUARE and the one before not
        for si, sg in enumerate(iseg):
            prev = 0
            for b, fr in sg:
                if b & 0x8000 and not prev & 0x8000:
                    press_frames.append((si, fr))
                prev = b
        # each SQUARE press-start frame -> its boundary time and the flip after it
        starts = []
        for si, fr in press_frames:
            if si < len(n_by_seg) and fr in n_by_seg[si]:
                starts.append(n_by_seg[si][fr])
        starts.sort()
        fq_list = [x[0] for x in F]
        presses = [json.loads(l) for l in open(a.presses)]
        used = set()
        for pr in presses:
            t = pr["ns"] * freq // 1_000_000_000
            w = int((t - t0) * ms / 1000 / a.win)
            if w not in rows:
                continue
            r = rows[w]
            r["taps"] += 1
            k = bisect.bisect_left(starts, t)
            # the press reaches the frame sampled at the next boundary (+ delay): within 10 frames
            if k < len(starts) and starts[k] - t < freq // 6 and k not in used:
                used.add(k)
                r["got"] += 1
                i = bisect.bisect_left(fq_list, starts[k])
                if i < len(F):
                    kk = bisect.bisect_left(xq, F[i][0])
                    if kk < len(xs):
                        dq = disp_of(xs[kk][0])
                        if dq:
                            r["lat"].append((dq - t) * ms)
                            r.setdefault("la", []).append((starts[k] - t) * ms)
                            r.setdefault("lb", []).append((dq - starts[k]) * ms)
    if a.screen:
        sv = []
        for line in open(a.screen):
            if line.startswith("#"):
                continue
            p = line.split()
            if len(p) >= 3:
                sv.append((int(p[0]), float(p[1])))
        for i in range(1, len(sv) - 1):
            w = int((sv[i][0] - t0) * ms / 1000 / a.win)
            if w not in rows:
                continue
            rows[w]["scr"] += 1
            if sv[i][1] < 0.5 * sv[i - 1][1] and sv[i][1] < 0.5 * sv[i + 1][1] and sv[i - 1][1] > 15 and sv[i + 1][1] > 15:
                rows[w]["dark"] += 1
    print("win  min  frames  ft_p50 ft_p99 >50ms | F->X p50/p99 | X->P p50/p99 | P->disp p50/p99 | taps got  press->disp p50/p90 | screen dark")
    for w in sorted(rows):
        r = rows[w]
        f = lambda v, p: pct(v, p)
        print("%3d %5.0f %6d  %6.2f %6.2f %4d | %5.2f %6.2f | %5.2f %6.2f | %5.2f %6.2f | %4d %4d  %6.1f %6.1f | %6d %4d" % (
            w, w * a.win / 60, r["n"], f(r["ft"], 50), f(r["ft"], 99), sum(1 for x in r["ft"] if x > 50),
            f(r["fx"], 50), f(r["fx"], 99), f(r["xp"], 50), f(r["xp"], 99), f(r["pd"], 50), f(r["pd"], 99),
            r["taps"], r["got"], f(r["lat"], 50), f(r["lat"], 90), r["scr"], r["dark"]))
    print("press split per window: press->input frame boundary p50 | that boundary->display p50")
    for w in sorted(rows):
        r = rows[w]
        if r.get("la"):
            print("%3d  %6.1f | %6.1f" % (w, pct(r["la"], 50), pct(r["lb"], 50)))
    if per:
        print("display period %.3f ms" % (per * ms))


if __name__ == "__main__":
    main()
