/* Online feel (docs/NETPLAY.md "Online feel and rollback capacity"): the rollback input delay the host picks for a
 * match from the round trip and from what a rollback costs on each of the two PCs. Pure functions, no state: the
 * host calls decide() once when its match starts and sends the result as before (PING / INPUT "rbd"), so both PCs
 * use the same delay from the same frame. Nothing here touches what the game simulates. */
#pragma once
#include <algorithm>
#include <cmath>
#include <cstdint>

namespace np { namespace feel {

/* A player's choice (launcher Settings -> Online feel, T5_RB_NET_FEEL). */
enum : uint8_t { kResponsive = 0, kBalanced = 1, kSmooth = 2, kUnknown = 0xFF };
constexpr uint8_t kCapUnknown = 0xFF;          /* this PC has not measured its rollbacks yet */
constexpr double  kFrameMs = 1000.0 / 59.94;
/* A frame has 16.7 ms; what the main thread may spend on the live frame plus one rollback and still be on time.
 * The rest is room for the present, the snapshot's spikes and the vblank's jitter. */
constexpr double  kBudgetMs = 15.0;
constexpr int     kMaxCapacity = 15;

inline const char* name(uint8_t f)
{
    return f == kResponsive ? "responsive" : f == kBalanced ? "balanced" : f == kSmooth ? "smooth" : "unknown";
}

/* T5_RB_NET_FEEL's value -> a feel (anything else: Balanced, the default). */
inline uint8_t parse(const char* v)
{
    if (!v || !*v) return kBalanced;
    switch (v[0] | 0x20) {
    case 'r': return kResponsive;
    case 's': return kSmooth;
    default:  return kBalanced;
    }
}

/* The deepest rollback this PC can run inside one frame and still keep 60 fps: the main thread's own time for a
 * live fight frame (live_ms: the game's frame and the snapshot, no waits), a restore (restore_ms) and one
 * re-simulated frame (resim_ms), all averaged over its last matches. 0..15 frames, kCapUnknown without numbers. */
inline uint8_t capacity(double live_ms, double restore_ms, double resim_ms)
{
    if (!std::isfinite(live_ms) || !std::isfinite(restore_ms) || !std::isfinite(resim_ms)) return kCapUnknown;
    if (!(resim_ms > 0.05) || live_ms < 0 || restore_ms < 0 || live_ms > 200 || resim_ms > 200) return kCapUnknown;
    const double spare = kBudgetMs - live_ms - restore_ms;
    if (spare <= 0) return 0;
    return (uint8_t)std::min<double>(kMaxCapacity, std::floor(spare / resim_ms));
}

/* Frames of the peer's input still on the wire when a frame runs: half the round trip, rounded up, plus the frame
 * the input waits for its packet. -1 without a round trip. */
inline int in_flight(double rtt_ms)
{
    if (!std::isfinite(rtt_ms) || rtt_ms < 0 || rtt_ms > 5000) return -1;
    return (int)std::ceil(rtt_ms / (2.0 * kFrameMs) - 1e-9) + 1;
}

/* The rollback depth to expect with `delay` frames of input delay (what each mispredicted input costs). */
inline int expected_depth(double rtt_ms, int delay)
{
    const int f = in_flight(rtt_ms);
    return f < 0 ? -1 : std::max(0, f - std::max(0, delay));
}

/* Two players' choices -> the match's: the same choice, or the one side that has one (an older game sends none);
 * two different choices meet in the middle. */
inline uint8_t combine(uint8_t a, uint8_t b)
{
    const bool ka = a <= kSmooth, kb = b <= kSmooth;
    if (ka && kb) return a == b ? a : kBalanced;
    if (ka) return a;
    if (kb) return b;
    return kBalanced;
}

/* The slower PC's capacity: the smaller known one (kCapUnknown when neither PC measured). */
inline uint8_t slower(uint8_t a, uint8_t b) { return std::min(a, b); }

struct Pick {
    int delay;           /* the match's rollback input delay */
    int extra;           /* frames added to the base pick */
    int depth;           /* expected rollback depth with that delay (-1: no round trip) */
    const char* why;     /* for the log */
};

/* One frame by measured cost (docs/NETPLAY.md "One frame by measured cost"). In the pair runs behind the rule
 * (60 / 100 / 120 / 150 ms, 2 % loss, one frame of delay) the 99th-percentile rollback was one frame deeper than
 * expected_depth() at every ping (3, 4, 5, 6 frames), so the rule plans with expected_depth(rtt, 1) + 1 and never
 * beyond the 6 frames measured at 150 ms; above that the lobby's far-match delay applies anyway. */
constexpr int kMeasuredDepthMax = 6;
inline int p99_depth_one_frame(double rtt_ms)
{
    const int e = expected_depth(rtt_ms, 1);
    return e < 0 ? -1 : e + 1;
}

/* The highest round trip (ms) at which the measured rule keeps one frame of delay for a slower-PC capacity `cap`:
 * ceil(rtt / 33.4) + 1 <= min(cap, 6). -1 without a measurement, 0 when it never does. */
inline double one_frame_up_to_ms(uint8_t cap)
{
    if (cap == kCapUnknown) return -1.0;
    return 2.0 * kFrameMs * std::max(0, std::min<int>(cap, kMeasuredDepthMax) - 1);
}

/* The match's delay: `base` is the 1.2.0 auto pick (1 / 2 by the round trip), `ceiling` the session's lockstep
 * delay (never above it), `feel` the combined choice, `cap` the slower PC's capacity, `measured` true when BOTH
 * PCs sent a measured capacity (then `cap` is the smaller of the two).
 *   One frame by measured cost (Responsive and Balanced, both PCs measured): where the 1.2.0 pick is 2 only
 *               because the round trip is above 60 ms, one frame is kept as long as the slower PC re-simulates
 *               the 99th-percentile rollback of one frame of delay inside a frame (p99_depth_one_frame(rtt) <=
 *               cap, at most 6).
 *   Responsive  that pick, nothing added.
 *   Balanced    one frame more when the slower PC cannot re-simulate the expected depth inside a frame (its
 *               rollbacks would drop frames for both players: the game waits for the slower PC).
 *   Smooth      enough frames that at most two frames are predicted (at most two more than the base), and the
 *               capacity rule's frame on top when still needed.
 * Without both measurements (a first match, an older game) everything is as it was. */
inline Pick decide(int base, double rtt_ms, int ceiling, uint8_t feel, uint8_t cap, bool measured = false)
{
    Pick p = { base, 0, expected_depth(rtt_ms, base), "base" };
    int floor_ = base;      /* the lowest pick: the 1.2.0 one, or one frame where both PCs measured that it holds */
    bool one = false;
    if (measured && cap != kCapUnknown && feel != kSmooth && base > 1 && p.depth >= 0) {
        const int d99 = p99_depth_one_frame(rtt_ms);
        if (d99 <= (int)cap && d99 <= kMeasuredDepthMax) { floor_ = 1; one = true; }
    }
    if (feel == kResponsive) {
        p.delay = one ? 1 : base;
        p.extra = p.delay - base;
        p.depth = expected_depth(rtt_ms, p.delay);
        p.why = one ? "responsive: one frame, both PCs re-simulate that depth inside a frame" : "responsive: the base pick";
        return p;
    }
    if (p.depth < 0) { p.why = "no round trip: the base pick"; return p; }
    int pick = floor_;
    if (feel == kSmooth) {
        const int want = in_flight(rtt_ms) - 2;
        pick = std::max(pick, std::min(want, base + 2));
        p.why = "smooth: at most two frames predicted";
    }
    if (cap != kCapUnknown && expected_depth(rtt_ms, pick) > (int)cap) {
        pick += 1;
        p.why = feel == kSmooth ? "smooth + a frame for the slower PC's rollbacks"
                                : "balanced: a frame for the slower PC's rollbacks";
    } else if (feel != kSmooth) {
        p.why = one ? "balanced: one frame, both PCs re-simulate that depth inside a frame"
              : cap == kCapUnknown ? "balanced: no PC measured yet, the base pick" : "balanced: both PCs keep up";
    }
    if (pick > ceiling) pick = std::max(floor_, ceiling);
    if (pick < floor_) pick = floor_;
    p.delay = pick;
    p.extra = pick - base;
    p.depth = expected_depth(rtt_ms, pick);
    return p;
}

} }
