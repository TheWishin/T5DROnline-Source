/*
 * T5_RB_MODE=test: rollback save / restore / re-simulate test (docs/ROLLBACK.md).
 *
 * Runs the game normally with scripted pads. From T5_RB_START on, at the frame
 * boundary (main thread, right after its per-frame semaphore wait returned,
 * i.e. just before the sim of logical frame f runs):
 *   - every frame: hash H[f] of the state regions (incremental: only the pages
 *     the kernel reports dirty since the previous boundary are rehashed)
 *   - every T5_RB_SAVE_EVERY frames: snapshot the state regions
 *   - T5_RB_RESIM frames after a snapshot: restore it, check the hash equals
 *     H[F], and re-simulate the N frames with the same inputs, with the
 *     present/flip/semaphore waits bypassed. At each re-simulated boundary
 *     the hash is compared with the one the uninterrupted run recorded. Then
 *     the game continues normally from the re-simulated state.
 *
 * Pad input is deterministic per logical frame: the keyread thread is parked
 * (its vblank wakes are swallowed) and its tick runs on the main thread at
 * every boundary with the script's input for that frame (np's finding).
 */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <vector>
#include <algorithm>

#include "rb.h"

extern "C" uint8_t* vm_base;

namespace rb {

namespace {

/* ---- state regions (NPUB30009 v01.00, this runtime's memory map) ------------ */
struct Range { uint32_t base, len; };
/* Snapshot set S: everything the main thread's simulation can touch. */
const Range kSave[] = {
    { 0x0E000000u, 0x00020000u },   /* 2 pages written per frame (lv2/liblv2 data?) */
    { 0x0F800000u, 0x00010000u },   /* 1 page written per frame */
    { 0x0FEF0000u, 0x00010000u },   /* main thread stack */
    { 0x10000000u, 0x00770000u },   /* ELF data + bss */
    { 0x10F00000u, 0x000F0000u },   /* TLS blocks (main thread's scene pointer lives here) */
    { 0x40000000u, 0x05F00000u },   /* the game's heap (sys_memory_allocate) */
};
/* Exclusions E: written by other threads asynchronously (sound core, audio
 * output, decoder); neither restored nor hashed. */
const Range kExclude[] = {
    { 0x10114000u, 0x00058000u },   /* sound core mix/output area (bnusCore) */
    { 0x40000000u, 0x00100000u },   /* the first heap chunk: sound system (bnusCore) voice slots, requests,
                                     * shared areas -- written by the sound threads asynchronously */
    { 0x45F00000u, 0x00100000u },   /* decoder / streaming */
};
bool excluded_page(uint32_t ea)
{
    for (const Range& r : kExclude) if (ea >= r.base && ea < r.base + r.len) return true;
    return false;
}
/* Restored but not hashed: rebuilt every frame from the state (render data),
 * and either legitimately different after a re-simulation with the GPU
 * handshake bypassed (the GCM command buffer) or not state at all. */
const Range kHashExclude[] = {
    { 0x0FEF0000u, 0x00010000u },   /* main thread stack: only the present chain's locals live there at the boundary */
    { 0x10532000u, 0x00001000u },   /* engine bookkeeping: request counters, vblank copies (follow the draw phase) */
    { 0x10750000u, 0x00003000u },   /* NU::File::RequestManager object and request list (requests issued by the draw) */
    { 0x400CA000u, 0x00011000u },   /* per-frame handoff ring written by the main thread (slot state follows the consumer) */
    { 0x40100000u, 0x00400000u },   /* GCM command buffer ring (cellGcmInit: begin 0x40100000, end 0x40500000) */
    { 0x43D00000u, 0x00340000u },   /* draw lists, buffers A (0x43D00000) and B (0x43EA0000), with their link pages */
    { 0x444F9000u, 0x0006E000u },   /* per-frame render scratch, written every frame */
};
std::vector<Range> g_hash_exclude_dyn;   /* T5_RB_HASH_EXCLUDE=addr:len,... (hex) */
bool hash_excluded_page(uint32_t ea)
{
    for (const Range& r : kHashExclude) if (ea >= r.base && ea < r.base + r.len) return true;
    for (const Range& r : g_hash_exclude_dyn) if (ea >= r.base && ea < r.base + r.len) return true;
    return false;
}

/* keyread (np's t5_hooks.cpp findings) */
constexpr uint32_t kKeyreadObj    = 0x104CB5E0;
constexpr uint32_t kKeyreadQuit   = 0x104CCDF4;
constexpr uint32_t kRingResetFlag = 0x104CCDF8;
constexpr uint32_t kRing          = 0x104CCDFC;
constexpr uint32_t kRingWriteIdx  = 0x104CCE3C;
constexpr uint32_t kFnTickCounter = 0x09A204;
constexpr uint32_t kFnPadUpdate   = 0x08F3A4;
constexpr uint32_t kFnRingReset   = 0x120764;  /* the loop's reset path (0x120CFC); 0x120D2C is a no-op */
constexpr uint32_t kFnPortMask    = 0x08F6F0;
constexpr uint32_t kFnRingAdvance = 0x12071C;
constexpr uint32_t kFnTickTail    = 0x13F91C;
constexpr uint32_t kMinVblanks    = 0x106D4D98;  /* present pacing: min vblanks per frame (u64) */

/* ---- per-page hash bookkeeping --------------------------------------------- */
constexpr uint32_t kPages = 1u << 20;
uint64_t* g_page_hash = nullptr;
uint64_t  g_hash = 0;
std::vector<void*> g_ww;

/* Words inside the state that follow the wall clock, not the inputs: masked
 * out of the hash (still restored with their page). */
struct Mask { uint32_t ea, len; };
const Mask kMask[] = {
    { 0x106D4D90u, 0x18 },   /* vblank counter (vblank handler) + the copies present takes */
    { 0x106D4520u, 0xF0 },   /* render duration / GCM timestamp statistics */
    { 0x105320C4u, 0x04 },   /* vblank counter copies kept by side threads */
    { 0x10624720u, 0x30 },   /* frame duration statistics (microseconds, vblank counts) */
    { 0x1074F9F8u, 0x08 },   /* a timebase (mftb) stamp taken every frame */
    { 0x0F800008u, 0x04 },   /* CellGcmContextData.current: the FIFO write pointer */
    { 0x106D4A44u, 0x04 },   /* graphics object: flip/present pending flag (render handshake) */
    { 0x106D4BE0u, 0x10 },   /* vblank callback list lock: owner is the ticker thread at times */
    { 0x106CF0FCu, 0x04 },   /* TNUD::ASync progress counter, advanced by its thread */
    { 0x1062E454u, 0x08 },   /* engine statistics (two floats following the frame time) */
    { 0x10053800u, 0x100 },  /* 15 objects' double-buffer index (1/2): follows the flip, not the sim */
    { 0x40049210u, 0x04 },   /* double-buffer selector (0x10/0x20): follows the flip */
};
std::vector<Mask> g_mask_dyn;
inline uint64_t mix(uint64_t x) { x ^= x >> 31; x *= 0x9E3779B97F4A7C15ull; x ^= x >> 29; return x; }
uint64_t hash_page(uint32_t ea)
{
    const uint64_t* p = (const uint64_t*)(vm_base + ea);
    alignas(16) uint64_t tmp[512];
    for (const Mask& m : kMask) {
        if (m.ea >= ea && m.ea < ea + 0x1000) {
            if (p != tmp) { memcpy(tmp, p, 0x1000); p = tmp; }
            memset((uint8_t*)tmp + (m.ea - ea), 0, m.len);
        }
    }
    for (const Mask& m : g_mask_dyn) {
        if (m.ea >= ea && m.ea < ea + 0x1000) {
            if (p != tmp) { memcpy(tmp, p, 0x1000); p = tmp; }
            memset((uint8_t*)tmp + (m.ea - ea), 0, m.len);
        }
    }
    uint64_t h = 0x243F6A8885A308D3ull;
    for (int i = 0; i < 512; i++) { h ^= p[i]; h *= 0x9E3779B97F4A7C15ull; h ^= h >> 32; }
    return h;
}
inline uint64_t weight(uint32_t pg) { return mix((uint64_t)pg * 0xD6E8FEB86659FD93ull + 1); }

void hash_full()
{
    g_hash = 0;
    for (const Range& r : kSave)
        for (uint32_t ea = r.base; ea < r.base + r.len; ea += 0x1000) {
            uint32_t pg = ea >> 12;
            if (excluded_page(ea) || hash_excluded_page(ea)) { g_page_hash[pg] = 0; continue; }
            g_page_hash[pg] = hash_page(ea);
            g_hash += g_page_hash[pg] * weight(pg);
        }
}

/* Content of the pages written during the frame after the snapshot (the
 * uninterrupted run's frame F): the reference a re-simulated frame F must
 * reproduce exactly. */
struct Captured { uint32_t ea; uint64_t hash; uint8_t* data; };
constexpr uint32_t kCapFrames = 16, kCapPages = 16384;
std::vector<Captured> g_cap[kCapFrames];   /* per original frame F+k: the pages frame F+k-1 wrote */
uint32_t g_cap_frame0 = 0, g_cap_n = 0;    /* g_cap[k] is the content at the boundary of F+k+1 */
uint8_t* g_cap_buf = nullptr;
uint32_t g_cap_used = 0;
int g_capture_left = 0;
/* The original run's content of page ea at the boundary of logical frame f. */
const uint8_t* original_content(uint32_t ea, uint32_t f, uint64_t* h)
{
    int kmax = (int)std::min<uint32_t>(g_cap_n, f - g_cap_frame0);
    for (int k = kmax - 1; k >= 0; k--)
        for (const Captured& c : g_cap[k]) if (c.ea == ea) { if (h) *h = c.hash; return c.data; }
    return nullptr;
}

/* Rehash the pages written since the last call (kernel write-watch, reset). */
uint32_t hash_update()
{
    uint32_t n = 0;
    const bool capture = g_capture_left > 0;
    std::vector<Captured>* cap = nullptr;
    if (capture) { g_capture_left--; cap = &g_cap[g_cap_n++]; cap->clear(); }
    for (const Range& r : kSave) {
        for (uint64_t off = 0; off < r.len; off += (64ull << 20)) {
            uint64_t len = std::min<uint64_t>(64ull << 20, r.len - off);
            ULONG_PTR count = g_ww.size();
            DWORD gran = 0;
            if (GetWriteWatch(WRITE_WATCH_FLAG_RESET, vm_base + r.base + off, (SIZE_T)len, g_ww.data(), &count, &gran) != 0) {
                note("GetWriteWatch failed (%lu) -- PS3_VM_WRITE_WATCH=1 missing?", GetLastError());
                return 0;
            }
            for (ULONG_PTR i = 0; i < count; i++) {
                uint32_t ea = (uint32_t)((uint8_t*)g_ww[i] - vm_base);
                if (excluded_page(ea) || hash_excluded_page(ea)) continue;
                uint32_t pg = ea >> 12;
                uint64_t h = hash_page(ea);
                g_hash += (h - g_page_hash[pg]) * weight(pg);
                g_page_hash[pg] = h;
                if (capture && g_cap_used < kCapPages) {
                    uint8_t* d = g_cap_buf + (size_t)g_cap_used++ * 0x1000;
                    memcpy(d, vm_base + ea, 0x1000);
                    cap->push_back({ ea, h, d });
                }
                n++;
            }
        }
    }
    return n;
}

/* ---- snapshot ------------------------------------------------------------------ */
uint8_t* g_snap = nullptr;
uint64_t* g_snap_page_hash = nullptr;   /* per-page hashes at snapshot time */
size_t   g_snap_size = 0;
uint32_t g_snap_frame = 0;
uint64_t g_snap_hash = 0;
bool     g_have_snap = false;

void snapshot_alloc()
{
    g_snap_size = 0;
    for (const Range& r : kSave) g_snap_size += r.len;
    g_snap = (uint8_t*)VirtualAlloc(nullptr, g_snap_size, MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE);
    g_snap_page_hash = (uint64_t*)calloc(kPages, sizeof(uint64_t));
    g_cap_buf = (uint8_t*)VirtualAlloc(nullptr, (size_t)kCapPages * 0x1000, MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE);
}
const uint8_t* snap_ptr(uint32_t ea)
{
    size_t off = 0;
    for (const Range& r : kSave) {
        if (ea >= r.base && ea < r.base + r.len) return g_snap + off + (ea - r.base);
        off += r.len;
    }
    return nullptr;
}
/* After re-simulating frame F: which pages differ from what the original
 * frame F produced (captured content for pages it wrote, the snapshot for
 * the rest), and where inside them. */
void diff_against_original(uint32_t f, int max_pages)
{
    int shown = 0, total = 0;
    for (const Range& r : kSave)
        for (uint32_t ea = r.base; ea < r.base + r.len; ea += 0x1000) {
            if (excluded_page(ea) || hash_excluded_page(ea)) continue;
            uint32_t pg = ea >> 12;
            uint64_t oh = g_snap_page_hash[pg];
            const uint8_t* ref = original_content(ea, f, &oh);
            if (!ref) ref = snap_ptr(ea);
            if (g_page_hash[pg] == oh) continue;
            total++;
            if (shown++ >= max_pages) continue;
            const uint32_t* a = (const uint32_t*)(vm_base + ea);
            const uint32_t* b = (const uint32_t*)ref;
            char line[400]; int n = 0, nd = 0;
            for (int i = 0; i < 1024 && n < 300; i++)
                if (a[i] != b[i]) { nd++; if (nd <= 12) n += snprintf(line + n, sizeof line - n, " +%03X:%08X/%08X", i * 4, _byteswap_ulong(a[i]), _byteswap_ulong(b[i])); }
            note("resim %u vs original: page %08X differs in %d words:%s", f, ea, nd, line);
        }
    note("resim %u vs original: %d page(s) differ", f, total);
}

/* Which pages differ from the snapshot right now, and where inside them. */
void diff_against_snapshot(const char* tag, int max_pages)
{
    int shown = 0, total = 0;
    for (const Range& r : kSave)
        for (uint32_t ea = r.base; ea < r.base + r.len; ea += 0x1000) {
            if (excluded_page(ea)) continue;
            uint32_t pg = ea >> 12;
            if (g_page_hash[pg] == g_snap_page_hash[pg]) continue;
            total++;
            if (shown++ >= max_pages) continue;
            const uint32_t* a = (const uint32_t*)(vm_base + ea);
            const uint32_t* b = (const uint32_t*)snap_ptr(ea);
            char line[400]; int n = 0, nd = 0;
            for (int i = 0; i < 1024 && n < 300; i++)
                if (a[i] != b[i]) { nd++; if (nd <= 12) n += snprintf(line + n, sizeof line - n, " +%03X:%08X/%08X", i * 4, _byteswap_ulong(a[i]), _byteswap_ulong(b[i])); }
            note("%s: page %08X differs in %d words:%s", tag, ea, nd, line);
        }
    note("%s: %d page(s) differ from the snapshot", tag, total);
}
double snapshot_save()
{
    LARGE_INTEGER f, a, b; QueryPerformanceFrequency(&f); QueryPerformanceCounter(&a);
    size_t off = 0;
    for (const Range& r : kSave) { memcpy(g_snap + off, vm_base + r.base, r.len); off += r.len; }
    memcpy(g_snap_page_hash, g_page_hash, kPages * sizeof(uint64_t));
    QueryPerformanceCounter(&b);
    return 1000.0 * (double)(b.QuadPart - a.QuadPart) / (double)f.QuadPart;
}
double snapshot_restore()
{
    LARGE_INTEGER f, a, b; QueryPerformanceFrequency(&f); QueryPerformanceCounter(&a);
    size_t off = 0;
    for (const Range& r : kSave) {
        for (uint32_t ea = r.base; ea < r.base + r.len; ea += 0x1000) {
            if (!excluded_page(ea)) memcpy(vm_base + ea, g_snap + off + (ea - r.base), 0x1000);
        }
        off += r.len;
    }
    QueryPerformanceCounter(&b);
    return 1000.0 * (double)(b.QuadPart - a.QuadPart) / (double)f.QuadPart;
}

/* ---- recorded history ------------------------------------------------------------ */
constexpr uint32_t kHist = 4096;
uint64_t g_hist_hash[kHist];
uint32_t g_hist_tag[kHist];

/* ---- control ----------------------------------------------------------------------- */
uint32_t g_start = 2700, g_save_every = 60, g_resim = 8, g_rollbacks_max = 1000000;
uint32_t g_logical = 0;          /* logical frame about to be simulated */
bool g_trace_on = false;         /* T5_RB_TRACE=1: syscall timeline of one normal and one resim frame */
bool g_sample = false;           /* T5_RB_SAMPLE=1: RIP samples of the main thread over the first resim */
int  g_trace_state = 0;
uint32_t g_resim_left = 0;       /* > 0: re-simulating */
uint32_t g_resim_target = 0;     /* logical frame at which the resim ends */
uint32_t g_rollbacks = 0, g_mismatches = 0, g_resim_frames = 0;
uint64_t g_saved_minvb = 1;
bool g_diag_done = false;
/* The main loop's call 0xAA1D4 -> 0xAA200 returns at once when the word its
 * TOC slot (r2 - 0x61E8) points to is zero. T5_RB_SKIPDRAW=1 zeroes it for
 * re-simulated frames. Measured: this does NOT remove the draw work -- the
 * word is zero even while the title screen renders, a "skipped" frame makes
 * the same NU resource-manager lock syscalls as a normal one and costs the
 * same CPU cycles. The draw packets are pushed from inside the scene update
 * (0x142300), interleaved with the logic. Kept as a switch; see
 * docs/ROLLBACK.md for what a real draw cut needs. */
constexpr uint32_t kDrawEnablePtrSlot = 0x470540u - 0x61E8u;   /* TOC slot -> pointer to the word */
bool g_skipdraw = false;
uint32_t g_draw_word = 0, g_draw_saved = 0;
LARGE_INTEGER g_qpf, g_last, g_resim_t0;
/* CPU time of this thread (QueryThreadCycleTime): the cost of a frame without
 * the wall-clock noise of other processes on the machine. */
ULONG64 g_cyc_last = 0, g_cyc_resim0 = 0, g_cyc_normal = 0;
uint32_t g_cyc_normal_n = 0;
ULONG64 cycles_now() { ULONG64 c = 0; QueryThreadCycleTime(GetCurrentThread(), &c); return c; }
bool g_inited = false;
double g_resim_ms_total = 0;

/* One keyread tick on the main thread (np's keyread_tick): samples the pads
 * (our override answers with the script for g_logical) into the ring. */
bool g_paddbg = false;
void keyread_tick()
{
    if (rd32(kKeyreadQuit)) return;
    gcall(kFnTickCounter);
    wr32(kKeyreadObj + 0x1810, 0);
    const uint32_t calls0 = pad_calls();
    gcall(kFnPadUpdate);
    if (rd32(kRingResetFlag)) gcall(kFnRingReset);
    const uint32_t slot = (rd32(kRingWriteIdx) & 15) * 2;
    const uint16_t m0 = (uint16_t)gcall(kFnPortMask, 0);
    const uint16_t m1 = (uint16_t)gcall(kFnPortMask, 1);
    if (g_paddbg && (g_logical % 100) < 3) {
        const PadInput in = script_input(0, g_logical);
        note("tick f=%u: pad calls +%u, script P1 %04X, game pad block %08X %08X, masks %04X %04X, wi %u ri %u reset %u",
             g_logical, pad_calls() - calls0, in.buttons, rd32(0x10099F24), rd32(0x10099F28), m0, m1,
             rd32(kRingWriteIdx), rd32(0x104CCE40), rd32(kRingResetFlag));
    }
    uint16_t be0 = _byteswap_ushort(m0), be1 = _byteswap_ushort(m1);
    memcpy(vm_base + kRing + slot, &be0, 2);
    memcpy(vm_base + kRing + 0x20 + slot, &be1, 2);
    gcall(kFnRingAdvance);
    gcall(kFnTickTail);
}

} // namespace

void test_on_frame(ppu_context* ctx)
{
    (void)ctx;
    LARGE_INTEGER now; QueryPerformanceCounter(&now);
    if (!g_inited) {
        g_inited = true;
        QueryPerformanceFrequency(&g_qpf);
        g_last = now;
        if (const char* e = getenv("T5_RB_START")) g_start = (uint32_t)atoi(e);
        if (const char* e = getenv("T5_RB_SAVE_EVERY")) g_save_every = (uint32_t)atoi(e);
        if (const char* e = getenv("T5_RB_RESIM")) g_resim = (uint32_t)atoi(e);
        if (const char* e = getenv("T5_RB_ROLLBACKS")) g_rollbacks_max = (uint32_t)atoi(e);
        if (const char* e = getenv("T5_RB_SKIPDRAW")) g_skipdraw = *e == '1';
        if (const char* e = getenv("T5_RB_PADDBG")) g_paddbg = *e == '1';
        if (const char* e = getenv("T5_RB_SAMPLE")) g_sample = *e == '1';
        if (const char* e = getenv("T5_RB_TRACE")) { g_trace_on = *e == '1'; if (g_trace_on) trace_install(); }
        g_draw_word = rd32(kDrawEnablePtrSlot);
        if (g_skipdraw && g_draw_word) {
            g_mask_dyn.push_back({ g_draw_word, 4 });
            note("draw-enable word at %08X (now %08X); re-simulated frames skip the draw phase", g_draw_word, rd32(g_draw_word));
        }
        g_page_hash = (uint64_t*)calloc(kPages, sizeof(uint64_t));
        g_ww.resize(1u << 16);
        snapshot_alloc();
        if (const char* e = getenv("T5_RB_HASH_EXCLUDE")) {
            const char* q = e;
            while (*q) {
                char* z; uint32_t a = (uint32_t)strtoul(q, &z, 16); if (z == q || *z != ':') break; q = z + 1;
                uint32_t l = (uint32_t)strtoul(q, &z, 16); if (z == q) break; q = z;
                g_hash_exclude_dyn.push_back({ a, l });
                while (*q == ',') q++;
            }
        }
        note("test mode: start %u, save every %u, resim %u frames, snapshot %zu MB", g_start, g_save_every,
             g_resim, g_snap_size >> 20);
        const uint32_t objs[] = { 0x1074BF00u, 0x107428B8u, 0x10751A28u, 0x106CD840u, 0x106D4510u, 0x106D4A00u, 0x106D4D00u };
        for (uint32_t o : objs) {
            char line[600]; int n = 0;
            for (int i = 0; i < 24; i++) n += snprintf(line + n, sizeof line - n, " %08X", rd32(o + i * 4));
            note("obj %08X:%s", o, line);
        }
    }
    const double dt_ms = 1000.0 * (double)(now.QuadPart - g_last.QuadPart) / (double)g_qpf.QuadPart;
    g_last = now;
    const ULONG64 cyc = cycles_now();
    const ULONG64 dcyc = cyc - g_cyc_last;
    g_cyc_last = cyc;

    /* Until the test starts the real keyread thread samples the (scripted)
     * pads on vblanks, as in measure mode -- that is what navigates the menus
     * into the fight. From g_start on the thread is parked and this thread
     * ticks it once per logical frame, so input is a function of the frame. */
    if (frame() < g_start) {
        g_logical = frame();
        set_sim_frame(g_logical);
        if ((g_logical % 100) == 0) {
            const uint32_t scene = rd32(0x10532DF0);
            logline("F %u pre-start scene %08X vtable %08X pad %04X ri %u wi %u", g_logical, scene,
                    scene ? rd32(scene) : 0, script_input(0, g_logical).buttons, rd32(0x104CCE40), rd32(0x104CCE3C));
        }
        return;
    }
    if (!keyread_parked()) {
        g_logical = frame();
        set_sim_frame(g_logical);
        return;                           /* until the keyread thread is parked, nothing else */
    }
    { static bool once = false; if (!once) { once = true; note("keyread parked at frame %u: the main thread ticks it from here", frame()); } }
    if (g_logical < g_start) { g_logical = frame(); }

    static bool hashed = false;
    uint32_t nre;
    if (!hashed) { hashed = true; hash_update(); hash_full(); nre = 0; note("state hash initialised at logical %u: %016llX", g_logical, (unsigned long long)g_hash); }
    else nre = hash_update();

    const uint32_t f = g_logical;
    if (g_trace_on && g_trace_state == 1) { trace_stop("normal frame"); g_trace_state = 2; }
    if (g_trace_on && g_trace_state == 3) { trace_stop("resim frame"); g_trace_state = 4; }
    if (g_trace_on && g_trace_state == 0 && f == g_start + 30) { g_trace_state = 1; }
    if (g_resim_left == 0) {
        /* uninterrupted run: record */
        g_hist_hash[f % kHist] = g_hash; g_hist_tag[f % kHist] = f + 1;
        if (f > g_start + 1) { g_cyc_normal += dcyc; g_cyc_normal_n++; }
        logline("F %u real %u dt %.2f cyc %.1fM rehashed %u hash %016llX vb %llu last %llu clk %llu tick %u anim %u cnt %u", f, frame(), dt_ms, dcyc / 1e6, nre,
                (unsigned long long)g_hash, (unsigned long long)rd64(0x106D4D90), (unsigned long long)rd64(0x106D4DA0),
                (unsigned long long)rd64(kFrameClock), rd32(0x1008EB9C), rd32(0x100900D4), rd32(0x1006404C));
        if (g_have_snap && f == g_snap_frame + g_resim && g_rollbacks < g_rollbacks_max) {
            /* ROLLBACK: restore F, re-simulate F..f-1 */
            double rms = snapshot_restore();
            uint32_t nr = hash_update();
            const bool ok = g_hash == g_snap_hash;
            note("ROLLBACK at %u -> %u: restore %.2f ms, %u pages rehashed, hash %016llX %s", f, g_snap_frame, rms, nr,
                 (unsigned long long)g_hash, ok ? "== snapshot" : "!= SNAPSHOT (restore not faithful)");
            if (!ok) { g_mismatches++; diff_against_snapshot("restore", 40); }
            g_rollbacks++;
            g_diag_done = false;
            g_have_snap = false;            /* one rollback per snapshot */
            g_resim_left = g_resim;
            g_resim_target = f;
            g_saved_minvb = rd64(kMinVblanks);
            wr32(kMinVblanks, 0); wr32(kMinVblanks + 4, 0);   /* no vblank pacing while re-simulating (u64) */
            if (g_skipdraw && g_draw_word) { g_draw_saved = rd32(g_draw_word); wr32(g_draw_word, 0); }
            set_bypass(true);
            QueryPerformanceCounter(&g_resim_t0);
            g_cyc_resim0 = cycles_now();
            /* re-run frame F now; the next boundary is logical F+1 */
            g_logical = g_snap_frame + 1;
            set_sim_frame(g_snap_frame);
            keyread_tick();
            if (g_trace_on && g_trace_state == 2) { g_trace_state = 3; trace_frame("resim frame"); }
            if (g_sample && g_rollbacks == 1) sample_start();
            return;
        }
        if ((f - g_start) % g_save_every == 0 && f + g_resim <= g_start + 100000) {
            double sms = snapshot_save();
            g_snap_frame = f; g_snap_hash = g_hash; g_have_snap = true;
            g_cap_frame0 = f; g_cap_n = 0; g_cap_used = 0;
            g_capture_left = (int)std::min<uint32_t>(g_resim, kCapFrames);
            note("SNAPSHOT at %u: %.2f ms, hash %016llX", f, sms, (unsigned long long)g_hash);
        }
        g_logical = f + 1;
        set_sim_frame(f);
        keyread_tick();
        if (g_trace_on && g_trace_state == 1) trace_frame("normal frame");
        return;
    }

    /* re-simulating: boundary of logical frame f (frame f-1 was just re-run) */
    g_resim_left--;
    g_resim_frames++;
    const bool known = g_hist_tag[f % kHist] == f + 1;
    const bool match = known && g_hist_hash[f % kHist] == g_hash;
    if (!match) { g_mismatches++; if (!g_diag_done) { g_diag_done = true; diff_against_original(f, 12); } }
    logline("R %u real %u dt %.2f cyc %.1fM rehashed %u hash %016llX %s vb %llu last %llu clk %llu tick %u anim %u cnt %u", f, frame(), dt_ms, dcyc / 1e6, nre,
            (unsigned long long)g_hash, !known ? "unknown" : match ? "MATCH" : "MISMATCH",
            (unsigned long long)rd64(0x106D4D90), (unsigned long long)rd64(0x106D4DA0),
            (unsigned long long)rd64(kFrameClock), rd32(0x1008EB9C), rd32(0x100900D4), rd32(0x1006404C));
    if (!match) note("resim frame %u: hash %016llX, original %016llX -> %s", f, (unsigned long long)g_hash,
                     (unsigned long long)(known ? g_hist_hash[f % kHist] : 0), known ? "MISMATCH" : "unknown");
    if (g_resim_left == 0) {
        LARGE_INTEGER t1; QueryPerformanceCounter(&t1);
        const double ms = 1000.0 * (double)(t1.QuadPart - g_resim_t0.QuadPart) / (double)g_qpf.QuadPart;
        g_resim_ms_total += ms;
        if (g_sample && g_rollbacks == 1) sample_stop("resim");
        set_bypass(false);
        wr32(kMinVblanks, (uint32_t)(g_saved_minvb >> 32)); wr32(kMinVblanks + 4, (uint32_t)g_saved_minvb);
        if (g_skipdraw && g_draw_word) wr32(g_draw_word, g_draw_saved);
        const double rc = (double)(cycles_now() - g_cyc_resim0) / 1e6 / g_resim;
        const double nc = g_cyc_normal_n ? (double)g_cyc_normal / 1e6 / g_cyc_normal_n : 0;
        note("RESIM done: %u frames in %.2f ms (%.2f ms/frame, %.1f Mcycles/frame CPU; a normal frame with draw: %.1f Mcycles); rollbacks %u, mismatching boundaries %u, resim frames %u",
             g_resim, ms, ms / g_resim, rc, nc, g_rollbacks, g_mismatches, g_resim_frames);
        /* continue the uninterrupted run from here: f == g_resim_target */
        g_logical = f + 1;
        set_sim_frame(f);
        keyread_tick();
        return;
    }
    g_logical = f + 1;
    set_sim_frame(f);
    keyread_tick();
}

} // namespace rb
