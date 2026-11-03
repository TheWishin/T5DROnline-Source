#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include "host_pacer.h"

static void rational_grid_and_ordinary_wake_jitter(void)
{
    hp_policy p;
    const int64_t f = 10000003, epoch = 1234567;
    hp_reset(&p, f, epoch, 7, f * 6 / 1000);
    const int64_t first = p.next_present;
    for (int64_t n = 0; n < 60000 * 8; n++) {
        assert(p.next_present == first + n * f * 1001 / 60000);
        hp_release(&p, hp_release_due(&p), 2);
        const hp_target frame = p.current;
        /* Ready early, ordinary 3 us timer/API overshoot: preserve epoch. */
        hp_presented(&p, &frame, frame.present_target_qpc - f / 1000,
                     frame.present_target_qpc + 3 * f / 1000000);
    }
}
static void alternating_work_targets_and_handoff(void)
{
    hp_policy p;
    hp_reset(&p, 60000000, 1000000, 1, 360000); /* exact 6 ms budget */
    int64_t previous = 0, immediate_previous = 0;
    int saw_short = 0, saw_long = 0;
    for (unsigned n = 0; n < 120; n++) {
        hp_release(&p, hp_release_due(&p), 2);
        const hp_target packet = p.current; /* RQ_PRESENT value copy */
        const int64_t ready = packet.release_qpc + (n & 1 ? 300000 : 150000);
        assert(ready < packet.present_target_qpc);
        if (previous) {
            assert(packet.present_target_qpc - previous == 1001000);
            const int64_t delta = ready - immediate_previous;
            saw_short |= delta < 900000; saw_long |= delta > 1100000;
        }
        previous = packet.present_target_qpc; immediate_previous = ready;
    }
    assert(saw_short && saw_long);
    const hp_target queued = p.current;
    const int64_t saved = queued.present_target_qpc;
    hp_release(&p, hp_release_due(&p), 2);
    assert(queued.present_target_qpc == saved);
    assert(p.current.present_target_qpc > saved);
}
static void late_recovery_skips_and_generation(void)
{
    hp_policy p;
    hp_reset(&p, 60000000, 1000000, 1, 0);
    hp_release(&p, hp_release_due(&p), 2);
    hp_target packet = p.current;
    const int64_t late = packet.present_target_qpc + 180000;
    hp_observe_ready(&p, &packet, late, 1);
    hp_presented(&p, &packet, late, late);
    assert(p.next_present >= late + 1001000);
    const int64_t before = p.next_present;
    hp_skip(&p); hp_skip(&p);
    assert(p.next_present == before + 2 * 1001000);
    hp_release(&p, hp_release_due(&p), 2);
    assert(p.current.intentional_skip_ticks == 2);
    hp_release(&p, hp_release_due(&p), 2);
    assert(p.current.intentional_skip_ticks == 0);
    hp_reset(&p, 60000000, 9000000, 2, 0);
    const int64_t reset_target = p.next_present;
    hp_presented(&p, &packet, late + 90000000, late + 90000000);
    assert(p.next_present == reset_target); /* old generation cancelled */
}
static void budget_excludes_holds_and_saturates_slow_local_frames(void)
{
    hp_policy p;
    hp_reset(&p, 60000000, 1000000, 1, 0);
    hp_release(&p, hp_release_due(&p), 2);
    hp_target packet = p.current;
    const int64_t original = p.budget;
    hp_observe_ready(&p, &packet, packet.release_qpc + 1200000, 0);
    assert(p.budget == original); /* network/unknown sample */
    packet.intentional_skip_ticks = 1;
    hp_observe_ready(&p, &packet, packet.release_qpc + 1200000, 1);
    assert(p.budget == original);
    packet.intentional_skip_ticks = 0;
    const int64_t ready = packet.release_qpc + 1200000; /* 20 ms local work */
    hp_observe_ready(&p, &packet, ready, 1);
    hp_presented(&p, &packet, ready, ready);
    assert(p.budget == 1001000 - 12000); /* period - 0.2 ms */
    assert(hp_release_due(&p) - ready == 12000); /* no extra 12.7 ms old-budget hold */
    hp_reset(&p, 60000000, 1000000, 3, 360000);
    hp_release(&p, hp_release_due(&p), 2);
    packet = p.current;
    hp_observe_ready(&p, &packet, packet.release_qpc + 500000, 1);
    assert(p.budget == 360000); /* controlled A/B budget frozen */
}
int main(void)
{
    rational_grid_and_ordinary_wake_jitter();
    alternating_work_targets_and_handoff();
    late_recovery_skips_and_generation();
    budget_excludes_holds_and_saturates_slow_local_frames();
    puts("PASS: rational grid, jitter, work variation, immutable targets, late recovery, holds, skips, reset");
    return 0;
}
