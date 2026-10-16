/*
 * T5DR netplay prototype -- where the lockstep core meets Tekken 5 DR
 * (NPUB30009 v01.00). All guest addresses below are for that exact EBOOT.
 *
 * How the game reads the pads (from its code):
 *   - A thread named "keyread" (code 0x120B68) loops on a semaphore whose id
 *     lives at 0x104CB5C0. Each wake it updates every pad (cellPadGetInfo +
 *     cellPadGetData per connected port, 0x375538), converts ports 0 and 1
 *     into a 16-bit game mask each (0x8F6F0) and stores them in a 16-entry
 *     ring (0x104CCDFC: P1 u16[16], P2 u16[16]; write index 0x104CCE3C).
 *   - The keyread semaphore is posted from the VBlank handler (0x34BC08 runs
 *     a callback list; 0x2598A8 posts it), i.e. on WALL-CLOCK vblanks.
 *   - The main loop samples the newest ring entry once per frame (0x12D74 ->
 *     0x120A78, read index 0x104CCE40) and computes its own press edges. It
 *     paces itself on a semaphore (id at 0x106D4A30) that the same VBlank
 *     handler posts: 0x34BAA0 waits for the flip, then sys_semaphore_wait on it.
 *
 * So which pad sample a game frame sees depends on a race between two threads
 * woken by the same vblank. For lockstep that has to go: with netplay on, the
 * vblank's keyread post is swallowed and the MAIN thread runs exactly one
 * keyread tick at the top of each of its frames (right after its frame
 * semaphore wait returns), with both players' inputs for that frame already
 * decided by the lockstep core. One tick per frame, always at the same point.
 *
 * Hooks used (no ps3recomp changes):
 *   - HLE overrides (ps3_hle_register_ctx is dispatched before the NID table):
 *     cellPadInit, cellPadGetInfo (always exactly two pads), cellPadGetData.
 *   - lv2 syscall table wrappers for sys_semaphore_wait (92) and
 *     sys_semaphore_post (94), installed from our cellPadInit (after
 *     lv2_init_syscalls has filled the table).
 *
 * Diagnostics (all optional):
 *   T5_NET_HASH      regions hashed into the per-frame state hash,
 *                    "addr:len,addr:len" (hex). Default: see kDefaultHash.
 *   T5_NET_PAGEHASH  "addr:len[:every]" (hex, every in frames, default 60):
 *                    write per-4KB-page hashes of that range to the frame log.
 *   T5_NET_DUMP      comma-separated frames at which to dump memory to
 *                    np_dump_f<frame>_<addr>.bin in the working directory.
 *   T5_NET_DUMP_RANGES  "addr:len,..." (hex) for T5_NET_DUMP.
 *   T5_NET_TRACE=1   log semaphore traffic and allocations.
 */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdlib.h>
#include <atomic>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>

#include "ppu_recomp.h"   /* ppu_context, vm_base -- from the lifter output */
#include "netplay.h"

extern "C" {
void    ps3_hle_register_ctx(uint32_t nid, const char* name, void (*fn)(ppu_context*));
int32_t cellPadInit(uint32_t max_connect);           /* ps3recomp libs/input/cellPad.c */
int32_t cellPadGetInfo(void* info_guest);
int32_t cellPadGetData(uint32_t port, void* data_guest);
uint64_t ppu_guest_call_ct(uint32_t code, uint32_t toc, uint64_t a0, uint64_t a1, uint64_t a2,
                           uint64_t a3, uint64_t a4, uint64_t a5, uint64_t a6, uint64_t a7);
typedef int64_t (*np_lv2_fn)(ppu_context*);
extern np_lv2_fn g_lv2_syscalls[];                   /* lv2_syscall_table { handlers[1024] } */
}

