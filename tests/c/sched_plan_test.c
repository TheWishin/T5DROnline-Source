/*
 * Thread placement (ps3recomp patch 0065, runtime/platform/host_sched_plan.h) on
 * made-up processor tables: the CPUs this PC does not have -- Intel hybrid parts
 * (12th-14th gen, Core Ultra with its low-power island), two-CCD and X3D Ryzens,
 * 4-core CCX Ryzens, SMT and no SMT, affinity masks -- built the way
 * GetSystemCpuSetInformation reports them (one entry per logical processor:
 * CoreIndex = the core's first logical processor, LastLevelCacheIndex,
 * EfficiencyClass higher = faster, SchedulingClass = the firmware's ranking).
 *
 * Built by tests/test_sched_plan.py against the patched runtime source; prints
 * "PASS <n> checks" and exits 0, or names every failed check and exits 1.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>

#include "platform/host_sched_plan.h"

static int g_checks, g_fails;
#define CHECK(cond, ...) do { g_checks++; if (!(cond)) { g_fails++; \
    printf("FAIL %s:%d: %s -- ", __FILE__, __LINE__, #cond); printf(__VA_ARGS__); printf("\n"); } } while (0)

typedef struct { hsp_cpu c[HSP_MAX]; int n; } table;

/* `cores` cores with `smt` logical processors each, efficiency class `eff`,
 * last-level cache `llc` of `l3_kb`, ranked `sched` (the same for all). */
static void add(table* t, int cores, int smt, int eff, int llc, int sched, uint32_t l3_kb)
{
    for (int k = 0; k < cores; k++) {
        const int first = t->n;
        for (int j = 0; j < smt; j++) {
            hsp_cpu* c = &t->c[t->n];
            c->id = 0x100u + (uint32_t)t->n;
            c->lp = (uint8_t)t->n;
            c->core = (uint8_t)first;
            c->llc = (uint8_t)llc;
            c->eff = (uint8_t)eff;
            c->sched = (uint8_t)sched;
            c->l3_kb = l3_kb;
            t->n++;
        }
    }
}

static void rank_core(table* t, int lp, int sched)    /* a preferred core: both its threads */
{
    const int core = t->c[lp].core;
    for (int i = 0; i < t->n; i++) if (t->c[i].core == core) t->c[i].sched = (uint8_t)sched;
}

static uint64_t all_of(const table* t) { return t->n >= 64 ? ~0ull : (1ull << t->n) - 1; }
static int core_of(const table* t, int lp) { return t->c[lp].core; }
static int eff_of(const table* t, int lp) { return t->c[lp].eff; }

static uint64_t lps_where(const table* t, int (*pred)(const hsp_cpu*, int), int arg)
{
    uint64_t m = 0;
    for (int i = 0; i < t->n; i++) if (pred(&t->c[i], arg)) m |= 1ull << t->c[i].lp;
    return m;
}
static int is_eff(const hsp_cpu* c, int e) { return c->eff == e; }
static int is_llc(const hsp_cpu* c, int g) { return c->llc == g; }

