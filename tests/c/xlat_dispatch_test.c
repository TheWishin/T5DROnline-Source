/*
 * Unit test of the span dispatch (ps3recomp patch 0062, libs/video/rsx_dispatch.c, docs/RENDER_PERF.md
 * "Translation CPU"): rsx_dispatch_method_block hands a run of incrementing words that land in registers of
 * one kind (plain state, the transform program window, the transform constant window) to blk_span in one go
 * instead of word by word.
 *
 * Two dispatchers get the same random method stream -- one with the spans, one with the per-word loop
 * (RSX_DISPATCH_SPANS=0, the code before the patch) -- and must end every block with byte-identical state
 * (register file, write counts, transform program, constants, generation counters, inline data) and make the
 * same sink calls in the same order, each seeing the same registers, program and constants. The stream mixes
 * the windows (whole, partial, crossing their ends), load pointers near the end of the program memory and
 * the constant file and far past them, plain state, draw methods, immediate data, inline arrays, flips and
 * methods past the register file.
 *
 *   xlat_dispatch_test      prints "PASS <n> checks" (exit 0) or the failures (exit 1)
 *
 * The runtime file is included as it is (its block tables are static). Built by tests/test_xlat_cpu.py with
 * clang-cl or cl.
 */
#include "rsx_dispatch.c"

static int g_checks, g_fails;
#define CHECK(cond, ...)                                                        \
    do {                                                                        \
        g_checks++;                                                             \
        if (!(cond)) {                                                          \
            g_fails++;                                                          \
            if (g_fails < 20) { printf("FAIL line %d: ", __LINE__); printf(__VA_ARGS__); printf("\n"); } \
        }                                                                       \
    } while (0)

/* ------------------------------------------------------------------ sink log */

typedef struct { u32 kind, a, b; unsigned long long state; } ev_t;
#define EV_CAP 400000
static ev_t g_ev[2][EV_CAP];
static u32 g_nev[2];
static rsx_dispatch* g_rsx[2];

static unsigned long long state_hash(const rsx_dispatch* r)
{
    unsigned long long h = 1469598103934665603ull;
    const u32* w = r->regs;
    for (u32 i = 0; i < RSX_DSP_NUM_REGS; i++) h = (h ^ w[i]) * 1099511628211ull;
    for (u32 i = 0; i < RSX_DSP_VP_WORDS; i++) h = (h ^ r->vp[i]) * 1099511628211ull;
    for (u32 i = 0; i < RSX_DSP_NUM_CONSTANTS; i++)
        for (u32 k = 0; k < 4; k++) h = (h ^ r->constants[i][k]) * 1099511628211ull;
    return h ^ r->vp_gen ^ ((unsigned long long)r->constants_gen << 32);
}

static void log_ev(const rsx_dispatch* r, u32 kind, u32 a, u32 b)
{
    const int who = r == g_rsx[1];
    if (g_nev[who] < EV_CAP) {
        ev_t* e = &g_ev[who][g_nev[who]++];
        e->kind = kind; e->a = a; e->b = b; e->state = state_hash(r);
    }
}
static void s_clear(void* u, const rsx_dispatch* r, u32 m) { (void)u; log_ev(r, 1, m, 0); }
static void s_begin(void* u, const rsx_dispatch* r, u32 p) { (void)u; log_ev(r, 2, p, 0); }
static void s_end(void* u, const rsx_dispatch* r) { (void)u; log_ev(r, 3, 0, 0); }
static void s_arrays(void* u, const rsx_dispatch* r, u32 f, u32 c) { (void)u; log_ev(r, 4, f, c); }
static void s_index(void* u, const rsx_dispatch* r, u32 f, u32 c) { (void)u; log_ev(r, 5, f, c); }
static void s_inline(void* u, const rsx_dispatch* r, const u8* d, u32 n)
{
    (void)u;
    u32 h = 2166136261u;
    for (u32 i = 0; i < n; i++) h = (h ^ d[i]) * 16777619u;
    log_ev(r, 6, n, h);
}
static void s_flip(void* u, const rsx_dispatch* r, u32 a) { (void)u; log_ev(r, 7, a, 0); }

