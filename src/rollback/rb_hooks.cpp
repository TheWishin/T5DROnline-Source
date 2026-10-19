/*
 * T5DR rollback research prototype (NPUB30009 v01.00) -- see docs/ROLLBACK.md.
 *
 * Everything is off unless T5_RB_MODE is set. Modes:
 *   measure   per-frame dirty-page statistics of guest memory (needs the
 *             runtime reserved with PS3_VM_WRITE_WATCH=1), host backtrace of
 *             the frame boundary, side-thread write attribution.
 *
 * Input: T5_RB_SCRIPT / T5_RB_SCRIPT2 = "frame:len:mask,..." (hex mask, np
 * packing: DIGITAL1 low byte, DIGITAL2 high byte) drive pads 0 and 1 from the
 * frame counter; nothing else reaches the game.
 *
 * Hooks (no ps3recomp changes needed beyond the write-watch flag):
 *   - HLE overrides for cellPadInit / cellPadGetInfo / cellPadGetData
 *   - lv2 syscall wrapper for sys_semaphore_wait (92): the main thread's wait
 *     on its per-frame semaphore (id at 0x106D4A30) is the frame boundary.
 */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <stdarg.h>
#include <atomic>
#include <vector>
#include <algorithm>

#include "sys_ppu_thread.h"     /* ppu_context, g_ppu_threads: names + host handles */
#include "lv2_syscall_table.h"  /* g_lv2_syscalls */
#include "rb.h"
#include "rb_net.h"

/* From the lifted output (ppu_recomp.h cannot be included next to the runtime's
 * ppu_context.h: both define the struct, identically). */
typedef struct { uint64_t addr; void (*func)(ppu_context*); const char* name; } func_entry;
#ifdef PS3_GAME_DLL
/* Release host: the lifted table lives in t5dr_game.dll; the runtime publishes
 * it once the DLL is loaded (runtime/ppu/ppu_game_dll.h). */
extern "C" const func_entry* ppu_game_table;
extern "C" uint64_t ppu_game_table_count;
#define function_table       ppu_game_table
#define function_table_count ppu_game_table_count
#else
extern "C" const func_entry function_table[];
extern "C" const uint64_t  function_table_count;
#endif
extern "C" uint8_t* vm_base;

extern "C" {
void    ps3_hle_register_ctx(uint32_t nid, const char* name, void (*fn)(ppu_context*));
int32_t cellPadInit(uint32_t max_connect);
int32_t cellPadGetInfo(void* info_guest);
void    cellGcmSetUserCommand(void* ctx, uint32_t cause);
int32_t cellGcmSetFlip(void* context, uint32_t bufferId);
uint32_t cellGcmGetFlipStatus(void);
int     cellGcm_xlat_presented(void);   /* ps3recomp patch 0034: the held flip is translated and presented */
void    cellGcmResetFlipStatus(void);
void    cellGcmSetWaitFlip(void);
uint64_t ppu_guest_call_ct(uint32_t code, uint32_t toc, uint64_t a0, uint64_t a1, uint64_t a2,
                           uint64_t a3, uint64_t a4, uint64_t a5, uint64_t a6, uint64_t a7);
}
typedef int64_t (*rb_lv2_fn)(ppu_context*);

