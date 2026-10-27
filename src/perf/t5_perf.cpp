/*
 * Frame timing for performance work (our own code; developer builds only).
 * Off unless T5_PERF_LOG=<path> is set. Do not combine with T5_RB_MODE (both
 * override cellGcmSetFlip).
 *
 * The game's main thread calls cellGcmSetFlip once per frame; each call writes
 * one line to <path>:
 *   f <n> t <ms since first flip> dt <ms since previous flip>
 *     cyc <main-thread cycles since previous flip, QueryThreadCycleTime>
 *     busy <the same in ms (TSC rate), minus cycles spent inside the hooked waits>
 *     sem <ms blocked on the frame semaphore> flip/cond/... <ms in other waits>
 *     scene <vtable of the current scene object>
 * and every 300 flips a summary goes to stderr:
 *   [perf] frames a..b: fps, frame time p50/p95/p99/max, main-thread busy p50/p95
 * Frame semaphore: id at 0x106D4A30 (see docs/ROLLBACK.md), waited on by the
 * main thread once per frame after the flip.
 */
#define WIN32_LEAN_AND_MEAN
#include "../platform/t5_win.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <atomic>
#include <vector>
#include <algorithm>

#include "sys_ppu_thread.h"     /* ppu_context */
#include "lv2_syscall_table.h"  /* g_lv2_syscalls */

extern "C" {
extern uint8_t* vm_base;
void    ps3_hle_register_ctx(uint32_t nid, const char* name, void (*fn)(ppu_context*));
int32_t cellGcmSetFlip(void* context, uint32_t bufferId);
void    cellGcmSetWaitFlip(void);
}

#ifdef T5_PGO_GEN
extern "C" int __llvm_profile_write_file(void);   /* clang_rt.profile */
#endif