/* ------------------------------------------------------------------ random stream */

static unsigned long long g_rng = 0x9E3779B97F4A7C15ull;
static u32 rnd(void)
{
    g_rng ^= g_rng << 13; g_rng ^= g_rng >> 7; g_rng ^= g_rng << 17;
    return (u32)(g_rng >> 16);
}
static u32 rnd_n(u32 n) { return n ? rnd() % n : 0; }

static u32 bswap(u32 v) { return __builtin_bswap32(v); }

/* a method header the game could plausibly write, and its data words (big-endian, as in the FIFO) */
static u32 pick(u32* method, int* incrementing, u32* words, u32 cap)
{
    u32 n = 1;
    *incrementing = rnd_n(8) != 0;
    switch (rnd_n(14)) {
    case 0: case 1: case 2: {                       /* transform program window */
        const u32 start = rnd_n(32);
        *method = 0x0B80 + start * 4;
        n = 1 + rnd_n(rnd_n(4) ? 32 - start : 40);   /* sometimes past the window's end */
        break; }
    case 3: {                                       /* program load pointer */
        static const u32 ld[] = { 0, 1, 100, 400, 535, 540, 541, 542, 543, 544, 545, 0x3FFFFFFFu,
                                  0x40000000u, 0xFFFFFFFFu, 0xFFFFFFF0u };
        *method = 0x1E9C;
        words[0] = bswap(rnd_n(3) ? rnd_n(560) : ld[rnd_n(sizeof(ld) / sizeof(ld[0]))]);
        return 1; }
    case 4: case 5: {                               /* transform constant window */
        const u32 start = rnd_n(32);
        *method = 0x1F00 + start * 4;
        n = 1 + rnd_n(rnd_n(4) ? 32 - start : 40);
        break; }
    case 6: {                                       /* constant load pointer */
        static const u32 id[] = { 0, 1, 100, 500, 505, 507, 508, 509, 510, 511, 512, 513,
                                  0x3FFFFFFFu, 0x40000000u, 0x40000001u, 0xFFFFFFFFu, 0xFFFFFFF8u };
        *method = 0x1EFC;
        words[0] = bswap(rnd_n(3) ? rnd_n(520) : id[rnd_n(sizeof(id) / sizeof(id[0]))]);
        return 1; }
    case 7: case 8:                                 /* plain state anywhere */
        *method = (rnd_n(0x4000)) * 4;
        n = 1 + rnd_n(rnd_n(3) ? 8 : 64);
        break;
    case 9:                                         /* texture / vertex format state, runs through the switch */
        *method = 0x1A00 + rnd_n(0x200) * 4 - (rnd_n(2) ? 0x40 : 0);
        n = 1 + rnd_n(48);
        break;
    case 10: {                                      /* draw methods */
        static const u32 m[] = { 0x1808, 0x1814, 0x1818, 0x1824, 0x1D94, 0xE920, 0xE924, 0xE944 };
        *method = m[rnd_n(sizeof(m) / sizeof(m[0]))];
        n = 1 + rnd_n(4);
        break; }
    case 11:                                        /* immediate vertex data */
        *method = 0x1C00 + rnd_n(0x40) * 4;
        n = 1 + rnd_n(16);
        break;
    case 12:                                        /* past the register file */
        *method = 0xFFF0 + rnd_n(4) * 4;
        n = 1 + rnd_n(12);
        break;
    default:                                        /* a burst across kinds */
        *method = 0x1D80 + rnd_n(0x60) * 4;
        n = 1 + rnd_n(80);
        break;
    }
    if (n > cap) n = cap;
    for (u32 i = 0; i < n; i++) {
        u32 v = rnd();
        if ((*method == 0x1808 || (*incrementing && *method + i * 4 == 0x1808)) && rnd_n(2)) v = rnd_n(11);
        if (rnd_n(4) == 0) v = rnd_n(16);           /* small values: repeats, so vp[] often does not change */
        words[i] = bswap(v);
    }
    return n;
}

