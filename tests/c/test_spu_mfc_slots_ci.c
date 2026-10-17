/*
 * ps3recomp's runtime/spu/tests/test_spu_mfc_slots.c (MIT, (c) 2026 Ned Heller /
 * sp00nznet), adapted so it runs on a machine with few CPUs. Same assertions on
 * the same unit (the MFC engine slot table in runtime/spu/spu_channels.c, patch
 * 0002's neighbourhood); only the way the threads meet changed. tests/
 * run_ps3recomp_tests.py builds this file in place of the upstream one.
 *
 * What the test checks (from the original): every live SPU context gets an MFC
 * engine of its own, and gives it back. Contexts that claim a slot at the same
 * instant must get different engines (a double claim is silent: two SPUs share
 * one command queue and tag mask, one's tag wait is satisfied by the other's
 * transfer); each engine keeps what its own context wrote while the others
 * write theirs; engines come back freshly initialized; and over many rounds,
 * none of them at an address a previous context used, exactly the same engines
 * are handed out again, which is what says slots come back rather than the
 * overflow engine being shared. Then the table is filled and the next context
 * must get the overflow engine, and a released slot must go to the next asker.
 *
 * What changed, and why:
 *
 *  - The original starts one worker per slot (SPU_MAX_CONTEXTS, 128 at the
 *    pin) and holds them at a spinning barrier with a 10 s deadline. That
 *    needs about as many CPUs as slots: a pure spin never gives its CPU away,
 *    so with 128 workers on 4 CPUs the workers that have not arrived yet get
 *    one only when a spinner's quantum runs out. On a GitHub runner (4 vCPUs)
 *    the barrier timed out, the later checks then failed one after the other,
 *    and the run took 367 s to say "!g_timeout, distinct x32, nseen == NCTX".
 *    It failed that way on every CI run. (On a desktop pinned to 4 CPUs the
 *    original takes 56 s, on 2 CPUs 144 s, and under compile load it fails
 *    the same way.)
 *  - Workers: 2 per logical CPU, at least 8, at most one per slot (override:
 *    T5_MFC_WORKERS=n; 128 reproduces the original). More workers than CPUs
 *    add nothing to the race the test is for -- only the threads running at
 *    the same moment can collide in the few instructions between "found a free
 *    slot" and "stored into it" -- and cost a scheduler quantum each.
 *  - The barrier still spins (a condition variable wakes threads one at a time
 *    and they then walk through the claim in single file, which is the reason
 *    the original spins), but a thread that has spun for a while gives its CPU
 *    away (SwitchToThread), so those not yet arrived can run. The threads
 *    that are on a CPU when it opens still leave it within a cache line's
 *    propagation of each other.
 *  - Rounds: as many as it takes to claim 4096 contexts in total, as the
 *    original does (32 rounds x 128), so the number of claims racing and the
 *    number of contexts alive (none freed, none at a reused address) stay the
 *    same whatever the worker count.
 *  - The deadline is 30 s and is measured from when the barrier's first thread
 *    arrived, not from when a thread started to wait.
 *  - The fill-the-table part at the end uses the table size, not the worker
 *    count.
 *
 * Teeth: against a copy of mfc_for() with the claim lock removed (the bug the
 * test exists for) this version fails with 8, 16, 64 and 128 workers pinned to
 * 4 CPUs (134 to 2400 failed checks); with the lock it takes about a second.
 *
 * spu_channels.c is compiled in rather than linked, because the slot table and
 * mfc_for() are file-static.
 *
 * Build (as tests/run_ps3recomp_tests.py does it; from the ps3recomp tree):
 *   clang-cl /O2 /std:c17 /I include /I runtime/spu /I runtime/platform /I <repo>/tests/shim
 *            <repo>/tests/c/test_spu_mfc_slots_ci.c runtime/spu/spu_drain.c
 *            runtime/spu/spu_lockstep.c runtime/spu/spu_coherency.c runtime/spu/spu_workload.c
 *            runtime/spu/spurs_policy.c runtime/spu/spurs_job.c runtime/spu/spu_tsp_weak.c
 *            runtime/spu/spu_vm_pagemap.c runtime/spu/spurs_policy_blob_weak.c runtime/spu/spu_interp.c
 *
 * Exit code: 0 if all passed, 1 if any failed. Final line prints a summary.
 */

#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

/* Guest memory. Nothing here issues a DMA, so the arena stays empty; the
 * symbol exists because the DMA paths compiled in below read through it. */
uint8_t* vm_base = NULL;
uint32_t ppu_vm_size = 0;

/* The unit under test. */
#include "spu_channels.c"

/* ---------------------------------------------------------------------------
 * Harness
 * -----------------------------------------------------------------------*/
static int g_pass, g_fail;

static void check(int ok, const char* what)
{
    if (ok) { g_pass++; return; }
    g_fail++;
    if (g_fail <= 40) printf("  FAIL: %s\n", what);
}

#define CHECK(cond)  check((cond), #cond)

/* ---------------------------------------------------------------------------
 * Workers claiming together, round after round
 * -----------------------------------------------------------------------*/
