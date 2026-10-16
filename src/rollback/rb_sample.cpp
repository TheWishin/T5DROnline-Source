/*
 * RIP sampler for the main guest thread: while a window is open, a watcher
 * thread suspends the main thread every ~0.3 ms and records its instruction
 * pointer. At the end the addresses are logged relative to the module base,
 * for resolution against the linker map (t5dr.map: lifted functions and the
 * runtime alike). Used to see where a re-simulated frame spends its time.
 */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdio.h>
#include <atomic>
#include <vector>
#include <algorithm>
#include <map>

#include "rb.h"

namespace rb {

namespace {
std::atomic<int> g_on{ 0 };
HANDLE g_target = nullptr, g_thread = nullptr;
std::vector<uintptr_t> g_rips;

DWORD WINAPI sampler(LPVOID)
{
    CONTEXT c;
    while (g_on) {
        if (SuspendThread(g_target) != (DWORD)-1) {
            c.ContextFlags = CONTEXT_CONTROL;
            if (GetThreadContext(g_target, &c)) g_rips.push_back((uintptr_t)c.Rip);
            ResumeThread(g_target);
        }
        LARGE_INTEGER f, a, b; QueryPerformanceFrequency(&f); QueryPerformanceCounter(&a);
        do { YieldProcessor(); QueryPerformanceCounter(&b); } while ((b.QuadPart - a.QuadPart) * 1000000 / f.QuadPart < 300);
    }
    return 0;
}
} // namespace

void sample_start()
{
    if (g_on) return;
    g_rips.clear();
    g_rips.reserve(1 << 16);
    g_target = OpenThread(THREAD_SUSPEND_RESUME | THREAD_GET_CONTEXT | THREAD_QUERY_INFORMATION, FALSE, GetCurrentThreadId());
    g_on = 1;
    g_thread = CreateThread(nullptr, 0, sampler, nullptr, 0, nullptr);
}

void sample_stop(const char* tag)
{
    if (!g_on) return;
    g_on = 0;
    WaitForSingleObject(g_thread, 2000);
    CloseHandle(g_thread); CloseHandle(g_target);
    const uintptr_t base = (uintptr_t)GetModuleHandleA(nullptr);
    std::map<uintptr_t, int> hist;
    int outside = 0;
    for (uintptr_t r : g_rips) {
        if (r >= base && r < base + (512u << 20)) hist[(r - base) & ~(uintptr_t)0x3F]++;   /* 64-byte buckets */
        else outside++;
    }
    std::vector<std::pair<int, uintptr_t>> v;
    for (auto& kv : hist) v.push_back({ kv.second, kv.first });
    std::sort(v.begin(), v.end(), [](auto& a, auto& b) { return a.first > b.first; });
    note("%s: %zu samples, %d outside the exe (system DLLs: waits/sleeps)", tag, g_rips.size(), outside);
    for (size_t i = 0; i < v.size() && i < 25; i++)
        logline("S %s rva %08llX count %d", tag, (unsigned long long)v[i].second, v[i].first);
}

} // namespace rb
