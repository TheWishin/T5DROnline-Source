/*
 * T5DR netplay prototype -- delay-based lockstep of pad input between two
 * instances of the game (see docs/NETPLAY.md).
 *
 * The core (netplay_core.cpp) knows nothing about the game: it samples the
 * local pad, exchanges inputs and state hashes with the peer over UDP and
 * hands back both players' input for a frame. The game hooks
 * (t5_hooks.cpp) decide WHEN a frame starts and WHERE the inputs go.
 *
 * Everything is off unless T5_NET_MODE is set; without it the hooks register
 * nothing and the runtime behaves exactly as before.
 */
#pragma once
#include <stdint.h>

namespace np {

/* One player's input for one frame: CELL_PAD_CTRL_* bits (DIGITAL1 in the
 * low byte, DIGITAL2 in the high byte, as ps3recomp's cellPad packs them)
 * and the four analog axes (0..255, centre 128). */
struct PadInput {
    uint16_t buttons;
    uint8_t  lx, ly, rx, ry;
    bool operator==(const PadInput& o) const {
        return buttons == o.buttons && lx == o.lx && ly == o.ly && rx == o.rx && ry == o.ry;
    }
};
static const PadInput kNeutral = { 0, 128, 128, 128, 128 };

enum class Mode { Off, Local, Host, Join };

Mode  mode();                 /* from T5_NET_MODE; Off when unset */
bool  enabled();              /* mode() != Off */
int   local_slot();           /* 0 = P1 (host, local), 1 = P2 (join) */
int   delay();                /* input delay in frames */

/* Parse the environment, open the socket, start the receive thread.
 * Idempotent; called by the hooks the first time they need the core. */
void  init();

/* A new game frame f starts (called once per frame, in frame order, from
 * one thread). Samples the local pad for frame f + delay, sends it, records
 * this instance's state hash for frame f, and blocks until the peer's input
 * for frame f is known. Fills out[0] = P1, out[1] = P2. */
void  begin_frame(uint32_t f, uint64_t state_hash, PadInput out[2]);

/* Frame log line extension (T5_NET_LOG): free-form text for frame f, written
 * after the inputs and hash. */
void  log_extra(uint32_t f, const char* text);

/* Passive reference mode (T5_NET_PASSIVE=1): no lockstep, the local sources
 * are polled on every pad read. player 0 = this PC's pad, 1 = T5_NET_SCRIPT2 /
 * T5_NET_PADFILE2. */
PadInput poll_now(int player);

void  note(const char* fmt, ...);

} // namespace np
