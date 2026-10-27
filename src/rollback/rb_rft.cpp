/*
 * Access tracer (diagnostics): who READS (and writes) a few guest bytes.
 *
 * T5_RB_RFT=addr:len (hex) names the bytes, T5_RB_RFT_NET=from:frames the live
 * frames of the netplay loop the trace covers. Their page is made
 * PAGE_NOACCESS; every access to it faults into our vectored handler, which
 * records the accessing guest function (with its caller chain) when the
 * access falls inside the named bytes, opens the page for that one
 * instruction (single step) and closes it again. Host code that touches the
 * page (the runtime, the rollback state's own copies) shows up as "host".
 * Results go to the game log and rb_frames.log ("R ..." lines). The page is
 * hot (pad blocks, fight state), so this costs a lot while armed: tests only.
 */
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include "../platform/t5_win.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <atomic>
#include <map>
#include <string>
#include <vector>
#include <algorithm>

#include "rb.h"

extern "C" uint8_t* vm_base;

namespace rb {

#if defined(_WIN32)   /* x86 trap flag + 4 KB page protection: Windows only (docs/MACOS.md) */
namespace {
uint32_t g_ea = 0, g_len = 0, g_page = 0;
std::atomic<bool> g_on{ false };
__declspec(thread) uintptr_t t_reclose = 0;
CRITICAL_SECTION g_cs;
std::map<std::string, int> g_who;
uint64_t g_faults = 0;

LONG CALLBACK veh(EXCEPTION_POINTERS* ep)
{
    const EXCEPTION_RECORD* er = ep->ExceptionRecord;
    if (er->ExceptionCode == EXCEPTION_SINGLE_STEP && t_reclose) {
        DWORD old;
        if (g_on) VirtualProtect((void*)t_reclose, 0x1000, PAGE_NOACCESS, &old);
        t_reclose = 0;
        ep->ContextRecord->EFlags &= ~0x100u;
        return EXCEPTION_CONTINUE_EXECUTION;
    }
    if (!g_on || er->ExceptionCode != EXCEPTION_ACCESS_VIOLATION || er->NumberParameters < 2) return EXCEPTION_CONTINUE_SEARCH;
    const uintptr_t a = (uintptr_t)er->ExceptionInformation[1];
    if (a < (uintptr_t)vm_base + g_page || a >= (uintptr_t)vm_base + g_page + 0x1000) return EXCEPTION_CONTINUE_SEARCH;
    const uint32_t ea = (uint32_t)(a - (uintptr_t)vm_base);
    DWORD old;
    VirtualProtect(vm_base + g_page, 0x1000, PAGE_READWRITE, &old);
    t_reclose = (uintptr_t)(vm_base + g_page);
    ep->ContextRecord->EFlags |= 0x100u;
    /* a multi-byte access starting below the range still touches it */
    if (ea + 16 > g_ea && ea < g_ea + g_len) {
        uint32_t off = 0;
        const uint32_t top = guest_of_host((uintptr_t)ep->ContextRecord->Rip, &off);
        char t[64];
        snprintf(t, sizeof t, "%s %08X %s%06X+%X | ", er->ExceptionInformation[0] == 1 ? "W" : "R", ea,
                 GetCurrentThreadId() == 0 ? "" : "", top, off);
        std::string k = t;
        k += top ? guest_backtrace(8) : std::string("host");
        EnterCriticalSection(&g_cs);
        g_who[k]++;
        g_faults++;
        LeaveCriticalSection(&g_cs);
    }
    return EXCEPTION_CONTINUE_EXECUTION;
}
} // namespace

bool rft_install()
{
    static int done = -1;
    if (done >= 0) return done != 0;
    done = 0;
    const char* e = getenv("T5_RB_RFT");
    if (!e || !*e) return false;
    unsigned a = 0, l = 0;
    if (sscanf(e, "%x:%x", &a, &l) != 2 || !l) return false;
    g_ea = a; g_len = l; g_page = a & ~0xFFFu;
    InitializeCriticalSection(&g_cs);
    AddVectoredExceptionHandler(1, veh);
    note("access tracer: %08X+%X (page %08X) -- reads and writes, tests only", g_ea, g_len, g_page);
    done = 1;
    return true;
}

void rft_arm()
{
    if (g_on || !g_page) return;
    g_who.clear(); g_faults = 0;
    g_on = true;
    DWORD old;
    VirtualProtect(vm_base + g_page, 0x1000, PAGE_NOACCESS, &old);
}

void rft_disarm(const char* tag)
{
    if (!g_on) return;
    g_on = false;
    DWORD old;
    VirtualProtect(vm_base + g_page, 0x1000, PAGE_READWRITE, &old);
    note("access trace %s: %llu accesses to %08X+%X, %zu distinct (access, word, function, chain)", tag,
         (unsigned long long)g_faults, g_ea, g_len, g_who.size());
    std::vector<std::pair<int, std::string>> v;
    for (auto& kv : g_who) v.push_back({ kv.second, kv.first });
    std::sort(v.begin(), v.end(), [](auto& x, auto& y) { return x.first > y.first; });
    for (auto& p : v) { logline("R %s x%d %s", tag, p.first, p.second.c_str()); note("access (%s) x%d: %s", tag, p.first, p.second.c_str()); }
}

#else
/* The same single-step trap would need the write watch's fault handler on 16 KB
 * pages (t5_plat_posix.c); tests only, never in a match. */
bool rft_install() { const char* e = getenv("T5_RB_RFT"); if (e && *e) note("access tracer: Windows only -- off"); return false; }
void rft_arm() {}
void rft_disarm(const char* tag) { (void)tag; }
#endif

} // namespace rb
