/* The state set, its hash and the undo-log snapshots -- see rb_state.h. */
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <vector>
#include <algorithm>

#include "rb.h"
#include "rb_state.h"

extern "C" uint8_t* vm_base;
/* libs/codec/cellAtrac.c (patch 0023): the HLE decoder's positional state, rewound with the rollback */
extern "C" size_t cellAtrac_rb_state_size(void);
extern "C" void   cellAtrac_rb_save(void* out);
extern "C" int    cellAtrac_rb_restore(const void* in);

namespace rb {

/* ---- state regions (NPUB30009 v01.00, this runtime's memory map) ------------ */
const Range kSave[] = {
    { 0x0E000000u, 0x00020000u },   /* main thread TLS: libc rand seed, a per-frame random word */
    { 0x0F800000u, 0x00010000u },   /* CellGcmContextData */
    { 0x0FEF0000u, 0x00010000u },   /* main thread stack */
    { 0x10000000u, 0x00770000u },   /* ELF data + bss */
    { 0x10F00000u, 0x000F0000u },   /* TLS blocks of created threads (main thread's scene pointer lives here) */
    { 0x40000000u, 0x05F00000u },   /* the game's heap (sys_memory_allocate) */
};
const size_t kSaveN = sizeof kSave / sizeof kSave[0];
const Range kExclude[] = {
    { 0x10114000u, 0x00058000u },   /* sound core mix/output area (bnusCore) */
    { 0x40000000u, 0x00100000u },   /* first heap chunk: sound system voice slots, requests, shared areas (sound threads) */
    { 0x45F00000u, 0x00100000u },   /* decoder / streaming */
};
const size_t kExcludeN = sizeof kExclude / sizeof kExclude[0];
const Range kHashExclude[] = {
    { 0x0FEF0000u, 0x00010000u },   /* main thread stack: only the present chain's locals live there at the boundary */
    { 0x10532000u, 0x00001000u },   /* engine bookkeeping: request counters, vblank copies (follow the draw phase) */
    { 0x10750000u, 0x00003000u },   /* NU::File::RequestManager object and request list (requests issued by the draw) */
    { 0x400CA000u, 0x00011000u },   /* per-frame handoff ring written by the main thread (slot state follows the consumer) */
    { 0x40100000u, 0x00400000u },   /* GCM command buffer ring (cellGcmInit: begin 0x40100000, end 0x40500000) */
    { 0x43D00000u, 0x00340000u },   /* draw lists, buffers A (0x43D00000) and B (0x43EA0000), with their link pages */
    { 0x444F9000u, 0x0006E000u },   /* per-frame render scratch, written every frame */
};
const size_t kHashExcludeN = sizeof kHashExclude / sizeof kHashExclude[0];
static std::vector<Range> g_hash_exclude_dyn;

bool excluded_page(uint32_t ea)
{
    for (const Range& r : kExclude) if (ea >= r.base && ea < r.base + r.len) return true;
    return false;
}
bool hash_excluded_page(uint32_t ea)
{
    for (const Range& r : kHashExclude) if (ea >= r.base && ea < r.base + r.len) return true;
    for (const Range& r : g_hash_exclude_dyn) if (ea >= r.base && ea < r.base + r.len) return true;
    return false;
}
void state_add_hash_exclude(uint32_t ea, uint32_t len) { g_hash_exclude_dyn.push_back({ ea, len }); }

/* Words inside the state that follow the wall clock, not the inputs: masked
 * out of the hash (still restored with their page). */
struct Mask { uint32_t ea, len; };
static const Mask kMask[] = {
    { 0x106D4D90u, 0x18 },   /* vblank counter (vblank handler) + the copies present takes */
    { 0x106D4520u, 0xF0 },   /* render duration / GCM timestamp statistics */
    { 0x105320C4u, 0x04 },   /* vblank counter copies kept by side threads */
    { 0x10624720u, 0x30 },   /* frame duration statistics (microseconds, vblank counts) */
    { 0x1074F9F8u, 0x08 },   /* a timebase (mftb) stamp taken every frame */
    { 0x0F800008u, 0x04 },   /* CellGcmContextData.current: the FIFO write pointer */
    { 0x106D4A44u, 0x04 },   /* graphics object: flip/present pending flag (render handshake) */
    { 0x106D4BE0u, 0x10 },   /* vblank callback list lock: owner is the ticker thread at times */
    { 0x106CF0F8u, 0x10 },   /* TNUD::ASync progress counters (+F8, +FC, +104), advanced by its thread */
    { 0x1062E454u, 0x08 },   /* engine statistics (two floats following the frame time) */
    { 0x10053800u, 0x100 },  /* 15 objects' double-buffer index (1/2): follows the flip, not the sim */
    { 0x40049210u, 0x04 },   /* double-buffer selector (0x10/0x20): follows the flip */
};
static std::vector<Mask> g_mask_dyn;
void state_add_mask(uint32_t ea, uint32_t len) { g_mask_dyn.push_back({ ea, len }); }

/* ---- hash -------------------------------------------------------------------- */
static constexpr uint32_t kPages = 1u << 20;
static uint64_t* g_page_hash = nullptr;
static uint64_t  g_hash = 0;
static std::vector<void*> g_ww;

static inline uint64_t mix(uint64_t x) { x ^= x >> 31; x *= 0x9E3779B97F4A7C15ull; x ^= x >> 29; return x; }
static inline uint64_t weight(uint32_t pg) { return mix((uint64_t)pg * 0xD6E8FEB86659FD93ull + 1); }
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
uint64_t state_hash() { return g_hash; }

/* the netplay desync check's regions and skips (t5_hooks.cpp), kept in sync by hand */
static const Range kGame[] = {
    { 0x10099F24u, 0x70 }, { 0x104CCDFCu, 0x40 }, { 0x106D4D88u, 0x8 }, { 0x10095168u, 0x9C0 }, { 0x10053578u, 0x4 },
    { 0x10076920u, 0x4 }, { 0x1074F218u, 0x10C }, { 0x1008E000u, 0x4000 }, { 0x10099600u, 0x600 }, { 0x100A0900u, 0x200 },
    { 0x100A3B00u, 0x300 },
};
static const Range kGameSkip[] = {
    /* the C library rand() word (0x369228's state, from the TOC): consumed by a
     * side thread (0x1230AC -> 0x12CF34 -> 0x12C558, 8 call sites, ~7 calls per
     * frame on stage 24, a few on stage 18) at its own pace, so it can never
     * be part of the deterministic fight -- the netplay runs stayed in sync
     * while it diverged, and it was the only word behind every stage-specific
     * mismatch of the draw-cut test (docs/ROLLBACK.md section 12) */
    { 0x1074F218u, 4 },
    { 0x1008F0C4u, 4 }, { 0x1008F0D0u, 4 }, { 0x1008FF00u, 0xC }, { 0x1008FFB0u, 0xC },
    { 0x100901B4u, 4 }, { 0x100901E0u, 4 }, { 0x10090314u, 4 }, { 0x10090870u, 8 },
    { 0x10090A84u, 4 }, { 0x10090AB0u, 4 }, { 0x10090BE4u, 4 }, { 0x10091140u, 8 },
};
uint32_t state_game_bytes(uint8_t* out, uint32_t cap)
{
    uint32_t n = 0;
    for (const Range& r : kGame) {
        if (n + r.len > cap) break;
        memcpy(out + n, vm_base + r.base, r.len);
        for (const Range& k : kGameSkip) {
            const uint32_t a = std::max(k.base, r.base), e = std::min(k.base + k.len, r.base + r.len);
            for (uint32_t x = a; x < e; x++) out[n + (x - r.base)] = 0;
        }
        n += r.len;
    }
    return n;
}
uint64_t state_game_hash()
{
    uint64_t h = 1469598103934665603ull;
    static uint8_t buf[0x4000];
    for (const Range& r : kGame) {
        memcpy(buf, vm_base + r.base, r.len);
        for (const Range& k : kGameSkip) {
            const uint32_t a = std::max(k.base, r.base), e = std::min(k.base + k.len, r.base + r.len);
            for (uint32_t x = a; x < e; x++) buf[x - r.base] = 0;
        }
        for (uint32_t i = 0; i < r.len; i++) { h ^= buf[i]; h *= 1099511628211ull; }
    }
    return h;
}
uint64_t state_page_hash(uint32_t ea) { return g_page_hash ? g_page_hash[ea >> 12] : 0; }

void state_hash_full()
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

/* ---- shadow + undo ring --------------------------------------------------------- */
static uint8_t* g_shadow = nullptr;
static size_t   g_shadow_size = 0;
const uint8_t* state_shadow(uint32_t ea)
{
    if (!g_shadow) return nullptr;
    size_t off = 0;
    for (const Range& r : kSave) {
        if (ea >= r.base && ea < r.base + r.len) return g_shadow + off + (ea - r.base);
        off += r.len;
    }
    return nullptr;
}
static inline uint8_t* shadow_rw(uint32_t ea) { return (uint8_t*)state_shadow(ea); }

/* Ring of page pre-images. An undo entry is (ea, the page's hash before the
 * frame, the pre-image); frame f's entries are contiguous in the ring. */
struct Entry { uint32_t ea; uint64_t hash; };
static constexpr uint32_t kRingPages = 24576;        /* 96 MB: ~30 fight frames of 700 dirty pages */
static constexpr uint32_t kLogFrames = 64;
static Entry*   g_ent = nullptr;                     /* kRingPages entries */
static uint8_t* g_pages = nullptr;                   /* kRingPages * 4 KB */
static uint32_t g_ring_pos = 0;                      /* next free ring slot */
struct Log { uint32_t tag; uint32_t start, count; }; /* tag = frame + 1 */
static Log g_log[kLogFrames];
/* per boundary: the cellAtrac HLE state as of that boundary (restored with a rollback to it) */
static uint8_t* g_atrac = nullptr; static size_t g_atrac_sz = 0; static uint32_t g_atrac_tag[kLogFrames];
static uint32_t g_newest = 0;                         /* frame + 1 of the newest log */
static bool g_ready = false;

/* The ring is written sequentially, so the slot about to be reused can only
 * belong to the oldest log still alive: drop logs from the oldest end until
 * the slot is free. O(1) amortised. */
static uint32_t g_oldest = 0;                         /* frame + 1 of the oldest log that may still be alive, 0 = none */
static void ring_reclaim(uint32_t slot)
{
    while (g_oldest && g_oldest < g_newest) {
        Log& l = g_log[(g_oldest - 1) % kLogFrames];
        if (l.tag != g_oldest) { g_oldest++; continue; }   /* already dropped */
        const uint32_t d = (slot + kRingPages - l.start) % kRingPages;
        if (d >= l.count) break;                             /* the slot is outside the oldest log: free */
        l.tag = 0; g_oldest++;
    }
}

void state_init()
{
    if (g_ready) return;
    g_page_hash = (uint64_t*)calloc(kPages, sizeof(uint64_t));
    g_ww.resize(1u << 16);
    g_shadow_size = 0;
    for (const Range& r : kSave) g_shadow_size += r.len;
    g_shadow = (uint8_t*)VirtualAlloc(nullptr, g_shadow_size, MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE);
    g_ent = (Entry*)calloc(kRingPages, sizeof(Entry));
    g_atrac_sz = cellAtrac_rb_state_size();
    g_atrac = (uint8_t*)calloc(kLogFrames, g_atrac_sz);
    memset(g_atrac_tag, 0, sizeof g_atrac_tag);
    g_pages = (uint8_t*)VirtualAlloc(nullptr, (size_t)kRingPages * 0x1000, MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE);
    LARGE_INTEGER f, a, b; QueryPerformanceFrequency(&f); QueryPerformanceCounter(&a);
    size_t off = 0;
    for (const Range& r : kSave) { memcpy(g_shadow + off, vm_base + r.base, r.len); off += r.len; }
    /* the pages dirtied before now are of no interest: reset the watch */
    for (const Range& r : kSave) ResetWriteWatch(vm_base + r.base, r.len);
    state_hash_full();
    QueryPerformanceCounter(&b);
    memset(g_log, 0, sizeof g_log);
    g_ring_pos = 0; g_newest = 0; g_oldest = 0;
    g_ready = true;
    note("state: %zu MB shadow + %u-page undo ring (%u MB) ready in %.1f ms, hash %016llX", g_shadow_size >> 20,
         kRingPages, kRingPages >> 8, 1000.0 * (double)(b.QuadPart - a.QuadPart) / (double)f.QuadPart,
         (unsigned long long)g_hash);
}
bool state_ready() { return g_ready; }

uint32_t state_commit(uint32_t f, void (*on_page)(uint32_t, uint64_t), double* ms)
{
    LARGE_INTEGER q, a, b; QueryPerformanceFrequency(&q); QueryPerformanceCounter(&a);
    uint32_t n = 0;
    Log* lg = nullptr;
    /* the decoder's state at this boundary (what a rollback to f puts back) */
    cellAtrac_rb_save(g_atrac + (size_t)(f % kLogFrames) * g_atrac_sz);
    g_atrac_tag[f % kLogFrames] = f + 1;
    if (f > 0) {
        lg = &g_log[(f - 1) % kLogFrames];
        if (lg->tag) { /* the slot in the frame table is reused: that log is gone */ lg->tag = 0; }
        lg->tag = f; lg->start = g_ring_pos; lg->count = 0;
        g_newest = f;
        if (!g_oldest) g_oldest = f;
        if (g_oldest + kLogFrames <= g_newest) g_oldest = g_newest - kLogFrames + 1;
    }
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
                const uint32_t ea = (uint32_t)((uint8_t*)g_ww[i] - vm_base);
                if (excluded_page(ea)) continue;
                const uint32_t pg = ea >> 12;
                const bool hashed = !hash_excluded_page(ea);
                uint8_t* sh = shadow_rw(ea);
                if (lg) {
                    /* pre-image + old hash into the ring; the slot's previous owner is gone */
                    const uint32_t slot = g_ring_pos;
                    ring_reclaim(slot);
                    g_ent[slot] = { ea, g_page_hash[pg] };
                    memcpy(g_pages + (size_t)slot * 0x1000, sh, 0x1000);
                    g_ring_pos = (g_ring_pos + 1) % kRingPages;
                    lg->count++;
                    if (lg->count >= kRingPages - 1) { note("undo ring full in one frame"); break; }
                }
                memcpy(sh, vm_base + ea, 0x1000);
                if (hashed) {
                    const uint64_t h = hash_page(ea);
                    g_hash += (h - g_page_hash[pg]) * weight(pg);
                    g_page_hash[pg] = h;
                    if (on_page) on_page(ea, h);
                }
                n++;
            }
        }
    }
    QueryPerformanceCounter(&b);
    if (ms) *ms = 1000.0 * (double)(b.QuadPart - a.QuadPart) / (double)q.QuadPart;
    return n;
}

