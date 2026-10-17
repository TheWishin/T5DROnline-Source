/*
 * The fight's simulation state in guest memory: the state set, its per-frame
 * hash and the undo-log snapshots (docs/ROLLBACK.md sections 1 and 7).
 *
 * All of it is driven from the main thread at the frame boundary. The kernel's
 * write watch (PS3_VM_WRITE_WATCH=1) supplies the pages written since the
 * previous boundary; one pass over them updates the incremental hash, appends
 * each page's pre-image (from a shadow copy of the state set) to the undo log
 * of the frame that just ran and refreshes the shadow. Rolling back k frames
 * applies k undo logs, newest first. No full copies after the initial shadow.
 */
#pragma once
#include <stdint.h>
#include <stddef.h>

namespace rb {

struct Range { uint32_t base, len; };

/* The state set S, the exclusions E (written asynchronously by other threads:
 * neither restored nor hashed) and the restored-but-not-hashed ranges. */
extern const Range kSave[];        extern const size_t kSaveN;
extern const Range kExclude[];     extern const size_t kExcludeN;
extern const Range kHashExclude[]; extern const size_t kHashExcludeN;
bool excluded_page(uint32_t ea);
bool hash_excluded_page(uint32_t ea);
void state_add_hash_exclude(uint32_t ea, uint32_t len);   /* T5_RB_HASH_EXCLUDE */
/* A range written by another thread (neither saved, restored nor hashed from
 * now on; e.g. a streaming buffer the HLE reports). Returns false if known. */
bool state_add_exclude(uint32_t ea, uint32_t len);
void state_add_mask(uint32_t ea, uint32_t len);           /* a word masked out of the hash */

/* Allocate the tables, the shadow (a copy of S taken now) and the undo ring.
 * Call once at a frame boundary before the first commit. */
void     state_init();
bool     state_ready();

/* At the boundary of logical frame f (frame f-1 has just run): scan the dirty
 * pages, update the hash, record frame f-1's undo log, refresh the shadow.
 * on_page (optional) sees every dirty state page with its new hash.
 * Returns the number of dirty state pages; ms gets the time spent. */
uint32_t state_commit(uint32_t f, void (*on_page)(uint32_t ea, uint64_t h), double* ms);

/* Rehash every page of S (the hash is incremental otherwise). */
void     state_hash_full();
uint64_t state_hash();
uint64_t state_page_hash(uint32_t ea);
/* The gameplay hash: the match state the netplay desync check compares
 * (src/netplay/t5_hooks.cpp kDefaultHash: pad blocks, input ring, frame
 * clock, random generators, round state, both fighters -- ~25 KB), computed
 * on demand. Unlike the full-state hash it is independent of whether a
 * frame was drawn, so it is the verdict of the draw-cut test and what the
 * peers compare. */
uint64_t state_game_hash();
/* The bytes the gameplay hash covers, in region order (for desync dumps);
 * returns the byte count, at most cap. */
uint32_t state_game_bytes(uint8_t* out, uint32_t cap);
uint64_t hash_page(uint32_t ea);

/* Roll the state back from the current boundary f to the boundary of frame
 * `to` (to < f) by applying the undo logs of frames f-1 .. to. Returns false
 * (and does nothing) when a log that far back is no longer in the ring.
 * Afterwards the hash is the hash the run had at that boundary, and the
 * write watch is reset. pages/ms report the work done. */
bool     state_rollback(uint32_t to, uint32_t* pages, double* ms);
uint32_t state_oldest_frame();       /* the oldest boundary a rollback can reach */
void     state_drop_logs();          /* forget every undo log (a barrier: no rollback past now) */
void     state_reset();              /* a new netplay session (persistent game): no logs, frame numbers from 0, shadow brought up to date */
uint32_t state_log_pages(uint32_t f); /* pages in frame f's undo log (0 when gone) */

/* Pointer into the shadow copy (the state as of the last commit), or null. */
const uint8_t* state_shadow(uint32_t ea);

} // namespace rb
