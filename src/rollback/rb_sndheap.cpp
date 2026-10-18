/*
 * The sound library's own heap, outside the rollback state (docs/ROLLBACK.md
 * section 32).
 *
 * The title's C library heap (malloc 0x3AB2C8, free 0x3AAA40; its state at
 * 0x10753EF0, its first arena at 0x40000000) serves the main thread, the
 * loaders and the sound library -- the library gets it as callbacks at init
 * (0x10088F0C/F10, copied to 0x10088F88/F8C). The heap's state is guest
 * memory and is rolled back; the sound library's blocks are not undone by a
 * rollback: its music stream thread (CnuSound2Thread), its ATRAC3+ decoder
 * thread and bnusCoreUpdateThread allocate and free at any time (a track
 * starts or stops: KO, round end, match end), and the sound hooks never
 * repeat the main thread's library calls in a re-simulated frame
 * (rb_sound.cpp). A restore then rewound the free lists under blocks that
 * stayed in use: a block went out twice -- a loader's compressed data was
 * overwritten ("inflate failed. error no:-3") and the decoder's next free()
 * found a broken chunk (abort, 0x3AABC0 from 0x349EB8).
 *
 * Every malloc whose caller is the sound library's code (0x326000..0x34B000)
 * is served from a pool at guest 0x7F000000 (nothing else maps there: the
 * sys_memory window ends at 0x50000000, the HLE heap at 0x58000000, cellAudio
 * takes 2 MB per port from 0x58000000, sys_vm 0x60000000..0x70000000); its
 * bookkeeping is host memory, so no restore touches either. A free of a pool
 * block, from anywhere, goes back to the pool. The C library heap is then
 * used only by the main thread and the loaders the boundary drains, whose
 * work a restore and re-simulation undo and redo consistently.
 * T5_RB_SNDHEAP=0 turns it off.
 */
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
#include <algorithm>
#include <iterator>
#include <map>
#include <unordered_map>

#include "sys_ppu_thread.h"
#include "rb.h"
#include "rb_detour.h"

extern "C" uint8_t* vm_base;

namespace rb {

namespace {
constexpr uint32_t kMalloc = 0x3AB2C8, kFree = 0x3AAA40;     /* the C library heap */
constexpr uint32_t kLibLo = 0x326000, kLibHi = 0x34B000;     /* the sound library and its core (bnus*): callers seen 0x32938C..0x34A944 */
constexpr uint32_t kPoolBase = 0x7F000000u, kPoolSize = 0x00800000u;
constexpr uint32_t kAlign = 16;                              /* what the C library hands out */

GuestFn o_malloc = nullptr, o_free = nullptr;
SRWLOCK g_lock = SRWLOCK_INIT;
bool g_on = false, g_mapped = false, g_full_noted = false;
std::map<uint32_t, uint32_t> g_free;                    /* start -> size, address order (coalescing) */
std::unordered_map<uint32_t, uint32_t> g_used;          /* start -> size */
uint64_t g_bytes = 0, g_peak = 0, g_allocs = 0, g_frees = 0, g_fallbacks = 0;

bool map_pool()
{
    if (g_mapped) return true;
    if (!VirtualAlloc(vm_base + kPoolBase, kPoolSize, MEM_COMMIT, PAGE_READWRITE)) return false;
    g_free[kPoolBase] = kPoolSize;
    g_mapped = true;
    return true;
}

uint32_t pool_alloc(uint32_t size)
{
    const uint32_t want = (std::max<uint32_t>(size, 1) + kAlign - 1) & ~(kAlign - 1);
    AcquireSRWLockExclusive(&g_lock);
    uint32_t got = 0;
    if (map_pool()) {
        for (auto it = g_free.begin(); it != g_free.end(); ++it) {
            if (it->second < want) continue;
            got = it->first;
            const uint32_t rest = it->second - want;
            g_free.erase(it);
            if (rest) g_free[got + want] = rest;
            g_used[got] = want;
            g_bytes += want; g_allocs++;
            if (g_bytes > g_peak) g_peak = g_bytes;
            break;
        }
    }
    if (!got) g_fallbacks++;
    const bool note_full = !got && !g_full_noted;
    if (note_full) g_full_noted = true;
    ReleaseSRWLockExclusive(&g_lock);
    if (note_full) note("sound heap: no room for 0x%X bytes (%llu KB in use) -- this block and any other that does not fit come from the C library heap",
                        size, (unsigned long long)(g_bytes >> 10));
    return got;
}

bool pool_free(uint32_t p)
{
    if (p < kPoolBase || p >= kPoolBase + kPoolSize) return false;
    AcquireSRWLockExclusive(&g_lock);
    auto u = g_used.find(p);
    if (u == g_used.end()) {
        ReleaseSRWLockExclusive(&g_lock);
        note("sound heap: free of %08X, which is not a block of it -- ignored", p);
        return true;
    }
    uint32_t start = p, size = u->second;
    g_used.erase(u);
    g_bytes -= size; g_frees++;
    auto next = g_free.lower_bound(start);
    if (next != g_free.end() && start + size == next->first) { size += next->second; next = g_free.erase(next); }
    if (next != g_free.begin()) {
        auto prev = std::prev(next);
        if (prev->first + prev->second == start) { start = prev->first; size += prev->second; g_free.erase(prev); }
    }
    g_free[start] = size;
    ReleaseSRWLockExclusive(&g_lock);
    return true;
}

void h_malloc(ppu_context* ctx)
{
    const uint32_t lr = (uint32_t)ctx->lr;
    if (g_on && lr >= kLibLo && lr < kLibHi) {
        if (const uint32_t p = pool_alloc((uint32_t)ctx->gpr[3])) { ctx->gpr[3] = p; return; }
    }
    o_malloc(ctx);
}

void h_free(ppu_context* ctx)
{
    if (pool_free((uint32_t)ctx->gpr[3])) { ctx->gpr[3] = 0; return; }
    o_free(ctx);
}
} // namespace

void sndheap_install()
{
    static bool done = false;
    if (done || !detour_ready()) return;
    done = true;
    const char* e = getenv("T5_RB_SNDHEAP");
    if (e && *e == '0') { note("sound heap: off (T5_RB_SNDHEAP=0) -- the sound library allocates from the C library heap"); return; }
    if (!detour(kFree, h_free, &o_free)) { note("sound heap: free 0x%06X not detourable -- off", kFree); return; }
    if (!detour(kMalloc, h_malloc, &o_malloc)) { note("sound heap: malloc 0x%06X not detourable -- only frees are routed", kMalloc); return; }
    g_on = true;
    note("sound heap: the sound library's blocks come from guest 0x%08X (%u MB, outside the rollback state)", kPoolBase, kPoolSize >> 20);
}

void sndheap_stats(char* out, size_t cap)
{
    AcquireSRWLockShared(&g_lock);
    snprintf(out, cap, "%llu KB in use (peak %llu KB) in %zu blocks, %llu allocations, %llu frees, %llu from the C library heap for want of room",
             (unsigned long long)(g_bytes >> 10), (unsigned long long)(g_peak >> 10), g_used.size(),
             (unsigned long long)g_allocs, (unsigned long long)g_frees, (unsigned long long)g_fallbacks);
    ReleaseSRWLockShared(&g_lock);
}

} // namespace rb