/* What every plan must hold, whatever the table. */
static void invariants(const char* what, const table* t, uint64_t allowed, const hsp_plan* p, int laptop)
{
    uint64_t in = 0;
    for (int i = 0; i < t->n; i++) if (t->c[i].lp < 64 && ((allowed >> t->c[i].lp) & 1u)) in |= 1ull << t->c[i].lp;
    for (int k = 0; k < HSP_KINDS; k++) {
        CHECK((p->set[k] & ~in) == 0, "%s: kind %d set 0x%llx outside the mask 0x%llx", what, k,
              (unsigned long long)p->set[k], (unsigned long long)in);
        CHECK(p->set[k] != in || in == 0, "%s: kind %d: a set equal to the whole mask must be 0 (none)", what, k);
    }
    for (int k = HSP_MAIN; k <= HSP_SPU; k++) {
        const int lp = p->ideal[k];
        if (!in) continue;
        CHECK(lp >= 0, "%s: kind %d has no ideal processor", what, k);
        if (lp < 0) continue;
        CHECK((in >> lp) & 1u, "%s: kind %d ideal LP %d outside the mask", what, k, lp);
        if (p->set[k]) CHECK((p->set[k] >> lp) & 1u, "%s: kind %d ideal LP %d outside its own set", what, k, lp);
    }
    if (in && p->ideal[HSP_MAIN] >= 0 && p->ideal[HSP_TICKER] >= 0) {
        const uint64_t crit = p->set[HSP_MAIN] ? p->set[HSP_MAIN] : in;
        if (hsp_cores_in(t->c, t->n, crit) >= 2)
            CHECK(core_of(t, p->ideal[HSP_MAIN]) != core_of(t, p->ideal[HSP_TICKER]),
                  "%s: game thread and translation on one core (LP %d, %d)", what, p->ideal[HSP_MAIN], p->ideal[HSP_TICKER]);
        if (hsp_cores_in(t->c, t->n, crit) >= 3)
            CHECK(core_of(t, p->ideal[HSP_SPU]) != core_of(t, p->ideal[HSP_MAIN]) &&
                  core_of(t, p->ideal[HSP_SPU]) != core_of(t, p->ideal[HSP_TICKER]),
                  "%s: sound core shares a core with the game thread or the translation", what);
    }
    if (p->hybrid) {
        int top = 0;
        for (int i = 0; i < t->n; i++) if (((in >> t->c[i].lp) & 1u) && t->c[i].eff > top) top = t->c[i].eff;
        for (int k = HSP_MAIN; k <= HSP_GAME; k++) {
            CHECK(p->set[k] != 0, "%s: hybrid, kind %d has no CPU set", what, k);
            for (int i = 0; i < t->n; i++)
                if ((p->set[k] >> t->c[i].lp) & 1u)
                    CHECK(t->c[i].eff == top, "%s: hybrid, kind %d may run on LP %d of class %d (top %d)", what, k,
                          t->c[i].lp, t->c[i].eff, top);
        }
    }
    CHECK(p->set[HSP_MAIN] == p->set[HSP_TICKER] && p->set[HSP_MAIN] == p->set[HSP_SPU] &&
          p->set[HSP_MAIN] == p->set[HSP_GAME], "%s: the frame's threads have different sets", what);
    CHECK(p->set[HSP_SPURS] == p->set[HSP_VERTEX], "%s: worker sets differ", what);
    CHECK((p->reserved & p->set[HSP_SPURS]) == 0, "%s: workers may run on reserved LPs", what);
    if (p->reserved) {
        CHECK(p->set[HSP_SPURS] != 0, "%s: reserved cores but no worker set", what);
        CHECK((p->reserved >> p->ideal[HSP_MAIN]) & 1u, "%s: the game thread's core is not reserved", what);
        CHECK((p->reserved >> p->ideal[HSP_TICKER]) & 1u, "%s: the translation's core is not reserved", what);
        /* whole cores: both siblings */
        for (int i = 0; i < t->n; i++)
            if ((p->reserved >> t->c[i].lp) & 1u)
                for (int j = 0; j < t->n; j++)
                    if (t->c[j].core == t->c[i].core && ((in >> t->c[j].lp) & 1u))
                        CHECK((p->reserved >> t->c[j].lp) & 1u, "%s: LP %d reserved, its sibling %d not", what,
                              t->c[i].lp, t->c[j].lp);
    }
    CHECK(p->spurs_threads >= 1 && p->spurs_threads <= 12, "%s: SPURS %d", what, p->spurs_threads);
    CHECK(p->spurs_threads <= (p->pool_lps > 1 ? p->pool_lps - 1 : 1), "%s: SPURS %d > processors - 1 (%d)", what,
          p->spurs_threads, p->pool_lps);
    if (laptop) CHECK(p->spurs_threads <= 6, "%s: power saving, SPURS %d", what, p->spurs_threads);
    CHECK(p->vertex_threads == 1 || p->vertex_threads == 3, "%s: vertex %d", what, p->vertex_threads);
    if (laptop) CHECK(p->vertex_threads == 1, "%s: power saving, vertex %d", what, p->vertex_threads);
}

