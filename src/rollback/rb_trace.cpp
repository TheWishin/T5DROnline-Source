/*
 * One-frame syscall timeline of the main thread: every lv2 syscall it makes
 * while a trace window is open is logged with the time since the window
 * opened, its duration, number, r3 and the lifted callers. Shows where a
 * frame spends its time between syscalls (CPU in lifted code) and inside them
 * (waits). Installed from the test mode; costs nothing while no window is open
 * beyond one predictable branch per syscall.
 */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdio.h>
#include <atomic>
#include <utility>

#include "sys_ppu_thread.h"
#include "lv2_syscall_table.h"
#include "rb.h"

namespace rb {

namespace {
typedef int64_t (*fn_t)(ppu_context*);
fn_t g_orig[LV2_SYSCALL_MAX];
std::atomic<int> g_window{ 0 };          /* > 0: tracing the main thread */
LARGE_INTEGER g_t0, g_qpf;
uint64_t g_main_tid = 1;
int g_lines = 0;

int64_t traced(int n, ppu_context* ctx)
{
    if (g_window <= 0 || ctx->thread_id != g_main_tid || g_lines >= 400) return g_orig[n](ctx);
    LARGE_INTEGER a, b; QueryPerformanceCounter(&a);
    uint64_t r3 = ctx->gpr[3];
    int64_t r = g_orig[n](ctx);
    QueryPerformanceCounter(&b);
    g_lines++;
    logline("T %8.3f +%7.3f sc %-4d r3 %08llX -> %lld  %s",
            1000.0 * (double)(a.QuadPart - g_t0.QuadPart) / (double)g_qpf.QuadPart,
            1000.0 * (double)(b.QuadPart - a.QuadPart) / (double)g_qpf.QuadPart,
            n, (unsigned long long)r3, (long long)r, guest_backtrace(4).c_str());
    return r;
}

template <int N> int64_t w(ppu_context* ctx) { return traced(N, ctx); }
template <int... Ns> void install_all(std::integer_sequence<int, Ns...>)
{
    fn_t table[] = { &w<Ns>... };
    for (int i = 0; i < LV2_SYSCALL_MAX; i++) {
        g_orig[i] = g_lv2_syscalls.handlers[i];
        if (g_orig[i]) g_lv2_syscalls.handlers[i] = table[i];
    }
}
} // namespace

void trace_install()
{
    static bool done = false;
    if (done) return;
    done = true;
    QueryPerformanceFrequency(&g_qpf);
    install_all(std::make_integer_sequence<int, LV2_SYSCALL_MAX>{});
    note("syscall timeline tracer installed (%d entries)", LV2_SYSCALL_MAX);
}

void trace_frame(const char* tag)
{
    QueryPerformanceCounter(&g_t0);
    g_lines = 0;
    logline("T --- %s ---", tag);
    g_window = 1;
}

void trace_stop(const char* tag)
{
    if (g_window <= 0) return;
    LARGE_INTEGER b; QueryPerformanceCounter(&b);
    g_window = 0;
    logline("T --- %s end at %.3f ms, %d syscalls ---", tag,
            1000.0 * (double)(b.QuadPart - g_t0.QuadPart) / (double)g_qpf.QuadPart, g_lines);
}

} // namespace rb
