/*
 * T5DR training overlay -- research build (trace only).
 */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "ppu_recomp.h"   /* ppu_context, vm_base */

namespace rb { namespace net { bool bypass(); } }

namespace {
FILE* g_trace = nullptr;
uint32_t g_n = 0;
int g_init = 0;
}

extern "C" void t5_training_frame(ppu_context* ctx)
{
    (void)ctx;
    if (!g_init) {
        g_init = 1;
        const char* t = getenv("T5_TRAINING_TRACE");
        if (t && *t) g_trace = fopen(t, "wb");
    }
    if (!g_trace || rb::net::bypass()) return;
    struct { uint32_t magic, n; } h = { 0x54524331u, g_n++ };
    fwrite(&h, sizeof h, 1, g_trace);
    fwrite(vm_base + 0x1008E000u, 1, 0x4000, g_trace);
    fwrite(vm_base + 0x104CCDF0u, 1, 0x60, g_trace);
    fwrite(vm_base + 0x10099F00u, 1, 0x200, g_trace);
    fwrite(vm_base + 0x106D4D88u, 1, 8, g_trace);
}