static hsp_plan plan(const char* what, const table* t, uint64_t allowed, int budget, int laptop)
{
    hsp_plan p;
    hsp_make(t->c, t->n, allowed, budget, laptop, &p);
    invariants(what, t, allowed, &p, laptop);
    return p;
}

/* ---- the CPUs -------------------------------------------------------------------- */

static void test_4c4t(void)        /* i5-7300HQ: the player's laptop */
{
    table t = { 0 };
    add(&t, 4, 1, 0, 0, 0, 6 * 1024);
    hsp_plan p = plan("4c/4t", &t, all_of(&t), 0, 0);
    CHECK(p.lps == 4 && p.cores == 4 && !p.smt && !p.hybrid && p.groups == 1 && p.small, "4c/4t: %d %d", p.lps, p.cores);
    for (int k = 0; k < HSP_KINDS; k++) CHECK(p.set[k] == 0, "4c/4t: no CPU sets (kind %d)", k);
    CHECK(p.reserved == 0, "4c/4t: nothing reserved");
    /* no core ranked above another: processor 0 (interrupts) last */
    CHECK(p.ideal[HSP_MAIN] == 1 && p.ideal[HSP_TICKER] == 2 && p.ideal[HSP_SPU] == 3,
          "4c/4t: ideal 1/2/3, processor 0 last, got %d/%d/%d", p.ideal[HSP_MAIN], p.ideal[HSP_TICKER], p.ideal[HSP_SPU]);
    CHECK(p.spurs_threads == 3, "4c/4t: 3 job threads (one per core but the game thread's), got %d", p.spurs_threads);
    CHECK(p.vertex_threads == 1 && p.vertex_spin == 300, "4c/4t: vertex %d spin %d", p.vertex_threads, p.vertex_spin);
    hsp_plan l = plan("4c/4t laptop", &t, all_of(&t), 0, 1);
    CHECK(l.spurs_threads == 3, "4c/4t power saving: still 3, got %d", l.spurs_threads);
}

static void test_2c4t(void)
{
    table t = { 0 };
    add(&t, 2, 2, 0, 0, 0, 4096);
    hsp_plan p = plan("2c/4t", &t, all_of(&t), 0, 0);
    CHECK(p.lps == 4 && p.cores == 2 && p.smt && p.small, "2c/4t");
    CHECK(p.spurs_threads == 2, "2c/4t: 2 job threads, got %d", p.spurs_threads);
    CHECK(p.reserved == 0 && p.set[HSP_SPURS] == 0, "2c/4t: too few cores to reserve any");
    CHECK(p.ideal[HSP_MAIN] == 2 && p.ideal[HSP_TICKER] == 0, "2c/4t: the game thread off processor 0's core");
}

static void test_4c8t(void)        /* i7-7700HQ */
{
    table t = { 0 };
    add(&t, 4, 2, 0, 0, 0, 6144);
    hsp_plan p = plan("4c/8t", &t, all_of(&t), 0, 0);
    CHECK(p.small && p.smt && p.cores == 4, "4c/8t");
    CHECK(p.spurs_threads == 4, "4c/8t: 4, got %d", p.spurs_threads);
    CHECK(p.reserved == 0, "4c/8t: no reservation below %d cores", HSP_RESERVE_MIN_CORES);
}

