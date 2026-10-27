/*
 * Kernel-side state across rollbacks (diagnostics): T5_RB_KTRACE=1|2|3.
 *
 * A restore puts guest memory back; it does not put back what the host keeps
 * for the guest -- open files (the cellFs descriptor table), lv2 objects
 * (semaphores and their counts, mutexes, condition variables, event queues),
 * memory handed out by sys_memory. Whatever a re-simulated frame does there a
 * second time, or what its first run did that the restore forgot, survives.
 * docs/ROLLBACK.md section 30 found one (the async reader's completion token);
 * this tracer looks for the rest.
 *
 * rb_ktrace_<pid>.log (working directory), one line per event, flushed at once:
 *   <ms> f<frame> <L|R> t<guest tid> <event> ...
 * frame = the logical frame running (sim_frame), L/R = live or re-simulating
 * (bypass on: the main thread re-runs frames; a side thread's event is tagged
 * with the main thread's state at that moment).
 *   1: cellFs open/close (the import stubs: every file the title opens), the
 *      title's own file object open/close (0x38C90C / 0x38C798), lv2 object
 *      creates/destroys, sys_memory allocate/free, rollbacks and sessions;
 *   2: also every request put into the file manager's list (who, which slot,
 *      which id) and every call of a request's process method by its thread;
 *   3: also, per boundary, the main thread's wake/take syscalls of the frame
 *      that just ran (semaphore wait/trywait/post, cond signal, event port
 *      send, event queue receive, event flag set) -- what a re-simulated
 *      frame does to the other threads, against what its live run did.
 */
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include "../platform/t5_win.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdarg.h>
#include <atomic>
#include <string>
#include <utility>

#include "sys_ppu_thread.h"
#include "lv2_syscall_table.h"
#include "rb.h"
#include "rb_detour.h"

extern "C" uint8_t* vm_base;
extern "C" void ps3_indirect_call_direct(ppu_context* ctx, uint32_t target);

