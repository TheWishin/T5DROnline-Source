/*
 * Rollback netplay loop (GGPO-style) for T5DR -- docs/ROLLBACK.md section 8.
 *
 * Runs on top of the netplay transport (src/netplay/netplay_core.cpp: input
 * rings, redundant resends, handshake, scene barrier, desync hash) and the
 * game hooks of src/netplay/t5_hooks.cpp, which call in here at every frame
 * boundary when T5_RB_MODE=net is set together with T5_NET_MODE=host|join|local.
 *
 * Per boundary of logical frame f (frame f-1 has just run):
 *   1. commit the state (undo log of f-1, hash H[f]);
 *   2. sample the local pad for frame f + delay and send it;
 *   3. for every frame g < min(f, peer inputs known) that was simulated with a
 *      predicted remote input: if the confirmed input differs, roll back to the
 *      first such g (undo logs), and re-simulate g..f-1 with the draw cut and
 *      the GPU/vblank waits bypassed; the live frame f then runs normally;
 *   4. if the peer is more than T5_RB_NET_MAXPRED frames behind, wait for it;
 *   5. hand the final hashes (frames whose inputs are all confirmed) to the
 *      transport for the desync check;
 *   6. return the inputs of the frame to run: local = the input decided
 *      delay frames ago, remote = confirmed, or the last confirmed input
 *      repeated (prediction).
 *
 * Environment: T5_RB_NET_START=frame:N (switch from the lockstep to rollback
 * at lockstep frame N; default 0 = from the start), T5_RB_NET_MAXPRED (max
 * frames of prediction before stalling, default 8), T5_RB_NET_LOG=1 (a line
 * per rollback).
 */
#pragma once
#include <stdint.h>
#include "../netplay/netplay.h"

namespace rb { namespace net {

bool     enabled();                 /* T5_RB_MODE=net */
bool     active();                  /* the rollback loop has taken over (after the start frame) */
bool     bypass();                  /* a re-simulated frame is running: no GPU/vblank waits */
uint32_t start_frame();             /* T5_RB_NET_START */

/* The hooks call this once per frame boundary with the lockstep frame number
 * f; it returns the frame the game must simulate now (f, or an earlier frame
 * while a rollback is being re-simulated) and fills that frame's inputs.
 * scene_flag: the game asked for an input-ring reset during f-1 (a scene
 * change): the loop then first confirms every input before f (stall) so the
 * caller can run the lockstep's scene barrier on a settled state. */
uint32_t on_boundary(uint32_t f, bool scene_flag, np::PadInput out[2]);

/* The caller ran a scene barrier at frame f (continuing at nf >= f): no
 * rollback may reach back before nf. */
void     scene_change(uint32_t nf);

/* Take over at lockstep frame f (state shadow taken now). */
void     start(uint32_t f);

} } // namespace rb::net