static void test_6c12t(void)       /* i5-12400 / Ryzen 5 7600: SMT, one kind, one cache */
{
    table t = { 0 };
    add(&t, 6, 2, 0, 0, 0, 18 * 1024);
    rank_core(&t, 4, 3);           /* the firmware's two best cores */
    rank_core(&t, 8, 2);
    hsp_plan p = plan("6c/12t", &t, all_of(&t), 0, 0);
    CHECK(!p.small && p.smt && !p.hybrid && p.hot < 0, "6c/12t");
    CHECK(p.set[HSP_MAIN] == 0, "6c/12t: the frame's threads anywhere");
    CHECK(p.ideal[HSP_MAIN] == 4 && p.ideal[HSP_TICKER] == 8, "6c/12t: best-ranked cores first: %d %d",
          p.ideal[HSP_MAIN], p.ideal[HSP_TICKER]);
    CHECK(p.reserved == 0x330ull, "6c/12t: the game thread's and translation's cores reserved: 0x%llx",
          (unsigned long long)p.reserved);
    CHECK(p.set[HSP_SPURS] == (all_of(&t) & ~0x330ull), "6c/12t: workers on the other 4 cores");
    CHECK(p.spurs_threads == 6, "6c/12t: 6, got %d", p.spurs_threads);
}

static void test_6c6t(void)
{
    table t = { 0 };
    add(&t, 6, 1, 0, 0, 0, 9216);
    hsp_plan p = plan("6c/6t", &t, all_of(&t), 0, 0);
    CHECK(!p.small && !p.smt && p.reserved == 0, "6c/6t: no SMT, nothing to reserve");
    CHECK(p.spurs_threads == 5, "6c/6t: 5, got %d", p.spurs_threads);
}

static void test_12700h(void)      /* 6 P-cores with HT + 8 E-cores, one L3 */
{
    table t = { 0 };
    add(&t, 6, 2, 1, 0, 0, 24 * 1024);
    add(&t, 8, 1, 0, 0, 0, 24 * 1024);
    rank_core(&t, 2, 5);           /* Turbo Boost Max favoured core */
    hsp_plan p = plan("12700H", &t, all_of(&t), 0, 0);
    const uint64_t pc = lps_where(&t, is_eff, 1), ec = lps_where(&t, is_eff, 0);
    CHECK(p.hybrid && p.p_cores == 6 && p.p_lps == 12 && p.e_cores == 8 && p.top_eff == 1, "12700H kinds");
    CHECK(p.set[HSP_MAIN] == pc, "12700H: frame on the P-cores: 0x%llx", (unsigned long long)p.set[HSP_MAIN]);
    CHECK(p.ideal[HSP_MAIN] == 2, "12700H: the favoured core first, got %d", p.ideal[HSP_MAIN]);
    CHECK(p.ideal[HSP_TICKER] == 4 && p.ideal[HSP_SPU] == 6, "12700H: then P-cores by number, processor 0's last: %d %d",
          p.ideal[HSP_TICKER], p.ideal[HSP_SPU]);
    CHECK(eff_of(&t, p.ideal[HSP_TICKER]) == 1 && eff_of(&t, p.ideal[HSP_SPU]) == 1, "12700H: ideal on P-cores");
    CHECK((p.set[HSP_SPURS] & ec) == ec, "12700H: workers may use every E-core");
    CHECK(p.reserved == 0x3Cull, "12700H: the two P-cores of the game thread and the translation reserved, got 0x%llx",
          (unsigned long long)p.reserved);
    CHECK(p.spurs_threads == 12, "12700H: 12, got %d", p.spurs_threads);
    hsp_plan l = plan("12700H laptop", &t, all_of(&t), 0, 1);
    CHECK(l.spurs_threads == 6 && l.vertex_threads == 1, "12700H power saving: 6 / 1, got %d / %d",
          l.spurs_threads, l.vertex_threads);
    /* an affinity mask with only E-cores: one kind inside it */
    hsp_plan e = plan("12700H E only", &t, ec, 0, 0);
    CHECK(!e.hybrid && e.set[HSP_MAIN] == 0, "12700H E-cores only: nothing to prefer");
    /* the mask of P-core threads 0,2 + all E-cores */
    hsp_plan m = plan("12700H mixed mask", &t, ec | 0x5ull, 0, 0);
    CHECK(m.hybrid && m.set[HSP_MAIN] == 0x5ull, "12700H mixed mask: the two P threads, got 0x%llx",
          (unsigned long long)m.set[HSP_MAIN]);
}

