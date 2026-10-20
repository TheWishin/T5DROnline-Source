/* Entry detours for lifted guest functions -- see rb_detour.cpp. */
#pragma once
#include <stdint.h>

struct ppu_context;

namespace rb {

typedef void (*GuestFn)(ppu_context*);

/* The host function the lifter made of guest function `addr`, or null. */
GuestFn host_of_guest(uint32_t addr);

/* The lifted function table is there (the game-DLL build loads it after static init). */
bool detour_ready();

/* Route every entry of guest function `guest` to `hook`; *orig gets a callable
 * that runs the original. False (nothing changed) when the function is not
 * lifted or its prologue is not one the detour can move. */
bool detour(uint32_t guest, GuestFn hook, GuestFn* orig);

/* T5_RB_CALLTRACE=addr,...|@file: log every call of those functions (rb_calls.log) */
void calltrace_install();

/* T5_RB_SHADOW_TRACE=1: the fighters' shadow box fit, per frame (rb_shadow.log; rb_shadowtrace.cpp) */
void shadowtrace_install();

} // namespace rb
