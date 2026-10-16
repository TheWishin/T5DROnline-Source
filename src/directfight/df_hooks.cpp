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

extern "C" uint8_t* vm_base;
extern "C" {
void    ps3_hle_register_ctx(uint32_t nid, const char* name, void (*fn)(ppu_context*));
int32_t cellSysutilRegisterCallback(int32_t slot, uint32_t func, uint32_t userdata);
int32_t cellPadGetInfo(void* info_guest);
int32_t cellPadGetData(uint32_t port, void* data_guest);
uint64_t ppu_guest_call_ct(uint32_t code, uint32_t toc, uint64_t a0, uint64_t a1, uint64_t a2,
                           uint64_t a3, uint64_t a4, uint64_t a5, uint64_t a6, uint64_t a7);
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

inline uint32_t rd32(uint32_t a) { uint32_t v; memcpy(&v, vm_base + a, 4); return _byteswap_ulong(v); }
inline uint64_t rd64(uint32_t a) { uint64_t v; memcpy(&v, vm_base + a, 8); return _byteswap_uint64(v); }
inline uint16_t rd16(uint32_t a) { uint16_t v; memcpy(&v, vm_base + a, 2); return _byteswap_ushort(v); }
inline uint8_t  rd8(uint32_t a)  { return vm_base[a]; }
inline void wr32(uint32_t a, uint32_t v) { v = _byteswap_ulong(v); memcpy(vm_base + a, &v, 4); }
inline void wr16(uint32_t a, uint16_t v) { v = _byteswap_ushort(v); memcpy(vm_base + a, &v, 2); }
inline void wr8(uint32_t a, uint8_t v)   { vm_base[a] = v; }

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

/* ---- scripted input ----------------------------------------------------- */
struct PadInput { uint16_t buttons; uint8_t lx, ly, rx, ry; };
const PadInput kNeutral = { 0, 128, 128, 128, 128 };
struct ScriptEvent { uint32_t frame, len; uint16_t mask; };
std::vector<ScriptEvent> g_script[2];
bool g_scripted[2] = { false, false };

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
uint64_t g_main_tid = 1;
df_lv2_fn g_orig_wait = nullptr;
std::atomic<bool> g_installed{ false };
bool g_probe = false, g_dump_modes = false;
std::vector<uint32_t> g_dump_frames;
uint32_t g_mgr = 0;            /* tcb_mode_manager_t object */
uint32_t g_last_cur = ~0u, g_last_next = ~0u, g_last_obj = 0;
uint32_t g_mode_changes = 0;

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
void dump_memory(uint32_t f, const char* tag)
{
    const uint32_t ranges[][2] = { { kDataBase, kDataLen }, { kHeapBase, kHeapLen } };
    for (auto& r : ranges) {
        char path[256];
        snprintf(path, sizeof path, "df_dump_%s_f%06u_%08X.bin", tag, f, r[0]);
        FILE* fp = fopen(path, "wb");
        if (!fp) continue;
        dump_range(fp, r[0], r[1]);
        fclose(fp);
    }
    note("frame %u: memory dumped (%s)", f, tag);
}

void probe(uint32_t f)
{
    if (!g_mgr || rd32(g_mgr) != kVtModeMgr) {
        if (f % 30) return;   /* rescan every half second at most */
        g_mgr = find_object(kVtModeMgr);
        if (g_mgr) note("frame %u: mode manager at 0x%08X", f, g_mgr);
        if (!g_mgr) return;
    }
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

void on_frame(ppu_context* ctx)
{
    (void)ctx;
    const uint32_t f = g_frame.load();
    LARGE_INTEGER t0, t1, fq;
    QueryPerformanceCounter(&t0);
    if (g_probe) probe(f);
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
        const char* pr = getenv("T5_DF_PROBE");
        const char* s1 = getenv("T5_DF_SCRIPT");
        const char* s2 = getenv("T5_DF_SCRIPT2");
        const char* dm = getenv("T5_DF_DUMP");
        if (!(fight && *fight) && !(pr && *pr) && !(s1 && *s1) && !(s2 && *s2) && !(dm && *dm)) return;
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
        note("directfight: probe=%d scripts %zu/%zu dumps %zu", g_probe, g_script[0].size(), g_script[1].size(), g_dump_frames.size());
        ps3_hle_register_ctx(NID_cellSysutilRegisterCallback, "cellSysutilRegisterCallback(df)", h_cellSysutilRegisterCallback);
        if (g_scripted[0] || g_scripted[1]) {   /* scripted pads: tests only (netplay owns the pads in a match) */
            ps3_hle_register_ctx(NID_cellPadGetInfo, "cellPadGetInfo(df)", h_cellPadGetInfo);
            ps3_hle_register_ctx(NID_cellPadGetData, "cellPadGetData(df)", h_cellPadGetData);
        }
    }
} g_register;

} // namespace df