static void test_core0(void)       /* processor 0's core is ranked best by the firmware */
{
    table t = { 0 };
    add(&t, 8, 2, 0, 0, 0, 32768);
    rank_core(&t, 0, 9);
    rank_core(&t, 6, 5);
    hsp_plan p = plan("core0 best", &t, all_of(&t), 0, 0);
    CHECK(p.ideal[HSP_MAIN] == 6 && core_of(&t, p.ideal[HSP_TICKER]) != 0 && core_of(&t, p.ideal[HSP_SPU]) != 0,
          "core 0 last even when ranked first: %d %d %d", p.ideal[HSP_MAIN], p.ideal[HSP_TICKER], p.ideal[HSP_SPU]);
    /* hybrid with processor 0 on the only P-core: the class wins */
    table h = { 0 };
    add(&h, 1, 2, 1, 0, 0, 12288);
    add(&h, 4, 1, 0, 0, 0, 12288);
    hsp_plan q = plan("1P+4E", &h, all_of(&h), 0, 0);
    CHECK(q.ideal[HSP_MAIN] == 0 || q.ideal[HSP_MAIN] == 1, "one P-core: the game thread there, got %d", q.ideal[HSP_MAIN]);
}

static void test_13900k(void)      /* 8P/16 + 16E */
{
    table t = { 0 };
    add(&t, 8, 2, 1, 0, 0, 36 * 1024);
    add(&t, 16, 1, 0, 0, 0, 36 * 1024);
    hsp_plan p = plan("13900K", &t, all_of(&t), 0, 0);
    CHECK(p.hybrid && p.set[HSP_MAIN] == 0xFFFFull, "13900K: P-cores LP 0-15");
    CHECK(p.vertex_threads == 3, "13900K: 3 vertex workers (32 logical), got %d", p.vertex_threads);
}

static void test_meteor_lake(void) /* Core Ultra 7 155H: 6P(HT) + 8E share an L3; 2 LP-E on their own */
{
    table t = { 0 };
    add(&t, 6, 2, 2, 0, 0, 24 * 1024);
    add(&t, 8, 1, 1, 0, 0, 24 * 1024);
    add(&t, 2, 1, 0, 1, 0, 0);
    hsp_plan p = plan("155H", &t, all_of(&t), 0, 0);
    const uint64_t lpe = lps_where(&t, is_llc, 1);
    CHECK(p.hybrid && p.top_eff == 2 && p.groups == 2, "155H kinds/groups");
    CHECK(p.hot == 0, "155H: the compute tile, got %d", p.hot);
    CHECK(p.set[HSP_MAIN] == lps_where(&t, is_eff, 2), "155H: frame on the P-cores");
    CHECK((p.set[HSP_SPURS] & lpe) == 0 && (p.set[HSP_SPURS] & lps_where(&t, is_eff, 1)), "155H: workers on the "
          "compute tile's E-cores, never the low-power island");
    /* Core Ultra 5 125H: only 4 P-cores, still 12 cores in the tile */
    table u = { 0 };
    add(&u, 4, 2, 2, 0, 0, 18 * 1024);
    add(&u, 8, 1, 1, 0, 0, 18 * 1024);
    add(&u, 2, 1, 0, 1, 0, 0);
    hsp_plan q = plan("125H", &u, all_of(&u), 0, 0);
    CHECK(q.hot == 0 && (q.set[HSP_SPURS] & lps_where(&u, is_llc, 1)) == 0, "125H: compute tile only");
}