namespace rb {

/* ---- guest addresses (NPUB30009 v01.00; see np's t5_hooks.cpp) ---------- */
constexpr uint32_t kTOC         = 0x470540;

constexpr uint32_t NID_cellPadInit    = 0x1CF98800;
constexpr uint32_t NID_cellPadGetInfo = 0x3AAAD464;
constexpr uint32_t NID_cellPadGetData = 0x8B72CDA1;
constexpr uint32_t NID_cellGcmSetUserCommand = 0x8BDE5EBF;
constexpr uint32_t NID_cellGcmSetFlip        = 0xDC09357E;
constexpr uint32_t NID_cellGcmGetFlipStatus  = 0x72A577CE;
constexpr uint32_t NID_cellGcmResetFlipStatus = 0xB2E761D4;
constexpr uint32_t NID_cellGcmSetWaitFlip     = 0x983FB9AA;
constexpr uint32_t kKeyreadSemPtr = 0x104CB5C0;   /* u32 semaphore id of the keyread thread */
constexpr uint32_t kKeyreadQuitFlag = 0x104CCDF4;
constexpr int SC_SEM_POST = 94;
constexpr int SC_SEM_WAIT = 92;
std::atomic<bool> g_bypass{ false };
std::atomic<bool> g_swallow{ false };
std::atomic<int>  g_kr_in_wait{ 0 };
std::atomic<bool> g_kr_parked{ false };
std::atomic<uint32_t> g_sim_frame{ 0 };

uint32_t rd32(uint32_t a) { uint32_t v; memcpy(&v, vm_base + a, 4); return _byteswap_ulong(v); }
uint64_t rd64(uint32_t a) { uint64_t v; memcpy(&v, vm_base + a, 8); return _byteswap_uint64(v); }
void wr32(uint32_t a, uint32_t v) { v = _byteswap_ulong(v); memcpy(vm_base + a, &v, 4); }
void wr16(uint32_t a, uint16_t v) { v = _byteswap_ushort(v); memcpy(vm_base + a, &v, 2); }
void wr8(uint32_t a, uint8_t v) { vm_base[a] = v; }

FILE* g_log = nullptr;
void note(const char* fmt, ...)
{
    char buf[1024];
    va_list ap; va_start(ap, fmt); vsnprintf(buf, sizeof buf, fmt, ap); va_end(ap);
    fprintf(stderr, "[rb] %s\n", buf);
    fflush(stderr);
    if (g_log) { fprintf(g_log, "# %s\n", buf); fflush(g_log); }
}
void logline(const char* fmt, ...)
{
    if (!g_log) return;
    va_list ap; va_start(ap, fmt); vfprintf(g_log, fmt, ap); va_end(ap);
    fputc('\n', g_log);
}

/* ---- scripted input ----------------------------------------------------- */
struct ScriptEvent { uint32_t frame, len; uint16_t mask; };
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

std::vector<ScriptEvent> g_script[2];
std::atomic<uint32_t> g_frame{ 0 };      /* frames seen at the boundary */
uint64_t g_main_tid = 1;                  /* ppu_thread_register_main: id 1 */
rb_lv2_fn g_orig_wait = nullptr;
std::atomic<bool> g_installed{ false };
Mode g_mode = Mode::Off;
PadInput g_override[2];
bool g_override_on = false;
bool g_df = false;                        /* direct fight drives the pads */
uint32_t g_script_base = 0;               /* script frame = logical frame - base */

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

PadInput scripted(int port, uint32_t f)
{
    PadInput in = kNeutral;
    in.buttons = f >= g_script_base ? script_mask(g_script[port], f - g_script_base) : 0;
    return in;
}
bool df_drives() { return g_df; }
void set_script_base(uint32_t f) { g_script_base = f; }

std::atomic<uint32_t> g_pad_calls{ 0 };
uint32_t pad_calls() { return g_pad_calls.load(); }
void h_cellPadGetData(ppu_context* ctx)
{
    uint32_t port = (uint32_t)ctx->gpr[3], ea = (uint32_t)ctx->gpr[4];
    g_pad_calls++;
    if (!ea) { ctx->gpr[3] = (uint64_t)(int64_t)(int32_t)0x80121104; return; }
    if (port < 2) {
        if (g_override_on) write_pad_data(ea, g_override[port]);
        else write_pad_data(ea, scripted((int)port, g_mode == Mode::Test ? g_sim_frame.load() : g_frame.load()));
    } else wr32(ea, 0);
    ctx->gpr[3] = 0;
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

/* ---- host backtrace -> lifted functions ----------------------------------- */
struct HG { uintptr_t h; uint32_t g; };
std::vector<HG> g_map;
void build_map()
{
    if (!g_map.empty()) return;
    for (uint64_t k = 0; k < function_table_count; k++)
        g_map.push_back({ (uintptr_t)function_table[k].func, (uint32_t)function_table[k].addr });
    std::sort(g_map.begin(), g_map.end(), [](const HG& a, const HG& b) { return a.h < b.h; });
}
uint32_t guest_of_host(uintptr_t tgt, uint32_t* off)
{
    build_map();
    auto it = std::upper_bound(g_map.begin(), g_map.end(), tgt,
                               [](uintptr_t v, const HG& e) { return v < e.h; });
    if (it == g_map.begin()) return 0;
    --it;
    uintptr_t end = (it + 1 != g_map.end()) ? (it + 1)->h : it->h + 0x4000;
    if (tgt >= end) return 0;
    if (off) *off = (uint32_t)(tgt - it->h);
    return it->g;
}
uint32_t guest_at_host(uintptr_t fn)
{
    build_map();
    auto it = std::lower_bound(g_map.begin(), g_map.end(), fn,
                               [](const HG& e, uintptr_t v) { return e.h < v; });
    return (it != g_map.end() && it->h == fn) ? it->g : 0;
}
std::string guest_backtrace(int max)
{
    void* fr[64]; unsigned short n = RtlCaptureStackBackTrace(0, 64, fr, 0);
    std::string s;
    int got = 0;
    for (unsigned short i = 0; i < n && got < max; i++) {
        uint32_t off = 0, g = guest_of_host((uintptr_t)fr[i], &off);
        if (!g) continue;
        char t[48];
        snprintf(t, sizeof t, "%sfunc_%08X+0x%X", got ? " <- " : "", g, off);
        s += t; got++;
    }
    return s;
}
uint64_t main_tid() { return g_main_tid; }

/* ---- thread table ------------------------------------------------------------ */
void list_threads()
{
    for (int i = 0; i < PPU_THREAD_MAX; i++) {
        const ppu_thread_info& t = g_ppu_threads[i];
        if (t.state == PPU_THREAD_STATE_FREE) continue;
        note("thread slot %d id %llu state %d name \"%s\" stack 0x%08X+0x%X host tid %lu", i,
             (unsigned long long)t.ctx.thread_id, t.state, t.name, t.stack_addr, t.stack_size,
             (unsigned long)t.host_tid);
    }
}

/* ---- GCM submit points, timestamped for the frame cost split -------------------- */
LARGE_INTEGER g_t_usercmd, g_t_flip;
void h_cellGcmSetUserCommand(ppu_context* ctx)
{
    if (ctx->thread_id == g_main_tid) QueryPerformanceCounter(&g_t_usercmd);
    if (g_bypass && ctx->thread_id == g_main_tid) { ctx->gpr[3] = 0; return; }   /* re-simulating: no GPU handshake */
    cellGcmSetUserCommand((void*)(uintptr_t)(uint32_t)ctx->gpr[3], (uint32_t)ctx->gpr[4]);
    ctx->gpr[3] = 0;
}
extern bool g_flip_asked;
/* T5_RB_NET_EARLY_COMMIT=present: the old place (after the present) */
bool g_early_commit_at_flip = [] { const char* e = getenv("T5_RB_NET_EARLY_COMMIT"); return !(e && !strcmp(e, "present")); }();
void h_cellGcmGetFlipStatus(ppu_context* ctx)
{
    if (g_bypass && ctx->thread_id == g_main_tid) { ctx->gpr[3] = 0; return; }   /* DONE */
    uint32_t st = cellGcmGetFlipStatus();
    /* early rollback (rb_net.cpp early_check): the frame is translated and
     * presented, a rollback is already known -- report the flip done so the
     * boundary can start now; it waits for the tick itself */
    if (st != 0 && g_mode == Mode::Net && ctx->thread_id == g_main_tid) {
        /* The next boundary's snapshot only reads guest memory, so it is taken
         * as soon as the frame has asked for its flip -- while the walker still
         * translates it (frame-time branch; it used to wait for the present,
         * and an early rollback then started only after it) */
        if (g_flip_asked || cellGcm_xlat_presented()) { net::early_commit(); g_flip_asked = false; }
        if (cellGcm_xlat_presented() && net::early_check()) st = 0;
    }
    ctx->gpr[3] = st;
}
void h_cellGcmResetFlipStatus(ppu_context* ctx)
{
    if (g_bypass && ctx->thread_id == g_main_tid) { ctx->gpr[3] = 0; return; }
    cellGcmResetFlipStatus();
    ctx->gpr[3] = 0;
}
bool g_flip_asked = false;   /* the main thread queued its frame's flip (early_commit may run) */
void h_cellGcmSetFlip(ppu_context* ctx)
{
    if (ctx->thread_id == g_main_tid) QueryPerformanceCounter(&g_t_flip);
    if (ctx->thread_id == g_main_tid && !g_bypass) g_flip_asked = g_early_commit_at_flip;
    if (g_bypass && ctx->thread_id == g_main_tid) { ctx->gpr[3] = 0; return; }   /* re-simulating: nothing to show */
    ctx->gpr[3] = (uint64_t)(int64_t)cellGcmSetFlip((void*)(uintptr_t)(uint32_t)ctx->gpr[3], (uint32_t)ctx->gpr[4]);
}
/* The present (0x383C04) queues the flip and then waits for it; while
 * re-simulating there is no flip to wait for -- this wait was 35 % of a
 * re-simulated frame's wall time in the phase-1 numbers. */
std::atomic<int> g_ts_sleep_us{ 0 };
void ts_sleep_request(double ms) { g_ts_sleep_us = (int)(ms * 1000.0); }
void h_cellGcmSetWaitFlip(ppu_context* ctx)
{
    if (g_bypass && ctx->thread_id == g_main_tid) { ctx->gpr[3] = 0; return; }
    cellGcmSetWaitFlip();
    if (ctx->thread_id == g_main_tid) {
        const int us = g_ts_sleep_us.exchange(0);
        if (us > 0) {
            LARGE_INTEGER f, a, b; QueryPerformanceFrequency(&f); QueryPerformanceCounter(&a);
            do { Sleep(1); QueryPerformanceCounter(&b); } while ((b.QuadPart - a.QuadPart) * 1000000 / f.QuadPart < us);
        }
    }
    ctx->gpr[3] = 0;
}
double t_usercmd_ms(LARGE_INTEGER since) { LARGE_INTEGER f; QueryPerformanceFrequency(&f); return 1000.0 * (double)(g_t_usercmd.QuadPart - since.QuadPart) / (double)f.QuadPart; }
double t_flip_ms(LARGE_INTEGER since) { LARGE_INTEGER f; QueryPerformanceFrequency(&f); return 1000.0 * (double)(g_t_flip.QuadPart - since.QuadPart) / (double)f.QuadPart; }

/* ---- frame boundary ------------------------------------------------------------- */
void (*g_on_frame)(ppu_context*) = nullptr;

rb_lv2_fn g_orig_post = nullptr;
int64_t w_sem_wait(ppu_context* ctx)
{
    const uint32_t id = (uint32_t)ctx->gpr[3];
    const uint32_t fs = rd32(kFrameSemPtr);
    const uint32_t kr = rd32(kKeyreadSemPtr);
    if (kr && id == kr && ctx->thread_id != g_main_tid) {
        /* the keyread thread entering its wait: from now on the main thread
         * can tick it; its wakes are swallowed once the test mode wants that */
        g_kr_in_wait = 1;
        if (g_swallow) g_kr_parked = true;
        int64_t r = g_orig_wait(ctx);
        g_kr_in_wait = 0;
        return r;
    }
    if (fs && id == fs && ctx->thread_id == g_main_tid) {
        int64_t r = g_bypass ? 0 : g_orig_wait(ctx);
        if (r == 0) {
            if (g_on_frame) g_on_frame(ctx);
            g_frame++;
        }
        return r;
    }
    return g_orig_wait(ctx);
}
int64_t w_sem_post(ppu_context* ctx)
{
    const uint32_t id = (uint32_t)ctx->gpr[3];
    if (g_swallow && id == rd32(kKeyreadSemPtr) && rd32(kKeyreadQuitFlag) == 0) {
        if (g_kr_in_wait) g_kr_parked = true;
        return 0;   /* the vblank's keyread wake: the main thread drives keyread now */
    }
    if (g_bypass && id == rd32(kFrameSemPtr)) return 0;   /* re-simulating: vblank posts must not pile up */
    return g_orig_post(ctx);
}
bool keyread_parked()
{
    if (g_mode != Mode::Test) return false;
    if (!rd32(kKeyreadSemPtr)) return false;
    if (!g_swallow) { g_swallow = true; return false; }
    return g_kr_parked.load();
}
void set_sim_frame(uint32_t f) { g_sim_frame = f; sound_begin_frame(f, g_bypass.load()); }
uint32_t sim_frame() { return g_sim_frame.load(std::memory_order_relaxed); }
void set_bypass(bool on) { g_bypass = on; }
bool bypass_on() { return g_bypass.load(std::memory_order_relaxed); }
constexpr uint32_t kSoundEnablePtrSlot = 0x470540u - 0x61E8u;   /* TOC slot -> pointer to the word */
uint32_t g_sound_word = 0, g_sound_saved = 0;
bool g_sound_skipped = false;
uint32_t sound_word() { if (!g_sound_word) g_sound_word = rd32(kSoundEnablePtrSlot); return g_sound_word; }
void sound_skip(bool on)
{
    const uint32_t w = sound_word();
    if (!w || on == g_sound_skipped) return;
    if (on && sound_mode() != SoundMode::Skip) return;   /* resim / raw: the update runs in re-simulated frames */
    /* The word is in the rollback state: a frame committed while it was
     * zeroed (a re-simulated frame) restores it as zero, so the value put
     * back is the last live one, not whatever the restore left (k0c: the
     * joiner's sound update stayed off after such a rollback, its round-end
     * music stop was never issued and the fight phase never advanced). */
    if (on) { const uint32_t v = rd32(w); if (v) g_sound_saved = v; wr32(w, 0); }
    else if (g_sound_saved) wr32(w, g_sound_saved);
    g_sound_skipped = on;
}

void install_syscall_hooks()
{
    bool expected = false;
    if (!g_installed.compare_exchange_strong(expected, true)) return;
    g_orig_wait = g_lv2_syscalls.handlers[SC_SEM_WAIT];
    g_lv2_syscalls.handlers[SC_SEM_WAIT] = w_sem_wait;
    g_orig_post = g_lv2_syscalls.handlers[SC_SEM_POST];
    g_lv2_syscalls.handlers[SC_SEM_POST] = w_sem_post;
    note("frame-boundary hook installed (sys_semaphore_wait)");
}

void h_cellPadInit(ppu_context* ctx)
{
    int32_t r = cellPadInit((uint32_t)ctx->gpr[3]);
    ctx->gpr[3] = (uint64_t)(int64_t)r;
    install_syscall_hooks();
}

struct Register {
    Register()
    {
        const char* m = getenv("T5_RB_MODE");
        /* online (T5_NET_MODE set) and nothing else asked for: the rollback loop
         * is offered to the peer (rb_net.cpp); its hooks are harmless until the
         * handshake agrees on it */
        if ((!m || !*m) && getenv("T5_NET_MODE") && *getenv("T5_NET_MODE")) m = "net";
        if ((!m || !*m) && getenv("T5_CTL_DIR") && *getenv("T5_CTL_DIR")) m = "net";   /* a persistent game: sessions come later */
        if (!m || !*m) return;
        if (!strcmp(m, "lockstep") || !strcmp(m, "off")) return;
        /* The rollback state needs the guest memory reserved with write
         * watch, which the runtime decides in main() from PS3_VM_WRITE_WATCH:
         * whenever this side will offer rollback (or a test mode runs), it is
         * switched on here, before main. */
        {
            /* Through the OS environment, not getenv(): the runtime's getenv
             * caches every answer, a miss too (boot_main.cpp cached_getenv),
             * and main() reads this one from that cache. */
            const bool needs = strcmp(m, "net") ? true : net::offered_by_env();
            char ww[8] = "";
            GetEnvironmentVariableA("PS3_VM_WRITE_WATCH", ww, sizeof ww);
            if (needs && ww[0] != '1') {
                SetEnvironmentVariableA("PS3_VM_WRITE_WATCH", "1");
                _putenv_s("PS3_VM_WRITE_WATCH", "1");
                fputs("[rb] PS3_VM_WRITE_WATCH=1 (the rollback state needs the write watch)\n", stderr);
            }
        }
        if (!strcmp(m, "measure")) g_mode = Mode::Measure;
        else if (!strcmp(m, "test")) g_mode = Mode::Test;
        else if (!strcmp(m, "net")) g_mode = Mode::Net;
        else { fprintf(stderr, "[rb] unknown T5_RB_MODE %s\n", m); return; }
        const char* lf = getenv("T5_RB_LOG");
        g_log = fopen(lf && *lf ? lf : "rb_frames.log", "w");
        if (g_mode == Mode::Net) {
            /* Rollback netplay: the pad and frame hooks are netplay's
             * (src/netplay/t5_hooks.cpp calls rb::net at every boundary); here
             * only the GPU-handshake bypass for re-simulated frames and the
             * draw cut are installed. */
            note("mode net: rollback netplay loop (needs T5_NET_MODE=host|join|local)");
            ps3_hle_register_ctx(NID_cellGcmSetUserCommand, "cellGcmSetUserCommand(rb)", h_cellGcmSetUserCommand);
            ps3_hle_register_ctx(NID_cellGcmSetFlip, "cellGcmSetFlip(rb)", h_cellGcmSetFlip);
            ps3_hle_register_ctx(NID_cellGcmGetFlipStatus, "cellGcmGetFlipStatus(rb)", h_cellGcmGetFlipStatus);
            ps3_hle_register_ctx(NID_cellGcmResetFlipStatus, "cellGcmResetFlipStatus(rb)", h_cellGcmResetFlipStatus);
            ps3_hle_register_ctx(NID_cellGcmSetWaitFlip, "cellGcmSetWaitFlip(rb)", h_cellGcmSetWaitFlip);
            icall_install();
            sound_install();
            dcut_install();
            return;
        }
        g_script[0] = parse_script(getenv("T5_RB_SCRIPT"));
        g_script[1] = parse_script(getenv("T5_RB_SCRIPT2"));
        note("mode %s, %zu + %zu scripted presses", m, g_script[0].size(), g_script[1].size());
        ps3_hle_register_ctx(NID_cellPadInit,    "cellPadInit(rb)",    h_cellPadInit);
        /* With a direct fight configured (T5_FIGHT), src/directfight owns the pad
         * overrides (it drives the menus); the test mode then feeds its fight
         * script through df::inject() per logical frame instead. */
        g_df = (getenv("T5_FIGHT") && *getenv("T5_FIGHT")) || (getenv("T5_FIGHT_FILE") && *getenv("T5_FIGHT_FILE"));
        if (!g_df) {
            ps3_hle_register_ctx(NID_cellPadGetInfo, "cellPadGetInfo(rb)", h_cellPadGetInfo);
            ps3_hle_register_ctx(NID_cellPadGetData, "cellPadGetData(rb)", h_cellPadGetData);
        }
        ps3_hle_register_ctx(NID_cellGcmSetUserCommand, "cellGcmSetUserCommand(rb)", h_cellGcmSetUserCommand);
        ps3_hle_register_ctx(NID_cellGcmSetFlip, "cellGcmSetFlip(rb)", h_cellGcmSetFlip);
        ps3_hle_register_ctx(NID_cellGcmGetFlipStatus, "cellGcmGetFlipStatus(rb)", h_cellGcmGetFlipStatus);
        ps3_hle_register_ctx(NID_cellGcmResetFlipStatus, "cellGcmResetFlipStatus(rb)", h_cellGcmResetFlipStatus);
        ps3_hle_register_ctx(NID_cellGcmSetWaitFlip, "cellGcmSetWaitFlip(rb)", h_cellGcmSetWaitFlip);
        g_on_frame = (g_mode == Mode::Measure) ? measure_on_frame : test_on_frame;
        if (g_mode == Mode::Test) { icall_install(); sound_install(); dcut_install(); }   /* before any guest thread runs */
    }
} g_register;

/* accessors for the other translation units */
Mode mode() { return g_mode; }
uint32_t frame() { return g_frame.load(); }
PadInput script_input(int port, uint32_t f) { return scripted(port, f); }
void set_override(const PadInput* in) { if (in) { g_override[0] = in[0]; g_override[1] = in[1]; g_override_on = true; } else g_override_on = false; }
uint64_t gcall(uint32_t code, uint64_t a0, uint64_t a1) { return ppu_guest_call_ct(code, kTOC, a0, a1, 0, 0, 0, 0, 0, 0); }

} // namespace rb