uint32_t state_oldest_frame()
{
    uint32_t oldest = g_newest;   /* frame + 1 */
    for (const Log& l : g_log) if (l.tag && l.tag < oldest) oldest = l.tag;
    /* the boundary of frame (tag - 1) is reachable through that log */
    return oldest ? oldest - 1 : 0;
}
void state_drop_logs()
{
    for (Log& l : g_log) l.tag = 0;
    g_oldest = g_newest;
}
uint32_t state_log_pages(uint32_t f)
{
    const Log& l = g_log[f % kLogFrames];
    return l.tag == f + 1 ? l.count : 0;
}

bool state_rollback(uint32_t to, uint32_t* pages, double* ms)
{
    LARGE_INTEGER q, a, b; QueryPerformanceFrequency(&q); QueryPerformanceCounter(&a);
    if (!g_newest || to >= g_newest) return false;
    /* every log from the newest (frame g_newest-1) down to frame `to` must be present */
    for (uint32_t f = g_newest - 1; ; f--) {
        if (g_log[f % kLogFrames].tag != f + 1) return false;
        if (f == to) break;
    }
    uint32_t n = 0;
    for (uint32_t f = g_newest - 1; ; f--) {
        const Log& l = g_log[f % kLogFrames];
        for (uint32_t i = 0; i < l.count; i++) {
            const uint32_t slot = (l.start + i) % kRingPages;
            const Entry& e = g_ent[slot];
            const uint32_t pg = e.ea >> 12;
            const uint8_t* src = g_pages + (size_t)slot * 0x1000;
            memcpy(vm_base + e.ea, src, 0x1000);
            memcpy(shadow_rw(e.ea), src, 0x1000);
            if (!hash_excluded_page(e.ea)) { g_hash += (e.hash - g_page_hash[pg]) * weight(pg); g_page_hash[pg] = e.hash; }
            n++;
        }
        if (f == to) break;
    }
    if (g_atrac_tag[to % kLogFrames] == to + 1) cellAtrac_rb_restore(g_atrac + (size_t)(to % kLogFrames) * g_atrac_sz);
    /* the logs above `to` describe frames that will be re-simulated: drop them
     * and hand their ring slots back (the ring position returns to the start
     * of frame `to`'s log) */
    g_ring_pos = g_log[to % kLogFrames].start;
    for (uint32_t f = to; f < g_newest; f++) g_log[f % kLogFrames].tag = 0;
    g_newest = to;   /* the next commit (at the boundary of to+1) records frame `to` */
    if (g_oldest > to) g_oldest = to;
    /* our own writes must not count as the next frame's dirt */
    for (const Range& r : kSave) ResetWriteWatch(vm_base + r.base, r.len);
    QueryPerformanceCounter(&b);
    if (pages) *pages = n;
    if (ms) *ms = 1000.0 * (double)(b.QuadPart - a.QuadPart) / (double)q.QuadPart;
    return true;
}

} // namespace rb