static void test_7950x(void)       /* two CCDs of 8 cores / 16 threads, 32 MB each */
{
    table t = { 0 };
    add(&t, 8, 2, 0, 0, 0, 32 * 1024);
    add(&t, 8, 2, 0, 1, 0, 32 * 1024);
    rank_core(&t, 6, 9); rank_core(&t, 10, 8); rank_core(&t, 4, 7); rank_core(&t, 20, 6);
    hsp_plan p = plan("7950X", &t, all_of(&t), 0, 0);
    CHECK(p.groups == 2 && p.hot == 0 && p.hot_cores == 8 && p.hot_lps == 16 && !p.hot_by_l3, "7950X: CCD0");
    CHECK(p.set[HSP_MAIN] == 0xFFFFull, "7950X: the frame on CCD0");
    CHECK(p.ideal[HSP_MAIN] == 6 && p.ideal[HSP_TICKER] == 10 && p.ideal[HSP_SPU] == 4, "7950X: best cores %d %d %d",
          p.ideal[HSP_MAIN], p.ideal[HSP_TICKER], p.ideal[HSP_SPU]);
    CHECK(p.reserved == 0xCC0ull && p.set[HSP_SPURS] == (0xFFFFull & ~0xCC0ull), "7950X: workers on CCD0 but the "
          "game's two cores: 0x%llx", (unsigned long long)p.set[HSP_SPURS]);
    CHECK(p.spurs_threads == 8 && p.vertex_threads == 1, "7950X: 8 / 1, got %d / %d", p.spurs_threads,
          p.vertex_threads);
    for (int k = 0; k < HSP_KINDS; k++)
        for (int i = 16; i < 32; i++) CHECK(!((p.set[k] >> i) & 1u), "7950X: kind %d may use CCD1 LP %d", k, i);
    /* the best core on CCD1: CCD1 */
    rank_core(&t, 20, 10);
    hsp_plan q = plan("7950X ccd1", &t, all_of(&t), 0, 0);
    CHECK(q.hot == 1 && q.set[HSP_MAIN] == 0xFFFF0000ull && q.ideal[HSP_MAIN] == 20, "7950X: CCD1 holds the best core");
    /* affinity masks: 4 threads on one CCD, and 4 cores of each CCD */
    hsp_plan a = plan("7950X 0x55", &t, 0x55ull, 0, 0);
    CHECK(a.lps == 4 && a.cores == 4 && !a.smt && a.groups == 1 && a.small && a.spurs_threads == 3, "7950X 0x55");
    hsp_plan b = plan("7950X 0xF", &t, 0xFull, 0, 0);
    CHECK(b.lps == 4 && b.cores == 2 && b.smt && b.spurs_threads == 2, "7950X 0xF: 2c/4t");
    hsp_plan c = plan("7950X across", &t, 0x00FF00FFull, 0, 0);
    CHECK(c.groups == 2 && c.hot < 0, "7950X 4+4 cores: no group big enough");
    CHECK(c.reserved != 0, "7950X 4+4 cores: 8 cores with SMT, the game's two reserved");
    /* PS3_CPUS=4 on the whole PC: pools from the budget */
    hsp_plan d = plan("7950X PS3_CPUS=4", &t, all_of(&t), 4, 0);
    CHECK(d.pool_lps == 4 && d.spurs_threads == 3, "PS3_CPUS=4: pools from 4, got %d/%d", d.pool_lps, d.spurs_threads);
}

static void test_7950x3d(void)     /* CCD0 96 MB V-Cache (lower clocks), CCD1 32 MB ranked higher */
{
    table t = { 0 };
    add(&t, 8, 2, 0, 0, 1, 96 * 1024);
    add(&t, 8, 2, 0, 1, 2, 32 * 1024);
    hsp_plan p = plan("7950X3D", &t, all_of(&t), 0, 0);
    CHECK(p.hot == 0 && p.hot_by_l3 && p.hot_l3_kb == 96 * 1024, "7950X3D: the V-Cache CCD, got %d", p.hot);
    CHECK(p.set[HSP_MAIN] == 0xFFFFull, "7950X3D: frame on CCD0");
    /* 7800X3D: one CCD */
    table u = { 0 };
    add(&u, 8, 2, 0, 0, 0, 96 * 1024);
    hsp_plan q = plan("7800X3D", &u, all_of(&u), 0, 0);
    CHECK(q.groups == 1 && q.hot < 0 && q.set[HSP_MAIN] == 0, "7800X3D: one cache, no set");
}

