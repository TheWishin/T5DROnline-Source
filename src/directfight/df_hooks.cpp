/*
 * T5DR "direct fight" (NPUB30009 v01.00) -- go straight into a VS fight
 * with given characters / stage, hold at a neutral point when it ends, and
 * accept the next fight without restarting (docs/DIRECTFIGHT.md).
 *
 * Everything is off unless T5_FIGHT or a T5_DF_* probe variable is set.
 *
 * Hooks (no ps3recomp changes): HLE overrides for cellPadInit (installs the
 * syscall hooks), cellPadGetInfo (two pads) and cellPadGetData (scripted
 * input by frame); lv2 syscall 92 (sys_semaphore_wait) on the main thread's
 * per-frame semaphore (id at 0x106D4A30) = the frame boundary.
 *
 * Probe / diagnostics:
 *   T5_DF_PROBE=1          log the mode manager's state every time it changes
 *   T5_DF_SCRIPT[2]        "frame:len:hexmask,..." or "@..." inline (np/rb packing:
 *                          DIGITAL1 low byte, DIGITAL2 high byte) for pad 0 / 1
 *   T5_DF_DUMP=f1,f2,...   dump data+bss and the committed heap at those frames
 *   T5_DF_DUMP_MODES=1     dump at every mode change (df_dump_m<n>_f<frame>_<addr>.bin)
 *   T5_DF_LOG=path         frame log (default df_frames.log in the cwd)
 */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <stdarg.h>
#include <atomic>
#include <string>
#include <vector>

#include "sys_ppu_thread.h"     /* ppu_context */
#include "lv2_syscall_table.h"  /* g_lv2_syscalls */
namespace rb {   /* src/rollback/rb_hooks.cpp (diagnostics: T5_DF_GUARD) */
uint32_t guest_of_host(uintptr_t host_pc, uint32_t* off);
std::string guest_backtrace(int max);
}
#include "df.h"

extern "C" {
void    ps3_hle_register_ctx(uint32_t nid, const char* name, void (*fn)(ppu_context*));
int32_t cellSysutilRegisterCallback(int32_t slot, uint32_t func, uint32_t userdata);
int32_t cellPadGetInfo(void* info_guest);
int32_t cellPadGetData(uint32_t port, void* data_guest);
uint64_t ppu_guest_call_ct(uint32_t code, uint32_t toc, uint64_t a0, uint64_t a1, uint64_t a2,
                           uint64_t a3, uint64_t a4, uint64_t a5, uint64_t a6, uint64_t a7);
void    t5_netplay_inject(int port, int on, unsigned buttons);   /* src/netplay/t5_hooks.cpp */
int     t5_netplay_enabled(void);
}
typedef int64_t (*df_lv2_fn)(ppu_context*);