namespace {

/* ---- guest addresses (NPUB30009 v01.00) ---------------------------------- */
constexpr uint32_t kKeyreadSemPtr = 0x104CB5C0;  /* u32 semaphore id */
constexpr uint32_t kKeyreadQuit   = 0x104CCDF4;  /* keyread object + 0x1814: thread exit flag */
constexpr uint32_t kFrameSemPtr   = 0x106D4A30;  /* graphics object + 0x30: per-frame semaphore id */
constexpr uint32_t kKeyreadObj    = 0x104CB5E0;  /* keyread thread's object (arg) */
constexpr uint32_t kRingResetFlag = 0x104CCDF8;
constexpr uint32_t kRing          = 0x104CCDFC;  /* u16 P1[16], u16 P2[16] */
constexpr uint32_t kRingWriteIdx  = 0x104CCE3C;
constexpr uint32_t kRingReadIdx   = 0x104CCE40;
constexpr uint32_t kFrameClock    = 0x106D4D88;  /* u64 read by the pad repeat logic; +8: vblank count */
constexpr uint32_t kTOC           = 0x470540;    /* main TOC (r2) */
constexpr uint32_t kFnTickCounter = 0x09A204;
constexpr uint32_t kFnPadUpdate   = 0x08F3A4;
constexpr uint32_t kFnRingReset   = 0x120764;
constexpr uint32_t kFnPortMask    = 0x08F6F0;
constexpr uint32_t kFnRingAdvance = 0x12071C;
constexpr uint32_t kFnTickTail    = 0x13F91C;

constexpr uint32_t NID_cellPadInit    = 0x1CF98800;
constexpr uint32_t NID_cellPadGetInfo = 0x3AAAD464;
constexpr uint32_t NID_cellPadGetData = 0x8B72CDA1;

constexpr int SC_SEM_WAIT = 92, SC_SEM_POST = 94, SC_MEM_ALLOC = 348;

/* ---- guest memory (big-endian) -------------------------------------------- */
inline uint32_t rd32(uint32_t a) { uint32_t v; memcpy(&v, vm_base + a, 4); return _byteswap_ulong(v); }
inline uint64_t rd64(uint32_t a) { uint64_t v; memcpy(&v, vm_base + a, 8); return _byteswap_uint64(v); }
inline void wr32(uint32_t a, uint32_t v) { v = _byteswap_ulong(v); memcpy(vm_base + a, &v, 4); }
inline void wr16(uint32_t a, uint16_t v) { v = _byteswap_ushort(v); memcpy(vm_base + a, &v, 2); }
inline void wr8(uint32_t a, uint8_t v) { vm_base[a] = v; }

uint64_t fnv64(const uint8_t* p, size_t n, uint64_t h = 1469598103934665603ull)
{
    for (size_t i = 0; i < n; i++) { h ^= p[i]; h *= 1099511628211ull; }
    return h;
}

struct Range { uint32_t addr, len; };
std::vector<Range> parse_ranges(const char* spec)
{
    std::vector<Range> r;
    if (!spec) return r;
    const char* p = spec;
    while (*p) {
        char* e;
        uint32_t a = (uint32_t)strtoul(p, &e, 16); if (e == p || *e != ':') break; p = e + 1;
        uint32_t l = (uint32_t)strtoul(p, &e, 16); if (e == p) break; p = e;
        r.push_back({ a, l });
        while (*p == ',' || *p == ' ') p++;
    }
    return r;
}

/* ---- state ----------------------------------------------------------------- */
np_lv2_fn g_orig_wait = nullptr, g_orig_post = nullptr, g_orig_alloc = nullptr;
std::atomic<bool> g_installed{ false };
std::atomic<bool> g_active{ false };          /* lockstep running: ticks are ours */
std::atomic<bool> g_swallow{ false };         /* vblank wakes of keyread are dropped */
std::atomic<uint32_t> g_kr_enter{ 0 }, g_kr_wake{ 0 };
std::atomic<int> g_kr_in_wait{ 0 };
std::atomic<uint32_t> g_swallowed{ 0 };
HANDLE g_kr_event = nullptr;                  /* set when keyread re-enters its wait */
uint32_t g_frame = 0;                          /* next lockstep frame (main thread only) */
uint64_t g_main_tid = ~0ull;
np::PadInput g_cur[2] = { np::kNeutral, np::kNeutral };
bool g_trace = false;
bool g_passive = false;   /* T5_NET_PASSIVE=1: pad overrides only, keyread untouched (reference runs) */
int  g_pads = 2;          /* T5_NET_PADS: pads reported connected (2 for netplay) */

std::vector<Range> g_hash_ranges, g_dump_ranges;
std::vector<uint32_t> g_dump_frames;
Range g_page_range = { 0, 0 };
uint32_t g_page_every = 60;

/* What goes into the per-frame state hash by default. Kept to memory whose
 * contents follow from the inputs; see docs/NETPLAY.md for how the regions
 * were found. */
const char* kDefaultHash =
    "10099F24:70,"      /* the game's two pad state blocks (56 B each) */
    "104CCDFC:40";      /* the P1/P2 input ring */

/* ---- the pad, as the game sees it ------------------------------------------ */

void write_pad_data(uint32_t ea, const np::PadInput& in)
{
    const int len = 8;   /* CELL_PAD_LEN_CHANGE_DEFAULT: the title never enables press/sensor mode */
    wr32(ea, (uint32_t)len);
    for (int i = 0; i < 64; i++) wr16(ea + 4 + i * 2, 0);
    wr16(ea + 4 + 1 * 2, (uint16_t)(0x70 | (len / 2)));
    wr16(ea + 4 + 2 * 2, (uint16_t)(in.buttons & 0xFF));         /* DIGITAL1 */
    wr16(ea + 4 + 3 * 2, (uint16_t)(in.buttons >> 8));           /* DIGITAL2 */
    wr16(ea + 4 + 4 * 2, in.rx);
    wr16(ea + 4 + 5 * 2, in.ry);
    wr16(ea + 4 + 6 * 2, in.lx);
    wr16(ea + 4 + 7 * 2, in.ly);
}

void h_cellPadGetData(ppu_context* ctx)
{
    uint32_t port = (uint32_t)ctx->gpr[3], ea = (uint32_t)ctx->gpr[4];
    if (!ea) { ctx->gpr[3] = (uint64_t)(int64_t)(int32_t)0x80121104; return; }   /* INVALID_PARAMETER */
    if (g_passive && port < (uint32_t)g_pads) {
        write_pad_data(ea, np::poll_now((int)port));
    } else if (port < 2) {
        write_pad_data(ea, g_active ? g_cur[port] : np::kNeutral);
    } else {
        wr32(ea, 0);   /* nothing connected there */
    }
    ctx->gpr[3] = 0;
}

/* CellPadInfo (v1): max_connect, now_connect, system_info, vendor_id[127] at
 * 0x0C, product_id[127] at 0x10A, status[127] at 0x208. Both instances must
 * see the same pads, so it is always exactly two DUALSHOCK 3s, whatever is
 * plugged into this PC. */
void h_cellPadGetInfo(ppu_context* ctx)
{
    uint32_t ea = (uint32_t)ctx->gpr[3];
    int32_t r = cellPadGetInfo((void*)(uintptr_t)ea);
    if (r == 0 && ea) {
        wr32(ea + 0x04, (uint32_t)g_pads);
        wr32(ea + 0x08, 0);
        for (uint32_t i = 0; i < 7; i++) {
            const bool on = i < (uint32_t)g_pads;
            wr16(ea + 0x00C + i * 2, on ? 0x054C : 0);
            wr16(ea + 0x10A + i * 2, on ? 0x0268 : 0);
            wr8(ea + 0x208 + i, on ? 1 : 0);
        }
    }
    ctx->gpr[3] = (uint64_t)(int64_t)r;
}

/* ---- per-frame hook ---------------------------------------------------------- */

uint64_t state_hash()
{
    uint64_t h = 1469598103934665603ull;
    for (const Range& r : g_hash_ranges) h = fnv64(vm_base + r.addr, r.len, h);
    return h;
}

void page_hashes(uint32_t f)
{
    if (!g_page_range.len || (f % g_page_every) != 0) return;
    std::string line = "P ";
    char tmp[16];
    snprintf(tmp, sizeof tmp, "%08X", g_page_range.addr); line += tmp;
    for (uint32_t a = g_page_range.addr; a < g_page_range.addr + g_page_range.len; a += 0x1000) {
        uint64_t h = fnv64(vm_base + a, 0x1000);
        snprintf(tmp, sizeof tmp, " %08x", (uint32_t)(h ^ (h >> 32)));
        line += tmp;
    }
    np::log_extra(f, line.c_str());
}

void dump_memory(uint32_t f)
{
    for (uint32_t df : g_dump_frames) {
        if (df != f) continue;
        for (const Range& r : g_dump_ranges) {
            char path[256];
            snprintf(path, sizeof path, "np_dump_f%06u_%08X.bin", f, r.addr);
            FILE* fp = fopen(path, "wb");
            if (!fp) continue;
            fwrite(vm_base + r.addr, 1, r.len, fp);
            fclose(fp);
        }
        np::note("frame %u: memory dumped (%zu range(s))", f, g_dump_ranges.size());
    }
}

uint64_t gcall(uint32_t code, uint64_t a0 = 0)
{
    return ppu_guest_call_ct(code, kTOC, a0, 0, 0, 0, 0, 0, 0, 0);
}

/* One keyread tick (the body of the loop at 0x120BE0..0x120C90), run on the
 * MAIN thread at the top of its frame. It cannot be handed to the keyread
 * thread and waited for: the pad update takes the lwmutex at 0x106D4D00
 * (to read the frame clock at 0x106D4D88), which the main thread holds while
 * it waits for its frame. Run here, that lock is a recursive re-lock. The
 * ring store skips the ring's lwmutex: the only other user of the ring is the
 * main thread itself (0x120A78) and the real keyread thread is parked. */
void keyread_tick()
{
    if (rd32(kKeyreadQuit)) return;
    gcall(kFnTickCounter);                       /* 0x9A204: 60-tick countdown */
    wr32(kKeyreadObj + 0x1810, 0);
    gcall(kFnPadUpdate);                         /* 0x8F3A4: cellPadGetInfo/GetData, port states */
    if (rd32(kRingResetFlag)) gcall(kFnRingReset);
    const uint32_t slot = (rd32(kRingWriteIdx) & 15) * 2;
    const uint16_t m0 = (uint16_t)gcall(kFnPortMask, 0);
    wr16(kRing + slot, m0);
    const uint16_t m1 = (uint16_t)gcall(kFnPortMask, 1);
    wr16(kRing + 0x20 + slot, m1);
    gcall(kFnRingAdvance);                       /* 0x12071C: write index++ */
    gcall(kFnTickTail);                          /* 0x13F91C */
}

void on_frame_start(ppu_context* ctx)
{
    if (!g_active) {
        /* Take over once the keyread thread exists and is parked in its wait
         * (not half-way through a tick of its own). It usually is not: its
         * tick blocks on the lwmutex this thread holds right now. So stop
         * its wakes first; it parks after the tick in flight. */
        if (!rd32(kKeyreadSemPtr)) return;
        g_swallow = true;
        if (!g_kr_in_wait.load()) return;
        g_main_tid = ctx->thread_id;
        g_active = true;
        np::note("keyread thread is parked (sem %u); lockstep from here, main thread tid %llu",
                 rd32(kKeyreadSemPtr), (unsigned long long)g_main_tid);
    }
    if (ctx->thread_id != g_main_tid) {
        static int n = 0;
        if (n++ < 5) np::note("frame semaphore waited by tid %llu (main is %llu) -- ignored",
                              (unsigned long long)ctx->thread_id, (unsigned long long)g_main_tid);
        return;
    }
    const uint32_t f = g_frame++;
    const uint64_t h = state_hash();
    page_hashes(f);
    dump_memory(f);
    np::PadInput in[2];
    np::begin_frame(f, h, in);
    g_cur[0] = in[0];
    g_cur[1] = in[1];
    keyread_tick();
    char extra[128];
    snprintf(extra, sizeof extra, "R%u W%u S%u T%llu V%llu", rd32(kRingReadIdx), rd32(kRingWriteIdx),
             g_swallowed.load(), (unsigned long long)rd64(kFrameClock), (unsigned long long)rd64(kFrameClock + 8));
    np::log_extra(f, extra);
}

/* ---- syscall wrappers ---------------------------------------------------------- */

int64_t w_sem_wait(ppu_context* ctx)
{
    const uint32_t id = (uint32_t)ctx->gpr[3];
    const uint32_t kr = rd32(kKeyreadSemPtr);
    if (kr && id == kr) {
        g_kr_in_wait = 1;
        g_kr_enter++;
        SetEvent(g_kr_event);
        int64_t r = g_orig_wait(ctx);
        g_kr_in_wait = 0;
        g_kr_wake++;
        return r;
    }
    int64_t r = g_orig_wait(ctx);
    const uint32_t fs = rd32(kFrameSemPtr);
    if (g_trace) {
        static std::atomic<int> n{ 0 };
        if (n++ < 40) np::note("sem_wait id=%u tid=%llu (frame sem %u, keyread sem %u)", id,
                               (unsigned long long)ctx->thread_id, fs, kr);
    }
    if (fs && id == fs && r == 0) on_frame_start(ctx);
    return r;
}

int64_t w_sem_post(ppu_context* ctx)
{
    const uint32_t id = (uint32_t)ctx->gpr[3];
    if (g_swallow && id == rd32(kKeyreadSemPtr) && rd32(kKeyreadQuit) == 0) {
        g_swallowed++;
        return 0;   /* the vblank's keyread wake: the main loop drives keyread now */
    }
    return g_orig_post(ctx);
}

int64_t w_mem_alloc(ppu_context* ctx)
{
    const uint32_t size = (uint32_t)ctx->gpr[3], out = (uint32_t)ctx->gpr[5];
    int64_t r = g_orig_alloc(ctx);
    if (r == 0 && out) np::note("sys_memory_allocate(0x%X) -> 0x%08X", size, rd32(out));
    return r;
}

void install_syscall_hooks()
{
    bool expected = false;
    if (!g_installed.compare_exchange_strong(expected, true)) return;
    g_kr_event = CreateEventA(nullptr, FALSE, FALSE, nullptr);
    g_orig_wait = g_lv2_syscalls[SC_SEM_WAIT];
    g_orig_post = g_lv2_syscalls[SC_SEM_POST];
    g_lv2_syscalls[SC_SEM_WAIT] = w_sem_wait;
    g_lv2_syscalls[SC_SEM_POST] = w_sem_post;
    if (g_trace) {
        g_orig_alloc = g_lv2_syscalls[SC_MEM_ALLOC];
        g_lv2_syscalls[SC_MEM_ALLOC] = w_mem_alloc;
    }
    np::note("semaphore hooks installed");
}

void h_cellPadInit(ppu_context* ctx)
{
    int32_t r = cellPadInit((uint32_t)ctx->gpr[3]);
    ctx->gpr[3] = (uint64_t)(int64_t)r;
    np::init();
    if (!np::enabled()) return;
    const char* hs = getenv("T5_NET_HASH");
    g_hash_ranges = parse_ranges(hs ? hs : kDefaultHash);
    if (const char* p = getenv("T5_NET_PAGEHASH")) {
        std::vector<Range> pr = parse_ranges(p);
        if (!pr.empty()) {
            g_page_range = pr[0];
            const char* e = strchr(strchr(p, ':') + 1, ':');
            if (e) g_page_every = (uint32_t)strtoul(e + 1, nullptr, 10);
            if (!g_page_every) g_page_every = 60;
        }
    }
    if (const char* d = getenv("T5_NET_DUMP")) {
        for (const char* p = d; *p;) {
            char* e; unsigned long v = strtoul(p, &e, 10);
            if (e == p) break;
            g_dump_frames.push_back((uint32_t)v);
            p = e; while (*p == ',') p++;
        }
        const char* dr = getenv("T5_NET_DUMP_RANGES");
        g_dump_ranges = parse_ranges(dr ? dr : "10000000:760000");
    }
    if (g_passive) { np::note("passive reference mode: %d pad(s), keyread left alone", g_pads); return; }
    install_syscall_hooks();
}

struct Register {
    Register()
    {
        const char* m = getenv("T5_NET_MODE");
        if (!m || !*m) return;   /* netplay off: register nothing, change nothing */
        const char* t = getenv("T5_NET_TRACE");
        g_trace = t && *t == '1';
        const char* pv = getenv("T5_NET_PASSIVE");
        g_passive = pv && *pv == '1';
        const char* pd = getenv("T5_NET_PADS");
        if (pd && (*pd == '1' || *pd == '2')) g_pads = *pd - '0';
        ps3_hle_register_ctx(NID_cellPadInit,    "cellPadInit(netplay)",    h_cellPadInit);
        ps3_hle_register_ctx(NID_cellPadGetInfo, "cellPadGetInfo(netplay)", h_cellPadGetInfo);
        ps3_hle_register_ctx(NID_cellPadGetData, "cellPadGetData(netplay)", h_cellPadGetData);
    }
} g_register;

} // namespace
