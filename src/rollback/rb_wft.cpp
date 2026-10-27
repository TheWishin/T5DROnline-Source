/*
 * Write-fault tracer: who writes a guest region, with the guest call chain.
 *
 * T5_RB_WFT=addr:len,addr:len,... (hex) names the regions; wft_arm() makes
 * their pages read-only for one frame. The first write to each page faults
 * into our vectored handler (installed FIRST, ahead of the runtime's commit
 * handler), which records the writer's lifted call chain, makes the page
 * writable again and resumes the faulting store. One fault per page per
 * window, so a frame costs at most a few hundred faults. Used to find the
 * complete set of draw-packet writers (docs/ROLLBACK.md section 6).
 */
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include "../platform/t5_win.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <atomic>
#include <vector>
#include <map>
#include <string>
#include <algorithm>

#include "sys_ppu_thread.h"
#include "rb.h"

extern "C" uint8_t* vm_base;

namespace rb {

#if defined(_WIN32)   /* x86 trap flag + 4 KB page protection: Windows only (docs/MACOS.md) */
namespace {
struct R { uint32_t base, len; };
std::vector<R> g_ranges, g_active;        /* configured ranges; the ranges armed right now */
std::atomic<bool> g_armed{ false };
bool g_all = false;                          /* T5_RB_WFT_ALL=1: every write (single-step re-protect), not just the first per page */
uint32_t g_only_addr = 0;                    /* T5_RB_WFT_ADDR=hex: record only writes to this exact word (the page still traps) */
__declspec(thread) uintptr_t t_reprotect = 0;
std::map<std::string, int> g_who;          /* "func chain|page" -> faults */
std::map<uint32_t, int> g_pages;
bool g_addrs = false;
DWORD g_arm_tid = 0;                         /* the thread that armed the trace (the main thread, at a boundary) */
std::map<std::string, int> g_addr_who;     /* "thread func word" -> writes (T5_RB_WFT_ADDRS) */
const char* thread_name_of_host(DWORD host_tid)
{
    for (int i = 0; i < PPU_THREAD_MAX; i++)
        if (g_ppu_threads[i].state != PPU_THREAD_STATE_FREE && g_ppu_threads[i].host_tid == host_tid) return g_ppu_threads[i].name;
    return host_tid == g_arm_tid ? "main" : "?";
}
CRITICAL_SECTION g_cs;
int g_faults = 0;

bool in_ranges(uintptr_t addr, uint32_t* ea)
{
    if (addr < (uintptr_t)vm_base || addr >= (uintptr_t)vm_base + 0x100000000ull) return false;
    uint32_t a = (uint32_t)(addr - (uintptr_t)vm_base);
    for (const R& r : g_active) if (a >= r.base && a < r.base + r.len) { *ea = a; return true; }
    return false;
}

LONG CALLBACK veh(EXCEPTION_POINTERS* ep)
{
    const EXCEPTION_RECORD* er = ep->ExceptionRecord;
    if (er->ExceptionCode == EXCEPTION_SINGLE_STEP && t_reprotect) {
        /* the traced store has executed: protect its page again */
        DWORD old;
        if (g_armed) VirtualProtect((void*)t_reprotect, 0x1000, PAGE_READONLY, &old);
        t_reprotect = 0;
        ep->ContextRecord->EFlags &= ~0x100u;
        return EXCEPTION_CONTINUE_EXECUTION;
    }
    if (!g_armed) return EXCEPTION_CONTINUE_SEARCH;
    if (er->ExceptionCode != EXCEPTION_ACCESS_VIOLATION || er->NumberParameters < 2 || er->ExceptionInformation[0] != 1)
        return EXCEPTION_CONTINUE_SEARCH;
    uint32_t ea;
    if (!in_ranges((uintptr_t)er->ExceptionInformation[1], &ea)) return EXCEPTION_CONTINUE_SEARCH;
    DWORD old;
    VirtualProtect(vm_base + (ea & ~0xFFFu), 0x1000, PAGE_READWRITE, &old);
    if (g_all) { t_reprotect = (uintptr_t)(vm_base + (ea & ~0xFFFu)); ep->ContextRecord->EFlags |= 0x100u; }
    if (g_only_addr && (ea & ~3u) != g_only_addr) return EXCEPTION_CONTINUE_EXECUTION;
    /* the writer: innermost lifted function at the fault pc, then its callers */
    uint32_t off = 0;
    uint32_t top = guest_of_host((uintptr_t)ep->ContextRecord->Rip, &off);
    std::string chain;
    char t[32];
    snprintf(t, sizeof t, "tid%lu ", (unsigned long)GetCurrentThreadId()); chain = t;
    if (top) { snprintf(t, sizeof t, "%06X+%X", top, off); chain += t; }
    chain += "|";
    chain += guest_backtrace(10);
    EnterCriticalSection(&g_cs);
    g_faults++;
    snprintf(t, sizeof t, "|%08X", ea & ~0xFFFu);
    g_who[chain + t]++;
    g_pages[ea & ~0xFFFu]++;
    if (g_addrs) {   /* T5_RB_WFT_ADDRS=1: every written word, by guest thread and writing function */
        char k[96]; snprintf(k, sizeof k, "%s %06X %08X", thread_name_of_host(GetCurrentThreadId()), top, ea & ~3u);
        g_addr_who[k]++;
    }
    LeaveCriticalSection(&g_cs);
    return EXCEPTION_CONTINUE_EXECUTION;
}
} // namespace

void wft_install()
{
    const char* e = getenv("T5_RB_WFT");
    if (!e || !*e) return;
    if (const char* a = getenv("T5_RB_WFT_ALL")) g_all = *a == '1';
    if (const char* a = getenv("T5_RB_WFT_ADDR")) g_only_addr = (uint32_t)strtoul(a, nullptr, 16) & ~3u;
    if (const char* a = getenv("T5_RB_WFT_ADDRS")) g_addrs = *a == '1';
    if (!strcmp(e, "diff")) {   /* ranges come later, from the test's page diff */
        InitializeCriticalSection(&g_cs);
        AddVectoredExceptionHandler(1, veh);
        g_ranges.push_back({ 0, 0 });
        note("write-fault tracer: armed on the pages of the first resim diff (%s)", g_all ? "all writes" : "first write per page");
        return;
    }
    const char* q = e;
    while (*q) {
        char* z; uint32_t a = (uint32_t)strtoul(q, &z, 16); if (z == q || *z != ':') break; q = z + 1;
        uint32_t l = (uint32_t)strtoul(q, &z, 16); if (z == q) break; q = z;
        g_ranges.push_back({ a, l });
        while (*q == ',') q++;
    }
    if (g_ranges.empty()) return;
    InitializeCriticalSection(&g_cs);
    AddVectoredExceptionHandler(1, veh);
    note("write-fault tracer: %zu range(s) (%s)", g_ranges.size(), g_all ? "all writes" : "first write per page");
}

bool wft_enabled() { return !g_ranges.empty(); }

static void protect_active(DWORD from, DWORD to)
{
    for (const R& r : g_active) {
        uint32_t a = r.base;
        while (a < r.base + r.len) {
            MEMORY_BASIC_INFORMATION mi;
            if (!VirtualQuery(vm_base + a, &mi, sizeof mi)) break;
            uint32_t run = (uint32_t)std::min<uint64_t>((uint64_t)mi.RegionSize - ((vm_base + a) - (uint8_t*)mi.BaseAddress), r.base + r.len - a);
            if (mi.State == MEM_COMMIT && (mi.Protect & from)) { DWORD old; VirtualProtect(vm_base + a, run, to, &old); }
            a += run;
        }
    }
}

void wft_arm_pages(const uint32_t* pages, size_t n)
{
    if (g_ranges.empty() || g_armed) return;
    g_active.clear();
    for (size_t i = 0; i < n; i++) g_active.push_back({ pages[i] & ~0xFFFu, 0x1000 });
    g_who.clear(); g_pages.clear(); g_faults = 0;
    g_armed = true;
    protect_active(PAGE_READWRITE, PAGE_READONLY);
}

void wft_arm()
{
    if (g_ranges.empty() || g_armed || g_ranges[0].len == 0) return;
    g_active = g_ranges;
    g_arm_tid = GetCurrentThreadId();
    g_who.clear(); g_pages.clear(); g_faults = 0;
    g_armed = true;
    for (const R& r : g_active) {
        /* only committed pages can be protected; walk the region in committed runs */
        uint32_t a = r.base;
        while (a < r.base + r.len) {
            MEMORY_BASIC_INFORMATION mi;
            if (!VirtualQuery(vm_base + a, &mi, sizeof mi)) break;
            uint32_t run = (uint32_t)std::min<uint64_t>((uint64_t)mi.RegionSize - ((vm_base + a) - (uint8_t*)mi.BaseAddress), r.base + r.len - a);
            if (mi.State == MEM_COMMIT && (mi.Protect & PAGE_READWRITE)) { DWORD old; VirtualProtect(vm_base + a, run, PAGE_READONLY, &old); }
            a += run;
        }
    }
}

void wft_disarm(const char* tag)
{
    if (!g_armed) return;
    g_armed = false;
    protect_active(PAGE_READONLY, PAGE_READWRITE);
    note("write-fault trace %s: %d faults on %zu pages, %zu distinct writer chains", tag, g_faults, g_pages.size(), g_who.size());
    /* writers grouped by chain (pages merged) */
    std::map<std::string, std::pair<int, int>> by_chain;
    for (auto& kv : g_who) {
        std::string c = kv.first.substr(0, kv.first.rfind('|'));
        by_chain[c].first += kv.second; by_chain[c].second++;
    }
    std::vector<std::pair<int, std::string>> v;
    for (auto& kv : by_chain) v.push_back({ kv.second.second, kv.first + " pages " + std::to_string(kv.second.second) });
    std::sort(v.begin(), v.end(), [](auto& a, auto& b) { return a.first > b.first; });
    for (auto& e : v) logline("W %s %s", tag, e.second.c_str());
    if (v.size() <= 16) for (auto& e : v) note("writer (%s): %s", tag, e.second.c_str());   /* small traces also to the game log (flushed) */
    /* per page: writes by chain (one fault per page per window unless T5_RB_WFT_ALL) */
    for (auto& kv : g_who) logline("WP %s %s writes %d", tag, kv.first.c_str(), kv.second);
    for (auto& kv : g_addr_who) logline("WA %s %s %d", tag, kv.first.c_str(), kv.second);
    g_addr_who.clear();
}

#else
/* A port would trap on 16 KB pages on Apple Silicon and use the write watch's
 * fault handler (t5_plat_posix.c) -- the two cannot both protect a page. */
void wft_install() { const char* e = getenv("T5_RB_WFT"); if (e && *e) note("write-fault tracer: Windows only -- off"); }
bool wft_enabled() { return false; }
void wft_arm() {}
void wft_arm_pages(const uint32_t* pages, size_t n) { (void)pages; (void)n; }
void wft_disarm(const char* tag) { (void)tag; }
#endif

} // namespace rb