#define TABLE        SPU_MAX_CONTEXTS    /* slots in the table, and the most workers */
#define TOTAL_CTX    4096                /* contexts claimed over the run (original: 32 x 128) */
#define MAX_ROUNDS   (TOTAL_CTX / 8)     /* with the fewest workers (8) */

static int g_nwork;                      /* workers, decided in main() */
static int g_rounds;                     /* TOTAL_CTX / g_nwork */

/* Every context in the run is live at once and none is freed, so no two ever
 * share an address. A round that reused an address would find a leaked slot by
 * pointer and pass while leaking. The table keys on the address and never
 * reads through it, so these stay untouched and cost address space only. */
static spu_context* g_ctx[MAX_ROUNDS][TABLE];

static mfc_engine*  g_engine[MAX_ROUNDS][TABLE];  /* what each context was handed  */
static int          g_fresh[MAX_ROUNDS][TABLE];   /* ...initialized when handed    */
static int          g_stable[MAX_ROUNDS][TABLE];  /* ...found again by the lookup  */
static int          g_private[MAX_ROUNDS][TABLE]; /* ...still holding its own state */
static volatile LONG g_timeout;                   /* a barrier gave up             */

/* A spinning barrier across the workers (see the header for why it spins and
 * why it yields). It has a deadline, so a regression is a failing test and not
 * a hanging one. */
static volatile LONG g_bar_arrived;
static volatile LONG g_bar_gen;
static volatile LONG64 g_bar_first;      /* GetTickCount64() of the first arrival, 0 if none */

static void barrier_wait(void)
{
    LONG gen = g_bar_gen;
    ULONGLONG now = GetTickCount64();
    InterlockedCompareExchange64(&g_bar_first, (LONG64)now, 0);
    if (InterlockedIncrement(&g_bar_arrived) == g_nwork) {
        g_bar_arrived = 0;
        g_bar_first = 0;
        InterlockedIncrement(&g_bar_gen);   /* releases the others */
        return;
    }
    unsigned spins = 0;
    while (g_bar_gen == gen) {
        if (++spins < 4000) { YieldProcessor(); continue; }
        spins = 0;
        SwitchToThread();                    /* let a worker that has not arrived run */
        LONG64 first = g_bar_first;
        if (first && (LONG64)GetTickCount64() - first > 30000) { g_timeout = 1; return; }
    }
}

static void* claim_thread(void* arg)
{
    int w = (int)(intptr_t)arg;

    for (int r = 0; r < g_rounds; r++) {
        spu_context* ctx = g_ctx[r][w];

        barrier_wait();                       /* all workers claim together */
        mfc_engine* e = mfc_for(ctx);
        g_engine[r][w] = e;
        /* A slot that came back from a previous owner has to come back clean:
         * all tags idle, nothing queued. */
        g_fresh[r][w]  = (e->tag_completed == 0xFFFFFFFFu) && (e->queue_count == 0);
        g_stable[r][w] = (mfc_for(ctx) == e);

        /* Something only this context would have written, in the two fields a
         * shared engine corrupts. */
        uint32_t mark = 0xA5000000u | (uint32_t)(r * g_nwork + w);
        e->tag_completed = mark;
        e->queue_count   = (uint32_t)w + 1u;

        barrier_wait();                       /* everyone has written theirs */
        g_private[r][w] = (e->tag_completed == mark) &&
                          (e->queue_count == (uint32_t)w + 1u);

        barrier_wait();                       /* ...and everyone has read it */
        spu_mfc_release(ctx);                 /* what the thread's exit does */
    }
    return NULL;
}

/* Is `e` in the first `n` entries of `set`? */
static int engine_seen(mfc_engine* const* set, int n, const mfc_engine* e)
{
    for (int i = 0; i < n; i++)
        if (set[i] == e) return 1;
    return 0;
}

static int worker_count(void)
{
    const char* env = getenv("T5_MFC_WORKERS");
    int n = env ? atoi(env) : 0;
    if (n <= 0) {
        n = 2 * (int)GetActiveProcessorCount(ALL_PROCESSOR_GROUPS);
        if (n < 8) n = 8;
    }
    if (n > TABLE) n = TABLE;
    if (n < 2) n = 2;
    return n;
}

