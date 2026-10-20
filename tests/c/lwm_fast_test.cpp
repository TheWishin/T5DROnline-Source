/*
 * Unit test of the guest lwmutex's host lock (ps3recomp patch 0061, runtime/ppu/ppu_lwm_fast.h;
 * docs/RENDER_PERF.md "The game thread's own time"): lock and unlock without a system call while
 * the lock is free, a contended lock handed to a waiter by the unlock.
 *
 *   mutual exclusion   8 threads, 2 locks, short and long critical sections, every lock/unlock
 *                      path (fast, contended, hand-over, timed): no two threads ever inside, no
 *                      increment lost
 *   hand-over          an unlock with a waiter leaves the lock locked for that waiter: the
 *                      unlocking thread cannot take it back first
 *   any thread unlocks a lock taken by another thread (guest code hands lwmutex ownership on)
 *   timeouts           a timed lock of a held lock gives up after its time and takes nothing;
 *                      the lock is free again after its owner's unlock
 *   over-release       unlocking a free lock leaves it free (the semaphore's release at its
 *                      maximum count failed harmlessly)
 *
 *   lwm_fast_test      prints "PASS <n> checks" (exit 0) or the failures (exit 1)
 *
 * Built by tests/test_lwm_fast.py with clang-cl against the patched runtime tree.
 */
#include "ppu_lwm_fast.h"

#include <stdio.h>
#include <stdlib.h>
#include <atomic>
#include <chrono>
#include <thread>
#include <vector>

static int g_checks, g_fails;
#define CHECK(cond, ...)                                                        \
    do {                                                                        \
        g_checks++;                                                             \
        if (!(cond)) {                                                          \
            g_fails++;                                                          \
            printf("FAIL %s:%d: ", __FILE__, __LINE__);                         \
            printf(__VA_ARGS__);                                                \
            printf("\n");                                                       \
        }                                                                       \
    } while (0)

using clk = std::chrono::steady_clock;
static int waiters(LwmFast* l) { std::lock_guard<std::mutex> g(lwm_fast_q().mu); return l->nwait; }
static void wait_for_waiters(LwmFast* l, int n)
{
    const auto end = clk::now() + std::chrono::seconds(10);
    while (waiters(l) < n && clk::now() < end) std::this_thread::yield();
}

static void test_basic()
{
    LwmFast l;
    CHECK(lwm_fast_try(&l) == 1, "a free lock is taken by a try");
    CHECK(lwm_fast_try(&l) == 0, "a held lock is not taken by a try");
    lwm_fast_release(&l);
    CHECK(l.st.load() == 0, "released without waiters: free (st %d)", l.st.load());
    CHECK(lwm_fast_acquire(&l, LWM_FAST_FOREVER) == 1, "acquire of a free lock");
    lwm_fast_release(&l);
    /* over-release: a free lock released again stays free, and is taken once */
    lwm_fast_release(&l);
    lwm_fast_release(&l);
    CHECK(l.st.load() == 0, "over-release leaves the lock free (st %d)", l.st.load());
    CHECK(lwm_fast_try(&l) == 1 && lwm_fast_try(&l) == 0, "after an over-release the lock is taken exactly once");
    lwm_fast_release(&l);
}

static void test_handover()
{
    LwmFast l;
    CHECK(lwm_fast_acquire(&l, LWM_FAST_FOREVER) == 1, "main takes the lock");
    std::atomic<int> got{ 0 };
    std::thread t([&] { if (lwm_fast_acquire(&l, LWM_FAST_FOREVER)) got = 1; });
    wait_for_waiters(&l, 1);
    CHECK(waiters(&l) == 1, "the second thread waits");
    lwm_fast_release(&l);
    /* handed over: it stays locked for the waiter, whatever the waiter's thread is doing now */
    CHECK(lwm_fast_try(&l) == 0, "after an unlock with a waiter the unlocking thread cannot take the lock back");
    t.join();
    CHECK(got == 1, "the waiter owns the lock");
    CHECK(l.st.load() == 1, "one owner, nobody waiting: st 1 (st %d)", l.st.load());
    /* any thread may unlock: the lock the other thread took is released here */
    lwm_fast_release(&l);
    CHECK(l.st.load() == 0, "released by another thread: free (st %d)", l.st.load());
}

