/*
 * Stack-sampling profiler for the main guest thread: while a window is open, a
 * watcher thread suspends the main thread every ~150 us, captures its context
 * and unwinds the host stack (RtlVirtualUnwind: the exe carries unwind info
 * for every function, lifted or runtime). Each host frame that lies in a
 * lifted function is mapped to its guest address, so a sample becomes the
 * guest call chain at that instant. At the end of the window:
 *   - inclusive counts (how many samples had the function on the stack) and
 *     self counts (innermost lifted frame) go to the frame log ("S" lines);
 *   - every distinct chain goes to rb_prof_<tag>.txt as folded stacks
 *     ("outer;...;inner count", flame-graph input) for offline analysis.
 * Samples whose innermost frame is runtime code (vm_write32, vmx_*, a syscall)
 * are charged to the nearest lifted caller, and the runtime RVA is counted
 * separately ("S rt" lines; resolve against t5dr.map).
 */
#define WIN32_LEAN_AND_MEAN
#include "../platform/t5_win.h"
#include <stdio.h>
#include <string.h>
#include <atomic>
#include <vector>
#include <algorithm>
#include <map>
#include <string>

#include "rb.h"

namespace rb {

#if defined(_WIN32)   /* SEH, RtlVirtualUnwind, SuspendThread: x64 Windows only (docs/MACOS.md) */
namespace {
std::atomic<int> g_on{ 0 };
HANDLE g_target = nullptr, g_thread = nullptr;
constexpr int kDepth = 384;
std::vector<uintptr_t> g_rips;     /* kDepth slots per sample, 0-terminated */
size_t g_samples = 0;
int g_interval_us = 150;

/* Unwind the suspended target from its context. Reads of a bad stack slot
 * (a thread caught between prologue instructions) are caught by SEH. */
int walk(CONTEXT& c, uintptr_t* out)
{
    int n = 0;
    __try {
        while (n < kDepth) {
            DWORD64 base = 0;
            PRUNTIME_FUNCTION rf = RtlLookupFunctionEntry(c.Rip, &base, nullptr);
            /* record the containing function's entry (exact match against the
             * lifted function table later), the raw pc for the innermost frame */
            out[n++] = (rf && n > 0) ? (uintptr_t)(base + rf->BeginAddress) : (uintptr_t)c.Rip;
            if (!rf) {   /* leaf function: the return address is at the top of the stack */
                c.Rip = *(DWORD64*)(uintptr_t)c.Rsp;
                c.Rsp += 8;
            } else {
                PVOID handler = nullptr; DWORD64 est = 0;
                RtlVirtualUnwind(UNW_FLAG_NHANDLER, base, c.Rip, rf, &c, &handler, &est, nullptr);
            }
            if (!c.Rip) break;
        }
    } __except (EXCEPTION_EXECUTE_HANDLER) { }
    return n;
}

DWORD WINAPI sampler(LPVOID)
{
    CONTEXT c;
    LARGE_INTEGER f; QueryPerformanceFrequency(&f);
    while (g_on) {
        if (g_rips.size() + kDepth + 1 > g_rips.capacity()) break;
        if (SuspendThread(g_target) != (DWORD)-1) {
            memset(&c, 0, sizeof c);
            c.ContextFlags = CONTEXT_FULL;
            if (GetThreadContext(g_target, &c)) {
                size_t at = g_rips.size();
                g_rips.resize(at + kDepth + 1, 0);
                int n = walk(c, g_rips.data() + at);
                g_rips.resize(at + n + 1);
                g_rips[at + n] = 0;
                g_samples++;
            }
            ResumeThread(g_target);
        }
        LARGE_INTEGER a, b; QueryPerformanceCounter(&a);
        do { YieldProcessor(); QueryPerformanceCounter(&b); } while ((b.QuadPart - a.QuadPart) * 1000000 / f.QuadPart < g_interval_us);
    }
    return 0;
}

/* cumulative over the windows since the last report */
std::map<uint32_t, int> g_incl, g_self;
std::map<uintptr_t, int> g_rt;
std::map<std::string, int> g_folded;
int g_total = 0;
} // namespace

void sample_start()
{
    if (g_on) return;
    if (const char* e = getenv("T5_RB_SAMPLE_US")) g_interval_us = atoi(e) > 10 ? atoi(e) : 10;
    g_rips.clear();
    g_rips.reserve(1u << 24);   /* 16M slots = 128 MB max per window */
    g_samples = 0;
    g_target = OpenThread(THREAD_SUSPEND_RESUME | THREAD_GET_CONTEXT | THREAD_QUERY_INFORMATION, FALSE, GetCurrentThreadId());
    g_on = 1;
    g_thread = CreateThread(nullptr, 0, sampler, nullptr, 0, nullptr);
}

void sample_stop(const char* tag)
{
    if (!g_on) return;
    g_on = 0;
    WaitForSingleObject(g_thread, 5000);
    CloseHandle(g_thread); CloseHandle(g_target);
    const uintptr_t base = (uintptr_t)GetModuleHandleA(nullptr);
    std::vector<uint32_t> chain;
    size_t i = 0;
    while (i < g_rips.size()) {
        chain.clear();
        uintptr_t inner_rt = 0;
        bool first = true;
        for (; i < g_rips.size() && g_rips[i]; i++) {
            uint32_t off;
            /* innermost: a raw pc (containing function); outer frames: exact function entries */
            uint32_t g = first ? guest_of_host(g_rips[i], &off) : guest_at_host(g_rips[i]);
            if (first && g) {   /* only trust the raw pc when it lies in a lifted function proper */
                DWORD64 b = 0; PRUNTIME_FUNCTION rf = RtlLookupFunctionEntry((DWORD64)g_rips[i], &b, nullptr);
                if (rf && guest_at_host((uintptr_t)(b + rf->BeginAddress)) != g) g = 0;
            }
            if (g) { if (chain.empty() || chain.back() != g) chain.push_back(g); }
            else if (first && g_rips[i] >= base && g_rips[i] < base + (512u << 20)) inner_rt = (g_rips[i] - base) & ~(uintptr_t)0x3F;
            first = false;
        }
        i++;   /* the terminator */
        g_total++;
        if (chain.empty()) { g_rt[inner_rt ? inner_rt : 1]++; continue; }
        g_self[chain[0]]++;
        if (inner_rt) g_rt[inner_rt]++;
        std::vector<uint32_t> d(chain); std::sort(d.begin(), d.end()); d.erase(std::unique(d.begin(), d.end()), d.end());
        for (uint32_t g : d) g_incl[g]++;
        std::string key;
        char t[12];
        for (size_t k = chain.size(); k-- > 0;) { snprintf(t, sizeof t, "%06X;", chain[k]); key += t; }
        g_folded[key]++;
    }
    note("%s: %zu samples this window, %d in total (%.1f%% of this window's time in the stack walk cost is excluded from cycle counts)",
         tag, g_samples, g_total, 0.0);
    auto top = [&](const char* what, std::map<uint32_t, int>& m, int n) {
        std::vector<std::pair<int, uint32_t>> v;
        for (auto& kv : m) v.push_back({ kv.second, kv.first });
        std::sort(v.begin(), v.end(), [](auto& a, auto& b) { return a.first > b.first; });
        logline("S --- %s %s (of %d samples) ---", tag, what, g_total);
        for (size_t k = 0; k < v.size() && (int)k < n; k++)
            logline("S %s %08X %d %.1f%%", what, v[k].second, v[k].first, 100.0 * v[k].first / g_total);
    };
    top("incl", g_incl, 60);
    top("self", g_self, 40);
    {
        std::vector<std::pair<int, uintptr_t>> v;
        for (auto& kv : g_rt) v.push_back({ kv.second, kv.first });
        std::sort(v.begin(), v.end(), [](auto& a, auto& b) { return a.first > b.first; });
        for (size_t k = 0; k < v.size() && k < 20; k++)
            logline("S rt rva %08llX %d %.1f%%", (unsigned long long)v[k].second, v[k].first, 100.0 * v[k].first / g_total);
    }
    char fn[256]; snprintf(fn, sizeof fn, "rb_prof_%s.txt", tag);
    if (FILE* fp = fopen(fn, "w")) {
        for (auto& kv : g_folded) fprintf(fp, "%s %d\n", kv.first.c_str(), kv.second);
        fclose(fp);
    }
    g_rips.clear(); g_rips.shrink_to_fit();
}

void sample_reset() { g_incl.clear(); g_self.clear(); g_rt.clear(); g_folded.clear(); g_total = 0; }

#else
/* A port would suspend the thread with thread_suspend/thread_get_state (Mach)
 * and walk frame pointers; nothing in a match needs it. */
void sample_start() { static bool told = false; if (!told) { told = true; note("stack sampler: Windows only -- off"); } }
void sample_stop(const char* tag) { (void)tag; }
void sample_reset() {}
#endif

} // namespace rb