namespace rb {

namespace {
int g_level = 0;
uint64_t g_main = 1;   /* the main thread's guest id */
FILE* g_kt = nullptr;
CRITICAL_SECTION g_kt_cs;
LARGE_INTEGER g_qpf, g_t0;

double now_ms() { LARGE_INTEGER t; QueryPerformanceCounter(&t); return 1000.0 * (double)(t.QuadPart - g_t0.QuadPart) / (double)g_qpf.QuadPart; }

void ktline(uint64_t tid, const char* fmt, ...)
{
    if (!g_kt) return;
    char buf[1024];
    va_list ap; va_start(ap, fmt); vsnprintf(buf, sizeof buf, fmt, ap); va_end(ap);
    EnterCriticalSection(&g_kt_cs);
    fprintf(g_kt, "%10.2f f%u %c t%llu %s\n", now_ms(), sim_frame(), bypass_on() ? 'R' : 'L', (unsigned long long)tid, buf);
    fflush(g_kt);
    LeaveCriticalSection(&g_kt_cs);
}

std::string guest_str(uint32_t ea, size_t max = 96)
{
    std::string s;
    if (!ea) return s;
    for (size_t i = 0; i < max; i++) { const char c = (char)vm_base[ea + i]; if (!c) break; s += c; }
    const size_t slash = s.rfind('/');
    return slash == std::string::npos ? s : s.substr(slash + 1);
}

/* ---- the title's file calls (entry detours) ---- */
constexpr uint32_t kStubFsOpen = 0x3C54A0, kStubFsClose = 0x3C5420;   /* cellFsOpen / cellFsClose import stubs */
constexpr uint32_t kGameOpen = 0x38C90C, kGameClose = 0x38C798;       /* the title's file device: open (stat, cellFsOpen, file object) / close */
GuestFn o_fs_open = nullptr, o_fs_close = nullptr, o_g_open = nullptr, o_g_close = nullptr;

void h_fs_open(ppu_context* ctx)
{
    const uint32_t path = (uint32_t)ctx->gpr[3], flags = (uint32_t)ctx->gpr[4], fdp = (uint32_t)ctx->gpr[5];
    const uint64_t tid = ctx->thread_id;
    o_fs_open(ctx);
    const int32_t r = (int32_t)ctx->gpr[3];
    ktline(tid, "FSOPEN %s flags %X -> %d fd %d | %s", guest_str(path).c_str(), flags, r, (r == 0 && fdp) ? (int)rd32(fdp) : -1,
           guest_backtrace(6).c_str());
}
void h_fs_close(ppu_context* ctx)
{
    const int32_t fd = (int32_t)ctx->gpr[3];
    const uint64_t tid = ctx->thread_id;
    o_fs_close(ctx);
    ktline(tid, "FSCLOSE fd %d -> %d | %s", fd, (int32_t)ctx->gpr[3], guest_backtrace(6).c_str());
}
void h_g_open(ppu_context* ctx)
{
    const uint64_t a3 = ctx->gpr[3], a4 = ctx->gpr[4], a5 = ctx->gpr[5], a6 = ctx->gpr[6], a7 = ctx->gpr[7];
    const uint64_t tid = ctx->thread_id;
    o_g_open(ctx);
    ktline(tid, "GOPEN dev %08llX %08llX %llX %llX %llX -> %08llX", a3 & 0xFFFFFFFF, a4 & 0xFFFFFFFF, a5, a6, a7, ctx->gpr[3] & 0xFFFFFFFF);
}
void h_g_close(ppu_context* ctx)
{
    const uint32_t dev = (uint32_t)ctx->gpr[3], obj = (uint32_t)ctx->gpr[4];
    const uint32_t h = obj ? rd32(obj + 4) : 0, fd = obj ? rd32(obj + 0x18) : 0;
    const uint64_t tid = ctx->thread_id;
    o_g_close(ctx);
    ktline(tid, "GCLOSE dev %08X obj %08X handle %08X fd %d -> %08llX | %s", dev, obj, h, (int)fd, ctx->gpr[3] & 0xFFFFFFFF, guest_backtrace(6).c_str());
}

/* level 2: reads and seeks, and the loader's inflate (the "decoder" thread's
 * job 0x1EB58C calls 0x671E4: r3 dst, r4 compressed size, r5 size, r6 src) */
constexpr uint32_t kStubFsRead = 0x3C5460, kStubFsLseek = 0x3C5500, kInflate = 0x671E4;
GuestFn o_fs_read = nullptr, o_fs_lseek = nullptr, o_inflate = nullptr;
uint32_t sum_guest(uint32_t ea, uint32_t n)   /* a cheap fingerprint of guest bytes */
{
    uint32_t h = 2166136261u;
    for (uint32_t i = 0; i < n && i < 0x100000; i += 61) { h ^= vm_base[ea + i]; h *= 16777619u; }
    return h;
}
void h_fs_read(ppu_context* ctx)
{
    const int32_t fd = (int32_t)ctx->gpr[3];
    const uint32_t buf = (uint32_t)ctx->gpr[4], size = (uint32_t)ctx->gpr[5], np = (uint32_t)ctx->gpr[6];
    const uint64_t tid = ctx->thread_id;
    o_fs_read(ctx);
    const uint32_t n = np ? rd32(np + 4) : 0;   /* u64 nread */
    if (g_level >= 2) ktline(tid, "FSREAD fd %d buf %08X size %X -> %d n %X sum %08X", fd, buf, size, (int)(int32_t)ctx->gpr[3], n, sum_guest(buf, n));
}
void h_fs_lseek(ppu_context* ctx)
{
    const int32_t fd = (int32_t)ctx->gpr[3];
    const int64_t off = (int64_t)ctx->gpr[4]; const uint32_t wh = (uint32_t)ctx->gpr[5], pp = (uint32_t)ctx->gpr[6];
    const uint64_t tid = ctx->thread_id;
    o_fs_lseek(ctx);
    if (g_level >= 2) ktline(tid, "FSSEEK fd %d off %llX whence %u -> %d pos %llX", fd, (long long)off, wh, (int)(int32_t)ctx->gpr[3], pp ? (unsigned long long)rd64(pp) : 0ull);
}
void h_inflate(ppu_context* ctx)
{
    const uint64_t a3 = ctx->gpr[3], a4 = ctx->gpr[4], a5 = ctx->gpr[5], a6 = ctx->gpr[6];
    const uint64_t tid = ctx->thread_id;
    const uint32_t src_sum = sum_guest((uint32_t)a6, (uint32_t)a4);
    o_inflate(ctx);
    if (g_level >= 2 || (int32_t)ctx->gpr[3] != 1)
        ktline(tid, "INFLATE dst %08llX csize %llX size %llX src %08llX srcsum %08X -> %lld | %s", a3 & 0xFFFFFFFF, a4 & 0xFFFFFFFF, a5 & 0xFFFFFFFF, a6 & 0xFFFFFFFF, src_sum,
               (long long)(int64_t)ctx->gpr[3], guest_backtrace(4).c_str());
}

/* ---- the NU::File request manager (thread "NU::File::RequestManager", object
 * 0x10751A00, its thread object +0x28; the class is shared with the two draw request managers): every
 * request put into its list (0x374438: lock, insert by priority, id = +0x48++,
 * post the manager's semaphore +0x40) and every call of a request's process
 * method by the manager's loop (0x37408C: vtable slot +8 at 0x37414C; 1 =
 * call again) ---- */
constexpr uint32_t kFileMgr = 0x10751A00, kEnqueue = 0x374438, kProcRet = 0x374150;
GuestFn o_enqueue = nullptr;
void h_enqueue(ppu_context* ctx)
{
    const uint32_t mgr = (uint32_t)ctx->gpr[3], req = (uint32_t)ctx->gpr[4];
    const uint64_t tid = ctx->thread_id;
    const uint32_t vt = req ? rd32(req) : 0, pri = req ? rd32(req + 8) : 0;
    o_enqueue(ctx);
    if (mgr == kFileMgr && g_level >= 2)
        ktline(tid, "ENQ req %08X vt %08X pri %d -> id %d | %s", req, vt, (int)pri, (int)(int32_t)ctx->gpr[3], guest_backtrace(6).c_str());
}
/* the C library heap: malloc 0x3AB2C8(size), free 0x3AAA40(ptr). The sound
 * library calls them through callbacks (0x10088F0C/F10, 0x10088F88/F8C):
 * indirect calls, logged here at level 2 (rb_sndheap.cpp routes them). */
constexpr uint32_t kMalloc = 0x3AB2C8, kFree = 0x3AAA40;
} // namespace
bool ktrace_icall(ppu_context* ctx, uint32_t target)
{
    if (g_kt && g_level >= 2 && (target == kMalloc || target == kFree)) {
        const uint32_t a3 = (uint32_t)ctx->gpr[3], lr = (uint32_t)ctx->lr;
        const uint64_t tid = ctx->thread_id;
        ps3_indirect_call_direct(ctx, target);
        if (target == kMalloc) ktline(tid, "SALLOC size %X -> %08X lr %06X", a3, (uint32_t)ctx->gpr[3], lr);
        else ktline(tid, "SFREE %08X lr %06X", a3, lr);
        return true;
    }
    if (!g_kt || g_level < 2 || ctx->lr != kProcRet || ctx->thread_id != 2) return false;
    const uint32_t req = (uint32_t)ctx->gpr[3];
    const uint32_t vt = req ? rd32(req) : 0, id = req ? rd32(req + 4) : 0;
    ps3_indirect_call_direct(ctx, target);
    ktline(ctx->thread_id, "PROC req %08X vt %08X id %d fn %06X -> %d", req, vt, (int)id, target, (int)(int32_t)ctx->gpr[3]);
    return true;
}
namespace {

/* ---- lv2 syscalls ---- */
typedef int64_t (*fn_t)(ppu_context*);
fn_t g_orig[LV2_SYSCALL_MAX];

struct ScInfo { int n; const char* name; int kind; };   /* kind 0: create (out id at *r3), 1: destroy/other (r3 = id), 2: wake/take (level 2, main thread, per frame) */
const ScInfo kSc[] = {
    { 90, "sem_create", 0 }, { 91, "sem_destroy", 1 },
    { 100, "mutex_create", 0 }, { 101, "mutex_destroy", 1 },
    { 105, "cond_create", 0 }, { 106, "cond_destroy", 1 },
    { 128, "eq_create", 0 }, { 129, "eq_destroy", 1 },
    { 134, "eport_create", 0 }, { 135, "eport_destroy", 1 },
    { 82, "eflag_create", 0 }, { 83, "eflag_destroy", 1 },
    { 95, "lwmutex_create", 0 }, { 96, "lwmutex_destroy", 1 },
    { 111, "lwcond_create", 0 }, { 112, "lwcond_destroy", 1 },
    { 120, "rwlock_create", 0 }, { 121, "rwlock_destroy", 1 },
    { 70, "timer_create", 0 }, { 71, "timer_destroy", 1 },
    { 52, "thread_create", 0 }, { 41, "thread_exit", 1 },
    { 348, "mem_alloc", 3 }, { 349, "mem_free", 1 },
    { 92, "W", 2 }, { 93, "T", 2 }, { 94, "P", 2 }, { 108, "S", 2 }, { 109, "SA", 2 }, { 110, "ST", 2 },
    { 115, "LS", 2 }, { 116, "LSA", 2 }, { 138, "E", 2 }, { 130, "Q", 2 }, { 131, "TQ", 2 }, { 87, "F", 2 },
};
const ScInfo* g_info[LV2_SYSCALL_MAX];

/* level 2: the main thread's wake/take syscalls of the frame running */
std::string g_frame_sig;

int64_t traced(int n, ppu_context* ctx)
{
    const ScInfo* in = g_info[n];
    const uint64_t a3 = ctx->gpr[3], a4 = ctx->gpr[4], a5 = ctx->gpr[5];
    const uint64_t tid = ctx->thread_id;
    if (in->kind == 2) {
        const int64_t r = g_orig[n](ctx);
        if (g_level >= 3 && tid == g_main) {
            char t[40]; snprintf(t, sizeof t, " %s%llu%s", in->name, (unsigned long long)(a3 & 0xFFFFFFFF), r ? "!" : "");
            if (g_frame_sig.size() < 4000) g_frame_sig += t;
        }
        return r;
    }
    const int64_t r = g_orig[n](ctx);
    if (in->kind == 0) ktline(tid, "%s -> %lld id %u | %s", in->name, (long long)r, (r == 0 && (uint32_t)a3) ? rd32((uint32_t)a3) : 0u, guest_backtrace(4).c_str());
    else if (in->kind == 3) ktline(tid, "%s size %llX -> %lld addr %08X | %s", in->name, a3, (long long)r, (r == 0 && (uint32_t)a5) ? rd32((uint32_t)a5) : 0u, guest_backtrace(4).c_str());
    else ktline(tid, "%s %llX %llX -> %lld | %s", in->name, a3, a4, (long long)r, guest_backtrace(4).c_str());
    return r;
}
template <int N> int64_t w(ppu_context* ctx) { return traced(N, ctx); }
template <int... Ns> void install_all(std::integer_sequence<int, Ns...>)
{
    fn_t table[] = { &w<Ns>... };
    for (const ScInfo& s : kSc) {
        if (!g_lv2_syscalls.handlers[s.n] || (s.kind == 2 && g_level < 3)) continue;
        g_info[s.n] = &s;
        g_orig[s.n] = g_lv2_syscalls.handlers[s.n];
        g_lv2_syscalls.handlers[s.n] = table[s.n];
    }
}
} // namespace

bool ktrace_on() { return g_kt != nullptr; }

void ktrace_install()
{
    static bool done = false;
    if (done) return;
    done = true;
    const char* e = getenv("T5_RB_KTRACE");
    if (!e || !*e || *e == '0') return;
    g_level = atoi(e);
    if (g_level < 1) g_level = 1;
    InitializeCriticalSection(&g_kt_cs);
    QueryPerformanceFrequency(&g_qpf); QueryPerformanceCounter(&g_t0);
    { char name[64]; snprintf(name, sizeof name, "rb_ktrace_%lu.log", (unsigned long)GetCurrentProcessId()); g_kt = fopen(name, "w"); }   /* per process: a restarted game must not overwrite the trace of the one that died */
    if (!g_kt) return;
    g_main = main_tid();
    int ok = 0;
    if (detour_ready()) {
        ok += detour(kStubFsOpen, h_fs_open, &o_fs_open);
        ok += detour(kStubFsClose, h_fs_close, &o_fs_close);
        ok += detour(kGameOpen, h_g_open, &o_g_open);
        ok += detour(kGameClose, h_g_close, &o_g_close);
        ok += detour(kEnqueue, h_enqueue, &o_enqueue);
        ok += detour(kStubFsRead, h_fs_read, &o_fs_read);
        ok += detour(kStubFsLseek, h_fs_lseek, &o_fs_lseek);
        ok += detour(kInflate, h_inflate, &o_inflate);
    }
    install_all(std::make_integer_sequence<int, LV2_SYSCALL_MAX>{});
    note("kernel-state trace (T5_RB_KTRACE=%d): %d of 8 file/loader detours, lv2 creates/destroys%s -> rb_ktrace_<pid>.log", g_level, ok,
         g_level >= 3 ? ", file requests, main-thread wake/take syscalls per frame" : g_level >= 2 ? ", file requests" : "");
}

void ktrace_note(const char* fmt, ...)
{
    if (!g_kt) return;
    char buf[512];
    va_list ap; va_start(ap, fmt); vsnprintf(buf, sizeof buf, fmt, ap); va_end(ap);
    ktline(g_main, "# %s", buf);
}

/* the boundary of frame f: the main thread's syscalls of the frame before it */
void ktrace_boundary(uint32_t f, bool resim)
{
    if (!g_kt || g_level < 3) return;
    if (!g_frame_sig.empty()) {
        EnterCriticalSection(&g_kt_cs);
        fprintf(g_kt, "%10.2f B %u %c%s\n", now_ms(), f, resim ? 'R' : 'L', g_frame_sig.c_str());
        fflush(g_kt);
        LeaveCriticalSection(&g_kt_cs);
    }
    g_frame_sig.clear();
}

} // namespace rb
