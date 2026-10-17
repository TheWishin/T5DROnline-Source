/* T5DR rollback research prototype -- shared declarations. */
#pragma once
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdint.h>
#include <string>

struct ppu_context;

namespace rb {

enum class Mode { Off, Measure, Test, Net };   /* Net: T5_RB_MODE=net, the rollback netplay loop (rb_net.cpp) */

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
bool     df_drives();                              /* T5_FIGHT set: direct fight owns the pads, scripts go through df::inject */
void     set_script_base(uint32_t f);              /* script frames count from this logical frame (T5_RB_START=auto) */
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
void     set_sim_frame(uint32_t f);                /* logical frame the pad override answers for (net mode: the frame running) */
uint32_t sim_frame();
/* rb_sound.cpp: the sound side in re-simulated frames (T5_RB_SOUND=resim|skip|raw) */
enum class SoundMode { Skip, Resim, Raw };
struct SoundStats { uint32_t started_live = 0, started_resim = 0, deduped = 0, deduped_moved = 0, orphaned = 0, ticks_skipped = 0, log_full = 0,
                    stops_kept = 0, stops_suppressed = 0, queries_replayed = 0, events_kept = 0, events_new = 0; };
void       sound_install();                        /* detours of the play entry and the library tick */
SoundMode  sound_mode();
void       sound_begin_frame(uint32_t f, bool resim);   /* frame f is about to run (set_sim_frame calls it) */
SoundStats sound_stats(bool reset);
void     set_bypass(bool on);                      /* re-simulating: no flip/semaphore waits, no GCM user command */
bool     bypass_on();
/* Time sync: a sleep requested by the rollback loop is taken inside the
 * present's flip wait (cellGcmSetWaitFlip, after the draw thread is done
 * with the frame), where it delays the whole frame pipeline. A sleep at the
 * frame boundary was absorbed by the draw thread's wait (run n8). */
void     ts_sleep_request(double ms);
/* The sound update (main loop 0xAA200 -> 0x32819C: the main thread's sound
 * requests to the bnusCore handoff area) is skipped while the word its TOC
 * slot (r2 - 0x61E8) points to is 0. Re-simulated frames must not re-issue
 * the sounds the original frames already started: the loop zeroes it for
 * them (rb_hooks.cpp). */
void     sound_skip(bool on);
uint32_t sound_word();                             /* the guest address of that word (masked out of the hash) */

uint32_t pad_calls();                              /* cellPadGetData override invocations so far */
uint64_t main_tid();                               /* guest thread id of the main thread (1) */
uint32_t guest_of_host(uintptr_t host_pc, uint32_t* off);   /* lifted function containing a host address, 0 if none */
uint32_t guest_at_host(uintptr_t host_fn);                  /* lifted function whose entry IS this host address, 0 if none */

/* stack-sampling profiler (rb_sample.cpp) */
void     sample_start();
void     sample_stop(const char* tag);
void     sample_reset();

/* indirect-call interposer (rb_icall.cpp): draw cut + per-target timing */
void     icall_install();
void     cut_set(bool on);                         /* route the cut set to stubs (re-simulating) */
uint64_t cut_hits();
void     icall_timing_start();
void     icall_timing_stop(const char* tag);

/* write-fault tracer (rb_wft.cpp): T5_RB_WFT=addr:len,... */
void     wft_install();
bool     wft_enabled();
void     wft_arm();
void     wft_arm_pages(const uint32_t* pages, size_t n);   /* T5_RB_WFT=diff: trace these pages */
void     wft_disarm(const char* tag);

/* syscall timeline (rb_trace.cpp) */
void     trace_install();
void     trace_frame(const char* tag);
void     trace_stop(const char* tag);

/* per-mode frame handlers (rb_measure.cpp / rb_test.cpp) */
void measure_on_frame(ppu_context* ctx);
void test_on_frame(ppu_context* ctx);

} // namespace rb
