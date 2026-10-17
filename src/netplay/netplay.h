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

/* The game changed scene at the start of frame f (k-th time). Scene changes
 * that wait on loading land a frame or two apart on the two PCs; this waits
 * until the peer has reached the same scene change and returns the frame
 * number both continue with (the later of the two -- the side that got there
 * first skips the difference). Returns f in local mode. */
uint32_t scene_barrier(uint32_t f);

/* Block until the peer has connected (no-op in local mode). begin_frame(0)
 * does this too; call it first to act on match_seed() before frame 0. */
void connect();

/* A number both peers share once frame 0 has begun (the host's session id):
 * seeds the game's random generators identically on both sides. */
uint32_t match_seed();

/* Next frame whose state hash differed from the peer's, if any (for the
 * hooks' T5_NET_DESYNC_DUMP diagnostics). */
bool take_mismatch(uint32_t* frame);

/* Frame log line extension (T5_NET_LOG): free-form text for frame f, written
 * after the inputs and hash. */
void  log_extra(uint32_t f, const char* text);

/* Passive reference mode (T5_NET_PASSIVE=1): no lockstep, the local sources
 * are polled on every pad read. player 0 = this PC's pad, 1 = T5_NET_SCRIPT2 /
 * T5_NET_PADFILE2. */
PadInput poll_now(int player);

void  note(const char* fmt, ...);

/* ---- session health (docs/NETPLAY.md "Connection problems") ---------------
 * The handshake runs in the background from init() on (boot), so a missing or
 * mismatched peer is known long before the match starts.
 *   failure()      non-null once connecting has failed for good: "no_peer" (no
 *                  answer within T5_NET_CONNECT_TIMEOUT), "build_mismatch",
 *                  "rejected" (the peer is in another session)
 *   lost_reason()  non-null once a connected peer is gone: "peer_quit",
 *                  "peer_timeout" (silent for T5_NET_TIMEOUT), "peer_stalled"
 *                  (alive but no input for T5_NET_TIMEOUT), "start_timeout"
 *                  (never reached the start of the match), "peer_restarted"
 * Either way the lockstep waits return (neutral peer input); the hooks end the
 * match. */
const char* failure();
const char* lost_reason();
bool  connected();
/* Per match: mismatching frames counted from frame f on (the match's sync
 * point), the frames whose hashes were compared, this PC's own speed. */
void     match_begin(uint32_t f);
uint32_t match_mismatches();
uint32_t checked_through();          /* hashes compared for every frame < this */
double   local_fps();                /* frames per second since match_begin(), time waiting for the peer left out */
void     bye();                      /* tell the peer we are leaving (BYE, 3x) */
/* Called (once) from the network thread when the session failed or the peer
 * was lost and the main thread did not act on it within a few seconds (it may
 * be blocked outside the lockstep waits). */
void     set_stuck_handler(void (*fn)(const char* reason));

/* ---- rollback mode (src/rollback/rb_net.cpp) ------------------------------
 * The same transport, rings, redundancy and desync check as the lockstep,
 * without the per-frame block: the rollback loop decides when to wait. */
void     rb_begin(uint32_t f);                   /* f == 0: handshake, neutral frames < delay (as begin_frame(0) does) */
void     rb_sample_local(uint32_t f, bool neutral = false);   /* sample this PC's input for frame f + delay() and send it (neutral: send neutral input, devices not read) */
PadInput rb_local(uint32_t f);                   /* the local input decided for frame f (neutral if none yet) */
bool     rb_remote(uint32_t f, PadInput* out);   /* the peer's input for frame f, if it has arrived */
uint32_t rb_remote_contig();                     /* the peer's inputs are known for every frame < this */
uint32_t rb_wait_remote(uint32_t f, uint32_t ms);/* wait up to ms for the peer's input for frame f; returns rb_remote_contig() */
void     rb_push_hash(uint32_t f, uint64_t h);   /* the FINAL state hash of frame f (all inputs before it confirmed) */
/* frames.log line for a live frame of the rollback loop: "f I <p1> <p2> <hash> R|P C|U"
 * (R = remote input confirmed, P = predicted; C = the hash is final/confirmed) */
void     rb_log_frame(uint32_t f, const PadInput in[2], uint64_t hash, bool predicted, bool confirmed);
void     rb_poll();                              /* resend when stalled (15 ms), compare hashes */
bool     rb_peer_lost();
/* Rollback is negotiated in the HELLO: each side that offers it sets a flag,
 * both flags set = the rollback loop runs, otherwise the lockstep does. The
 * offer must be made before the handshake (the rollback loop does it when
 * T5_RB_MODE is unset or "net"; T5_RB_MODE=off or lockstep keeps the lockstep). */
void     rb_offer(bool on);
bool     rb_negotiated();
int      rb_apply_delay();                       /* rollback agreed: switch to the rollback input delay (the host's T5_RB_NET_DELAY); returns the delay */
void     rb_account_frame(uint64_t wait_us);     /* a live frame of the rollback loop ran: the speed line and local_fps() (wait_us: time spent waiting for the peer) */
/* Time sync: each packet carries the sender's frame-advantage estimate. */
void     rb_set_lead(int lead);
int      rb_peer_lead();
uint32_t rb_mismatches();
uint32_t rb_peer_ack();                          /* the peer has our inputs for frames < this */

/* While on, the local player's sample is exactly `buttons` (direct-fight menu
 * driving during lockstep; see t5_netplay_inject). */
void  set_local_inject(bool on, uint16_t buttons);
/* T5_NET_SCRIPT_FIGHT=1 (tests): the scripted local input (T5_NET_SCRIPT) applies
 * only while the direct-fight driver is in a fight, so it never presses
 * anything in the menus direct fight drives between matches. */
void  set_script_gate(bool on);

} // namespace np

/* Game-side entry point (t5_hooks.cpp), C linkage so any part of the port can
 * call it: the direct-fight mode calls t5_netplay_start() on the main thread at
 * the frame its fight starts. With T5_NET_START=external lockstep begins there
 * (both PCs meet at the frame-0 handshake); while lockstep runs it marks a sync
 * point (next match in the same process). No-op when netplay is off. */
extern "C" void t5_netplay_start(void);

/* Menu driving by the direct-fight mode: while `on`, pad `port` reads exactly
 * `buttons` (CELL_PAD_CTRL_* packed as PadInput::buttons) instead of the local
 * pad or the lockstep input -- both PCs inject the same sequence from the same
 * game state. t5_netplay_enabled() tells whether netplay owns the pads at all. */
extern "C" void t5_netplay_inject(int port, int on, unsigned buttons);
extern "C" int  t5_netplay_enabled(void);
/* Lockstep running (after t5_netplay_start()): then only the local slot's
 * injection applies, as the local player's exchanged input; the peer drives
 * its own. Before lockstep both ports are injected locally. */
extern "C" int  t5_netplay_lockstep_active(void);
extern "C" int  t5_netplay_local_slot(void);     /* 0 = P1 (host), 1 = P2 (join) */
/* The lobby's id of the match about to start (direct fight: from the fight line's
 * match=<id>); goes into the result file so the launcher never takes a result
 * of one match for another. T5_NET_MATCH until set. */
extern "C" void t5_netplay_set_match(const char* id);
/* The seed both PCs share for this session (T5_NET_SEED, else the host's
 * session id; waits for the handshake). Direct fight derives a stage from it
 * when none was given. */
extern "C" unsigned t5_netplay_match_seed(void);