namespace df {

/* ---- guest addresses (NPUB30009 v01.00) ---------------------------------- */
constexpr uint32_t kTOC          = 0x470540;
constexpr uint32_t kFrameSemPtr  = 0x106D4A30;   /* graphics object + 0x30: per-frame semaphore id */
constexpr uint32_t kFrameClock   = 0x106D4D88;   /* u64 frame clock */
constexpr uint32_t kVtModeMgr    = 0x10050054;   /* tcb_mode_manager_t vtable (heap object found by scan) */
constexpr uint32_t kModeReq      = 0x58;         /* mode manager + 0x58: {cur, next (0xE = none), prev}, param at +0x64 */
constexpr uint32_t kModeNone     = 0xE;
constexpr uint32_t kHeapBase     = 0x40000000, kHeapLen = 0x05F00000;
constexpr uint32_t kDataBase     = 0x10000000, kDataLen = 0x00770000;
constexpr uint32_t NID_cellSysutilRegisterCallback = 0x9D98AFA0;
constexpr uint32_t NID_cellPadGetInfo = 0x3AAAD464;
constexpr uint32_t NID_cellPadGetData = 0x8B72CDA1;

FILE* g_log = nullptr;
void note(const char* fmt, ...)
{
    char buf[1024];
    va_list ap; va_start(ap, fmt); vsnprintf(buf, sizeof buf, fmt, ap); va_end(ap);
    fprintf(stderr, "[df] %s\n", buf);
    fflush(stderr);
    if (g_log) { fprintf(g_log, "# %s\n", buf); fflush(g_log); }
}

bool committed(uint32_t ea)
{
    MEMORY_BASIC_INFORMATION mi;
    return VirtualQuery(vm_base + ea, &mi, sizeof mi) && mi.State == MEM_COMMIT &&
           !(mi.Protect & (PAGE_NOACCESS | PAGE_GUARD));
}

/* RTTI class name of a guest object (ILP32 vtable: typeinfo pointer at vtable-4). */
std::string class_name(uint32_t obj)
{
    if (!obj || !committed(obj)) return "?";
    uint32_t vt = rd32(obj);
    if (vt < 0x10050000 || vt >= 0x10760000) return "?";
    uint32_t ti = rd32(vt - 4);
    if (ti < 0x10000000 || ti >= 0x10760000) return "?";
    uint32_t np = rd32(ti + 4);
    if (np < 0x10000000 || np >= 0x10760000) return "?";
    const char* s = (const char*)(vm_base + np);
    while (*s >= '0' && *s <= '9') s++;
    return std::string(s, strnlen(s, 64));
}

/* ---- scripted / injected input ------------------------------------------ */
struct PadInput { uint16_t buttons; uint8_t lx, ly, rx, ry; };
const PadInput kNeutral = { 0, 128, 128, 128, 128 };
struct ScriptEvent { uint32_t frame, len; uint16_t mask; };
std::vector<ScriptEvent> g_script[2];
bool g_scripted[2] = { false, false };
std::atomic<uint32_t> g_inject_on{ 0 };      /* bit per port: our own cellPadGetData override answers with g_inject */
std::atomic<uint16_t> g_inject[2] = { 0, 0 };
bool g_np = false;                           /* netplay owns the pads: route injection through t5_netplay_inject */

bool netplay_on() { return g_np; }
void inject(int port, bool on, uint16_t buttons)
{
    if (port < 0 || port > 1) return;
    if (g_np) { t5_netplay_inject(port, on ? 1 : 0, buttons); return; }
    g_inject[port] = buttons;
    if (on) g_inject_on |= (1u << port); else g_inject_on &= ~(1u << port);
}
uint64_t gcall(uint32_t code, uint64_t a0, uint64_t a1, uint64_t a2)
{
    return ppu_guest_call_ct(code, kTOC, a0, a1, a2, 0, 0, 0, 0, 0);
}

std::vector<ScriptEvent> parse_script(const char* spec)
{
    std::vector<ScriptEvent> ev;
    if (!spec || !*spec) return ev;
    std::string text;
    if (*spec == '@') text = spec + 1;
    else {
        FILE* f = fopen(spec, "r");
        if (!f) { note("script %s: cannot open", spec); return ev; }
        char line[256];
        while (fgets(line, sizeof line, f)) { text += line; text += ','; }
        fclose(f);
    }
    const char* p = text.c_str();
    while (*p) {
        while (*p == ',' || *p == ' ' || *p == '\n' || *p == '\r') p++;
        if (!*p) break;
        char* e;
        unsigned long f = strtoul(p, &e, 10); if (e == p) break; p = e;
        if (*p == ':' || *p == ' ') p++;
        unsigned long l = strtoul(p, &e, 10); if (e == p) break; p = e;
        if (*p == ':' || *p == ' ') p++;
        unsigned long m = strtoul(p, &e, 16); if (e == p) break; p = e;
        ev.push_back({ (uint32_t)f, (uint32_t)l, (uint16_t)m });
    }
    return ev;
}
uint16_t script_mask(const std::vector<ScriptEvent>& ev, uint32_t f)
{
    uint16_t m = 0;
    for (const ScriptEvent& e : ev) if (f >= e.frame && f < e.frame + e.len) m |= e.mask;
    return m;
}

void write_pad_data(uint32_t ea, const PadInput& in)
{
    const int len = 8;
    wr32(ea, (uint32_t)len);
    for (int i = 0; i < 64; i++) wr16(ea + 4 + i * 2, 0);
    wr16(ea + 4 + 1 * 2, (uint16_t)(0x70 | (len / 2)));
    wr16(ea + 4 + 2 * 2, (uint16_t)(in.buttons & 0xFF));
    wr16(ea + 4 + 3 * 2, (uint16_t)(in.buttons >> 8));
    wr16(ea + 4 + 4 * 2, in.rx);
    wr16(ea + 4 + 5 * 2, in.ry);
    wr16(ea + 4 + 6 * 2, in.lx);
    wr16(ea + 4 + 7 * 2, in.ly);
}

/* ---- state -------------------------------------------------------------- */
std::atomic<uint32_t> g_frame{ 0 };
/* T5_DF_POKE=frame:addr:width:value,... (hex addr/value): guest writes at the top of that frame */
struct Poke { uint32_t frame, addr, width, value; };
std::vector<Poke> g_pokes;
/* T5_DF_WATCH=addr,addr,... (hex): log every change of those guest words, per frame */
std::vector<std::pair<uint32_t, uint32_t>> g_watch;   /* addr, last value */
/* T5_DF_STARTVS=N: N frames after the title mode starts, call the game's own
 * "start game type" routine func_0004E9DC(4 = VS BATTLE, 3 = both players) */
int g_startvs = -1; uint32_t g_title_frame = UINT32_MAX; bool g_startvs_done = false;
constexpr uint32_t kFnStartGame = 0x0004E9DC;
/* T5_DF_SHOT=f1,f2,...: frame-exact screenshots through the live renderer's LD_SURF_DUMP_GATE */
std::vector<uint32_t> g_shot_frames;
std::string g_shot_gate;
uint32_t g_shot_armed = UINT32_MAX;
uint64_t g_main_tid = 1;
df_lv2_fn g_orig_wait = nullptr;
std::atomic<bool> g_installed{ false };
bool g_probe = false, g_dump_modes = false;
std::vector<uint32_t> g_dump_frames;
uint32_t g_mgr = 0;            /* tcb_mode_manager_t object */
uint32_t g_last_cur = ~0u, g_last_next = ~0u, g_last_obj = 0;
uint32_t g_mode_changes = 0;

uint32_t mode_manager() { return g_mgr; }
uint32_t mode_cur()  { return g_mgr ? rd32(g_mgr + kModeReq) : 0xFFFFFFFFu; }
uint32_t mode_next() { return g_mgr ? rd32(g_mgr + kModeReq + 4) : 0xFFFFFFFFu; }

/* Walk the committed regions of [base, base+len) (VirtualQuery region by region,
 * not page by page: the guest space is one 4 GB reservation committed lazily). */
template <class F> void for_committed(uint32_t base, uint32_t len, F fn)
{
    uint32_t a = base;
    const uint32_t end = base + len;
    while (a < end) {
        MEMORY_BASIC_INFORMATION mi;
        if (!VirtualQuery(vm_base + a, &mi, sizeof mi)) break;
        uint64_t rend = (uint64_t)((uint8_t*)mi.BaseAddress - vm_base) + mi.RegionSize;
        if (rend > end) rend = end;
        if (mi.State == MEM_COMMIT && !(mi.Protect & (PAGE_NOACCESS | PAGE_GUARD)))
            fn(a, (uint32_t)(rend - a));
        a = (uint32_t)rend;
    }
}

uint32_t find_object(uint32_t vtable)
{
    const uint32_t pat = _byteswap_ulong(vtable);
    uint32_t found = 0;
    LARGE_INTEGER t0, t1, fq;
    QueryPerformanceCounter(&t0);
    auto scan = [&](uint32_t a, uint32_t n) {
        if (found) return;
        const uint32_t* p = (const uint32_t*)(vm_base + a);
        for (uint32_t i = 0; i < n / 4; i++) if (p[i] == pat) { found = a + i * 4; return; }
    };
    for_committed(0x10050000u, 0x00710000u, scan);   /* ELF data + bss (tcb pools live there) */
    if (!found) for_committed(kHeapBase, kHeapLen, scan);
    QueryPerformanceCounter(&t1); QueryPerformanceFrequency(&fq);
    static int n = 0;
    if (n++ < 3) note("heap scan for vtable 0x%08X: %.2f ms -> 0x%08X", vtable,
                      1000.0 * (double)(t1.QuadPart - t0.QuadPart) / (double)fq.QuadPart, found);
    return found;
}

void dump_range(FILE* fp, uint32_t base, uint32_t len)
{
    static const uint8_t zero[0x1000] = {};
    uint32_t pos = base;
    for_committed(base, len, [&](uint32_t a, uint32_t n) {
        while (pos < a) { fwrite(zero, 1, 0x1000, fp); pos += 0x1000; }
        fwrite(vm_base + a, 1, n, fp);
        pos = a + n;
    });
    while (pos < base + len) { fwrite(zero, 1, 0x1000, fp); pos += 0x1000; }
}
struct Range { uint32_t base, len; };
std::vector<Range> g_dump_ranges;   /* T5_DF_DUMP_RANGES=addr:len,... (hex); default data+bss and the heap */

void dump_memory(uint32_t f, const char* tag)
{
    for (const Range& r : g_dump_ranges) {
        char path[256];
        snprintf(path, sizeof path, "df_dump_%s_f%06u_%08X.bin", tag, f, r.base);
        FILE* fp = fopen(path, "wb");
        if (!fp) continue;
        dump_range(fp, r.base, r.len);
        fclose(fp);
    }
    note("frame %u: memory dumped (%s)", f, tag);
}

void find_manager(uint32_t f)
{
    if (g_mgr && rd32(g_mgr) == kVtModeMgr) return;
    if (f % 30) return;   /* rescan every half second at most */
    g_mgr = find_object(kVtModeMgr);
    if (g_mgr) note("frame %u: mode manager at 0x%08X", f, g_mgr);
}

void probe(uint32_t f)
{
    if (!g_mgr) return;
    const uint32_t cur = rd32(g_mgr + kModeReq), next = rd32(g_mgr + kModeReq + 4), prev = rd32(g_mgr + kModeReq + 8);
    const uint32_t obj = rd32(g_mgr + 0x6C);
    if (cur != g_last_cur || next != g_last_next || obj != g_last_obj) {
        note("frame %u: mode cur=%u next=%u prev=%u param=0x%X obj=0x%08X (%s) state=%u flags=%02X %02X %02X",
             f, cur, next, prev, rd32(g_mgr + kModeReq + 0xC), obj, class_name(obj).c_str(),
             rd32(g_mgr + 0x48), rd8(g_mgr + 0x68), rd8(g_mgr + 0x69), rd8(g_mgr + 0x6A));
        if (cur != g_last_cur && g_dump_modes && g_last_cur != ~0u) {
            char tag[32]; snprintf(tag, sizeof tag, "m%u", ++g_mode_changes);
            dump_memory(f, tag);
        }
        g_last_cur = cur; g_last_next = next; g_last_obj = obj;
    }
}

/* T5_DF_FIND=frame:text,...: at that frame, search all committed guest memory
 * for the text as ASCII and as UTF-16BE and log every address (diagnostics:
 * where the game keeps a string it shows). */
struct FindReq { uint32_t frame; std::string text; };
std::vector<FindReq> g_finds;
void find_text(uint32_t f)
{
    for (const FindReq& q : g_finds) {
        if (q.frame != f) continue;
        std::string pats[2] = { q.text, std::string() };
        for (char c : q.text) { pats[1] += '\0'; pats[1] += c; }
        int hits = 0;
        for_committed(0x00010000u, 0xFFFE0000u, [&](uint32_t a, uint32_t n) {
            for (int k = 0; k < 2; k++) {
                const std::string& p = pats[k];
                const uint8_t* b = vm_base + a;
                for (uint32_t i = 0; i + p.size() <= n && hits < 200; i++) {
                    if (b[i] != (uint8_t)p[0] || memcmp(b + i, p.data(), p.size())) continue;
                    hits++;
                    note("frame %u: '%s' (%s) at 0x%08X", f, q.text.c_str(), k ? "UTF-16BE" : "ASCII", a + i);
                }
            }
        });
        note("frame %u: '%s': %d hit(s)", f, q.text.c_str(), hits);
    }
}

void shot(uint32_t f)
{
    if (g_shot_gate.empty()) return;
    if (g_shot_armed != UINT32_MAX && f >= g_shot_armed + 30) {
        remove(g_shot_gate.c_str());   /* re-arms the renderer for the next one */
        g_shot_armed = UINT32_MAX;
    }
    for (uint32_t sf : g_shot_frames) {
        if (sf != f || g_shot_armed != UINT32_MAX) continue;
        Sleep(150);
        if (FILE* fp = fopen(g_shot_gate.c_str(), "wb")) { fprintf(fp, "%u", f); fclose(fp); }
        g_shot_armed = f;
        note("frame %u: screenshot requested", f);
    }
}

/* T5_DF_GUARD=addr:len,... (hex), T5_DF_GUARD_AT=<frame> (default: the first
 * title): from then on those pages are read-only; the first write to each
 * page is logged with the writer (the lifted function at the faulting store,
 * its lifted callers, the host thread), then the page is writable again.
 * Found who zeroed the vblank handler's descriptor (0x4635A8) on the second
 * visit to the title after a fight: the title's own memset 0x3AF974 from
 * 0x2DBBEC (docs/DIRECTFIGHT.md "After a session ends"). */
struct Guard { uint32_t addr, len; };
std::vector<Guard> g_guards;
uint32_t g_guard_at = UINT32_MAX;
std::atomic<bool> g_guard_armed{ false };
std::atomic<int> g_guard_hits{ 0 };
LONG CALLBACK guard_veh(EXCEPTION_POINTERS* ep)
{
    const EXCEPTION_RECORD* er = ep->ExceptionRecord;
    if (!g_guard_armed || er->ExceptionCode != EXCEPTION_ACCESS_VIOLATION || er->NumberParameters < 2 ||
        er->ExceptionInformation[0] != 1)
        return EXCEPTION_CONTINUE_SEARCH;
    const uintptr_t at = (uintptr_t)er->ExceptionInformation[1];
    if (at < (uintptr_t)vm_base || at >= (uintptr_t)vm_base + 0x100000000ull) return EXCEPTION_CONTINUE_SEARCH;
    const uint32_t ea = (uint32_t)(at - (uintptr_t)vm_base);
    bool ours = false;
    for (const Guard& g : g_guards) if (ea >= (g.addr & ~0xFFFu) && ea < ((g.addr + g.len + 0xFFFu) & ~0xFFFu)) ours = true;
    if (!ours) return EXCEPTION_CONTINUE_SEARCH;
    DWORD old;
    VirtualProtect(vm_base + (ea & ~0xFFFu), 0x1000, PAGE_READWRITE, &old);
    uint32_t off = 0;
    const uint32_t top = rb::guest_of_host((uintptr_t)ep->ContextRecord->Rip, &off);
    HMODULE mod = nullptr; char mname[MAX_PATH] = "?";
    if (GetModuleHandleExA(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
                           (LPCSTR)ep->ContextRecord->Rip, &mod) && mod)
        GetModuleFileNameA(mod, mname, sizeof mname);
    const char* base = strrchr(mname, 0x5C);   /* the last backslash */
    if (g_guard_hits++ < 32)
        note("frame %u: GUARD write to 0x%08X by host thread %lu at %s+0x%llX (lifted %s%06X+0x%X) <- %s", g_frame.load(), ea,
             (unsigned long)GetCurrentThreadId(), base ? base + 1 : mname,
             (unsigned long long)(ep->ContextRecord->Rip - (uintptr_t)mod), top ? "func_" : "none ", top, off,
             rb::guest_backtrace(12).c_str());
    return EXCEPTION_CONTINUE_EXECUTION;
}
void guard_arm(uint32_t f)
{
    if (g_guards.empty() || g_guard_armed) return;
    (void)rb::guest_of_host(0, nullptr);   /* build the lifted-function map now, not in the handler */
    AddVectoredExceptionHandler(1, guard_veh);
    g_guard_armed = true;
    for (const Guard& g : g_guards) {
        DWORD old;
        const uint32_t a = g.addr & ~0xFFFu, e = (g.addr + g.len + 0xFFFu) & ~0xFFFu;
        VirtualProtect(vm_base + a, e - a, PAGE_READONLY, &old);
        note("frame %u: guard on 0x%08X..0x%08X (read-only until written)", f, a, e);
    }
}

void on_frame(ppu_context* ctx)
{
    (void)ctx;
    const uint32_t f = g_frame.load();
    LARGE_INTEGER t0, t1, fq;
    QueryPerformanceCounter(&t0);
    for (const Poke& p : g_pokes) {
        if (p.frame != f) continue;
        if (p.width == 1) wr8(p.addr, (uint8_t)p.value);
        else if (p.width == 2) wr16(p.addr, (uint16_t)p.value);
        else wr32(p.addr, p.value);
        note("frame %u: poke [0x%08X] w%u = 0x%X", f, p.addr, p.width, p.value);
    }
    find_manager(f);
    if (!g_guards.empty() && !g_guard_armed &&
        (f == g_guard_at || (g_guard_at == UINT32_MAX && g_mgr && rd32(g_mgr + kModeReq) == 1))) guard_arm(f);
    if (g_probe) probe(f);
    fight_on_frame(f);
    for (auto& w : g_watch) {
        const uint32_t v = rd32(w.first);
        if (v != w.second) { note("frame %u: [0x%08X] 0x%08X -> 0x%08X", f, w.first, w.second, v); w.second = v; }
    }
    if (g_startvs >= 0 && !g_startvs_done && g_mgr) {
        if (g_title_frame == UINT32_MAX && rd32(g_mgr + kModeReq) == 1) g_title_frame = f;
        if (g_title_frame != UINT32_MAX && f >= g_title_frame + (uint32_t)g_startvs) {
            g_startvs_done = true;
            note("frame %u: calling start-game(4 VS, 3) from the title mode", f);
            ppu_guest_call_ct(kFnStartGame, kTOC, 4, 3, 0, 0, 0, 0, 0, 0);
            note("frame %u: start-game returned; game type now %u, mode next=%u", f, rd32(0x1008EBAC), rd32(g_mgr + kModeReq + 4));
        }
    }
    shot(f);
    find_text(f);
    for (uint32_t d : g_dump_frames) if (d == f) dump_memory(f, "f");
    QueryPerformanceCounter(&t1); QueryPerformanceFrequency(&fq);
    const double ms = 1000.0 * (double)(t1.QuadPart - t0.QuadPart) / (double)fq.QuadPart;
    static int slow = 0;
    if (ms > 50 && slow++ < 10) note("frame %u: hook took %.1f ms", f, ms);
    if (g_log && (f % 60) == 0) {
        fprintf(g_log, "F %u clock %llu\n", f, (unsigned long long)rd64(kFrameClock));
        fflush(g_log);
    }
}

/* ---- hooks ---------------------------------------------------------------- */
int64_t w_sem_wait(ppu_context* ctx)
{
    const uint32_t id = (uint32_t)ctx->gpr[3];
    const uint32_t fs = rd32(kFrameSemPtr);
    int64_t r = g_orig_wait(ctx);
    if (fs && id == fs && ctx->thread_id == g_main_tid && r == 0) {
        on_frame(ctx);
        g_frame++;
    }
    return r;
}

void install_syscall_hooks()
{
    bool expected = false;
    if (!g_installed.compare_exchange_strong(expected, true)) return;
    g_orig_wait = g_lv2_syscalls.handlers[SYS_SEMAPHORE_WAIT];
    g_lv2_syscalls.handlers[SYS_SEMAPHORE_WAIT] = w_sem_wait;
    note("frame-boundary hook installed");
}

/* The game's first firmware call (right after its first sys_memory_allocate):
 * the lv2 syscall table is live by then, and no other module of ours overrides
 * this one (netplay and rollback take cellPadInit; ctx overrides dispatch in
 * registration order, so sharing a NID with them would be a static-init race). */
void h_cellSysutilRegisterCallback(ppu_context* ctx)
{
    install_syscall_hooks();
    int32_t r = cellSysutilRegisterCallback((int32_t)ctx->gpr[3], (uint32_t)ctx->gpr[4], (uint32_t)ctx->gpr[5]);
    ctx->gpr[3] = (uint64_t)(int64_t)r;
}
void h_cellPadGetInfo(ppu_context* ctx)
{
    uint32_t ea = (uint32_t)ctx->gpr[3];
    int32_t r = cellPadGetInfo((void*)(uintptr_t)ea);
    if (r == 0 && ea) {
        wr32(ea + 0x04, 2);
        wr32(ea + 0x08, 0);
        for (uint32_t i = 0; i < 7; i++) {
            const bool on = i < 2;
            wr16(ea + 0x00C + i * 2, on ? 0x054C : 0);
            wr16(ea + 0x10A + i * 2, on ? 0x0268 : 0);
            wr8(ea + 0x208 + i, on ? 1 : 0);
        }
    }
    ctx->gpr[3] = (uint64_t)(int64_t)r;
}
void h_cellPadGetData(ppu_context* ctx)
{
    uint32_t port = (uint32_t)ctx->gpr[3], ea = (uint32_t)ctx->gpr[4];
    if (!ea) { ctx->gpr[3] = (uint64_t)(int64_t)(int32_t)0x80121104; return; }
    if (port < 2 && (g_inject_on.load() & (1u << port))) {
        PadInput in = kNeutral;
        in.buttons = g_inject[port].load();
        write_pad_data(ea, in);
        ctx->gpr[3] = 0;
        return;
    }
    if (port < 2 && g_scripted[port]) {
        PadInput in = kNeutral;
        in.buttons = script_mask(g_script[port], g_frame.load());
        write_pad_data(ea, in);
        ctx->gpr[3] = 0;
        return;
    }
    if (port < 2) { ctx->gpr[3] = (uint64_t)(int64_t)cellPadGetData(port, (void*)(uintptr_t)ea); return; }
    wr32(ea, 0);
    ctx->gpr[3] = 0;
}

struct Register {
    Register()
    {
        const char* fight = getenv("T5_FIGHT");
        const char* ffile = getenv("T5_FIGHT_FILE");
        const char* pr = getenv("T5_DF_PROBE");
        const char* s1 = getenv("T5_DF_SCRIPT");
        const char* s2 = getenv("T5_DF_SCRIPT2");
        const char* dm = getenv("T5_DF_DUMP");
        const char* ctl = getenv("T5_CTL_DIR");
        if (!(fight && *fight) && !(ffile && *ffile) && !(pr && *pr) && !(s1 && *s1) && !(s2 && *s2) && !(dm && *dm) &&
            !(ctl && *ctl)) return;
        /* netplay owns the pads with T5_NET_MODE, and in a persistent game (its
         * hooks are in from boot for the sessions to come) */
        { const char* nm = getenv("T5_NET_MODE"); g_np = (nm && *nm) || (ctl && *ctl); }
        ctl_init();
        fight_init();
        const char* lf = getenv("T5_DF_LOG");
        g_log = fopen(lf && *lf ? lf : "df_frames.log", "w");
        g_probe = pr && *pr == '1';
        { const char* d = getenv("T5_DF_DUMP_MODES"); g_dump_modes = d && *d == '1'; }
        if (s1 && *s1) { g_script[0] = parse_script(s1); g_scripted[0] = true; }
        if (s2 && *s2) { g_script[1] = parse_script(s2); g_scripted[1] = true; }
        if (dm) for (const char* p = dm; *p;) {
            char* e; unsigned long v = strtoul(p, &e, 10);
            if (e == p) break;
            g_dump_frames.push_back((uint32_t)v);
            p = e; while (*p == ',') p++;
        }
        if (const char* pk = getenv("T5_DF_POKE")) for (const char* p = pk; *p;) {
            char* e; Poke k;
            k.frame = (uint32_t)strtoul(p, &e, 10); if (e == p || *e != ':') break; p = e + 1;
            k.addr  = (uint32_t)strtoul(p, &e, 16); if (e == p || *e != ':') break; p = e + 1;
            k.width = (uint32_t)strtoul(p, &e, 10); if (e == p || *e != ':') break; p = e + 1;
            k.value = (uint32_t)strtoul(p, &e, 16); if (e == p) break; p = e;
            g_pokes.push_back(k);
            while (*p == ',' || *p == ' ') p++;
        }
        if (const char* w = getenv("T5_DF_WATCH")) for (const char* p = w; *p;) {
            char* e; uint32_t a = (uint32_t)strtoul(p, &e, 16);
            if (e == p) break;
            g_watch.push_back({ a, 0xFFFFFFFFu });
            p = e; while (*p == ',' || *p == ' ') p++;
        }
        if (const char* sv = getenv("T5_DF_STARTVS")) g_startvs = atoi(sv);
        if (const char* gd = getenv("T5_DF_GUARD")) for (const char* p = gd; *p;) {
            char* e; Guard g;
            g.addr = (uint32_t)strtoul(p, &e, 16); if (e == p || *e != ':') break; p = e + 1;
            g.len = (uint32_t)strtoul(p, &e, 16); if (e == p) break; p = e;
            g_guards.push_back(g);
            while (*p == ',' || *p == ' ') p++;
        }
        if (const char* ga = getenv("T5_DF_GUARD_AT")) g_guard_at = (uint32_t)atoi(ga);
        if (const char* fd = getenv("T5_DF_FIND")) {
            std::string s = fd, item;
            for (size_t i = 0; i <= s.size(); i++) {
                if (i == s.size() || s[i] == ',') {
                    const size_t c = item.find(':');
                    if (c != std::string::npos) g_finds.push_back({ (uint32_t)strtoul(item.c_str(), nullptr, 10), item.substr(c + 1) });
                    item.clear();
                } else item += s[i];
            }
        }
        if (const char* d = getenv("T5_DF_SHOT")) {
            for (const char* p = d; *p;) {
                char* e; unsigned long v = strtoul(p, &e, 10);
                if (e == p) break;
                g_shot_frames.push_back((uint32_t)v);
                p = e; while (*p == ',') p++;
            }
            const char* g = getenv("LD_SURF_DUMP_GATE");
            if (g) { g_shot_gate = g; remove(g); }
            else note("T5_DF_SHOT needs LD_SURF_DUMP=<dir> and LD_SURF_DUMP_GATE=<file>");
        }
        {
            const char* dr = getenv("T5_DF_DUMP_RANGES");
            const char* spec = dr && *dr ? dr : "10000000:770000,40000000:5F00000";
            for (const char* p = spec; *p;) {
                char* e;
                uint32_t a = (uint32_t)strtoul(p, &e, 16); if (e == p || *e != ':') break; p = e + 1;
                uint32_t l = (uint32_t)strtoul(p, &e, 16); if (e == p) break; p = e;
                g_dump_ranges.push_back({ a, l });
                while (*p == ',' || *p == ' ') p++;
            }
        }
        note("directfight: probe=%d scripts %zu/%zu dumps %zu", g_probe, g_script[0].size(), g_script[1].size(), g_dump_frames.size());
        ps3_hle_register_ctx(NID_cellSysutilRegisterCallback, "cellSysutilRegisterCallback(df)", h_cellSysutilRegisterCallback);
        /* Our own pad override carries the scripted input (tests) and the menu
         * injection; with netplay on, its hooks own the pads and we inject
         * through t5_netplay_inject() instead (ctx overrides dispatch in
         * registration order, so two overrides of one NID would race). */
        if (!g_np && (g_scripted[0] || g_scripted[1] || fight_configured())) {
            ps3_hle_register_ctx(NID_cellPadGetInfo, "cellPadGetInfo(df)", h_cellPadGetInfo);
            ps3_hle_register_ctx(NID_cellPadGetData, "cellPadGetData(df)", h_cellPadGetData);
        }
    }
} g_register;

} // namespace df