static void test_timeout()
{
    LwmFast l;
    lwm_fast_acquire(&l, LWM_FAST_FOREVER);
    int r = -1;
    double ms = 0;
    std::thread t([&] {
        const auto a = clk::now();
        r = lwm_fast_acquire(&l, 60);
        ms = std::chrono::duration<double, std::milli>(clk::now() - a).count();
    });
    t.join();
    CHECK(r == 0, "a timed lock of a held lock times out (r %d)", r);
    CHECK(ms >= 50.0, "it waited its time (%.1f ms)", ms);
    CHECK(waiters(&l) == 0, "the timed-out waiter withdrew");
    lwm_fast_release(&l);
    CHECK(l.st.load() == 0, "after the owner's unlock the lock is free (st %d)", l.st.load());
    CHECK(lwm_fast_try(&l) == 1, "and can be taken");
    lwm_fast_release(&l);

    /* a timed waiter that is handed the lock before its time runs out owns it */
    lwm_fast_acquire(&l, LWM_FAST_FOREVER);
    std::thread t2([&] { r = lwm_fast_acquire(&l, 5000); });
    wait_for_waiters(&l, 1);
    lwm_fast_release(&l);
    t2.join();
    CHECK(r == 1, "a timed waiter handed the lock owns it (r %d)", r);
    CHECK(lwm_fast_try(&l) == 0, "and the lock is held");
    lwm_fast_release(&l);
    CHECK(lwm_fast_try(&l) == 1, "free after its unlock");
    lwm_fast_release(&l);
}

/* every path at once: fast and contended locks, timed locks that give up, unlocks by another
 * thread (a token passed on with the lock), critical sections from nothing to a sleep */
static void test_stress()
{
    LwmFast locks[2];
    long long counter[2] = { 0, 0 };
    std::atomic<int> inside[2] = { { 0 }, { 0 } };
    std::atomic<int> overlap{ 0 }, timeouts{ 0 };
    long long done[2] = { 0, 0 };
    const int T = 8, N = 40000;
    std::vector<std::thread> th;
    std::atomic<int> handoff_pending{ -1 };   /* a lock index whose owner left it for another thread to release */
    for (int t = 0; t < T; t++) {
        th.emplace_back([&, t] {
            uint32_t rng = 0x9E3779B9u * (t + 1);
            auto rnd = [&] { rng ^= rng << 13; rng ^= rng >> 17; rng ^= rng << 5; return rng; };
            for (int i = 0; i < N; i++) {
                /* release a lock another thread left locked for us */
                int hp = handoff_pending.load();
                if (hp >= 0 && handoff_pending.compare_exchange_strong(hp, -1)) {
                    inside[hp].fetch_sub(1);
                    lwm_fast_release(&locks[hp]);
                }
                const int k = (int)(rnd() & 1);
                const uint32_t mode = rnd() % 16;
                int ok;
                if (mode == 0) ok = lwm_fast_try(&locks[k]);
                else if (mode < 3) { ok = lwm_fast_acquire(&locks[k], rnd() % 3); if (!ok) timeouts++; }
                else ok = lwm_fast_acquire(&locks[k], LWM_FAST_FOREVER);
                if (!ok) continue;
                if (inside[k].fetch_add(1) != 0) overlap++;
                counter[k]++;
                done[k]++;
                const uint32_t w = rnd() % 64;
                if (w == 0 && rnd() % 16 == 0) std::this_thread::sleep_for(std::chrono::microseconds(200));   /* a long hold now and then */
                else for (uint32_t s = 0; s < w; s++) std::atomic_signal_fence(std::memory_order_seq_cst);
                int none = -1;
                if (rnd() % 97 == 0 && handoff_pending.compare_exchange_strong(none, k)) continue;   /* someone else unlocks */
                inside[k].fetch_sub(1);
                lwm_fast_release(&locks[k]);
            }
            /* a lock this thread left for another one may have nobody left to release it */
            int hp = handoff_pending.load();
            if (hp >= 0 && handoff_pending.compare_exchange_strong(hp, -1)) {
                inside[hp].fetch_sub(1);
                lwm_fast_release(&locks[hp]);
            }
        });
    }
    for (auto& x : th) x.join();
    int hp = handoff_pending.load();
    if (hp >= 0) { inside[hp].fetch_sub(1); lwm_fast_release(&locks[hp]); }
    CHECK(overlap == 0, "never two threads inside one lock (%d overlaps)", overlap.load());
    CHECK(counter[0] == done[0] && counter[1] == done[1], "no increment lost");
    CHECK(done[0] + done[1] > T * N / 2, "most locks were taken (%lld)", done[0] + done[1]);
    for (int k = 0; k < 2; k++) {
        CHECK(locks[k].st.load() == 0, "lock %d free at the end (st %d)", k, locks[k].st.load());
        CHECK(waiters(&locks[k]) == 0 && locks[k].tokens == 0, "lock %d: no waiter or hand-over left", k);
    }
    printf("stress: %lld + %lld locks, %d timed out\n", done[0], done[1], timeouts.load());
}

int main()
{
    test_basic();
    test_handover();
    test_timeout();
    test_stress();
    if (g_fails) { printf("FAILED %d of %d checks\n", g_fails, g_checks); return 1; }
    printf("PASS %d checks\n", g_checks);
    return 0;
}
