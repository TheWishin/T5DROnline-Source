/* Rollback cost samples (docs/NETPLAY.md "Online feel and rollback capacity"): a histogram per measured quantity and
 * its trimmed mean. Pure, no runtime calls; tests/c/rb_cost_hist_test.cpp checks it.
 *
 * Why (1.2.3, long-session runs): the measurement window's plain mean let one hitch decide a whole window. One
 * rollback that met a 400 ms stall (a pipeline built at first sight, another program, the OS) made the window's
 * "re-simulated frame" 18 ms instead of 5, the kept value (halfway towards each window) 12 ms, this PC's capacity 0,
 * and the Balanced online feel gave the next matches one frame more input delay -- and rb_cost.txt kept it for the
 * next game. The trimmed mean drops the top and bottom tenth of the samples (by weight), so a few stalls in a
 * window do not count, while a PC that really got slower still moves every sample. */
#pragma once
#include <stdint.h>
#include <string.h>

namespace rb {

struct CostHist {
    static constexpr int kBins = 2000;           /* 0.05 ms bins up to 100 ms */
    static constexpr double kBinMs = 0.05;
    uint32_t bin[kBins];
    uint64_t n;                                  /* total weight */
    double sum;                                  /* plain weighted sum (the old mean, for the log) */

    void reset() { memset(bin, 0, sizeof bin); n = 0; sum = 0; }
    /* one sample of `ms`, counted `weight` times (a rollback's per-frame time counts once per re-simulated frame) */
    void add(double ms, uint32_t weight = 1)
    {
        if (!(ms >= 0) || !weight) return;
        int b = (int)(ms / kBinMs);
        if (b >= kBins) b = kBins - 1;
        bin[b] += weight;
        n += weight;
        sum += ms * weight;
    }
    double mean() const { return n ? sum / (double)n : 0.0; }
    /* the mean of the samples between the `trim` and 1 - `trim` quantiles (by weight), bin centres */
    double trimmed(double trim = 0.10) const
    {
        if (!n) return 0.0;
        const double lo = trim * (double)n, hi = (1.0 - trim) * (double)n;
        double acc = 0, w = 0, s = 0;
        for (int b = 0; b < kBins && acc < hi; b++) {
            if (!bin[b]) continue;
            const double a0 = acc, a1 = acc + bin[b];
            acc = a1;
            const double take = (a1 < hi ? a1 : hi) - (a0 > lo ? a0 : lo);
            if (take <= 0) continue;
            w += take;
            s += take * (b + 0.5) * kBinMs;
        }
        return w > 0 ? s / w : mean();
    }
};

/* The kept value moves halfway towards each window's number, as before; a window more than 1.5 times the kept value
 * moves it as if it were 1.5 times (a PC that really got slower gets there in a few windows; one bad window costs
 * at most a quarter). Getting faster is followed at once, as before. */
inline double cost_keep(bool known, double kept, double sample)
{
    if (!known || !(kept > 0)) return sample;
    const double s = sample > 1.5 * kept ? 1.5 * kept : sample;
    return 0.5 * (kept + s);
}

}  // namespace rb