namespace {

constexpr uint32_t NID_cellGcmSetFlip = 0xDC09357E;
constexpr uint32_t kFrameSemPtr = 0x106D4A30;
constexpr uint32_t kScenePtr = 0x10532DF0;
constexpr int SC_SEM_WAIT = 92;
constexpr uint32_t NID_cellGcmSetWaitFlip = 0x983FB9AA, NID_cellGcmSetWaitFlipUnsafe = 0xDF6476BD;
/* main-thread blocking, by kind, accumulated in QPC ticks since the last flip */
enum { W_SEM, W_FLIP, W_COND, W_LWCOND, W_MUTEX, W_EQ, W_SLEEP, W_N };
const int kWaitSc[W_N] = { 92, -1, 107, 113, 102, 130, 141 };
const char* const kWaitName[W_N] = { "sem", "flip", "cond", "lwcond", "mutex", "eq", "sleep" };
std::atomic<int64_t> g_wait[W_N];
lv2_syscall_fn g_orig_sc[W_N];

uint32_t rd32(uint32_t a) { uint32_t v; memcpy(&v, vm_base + a, 4); return _byteswap_ulong(v); }

FILE* g_out = nullptr;
LARGE_INTEGER g_qpf, g_t0, g_last;
ULONG64 g_cyc_last = 0;
double g_tsc_per_ms = 0;
uint64_t g_main_tid = 0;
uint64_t g_frames = 0;
std::atomic<int64_t> g_sem_ticks{ 0 };     /* QPC ticks blocked on the frame semaphore since the last flip */
std::vector<double> g_win_dt, g_win_busy;
uint64_t g_win_f0 = 0;

double qpc_ms(LONGLONG d) { return 1000.0 * (double)d / (double)g_qpf.QuadPart; }

/* main-thread cycles spent inside the wrappers below: a wait that spins
 * (sys_timer_usleep's precise tail, the flip poll) burns cycles that are not
 * game work, so "work" = cycles - these */
std::atomic<uint64_t> g_wait_cyc{ 0 };
template <int K> int64_t w_wait(ppu_context* ctx)
{
    if (ctx->thread_id != g_main_tid) return g_orig_sc[K](ctx);
    LARGE_INTEGER a, b;
    ULONG64 c0 = 0, c1 = 0;
    c0 = t5p_thread_cycles();
    QueryPerformanceCounter(&a);
    int64_t r = g_orig_sc[K](ctx);
    QueryPerformanceCounter(&b);
    c1 = t5p_thread_cycles();
    g_wait_cyc += c1 - c0;
    /* the frame semaphore separately from other semaphores */
    if (K == W_SEM && (uint32_t)ctx->gpr[3] == rd32(kFrameSemPtr)) g_sem_ticks += b.QuadPart - a.QuadPart;
    else g_wait[K] += b.QuadPart - a.QuadPart;
    return r;
}
void h_wait_flip(ppu_context* ctx)
{
    LARGE_INTEGER a, b;
    ULONG64 c0 = 0, c1 = 0;
    c0 = t5p_thread_cycles();
    QueryPerformanceCounter(&a);
    cellGcmSetWaitFlip();
    QueryPerformanceCounter(&b);
    c1 = t5p_thread_cycles();
    if (ctx->thread_id == g_main_tid) { g_wait[W_FLIP] += b.QuadPart - a.QuadPart; g_wait_cyc += c1 - c0; }
}
template <int K> void hook(lv2_syscall_fn fn)
{
    g_orig_sc[K] = g_lv2_syscalls.handlers[kWaitSc[K]];
    g_lv2_syscalls.handlers[kWaitSc[K]] = fn;
}

double pct(std::vector<double>& v, double p)
{
    if (v.empty()) return 0;
    size_t i = (size_t)(p * (double)(v.size() - 1) + 0.5);
    std::nth_element(v.begin(), v.begin() + i, v.end());
    return v[i];
}

/* CPU time of every guest thread over the summary window, per frame */
uint64_t g_thr_cpu[PPU_THREAD_MAX];
DWORD g_thr_tid[PPU_THREAD_MAX];
void thread_cpu(uint64_t frames)
{
#if !defined(_WIN32)
    (void)frames;   /* GetThreadTimes on the host thread's handle: Windows only (a diagnostic) */
#else
    char line[1600]; int n = 0;
    for (int i = 0; i < PPU_THREAD_MAX; i++) {
        const ppu_thread_info& t = g_ppu_threads[i];
        if (t.state == PPU_THREAD_STATE_FREE || !t.host_thread) continue;
        FILETIME c, e, k, u;
        if (!GetThreadTimes(t.host_thread, &c, &e, &k, &u)) continue;
        const uint64_t cpu = (((uint64_t)k.dwHighDateTime << 32) | k.dwLowDateTime) + (((uint64_t)u.dwHighDateTime << 32) | u.dwLowDateTime);
        if (g_thr_tid[i] == t.host_tid && frames) {
            const double ms = (double)(cpu - g_thr_cpu[i]) / 1e4 / (double)frames;
            if (ms >= 0.2 && n < (int)sizeof line - 80)
                n += snprintf(line + n, sizeof line - n, " [%llu %s %.2f]", (unsigned long long)t.ctx.thread_id, t.name, ms);
        }
        g_thr_tid[i] = t.host_tid; g_thr_cpu[i] = cpu;
    }
    if (n) fprintf(stderr, "[perf] guest thread cpu ms/frame:%s\n", line);
#endif
}

void summary()
{
    thread_cpu(g_frames - g_win_f0);
    std::vector<double> dt = g_win_dt, busy = g_win_busy;
    double sum = 0;
    for (double d : dt) sum += d;
    double mx = dt.empty() ? 0 : *std::max_element(dt.begin(), dt.end());
    fprintf(stderr, "[perf] frames %llu..%llu: %.1f fps, frame ms p50 %.2f p95 %.2f p99 %.2f max %.2f;"
                    " main busy ms p50 %.2f p95 %.2f\n",
            (unsigned long long)g_win_f0, (unsigned long long)g_frames, dt.size() * 1000.0 / (sum > 0 ? sum : 1),
            pct(dt, 0.5), pct(dt, 0.95), pct(dt, 0.99), mx, pct(busy, 0.5), pct(busy, 0.95));
    g_win_dt.clear(); g_win_busy.clear();
    g_win_f0 = g_frames;
}

void h_cellGcmSetFlip(ppu_context* ctx)
{
    LARGE_INTEGER now; QueryPerformanceCounter(&now);
    ULONG64 cyc = t5p_thread_cycles();
    if (!g_main_tid) {
        g_main_tid = ctx->thread_id;
        g_t0 = g_last = now;
        g_cyc_last = cyc;
        /* TSC rate: QueryThreadCycleTime counts TSC ticks */
        LARGE_INTEGER a, b; QueryPerformanceCounter(&a); unsigned long long ta = t5p_cycles();
        Sleep(50);
        QueryPerformanceCounter(&b); unsigned long long tb = t5p_cycles();
        g_tsc_per_ms = (double)(tb - ta) / qpc_ms(b.QuadPart - a.QuadPart);
        hook<W_SEM>(w_wait<W_SEM>); hook<W_COND>(w_wait<W_COND>); hook<W_LWCOND>(w_wait<W_LWCOND>);
        hook<W_MUTEX>(w_wait<W_MUTEX>); hook<W_EQ>(w_wait<W_EQ>); hook<W_SLEEP>(w_wait<W_SLEEP>);
        fprintf(stderr, "[perf] frame log on, main thread %llu, TSC %.0f MHz\n",
                (unsigned long long)g_main_tid, g_tsc_per_ms / 1000.0);
        QueryPerformanceCounter(&g_last);
        g_cyc_last = t5p_thread_cycles();
    } else if (ctx->thread_id == g_main_tid) {
        const double dt = qpc_ms(now.QuadPart - g_last.QuadPart);
        const uint64_t wc = g_wait_cyc.exchange(0);
        const uint64_t dc = cyc - g_cyc_last;
        const double busy = (double)(dc > wc ? dc - wc : 0) / g_tsc_per_ms;   /* game work only */
        const double sem = qpc_ms(g_sem_ticks.exchange(0));
        const uint32_t scene = rd32(kScenePtr);
        g_frames++;
#ifdef T5_PGO_GEN
        { static long at = -1;
          if (at < 0) { const char* e = getenv("T5_PGO_WRITE_AT"); at = e ? atol(e) : 0; }
          if (at > 0 && g_frames == (uint64_t)at) {
              int rc = __llvm_profile_write_file();
              fprintf(stderr, "[perf] PGO profile written at frame %llu (rc %d)\n", (unsigned long long)g_frames, rc);
          } }
#endif
        char w[200]; int n = 0;
        for (int k = 1; k < W_N; k++) n += snprintf(w + n, sizeof w - n, " %s %.3f", kWaitName[k], qpc_ms(g_wait[k].exchange(0)));
        FILETIME ft; GetSystemTimePreciseAsFileTime(&ft);
        const double epoch_s = (double)((((uint64_t)ft.dwHighDateTime << 32) | ft.dwLowDateTime) - 116444736000000000ull) / 1e7;
        /* sim: the game's per-frame sim counter (docs/ROLLBACK.md), to pair
         * frames of two runs with the same scripted input */
        fprintf(g_out, "f %llu e %.3f t %.2f dt %.3f cyc %.2f busy %.3f sem %.3f%s sim %u scene %08X\n",
                (unsigned long long)g_frames, epoch_s, qpc_ms(now.QuadPart - g_t0.QuadPart), dt,
                (double)(cyc - g_cyc_last) / 1e6, busy, sem, w, rd32(0x1008EB9Cu), scene ? rd32(scene) : 0);
        g_win_dt.push_back(dt); g_win_busy.push_back(busy);
        if ((g_frames % 300) == 0) { summary(); fflush(g_out); }
        g_last = now;
        g_cyc_last = cyc;
    }
    ctx->gpr[3] = (uint64_t)(int64_t)cellGcmSetFlip((void*)(uintptr_t)(uint32_t)ctx->gpr[3], (uint32_t)ctx->gpr[4]);
}

struct Register {
    Register()
    {
        const char* p = getenv("T5_PERF_LOG");
        if (!p || !*p) return;
        g_out = fopen(p, "w");
        if (!g_out) { fprintf(stderr, "[perf] cannot open %s\n", p); return; }
        QueryPerformanceFrequency(&g_qpf);
        ps3_hle_register_ctx(NID_cellGcmSetFlip, "cellGcmSetFlip(perf)", h_cellGcmSetFlip);
        ps3_hle_register_ctx(NID_cellGcmSetWaitFlip, "cellGcmSetWaitFlip(perf)", h_wait_flip);
        ps3_hle_register_ctx(NID_cellGcmSetWaitFlipUnsafe, "cellGcmSetWaitFlipUnsafe(perf)", h_wait_flip);
    }
} g_register;

} // namespace