int main(void)
{
    static rsx_dispatch a, b;
    rsx_dispatch_sink sink = {0};
    sink.clear = s_clear; sink.begin = s_begin; sink.end = s_end; sink.draw_arrays = s_arrays;
    sink.draw_index_array = s_index; sink.inline_array = s_inline; sink.flip = s_flip;
    rsx_dispatch_init(&a, &sink);
    rsx_dispatch_init(&b, &sink);
    g_rsx[0] = &a; g_rsx[1] = &b;
    blk_init();
    CHECK(s_blk_ready == 1, "block dispatch is on (no probe variable set)");
    CHECK(s_blk_run[0x0B80 >> 2] == 32 && s_blk_run[0x1F00 >> 2] == 32, "window runs are 32 registers");
    CHECK(s_blk_run[(0x0B80 >> 2) + 31] == 1 && s_blk_kind[(0x0B80 >> 2) + 31] == 1, "last word of the window");

    static u32 words[2048];
    u32 blocks = 0, mism_state = 0;
    for (int round = 0; round < 200000; round++) {
        u32 method; int inc;
        const u32 n = pick(&method, &inc, words, 2047);
        s_blk_spans = 1;
        rsx_dispatch_method_block(&a, method, inc, words, n);
        s_blk_spans = 0;
        rsx_dispatch_method_block(&b, method, inc, words, n);
        blocks++;
        if ((round & 15) == 0) {
            const int same = memcmp(&a, &b, sizeof(a)) == 0;
            if (!same) mism_state++;
            CHECK(same, "state differs after block %d (method 0x%04X inc=%d n=%u)", round, method, inc, n);
            if (!same) {
                for (u32 i = 0; i < RSX_DSP_NUM_REGS; i++)
                    if (a.regs[i] != b.regs[i] || a.seen[i] != b.seen[i]) {
                        printf("  reg 0x%04X: %08X/%u vs %08X/%u\n", i * 4, a.regs[i], a.seen[i], b.regs[i], b.seen[i]);
                        break;
                    }
                printf("  vp_gen %u/%u constants_gen %u/%u vp %d constants %d\n", a.vp_gen, b.vp_gen,
                       a.constants_gen, b.constants_gen, memcmp(a.vp, b.vp, sizeof(a.vp)) != 0,
                       memcmp(a.constants, b.constants, sizeof(a.constants)) != 0);
                /* carry on from equal state so later blocks are still compared */
                memcpy(&b, &a, sizeof(a));
            }
        }
        if (g_nev[0] > EV_CAP - 4096 || g_nev[1] > EV_CAP - 4096) {
            CHECK(g_nev[0] == g_nev[1], "sink call count %u vs %u", g_nev[0], g_nev[1]);
            CHECK(memcmp(g_ev[0], g_ev[1], sizeof(ev_t) * (g_nev[0] < g_nev[1] ? g_nev[0] : g_nev[1])) == 0,
                  "sink calls differ");
            g_nev[0] = g_nev[1] = 0;
        }
    }
    CHECK(g_nev[0] == g_nev[1], "sink call count %u vs %u", g_nev[0], g_nev[1]);
    CHECK(memcmp(g_ev[0], g_ev[1], sizeof(ev_t) * (g_nev[0] < g_nev[1] ? g_nev[0] : g_nev[1])) == 0,
          "sink calls differ");
    CHECK(a.vp_gen > 1000 && a.constants_gen > 1000, "the stream changed the program and the constants (%u, %u)",
          a.vp_gen, a.constants_gen);
    printf("%u blocks, vp_gen %u, constants_gen %u, %u state mismatches\n", blocks, a.vp_gen, a.constants_gen,
           mism_state);
    if (g_fails) {
        printf("FAIL %d of %d checks\n", g_fails, g_checks);
        return 1;
    }
    printf("PASS %d checks\n", g_checks);
    return 0;
}
