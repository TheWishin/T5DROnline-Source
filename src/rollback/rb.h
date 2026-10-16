/* T5DR rollback research prototype -- shared declarations. */
#pragma once
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdint.h>
#include <string>

struct ppu_context;

namespace rb {

enum class Mode { Off, Measure, Test };

/* guest addresses (NPUB30009 v01.00; see np's t5_hooks.cpp) */
constexpr uint32_t kFrameSemPtr = 0x106D4A30;   /* graphics object + 0x30: per-frame semaphore id */
constexpr uint32_t kFrameClock  = 0x106D4D88;   /* u64 frame clock, +8 vblank count */

struct PadInput {
    uint16_t buttons;
    uint8_t  lx, ly, rx, ry;
};
static const PadInput kNeutral = { 0, 128, 128, 128, 128 };

Mode     mode();
uint32_t frame();                                  /* frames seen at the boundary so far */
PadInput script_input(int port, uint32_t f);
void     set_override(const PadInput* in);         /* both pads fixed (nullptr: back to script) */
uint64_t gcall(uint32_t code, uint64_t a0 = 0, uint64_t a1 = 0);

uint32_t rd32(uint32_t a);
uint64_t rd64(uint32_t a);
void     wr32(uint32_t a, uint32_t v);
void     note(const char* fmt, ...);
void     logline(const char* fmt, ...);
std::string guest_backtrace(int max);
double   t_usercmd_ms(LARGE_INTEGER since);    /* last cellGcmSetUserCommand on main, relative */
double   t_flip_ms(LARGE_INTEGER since);
void     list_threads();

/* test-mode plumbing (rb_hooks.cpp) */
bool     keyread_parked();                         /* keyread thread parked, main thread ticks it */
void     set_sim_frame(uint32_t f);                /* logical frame the pad override answers for */
void     set_bypass(bool on);                      /* re-simulating: no flip/semaphore waits, no GCM user command */

uint32_t pad_calls();                              /* cellPadGetData override invocations so far */
void     sample_start();                           /* rb_sample.cpp */
void     sample_stop(const char* tag);

/* syscall timeline (rb_trace.cpp) */
void     trace_install();
void     trace_frame(const char* tag);
void     trace_stop(const char* tag);

/* per-mode frame handlers (rb_measure.cpp / rb_test.cpp) */
void measure_on_frame(ppu_context* ctx);
void test_on_frame(ppu_context* ctx);

} // namespace rb