int main(void)
{
    g_nwork = worker_count();
    g_rounds = TOTAL_CTX / g_nwork;
    if (g_rounds > MAX_ROUNDS) g_rounds = MAX_ROUNDS;
    printf("SPU MFC engine slots (%d workers, %d rounds, %lu logical CPUs, %d slots)\n",
           g_nwork, g_rounds, (unsigned long)GetActiveProcessorCount(ALL_PROCESSOR_GROUPS), TABLE);

    for (int r = 0; r < g_rounds; r++) {
        for (int w = 0; w < g_nwork; w++) {
            g_ctx[r][w] = (spu_context*)calloc(1, sizeof(spu_context));
            if (!g_ctx[r][w]) {
                printf("  FAIL: out of memory for %d SPU contexts\n", g_rounds * g_nwork);
                return 1;
            }
        }
    }

    pthread_t th[TABLE];
    for (int w = 0; w < g_nwork; w++)
        if (pthread_create(&th[w], NULL, claim_thread, (void*)(intptr_t)w) != 0) {
            printf("  FAIL: could not start worker %d\n", w);
            return 1;
        }
    for (int w = 0; w < g_nwork; w++)
        pthread_join(th[w], NULL);

    CHECK(!g_timeout);

    /* No two contexts of a round share an engine, each engine was handed over
     * initialized, the lookup keeps finding it, and it holds only what its own
     * context put in it. */
    for (int r = 0; r < g_rounds; r++) {
        int distinct = 1;
        for (int w = 0; w < g_nwork; w++) {
            if (!g_engine[r][w]) { distinct = 0; continue; }
            for (int v = w + 1; v < g_nwork; v++)
                if (g_engine[r][w] == g_engine[r][v]) distinct = 0;
        }
        CHECK(distinct);
        for (int w = 0; w < g_nwork; w++) {
            CHECK(g_fresh[r][w]);
            CHECK(g_stable[r][w]);
            CHECK(g_private[r][w]);
        }
    }

    /* TOTAL_CTX contexts, g_nwork engines. More than that would mean a round
     * fell through to the shared overflow engine or to a new slot, which is what
     * happens when a slot is not given back (the claim takes the lowest free
     * slot, so workers that all come back see the same lowest g_nwork). */
    static mfc_engine* seen[TOTAL_CTX];
    int nseen = 0;
    for (int r = 0; r < g_rounds; r++)
        for (int w = 0; w < g_nwork; w++)
            if (g_engine[r][w] && !engine_seen(seen, nseen, g_engine[r][w]))
                seen[nseen++] = g_engine[r][w];
    CHECK(nseen == g_nwork);

    /* Releasing a context that never issued a DMA, and so holds no slot, is a
     * scan that finds nothing rather than a slot lost. */
    spu_context* idle = (spu_context*)calloc(1, sizeof(spu_context));
    CHECK(idle != NULL);
    spu_mfc_release(idle);

    /* The table is empty again: fill it, then check what the next context
     * gets. Sharing the overflow engine is the documented behaviour above
     * SPU_MAX_CONTEXTS -- a real group has at most six -- and it must not cost
     * a slot, so releasing one of them hands that same slot to the next
     * context that asks. */
    static spu_context* held[TABLE];
    static mfc_engine*  helde[TABLE];
    for (int i = 0; i < TABLE; i++) {
        held[i] = (spu_context*)calloc(1, sizeof(spu_context));
        CHECK(held[i] != NULL);
        helde[i] = mfc_for(held[i]);
    }
    spu_context* ninth = (spu_context*)calloc(1, sizeof(spu_context));
    CHECK(ninth != NULL);
    mfc_engine* ninthe = mfc_for(ninth);
    CHECK(ninthe != NULL);
    CHECK(!engine_seen(helde, TABLE, ninthe));   /* the overflow one */

    spu_mfc_release(held[3]);
    spu_context* reuser = (spu_context*)calloc(1, sizeof(spu_context));
    CHECK(reuser != NULL);
    mfc_engine* reusere = mfc_for(reuser);
    CHECK(reusere == helde[3]);                 /* the freed slot, not overflow */
    CHECK(reusere->tag_completed == 0xFFFFFFFFu);

    printf("SPU MFC engine slots: %d passed, %d failed\n", g_pass, g_fail);
    return g_fail ? 1 : 0;
}

/* ---------------------------------------------------------------------------
 * The runtime beyond the SPU channel layer, stubbed. These are what
 * spu_channels.c reaches for outside its own subsystem: the lv2 mailbox
 * delivery hook's owner, the PPU's reservation and watch helpers, and the
 * title-specific SPURS hooks. None of them is on the path this test drives.
 * -----------------------------------------------------------------------*/
void ppu_resv_break_store(uint64_t ea)                 { (void)ea; }
void ps3_ww_report_inline(uint32_t a, uint64_t v, int w)
{
    (void)a; (void)v; (void)w;
}
unsigned long long ps3_ms_now(void)                    { return 0; }
uint32_t g_ww_lo = 0xFFFFFFFFu, g_ww_hi = 0;
int      g_resv_store_active = 0;
uint32_t g_barrier_sync_watch = 0;

void (*g_spurs_kernel_hook)(uint32_t) = 0;
uint32_t g_ydkj_spurs_ctx_ea = 0;
uint32_t g_ydkj_real_spurs_ea = 0;
uint32_t g_ydkj_real_taskset_ea = 0;
uint32_t g_ydkj_real_taskid = 0;
void spurs_ef_set_from_spu(uint32_t ea, uint16_t bits) { (void)ea; (void)bits; }
void ydkj_wake_all_event_flags(void)                   { }
void spurs_pm_build_context(spu_context* c, uint32_t a, uint32_t b, uint32_t d)
{
    (void)c; (void)a; (void)b; (void)d;
}

/* Loader diagnostics and worker publication are outside this fixture. */
uint32_t g_spu_image_src_ea, g_spu_image_ls_start, g_spu_image_span;
void spu_thread_publish_ctx(uint32_t tid, void* ctx) { (void)tid; (void)ctx; }
