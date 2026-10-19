/*
 * Replays (docs/REPLAYS.md): every online session's confirmed inputs, its sync
 * points and its match setups in a small file; played back by the same netplay
 * loop with the file as a perfect peer.
 *
 * Recording (T5_NET_MODE host/join with T5_REPLAY_DIR set): the netplay core
 * hands over every frame's two confirmed inputs and the state hash of every
 * T5_REPLAY_HASH_EVERY-th frame (the hash the peers compare), the hooks every
 * sync point (its frame, the frame both games continued at, the seed of the
 * random generators and the game's frame counters after it) and each match's
 * result, the direct-fight driver each match's setup at FIGHT START. Nothing is
 * written to guest memory and nothing changes what the game does; the file is
 * written by a worker thread at a match's end (and again once its after-match
 * frames are in), at session end on the calling thread.
 *
 * Playback (T5_NET_MODE=replay, T5_REPLAY_FILE=<file>): netplay's local mode
 * (no socket) whose inputs, sync points, seeds and counters come from the
 * file; the same loop (lockstep or rollback, as recorded) and the same direct
 * fight run as in the live match, and every recorded hash is compared.
 */
#pragma once
#include <stdint.h>
#include <string>
#include "netplay.h"

namespace rp {

/* Sync point kinds (t5_hooks.cpp): the match start of a later match in the
 * session, the end of a fight's loading, a lockstep scene change (input ring
 * reset), the in-game select's pause and its resume. Frame 0 of a session is not
 * one (its seed and counters are the session's). */
enum Kind : uint32_t { kResync = 1, kLoad = 2, kRing = 3, kPause = 4, kResume = 5 };

struct Barrier {
    uint32_t kind = 0, f = 0, nf = 0, seed = 0;
    bool has_state = false;            /* the counters below were set at this sync point */
    uint64_t clock = 0;                /* 0x106D4D88 */
    uint32_t c[3] = { 0, 0, 0 };       /* 0x1008EB9C, 0x1008F07C, 0x1009442C */
};

/* A match's setup at FIGHT START (direct fight): characters, confirm buttons
 * (costumes), the model ids the game fights with, stage, rounds, the in-game
 * select's seconds (0 = picked by the lobby/launcher), the HUD names. */
struct Fight {
    int chr[2] = { -1, -1 }, btn[2] = { 0, 0 }, model[2] = { -1, -1 };
    int stage = -1, rounds = 3, pick = 0;
    std::string names[2];
};

/* ---- recording ----------------------------------------------------------- */
bool recording();                                   /* this session is being recorded */
void rec_session_begin(int slot, const char* build, uint32_t session_seed);   /* netplay_core configure() (host/join) */
void rec_session_end(const char* why);              /* the session is over: the file is written now (this thread) */
void rec_start(uint32_t match_seed, bool rollback, int delay);   /* lockstep frame 0 (t5_hooks) */
void rec_rollback_delay(int d);                     /* the rollback loop's input delay for the session */
void rec_input(uint32_t f, const np::PadInput& p1, const np::PadInput& p2);   /* frames in order, from 0 */
void rec_hash(uint32_t f, uint64_t h);              /* the state hash the peers compare for frame f */
void rec_barrier(const Barrier& b);
void rec_fight(const Fight& ft);                    /* direct fight, FIGHT START (before t5_netplay_start()) */
void rec_match_begin(uint32_t f);                   /* the match's sync point is frame f (t5_hooks match_begins) */
void rec_result(const char* winner, unsigned w1, unsigned w2, const char* reason, uint32_t frames,
                bool have_hash, uint64_t hash, uint32_t desync, uint32_t at_frame);
void rec_frame(uint32_t f);                         /* a live frame ran (periodic and after-match writes) */
uint32_t hash_every();

/* ---- playback ------------------------------------------------------------ */
bool playing();                                     /* T5_NET_MODE=replay with a loaded file */
bool play_load(const char* path);                   /* netplay_core configure(); false = no usable file (play_error() says why) */
const char* play_error();
int  play_slot();
int  play_delay();
bool play_rollback();
uint32_t play_session_seed();
uint32_t play_match_seed();
void play_inputs(uint32_t p, np::PadInput out[2]);  /* the recorded inputs of playback frame p (P1, P2) */
uint32_t play_barrier(uint32_t k, uint32_t f);      /* the k-th sync point, reached at playback frame f: the frame to continue at */
/* after the hooks did their part of sync point k: the recorded seed for the
 * reseed (`computed` when the file has none) and, if the file has them, the
 * frame counters to set (true) */
uint32_t play_barrier_seed(uint32_t k, uint32_t kind, uint32_t computed);
bool play_barrier_state(uint32_t k, uint64_t* clock, uint32_t c[3]);
void play_hash(uint32_t p, uint64_t h);
void play_fight(const Fight& ft, uint32_t match);   /* FIGHT START of the playback's match-th match: compared */
bool play_fight_line(uint32_t match, std::string* line);   /* the direct-fight line of match `match` (1-based) */
void play_result(const char* winner, unsigned w1, unsigned w2, uint32_t frames, bool have_hash, uint64_t hash, uint32_t p);
void play_match_begin(uint32_t p);                  /* a match's sync point in the playback */
/* every playback frame boundary (main thread): returns false once the replay is over */
bool play_frame(uint32_t p);
void play_finish(const char* why);                  /* write T5_REPLAY_RESULT, log the verdict */
void play_fail(const char* path, const char* why);  /* the file could not be played: T5_REPLAY_RESULT says why */
uint32_t play_target();                             /* the match being watched (1-based) */
uint32_t play_match_index();                        /* matches begun so far in the playback */

} // namespace rp
