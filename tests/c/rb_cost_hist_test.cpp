// Checks src/rollback/rb_cost_hist.h: the trimmed mean of the rollback cost samples and the kept value's step.
#include "../../src/rollback/rb_cost_hist.h"
#include "../../src/netplay/rollback_feel.h"
#include <stdio.h>
#include <math.h>

static int g_checks = 0, g_fails = 0;
#define CHECK(c, what) do { g_checks++; if (!(c)) { g_fails++; printf("FAIL: %s\n", what); } } while (0)

static rb::CostHist h;

int main()
{
    /* steady samples: the trimmed mean is the mean (within a bin) */
    h.reset();
    for (int i = 0; i < 600; i++) h.add(4.0 + 0.002 * (i % 50));
    CHECK(fabs(h.trimmed() - h.mean()) < 0.06, "steady: trimmed = mean");

    /* the 1.2.3 long-session case: 40 rollbacks of 3 frames at 5 ms a frame, one met a 400 ms stall */
    h.reset();
    for (int i = 0; i < 39; i++) h.add(5.0, 3);
    h.add(400.0 / 3.0, 3);
    CHECK(h.mean() > 8.0, "the plain mean is dragged by one stall");
    CHECK(fabs(h.trimmed() - 5.0) < 0.06, "the trimmed mean is not");
    /* capacity with the window's numbers (live 4.0, restore 0.8): the old mean gives at most 1 frame, the trimmed one 2 */
    CHECK(np::feel::capacity(4.0, 0.8, h.mean()) <= 1, "old mean: at most 1 frame");
    CHECK(np::feel::capacity(4.0, 0.8, h.trimmed()) == 2, "trimmed: 2 frames");

    /* a PC that really got slower: every sample moves, so the trimmed mean follows */
    h.reset();
    for (int i = 0; i < 100; i++) h.add(9.0, 2);
    CHECK(fabs(h.trimmed() - 9.0) < 0.06, "a slower PC is seen");

    /* weights: one rollback of 8 frames counts 8 times */
    h.reset();
    h.add(2.0, 8); h.add(6.0, 2);
    CHECK(fabs(h.mean() - 2.8) < 1e-9, "weighted mean");
    CHECK(h.trimmed() > 2.0 && h.trimmed() < 3.0, "weighted trimmed");

    /* edges: nothing, negative, past the last bin */
    h.reset();
    CHECK(h.trimmed() == 0.0 && h.mean() == 0.0, "empty");
    h.add(-1.0); h.add(1e9);
    CHECK(h.n == 1, "negative ignored, huge counted in the last bin");

    /* the kept value */
    CHECK(rb::cost_keep(false, 0, 7.0) == 7.0, "first window taken as it is");
    CHECK(fabs(rb::cost_keep(true, 5.0, 6.0) - 5.5) < 1e-9, "halfway, as before");
    CHECK(fabs(rb::cost_keep(true, 5.0, 18.0) - 6.25) < 1e-9, "one bad window: at most 1.5 times counted");
    CHECK(fabs(rb::cost_keep(true, 5.0, 2.0) - 3.5) < 1e-9, "faster at once, halfway");
    double k = 5.0;
    for (int i = 0; i < 6; i++) k = rb::cost_keep(true, k, 10.0);
    CHECK(k > 9.5, "a PC that stays slower is followed within a few windows");

    if (g_fails) { printf("FAILED %d of %d checks\n", g_fails, g_checks); return 1; }
    printf("PASS %d checks\n", g_checks);
    return 0;
}
