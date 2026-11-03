/* Opt-in match-start jitter policy. No wire format or mid-match input changes. */
#pragma once
#include <algorithm>
#include <cmath>

namespace np { namespace detail {
inline int jitter_delay(const float* rtt_ms, unsigned count, int baseline, int cap)
{
    /* Four real PING echoes minimum; a lobby estimate cannot measure jitter.
     * At >=110 ms RTT budget for at most two frames of prediction at p95.
     * A deliberately small cap trades additional rollback for bounded latency. */
    float sorted[32];
    unsigned n = 0;
    for (unsigned i = 0; i < count && i < 32; ++i)
        if (std::isfinite(rtt_ms[i]) && rtt_ms[i] >= 0 && rtt_ms[i] < 2000)
            sorted[n++] = rtt_ms[i];
    if (n < 4 || cap <= baseline) return baseline;
    std::sort(sorted, sorted + n);
    const float p95 = sorted[(95 * n + 99) / 100 - 1];
    if (p95 < 110) return baseline;
    const int wanted = static_cast<int>(std::ceil(p95 * 60.0 / 2000.0)) - 2;
    return std::max(baseline, std::min(wanted, cap));
}
} }