static void test_3700x(void)       /* two CCXs of 4 cores: too small to hold the frame */
{
    table t = { 0 };
    add(&t, 4, 2, 0, 0, 0, 16 * 1024);
    add(&t, 4, 2, 0, 1, 0, 16 * 1024);
    hsp_plan p = plan("3700X", &t, all_of(&t), 0, 0);
    CHECK(p.groups == 2 && p.hot < 0 && p.set[HSP_MAIN] == 0, "3700X: nothing restricted");
    CHECK(p.reserved != 0 && p.spurs_threads == 8, "3700X: SMT, 8 cores: reserved, 8 job threads (got %d)",
          p.spurs_threads);
}

static void test_no_table(void)
{
    hsp_plan p;
    hsp_make(NULL, 0, 0, 8, 0, &p);
    CHECK(p.lps == 8 && p.spurs_threads == 7 && p.set[HSP_MAIN] == 0 && p.ideal[HSP_MAIN] == -1,
          "no table: budget only (%d, %d)", p.lps, p.spurs_threads);
}

static void test_mask_text(void)
{
    char b[64];
    CHECK(!strcmp(hsp_mask_text(0xFull, b, sizeof b), "0-3"), "%s", b);
    CHECK(!strcmp(hsp_mask_text(0x55ull, b, sizeof b), "0,2,4,6"), "%s", b);
    CHECK(!strcmp(hsp_mask_text(0xF0F3ull, b, sizeof b), "0-1,4-7,12-15"), "%s", b);
    CHECK(!strcmp(hsp_mask_text(0, b, sizeof b), "all"), "%s", b);
    CHECK(!strcmp(hsp_mask_text(1ull << 63, b, sizeof b), "63"), "%s", b);
}

/* Random tables and masks: the invariants hold for all of them. */
static uint32_t g_rng = 12345u;
static uint32_t rnd(uint32_t n) { g_rng = g_rng * 1103515245u + 12345u; return (g_rng >> 8) % n; }

static void test_random(void)
{
    for (int it = 0; it < 4000; it++) {
        table t = { 0 };
        const int kinds = 1 + (int)rnd(3), groups = 1 + (int)rnd(4);
        for (int g = 0; g < groups && t.n < 60; g++)
            for (int k = 0; k < kinds && t.n < 60; k++) {
                int cores = 1 + (int)rnd(8), smt = 1 + (int)rnd(2);
                if (t.n + cores * smt > 64) cores = (64 - t.n) / smt;
                if (cores > 0) add(&t, cores, smt, kinds - 1 - k, g, (int)rnd(4), rnd(2) ? (1u + rnd(3)) * 16384u : 0);
            }
        if (!t.n) continue;
        for (int i = 0; i < t.n; i++) if (rnd(4) == 0) rank_core(&t, i, (int)rnd(8));
        uint64_t mask = all_of(&t);
        if (rnd(2)) { mask = 0; for (int i = 0; i < t.n; i++) if (rnd(3)) mask |= 1ull << i; if (!mask) mask = 1; }
        char what[48];
        snprintf(what, sizeof what, "random #%d", it);
        hsp_plan p = plan(what, &t, mask, rnd(5) == 0 ? 1 + (int)rnd(16) : 0, (int)rnd(2));
        (void)p;
    }
}

int main(void)
{
    test_4c4t();
    test_2c4t();
    test_4c8t();
    test_6c12t();
    test_6c6t();
    test_12700h();
    test_core0();
    test_13900k();
    test_meteor_lake();
    test_7950x();
    test_7950x3d();
    test_3700x();
    test_no_table();
    test_mask_text();
    test_random();
    if (g_fails) { printf("FAILED %d of %d checks\n", g_fails, g_checks); return 1; }
    printf("PASS %d checks\n", g_checks);
    return 0;
}
