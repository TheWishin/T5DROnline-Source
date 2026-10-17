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
 * at lockstep frame N; default 0 = from the first frame after the handshake,
 * which with T5_NET_START=external is the fight start), T5_RB_NET_MAXPRED
 * (max frames of prediction before stalling, default 8), T5_RB_NET_LOG=1 (a
 * line per rollback), T5_RB_NET_TIMESYNC=0 (no frame-advantage balancing).
 *
 * Time sync (GGPO's): every packet carries the sender's lead estimate
 * (own frame minus the peer's frame as implied by its latest input); the
 * true advantage is (mine - theirs) / 2 averaged over a window; the side
 * ahead by a frame or more sleeps that many frames (at most 3) at the
 * boundary, no more than once per second, so both peers predict and roll
 * back about equally instead of the one that happens to run ahead doing it
 * all.
 */
#pragma once
#include <stdint.h>
#include "../netplay/netplay.h"

namespace rb { namespace net {

bool     enabled();                 /* rollback offered (T5_RB_MODE unset or "net") and agreed with the peer in the HELLO */
bool     active();                  /* the rollback loop has taken over (after the start frame) */
bool     bypass();                  /* a re-simulated frame is running: no GPU/vblank waits */
uint32_t start_frame();             /* T5_RB_NET_START */

/* Early rollback (T5_RB_NET_EARLY, default on; docs/ROLLBACK.md section 26).
 * early_check(): from the main thread's flip-status poll once its frame is
 * translated and presented (cellGcm_xlat_presented); true when a rollback is
 * already known -- the hook then reports the flip done, the title goes on to
 * its frame semaphore, and the hooks run the boundary at once (early_pending)
 * instead of after the wait; the boundary re-simulates in the time the frame
 * would have waited, then waits for the tick through the waiter set here.
 * early_tick_posted(): the semaphore post the hooks swallowed while that
 * re-simulation ran (it was the tick). */
bool     early_check();
void     early_commit();   /* the next boundary's snapshot, taken early (same hook, before early_check) */
bool     early_pending();
void     early_tick_posted();
void     set_tick_waiter(void (*fn)());

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

/* The game waited for its loader threads before live frame f (t5_hooks.cpp's
 * drain): a load completed. Loader and kernel state are not rolled back, so no
 * re-simulation may run across it: the loop runs in lockstep for
 * T5_RB_NET_LOAD_LOCK frames from here. */
void     load_seen(uint32_t f, double ms);

/* The gameplay hash of frame f once it is final (every input before it
 * confirmed and handed to the desync check); false before that. */
bool     final_hash(uint32_t f, uint64_t* h);

/* Take over at lockstep frame f (state shadow taken now). */
void     start(uint32_t f);

/* Called from the netplay init (before the handshake): offer rollback to the
 * peer unless T5_RB_MODE says lockstep/off or is one of the test modes. */
void     offer();

/* What the environment asks for (T5_NET_MODE set, T5_RB_MODE unset/net/off),
 * before any handshake: true when this side will offer rollback. */
bool     offered_by_env();

/* A persistent game (T5_CTL_DIR) ends a session: the loop stops (a
 * re-simulation in progress is abandoned), its history and the state's undo
 * logs go; the next session's start() takes over at its frame again. */
void     session_reset();

} } // namespace rb::net
