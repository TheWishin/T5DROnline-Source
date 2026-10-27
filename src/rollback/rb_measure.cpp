/*
 * T5_RB_MODE=measure: which guest memory changes per game frame, and who
 * changes it. Needs the runtime started with PS3_VM_WRITE_WATCH=1 (the 4 GB
 * guest reservation carries MEM_WRITE_WATCH, so GetWriteWatch(RESET) hands us
 * the pages written since the previous frame boundary without diffing).
 *
 * At every frame boundary (main thread, right after its per-frame semaphore
 * wait returned):
 *   - the dirty pages of the frame are counted per region and per page
 *   - every T5_RB_PARK_EVERY frames (default 120) the main thread is parked
 *     for T5_RB_PARK_MS (default 50) with the watch reset: pages that turn
 *     dirty meanwhile were written by OTHER threads (side threads, SPU jobs,
 *     HLE). Attributed separately.
 *   - every T5_RB_SUMMARY frames (default 300) a summary of hot runs goes to
 *     the log: contiguous pages dirty in >= half of the frames.
 */
#define WIN32_LEAN_AND_MEAN
#include "../platform/t5_win.h"
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <vector>
#include <algorithm>

#include "ppu_recomp.h"
#include "rb.h"

namespace rb {

namespace {

struct Region { uint64_t base, size; DWORD protect; };
std::vector<Region> g_regions;
void enumerate_regions()
{
    g_regions.clear();
    uint8_t* p = vm_base;
    uint8_t* end = vm_base + 0x100000000ull;
    MEMORY_BASIC_INFORMATION mbi;
    while (p < end && VirtualQuery(p, &mbi, sizeof mbi) == sizeof mbi) {
        if (mbi.State == MEM_COMMIT && (mbi.Protect & (PAGE_READWRITE | PAGE_EXECUTE_READWRITE | PAGE_WRITECOPY)))
            g_regions.push_back({ (uint64_t)((uint8_t*)mbi.BaseAddress - vm_base), (uint64_t)mbi.RegionSize, mbi.Protect });
        p = (uint8_t*)mbi.BaseAddress + mbi.RegionSize;
    }
}

/* per-page dirty counters (4 GB / 4 KB = 1M pages) */
constexpr uint32_t kPages = 1u << 20;
uint16_t* g_cnt = nullptr;        /* dirty count over the current summary window, by the frame */
uint16_t* g_park = nullptr;       /* dirty count while the main thread was parked */
uint32_t g_win_frames = 0, g_win_parks = 0;
std::vector<void*> g_buf;
bool g_watch_ok = true;
LARGE_INTEGER g_qpf, g_last, g_t0;
uint32_t g_park_every = 120, g_park_ms = 50, g_summary = 300;

/* Collect the dirty pages of all committed regions (and reset the watch). */
uint32_t collect(uint16_t* table, uint32_t* by_cat)
{
    uint32_t total = 0;
    for (const Region& r : g_regions) {
        for (uint64_t off = 0; off < r.size; off += (64ull << 20)) {
            uint64_t len = std::min<uint64_t>(64ull << 20, r.size - off);
            uintptr_t count = g_buf.size();
            uint32_t gran = 0;
            int rc = t5p_write_watch(1, vm_base + r.base + off, (size_t)len,
                                     g_buf.data(), &count, &gran);
            if (rc != 0) {
                static int n = 0;
                if (n++ < 3) note("GetWriteWatch failed at 0x%08llX+0x%llX: %lu (is PS3_VM_WRITE_WATCH=1 set?)",
                                  (unsigned long long)(r.base + off), (unsigned long long)len, (unsigned long)GetLastError());
                g_watch_ok = false;
                return 0;
            }
            for (ULONG_PTR i = 0; i < count; i++) {
                uint64_t ea = (uint64_t)((uint8_t*)g_buf[i] - vm_base);
                uint32_t pg = (uint32_t)(ea >> 12);
                if (table[pg] < 0xFFFF) table[pg]++;
                total++;
                if (by_cat) {
                    int c = ea < 0x10000000ull ? 0 : ea < 0x20000000ull ? 1 : ea < 0xD0000000ull ? 2 : 3;
                    by_cat[c]++;
                }
            }
        }
    }
    return total;
}

void summary(const char* tag, uint16_t* table, uint32_t frames)
{
    if (!frames) return;
    const uint32_t half = (frames + 1) / 2;
    uint64_t hot_pages = 0, any_pages = 0;
    struct Run { uint32_t start, len; uint64_t sum; };
    std::vector<Run> runs;
    for (uint32_t pg = 0; pg < kPages; pg++) {
        if (!table[pg]) continue;
        any_pages++;
        if (table[pg] < half) continue;
        hot_pages++;
        if (!runs.empty() && runs.back().start + runs.back().len == pg) { runs.back().len++; runs.back().sum += table[pg]; }
        else runs.push_back({ pg, 1, table[pg] });
    }
    note("%s over %u frames: %llu pages touched at all, %llu pages dirty in >= half the frames (%llu KB), %zu hot runs",
         tag, frames, (unsigned long long)any_pages, (unsigned long long)hot_pages,
         (unsigned long long)(hot_pages * 4), runs.size());
    for (const Run& r : runs)
        logline("%s-RUN %08X +%06X pages %u avg %.0f%%", tag, r.start << 12, r.len << 12, r.len,
                100.0 * (double)r.sum / ((double)r.len * frames));
    /* also the warm pages: touched in >= 10% of frames but < half */
    uint64_t warm = 0;
    for (uint32_t pg = 0; pg < kPages; pg++) if (table[pg] && table[pg] >= (frames + 9) / 10 && table[pg] < half) warm++;
    note("%s: %llu warm pages (dirty in 10%%..50%% of frames)", tag, (unsigned long long)warm);
    /* coarse map: 1 MB buckets with any hot page, so the layout is readable */
    std::string line;
    uint64_t last_mb = ~0ull;
    for (uint32_t pg = 0; pg < kPages; pg++) {
        if (!table[pg] || table[pg] < half) continue;
        uint64_t mb = ((uint64_t)pg << 12) >> 20;
        if (mb != last_mb) {
            char t[16]; snprintf(t, sizeof t, " %03llX", (unsigned long long)mb);
            line += t; last_mb = mb;
        }
    }
    logline("%s-MB%s", tag, line.c_str());
    memset(table, 0, kPages * sizeof(uint16_t));
}

} // namespace

void measure_on_frame(ppu_context* ctx)
{
    static bool init = false;
    const uint32_t f = frame();
    LARGE_INTEGER now; QueryPerformanceCounter(&now);
    if (!init) {
        init = true;
        QueryPerformanceFrequency(&g_qpf);
        g_last = now;
        /* process start in QPC units: now - (wall now - creation time) */
        g_t0.QuadPart = now.QuadPart - (LONGLONG)(t5p_process_uptime_s() * (double)g_qpf.QuadPart);
        if (const char* e = getenv("T5_RB_PARK_EVERY")) g_park_every = (uint32_t)atoi(e);
        if (const char* e = getenv("T5_RB_PARK_MS")) g_park_ms = (uint32_t)atoi(e);
        if (const char* e = getenv("T5_RB_SUMMARY")) g_summary = (uint32_t)atoi(e);
        g_cnt = (uint16_t*)calloc(kPages, sizeof(uint16_t));
        g_park = (uint16_t*)calloc(kPages, sizeof(uint16_t));
        g_buf.resize(1u << 16);   /* 64 MB chunks = 16384 pages; room to spare */
        enumerate_regions();
        uint64_t committed = 0;
        for (const Region& r : g_regions) {
            committed += r.size;
            note("committed region 0x%08llX size 0x%llX prot 0x%lX", (unsigned long long)r.base,
                 (unsigned long long)r.size, (unsigned long)r.protect);
        }
        note("committed total %llu MB", (unsigned long long)(committed >> 20));
        note("frame boundary on main thread (ctx tid %llu, r1=0x%08llX): %s",
             (unsigned long long)ctx->thread_id, (unsigned long long)ctx->gpr[1], guest_backtrace(12).c_str());
        list_threads();
        collect(g_cnt, nullptr);     /* reset: everything written during boot */
        memset(g_cnt, 0, kPages * sizeof(uint16_t));
        return;
    }
    const double dt_ms = 1000.0 * (double)(now.QuadPart - g_last.QuadPart) / (double)g_qpf.QuadPart;
    const double wall = (double)(now.QuadPart - g_t0.QuadPart) / (double)g_qpf.QuadPart;
    const LARGE_INTEGER g_prev = g_last;
    g_last = now;
    if ((f % 600) == 0) {
        enumerate_regions();
        note("frame %u (%.1fs, clk %llu): %s", f, wall, (unsigned long long)rd64(kFrameClock), guest_backtrace(10).c_str());
    }
    if ((f % 100) == 0) {
        const uint32_t scene = rd32(0x10532DF0);
        logline("F %u scene %08X vtable %08X", f, scene, scene ? rd32(scene) : 0);
    }
    if (!g_watch_ok) {
        logline("F %u t %.2f dt %.2f clk %llu vb %llu sc %u ri %u wi %u", f, wall, dt_ms, (unsigned long long)rd64(kFrameClock),
                (unsigned long long)rd64(kFrameClock + 8), rd32(0x104CCDF8), rd32(0x104CCE40), rd32(0x104CCE3C));
        return;
    }

    uint32_t cat[4] = { 0, 0, 0, 0 };
    LARGE_INTEGER t0; QueryPerformanceCounter(&t0);
    uint32_t total = collect(g_cnt, cat);
    LARGE_INTEGER t1; QueryPerformanceCounter(&t1);
    g_win_frames++;
    logline("F %u t %.2f dt %.2f uc %.2f fl %.2f dirty %u main %u data %u mid %u stack %u clk %llu vb %llu sc %u ri %u wi %u ww %.2fms", f, wall, dt_ms,
            t_usercmd_ms(g_prev), t_flip_ms(g_prev), total,
            cat[0], cat[1], cat[2], cat[3], (unsigned long long)rd64(kFrameClock),
            (unsigned long long)rd64(kFrameClock + 8), rd32(0x104CCDF8), rd32(0x104CCE40), rd32(0x104CCE3C),
            1000.0 * (double)(t1.QuadPart - t0.QuadPart) / (double)g_qpf.QuadPart);

    if (g_park_every && (f % g_park_every) == 0) {
        /* Park: nothing of the main thread runs; what turns dirty is other threads'. */
        Sleep(g_park_ms);
        uint32_t pcat[4] = { 0, 0, 0, 0 };
        uint32_t ptotal = collect(g_park, pcat);
        g_win_parks++;
        logline("PARK %u ms %u dirty %u main %u data %u mid %u stack %u", f, g_park_ms, ptotal, pcat[0], pcat[1], pcat[2], pcat[3]);
        QueryPerformanceCounter(&g_last);   /* do not count the park as frame time */
    }
    if (g_summary && (f % g_summary) == 0) {
        summary("FRAME", g_cnt, g_win_frames);
        summary("PARK", g_park, g_win_parks);
        g_win_frames = g_win_parks = 0;
        fflush(stderr);
    }
}

} // namespace rb
