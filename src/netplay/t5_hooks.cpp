/*
 * T5DR netplay prototype -- where the lockstep core meets Tekken 5 DR
 * (NPUB30009 v01.00). All guest addresses below are for that exact EBOOT.
 *
 * How the game reads the pads (from its code):
 *   - A thread named "keyread" (code 0x120B68) loops on a semaphore whose id
 *     lives at 0x104CB5C0. Each wake it updates every pad (cellPadGetInfo +
 *     cellPadGetData per connected port, 0x375538), converts ports 0 and 1
 *     into a 16-bit game mask each (0x8F6F0) and stores them in a 16-entry
 *     ring (0x104CCDFC: P1 u16[16], P2 u16[16]; write index 0x104CCE3C).
 *   - The keyread semaphore is posted from the VBlank handler (0x34BC08 runs
 *     a callback list; 0x2598A8 posts it), i.e. on WALL-CLOCK vblanks.
 *   - The main loop samples the newest ring entry once per frame (0x12D74 ->
 *     0x120A78, read index 0x104CCE40) and computes its own press edges. It
 *     paces itself on a semaphore (id at 0x106D4A30) that the same VBlank
 *     handler posts: 0x34BAA0 waits for the flip, then sys_semaphore_wait on it.
 *
 * So which pad sample a game frame sees depends on a race between two threads
 * woken by the same vblank. For lockstep that has to go. With netplay on:
 *   - the vblank's keyread wake is swallowed (keyread parks for good) and the
 *     MAIN thread runs the keyread tick itself, once, at the top of each of its
 *     frames, with both players' input for that frame already decided by the
 *     lockstep core (the keyread thread cannot be woken and waited for: the pad
 *     update takes the lwmutex 0x106D4D00 that the main thread holds there);
 *   - the loader threads the main loop feeds are drained at the top of every
 *     frame, so a load finishes in the same frame on both PCs;
 *   - the game's random generators are seeded from the match seed at frame 0
 *     and at every scene change, and scene changes are sync points (both PCs
 *     continue from the same frame number) in case something still lands a
 *     frame apart;
 *   - a hash of the match state is exchanged every frame (desync detector).
 *
 * Hooks used (no ps3recomp changes):
 *   - HLE overrides (ps3_hle_register_ctx is dispatched before the NID table):
 *     cellPadInit, cellPadGetInfo (always exactly two pads), cellPadGetData.
 *   - lv2 syscall table wrappers for sys_semaphore_wait (92) and
 *     sys_semaphore_post (94), installed from our cellPadInit (after
 *     lv2_init_syscalls has filled the table).
 *   - guest calls (ppu_guest_call_ct) into the game's own keyread pieces and
 *     RNG seeding functions.
 *
 * Options and diagnostics (all optional):
 *   T5_NET_RESULT_FILE  {"match":id,"winner":0|1|null,"score":[p1,p2],"desync":n,"frames":n,
 *                    "hash":"..","fps":x} when a match ends; with "reason" when it could not
 *                    be played to the end (peer lost, no peer, other build)
 *   T5_NET_ON_LOST   exit (default): a failed or lost session ends the match -- result file,
 *                    then the game closes (exit code 3 peer lost, 4 no connection, 5 other
 *                    build); idle: the old behaviour, play on with the peer's player idle
 *   T5_NET_ROUNDS    rounds to win, written to the battle config (0x1008EBD4) at every sync
 *                    point of a VS game (menu-driven play; direct fight takes T5_FIGHT's)
 *   T5_NET_DRAIN     semaphore ids of loader threads to drain (default "8,10")
 *   T5_NET_HASH      regions hashed into the per-frame state hash,
 *                    "addr:len,addr:len" (hex). Default: kDefaultHash.
 *   T5_NET_HASH_SKIP words inside those regions left out (default kDefaultHashSkip)
 *   T5_NET_DESYNC_DUMP=1  on a hash mismatch, write the hashed bytes of that (=<n>: up to n files, default 20)
 *                    frame to np_desync_f<frame>.bin (diff the two PCs' files)
 *   T5_NET_PAGEHASH  "addr:len[:every]" (hex, every in frames, default 60):
 *                    write per-4KB-page hashes of that range to the frame log.
 *   T5_NET_DUMP      comma-separated frames at which to dump memory to
 *                    np_dump_f<frame>_<addr>.bin in the working directory.
 *   T5_NET_DUMP_RANGES  "addr:len,..." (hex) for T5_NET_DUMP.
 *   T5_NET_SHOT      frames to screenshot exactly (needs LD_SURF_DUMP and
 *                    LD_SURF_DUMP_GATE; tools/netplay_test.py sets them)
 *   T5_NET_PASSIVE=1 reference runs: pad overrides only, keyread untouched
 *   T5_NET_PADS      pads reported connected (default 2)
 *   T5_NET_TRACE=1   log semaphore / syscall traffic per thread and allocations.
 */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <bcrypt.h>
#include <stdlib.h>
#include <atomic>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>

#include "ppu_recomp.h"   /* ppu_context, vm_base -- from the lifter output */
#include "netplay.h"
#include "replay.h"       /* replays: recording and playback (docs/REPLAYS.md) */
#include "no_pause.h"     /* no pause online: the rule (docs/NETPLAY.md "No pause online") */
#include "match_score.h"  /* a decided match's score: the fighters' round counts (docs/NETPLAY.md "Match result") */
#include "../rollback/rb_net.h"   /* T5_RB_MODE=net: the rollback loop takes the per-frame decisions */
namespace rb { void rand_install(); void tls_rand_reseed(uint32_t tls_base, uint32_t seed, bool streams); }   /* rb_rand.cpp: the TLS random generator */

extern "C" int t5_df_in_fight(void);   /* src/directfight/df_fight.cpp (T5_NET_SCRIPT_FIGHT) */
extern "C" void t5_df_frame_tick(ppu_context* ctx);   /* src/directfight/df_hooks.cpp: its frame hook, when no wait runs it */
extern "C" int t5_df_game_mode(void);  /* src/directfight/df_fight.cpp: the game's mode manager is in the game mode */
extern "C" uint32_t t5_df_mode_cur(void);  /* src/directfight/df_fight.cpp: the mode manager's current mode (6 = select) */
extern "C" uint32_t t5_df_mode_next(void); /* src/directfight/df_fight.cpp: the mode the manager was asked for (14 = none) */
extern "C" void t5_df_window_closed(void);   /* src/directfight/df_fight.cpp: state.json "quit" (persistent game) */
extern "C" void t5_training_frame(ppu_context* ctx);   /* src/training/training.cpp: the training overlay */
/* ps3recomp patch 0035 (boot_main.cpp, rsx_null_backend.c): the game window was closed; Esc asks twice */
extern "C" void ps3_set_window_closed_handler(void (*fn)(void));
extern "C" void ps3_set_window_close_guard(int (*fn)(void));
namespace rb { void sndheap_install(); }   /* src/rollback/rb_sndheap.cpp */
extern "C" void t5_unlock_install(void);   /* src/directfight/df_unlock.cpp: unlocks (docs/DIRECTFIGHT.md "Unlocks") */
extern "C" void t5_select_trace(void);     /* src/directfight/df_unlock.cpp: T5_SELECT_TRACE=1 (diagnostics) */
extern "C" uint32_t t5_df_session_matches(void);   /* src/directfight/df_fight.cpp: fights started in this netplay session */
extern "C" uint32_t t5_df_find_mode(uint32_t f);    /* src/directfight/df_hooks.cpp: the mode manager's mode (offline tests) */
extern "C" {
void    ps3_hle_register_ctx(uint32_t nid, const char* name, void (*fn)(ppu_context*));
int32_t cellPadInit(uint32_t max_connect);           /* ps3recomp libs/input/cellPad.c */
int32_t cellPadGetInfo(void* info_guest);
int32_t cellPadGetData(uint32_t port, void* data_guest);
uint64_t ppu_guest_call_ct(uint32_t code, uint32_t toc, uint64_t a0, uint64_t a1, uint64_t a2,
                           uint64_t a3, uint64_t a4, uint64_t a5, uint64_t a6, uint64_t a7);
typedef int64_t (*np_lv2_fn)(ppu_context*);
/* runtime/syscalls/sys_semaphore.h (Windows layout), read-only use: the
 * semaphore table tells whether a loader thread is parked with nothing to do. */
struct np_sys_semaphore_info {
    int      active;
    char     name[8];
    uint32_t protocol;
    int32_t  value;
    int32_t  max_value;
    int32_t  waiters;
    HANDLE   sem_handle;
    CRITICAL_SECTION value_lock;
};
extern np_sys_semaphore_info g_sys_semaphores[];
extern np_lv2_fn g_lv2_syscalls[];                   /* lv2_syscall_table { handlers[1024] } */
}

namespace {

/* ---- guest addresses (NPUB30009 v01.00) ---------------------------------- */
constexpr uint32_t kKeyreadSemPtr = 0x104CB5C0;  /* u32 semaphore id */
constexpr uint32_t kKeyreadQuit   = 0x104CCDF4;  /* keyread object + 0x1814: thread exit flag */
constexpr uint32_t kFrameSemPtr   = 0x106D4A30;  /* graphics object + 0x30: per-frame semaphore id */
constexpr uint32_t kKeyreadObj    = 0x104CB5E0;  /* keyread thread's object (arg) */
constexpr uint32_t kRingResetFlag = 0x104CCDF8;
constexpr uint32_t kRing          = 0x104CCDFC;  /* u16 P1[16], u16 P2[16] */
constexpr uint32_t kRingWriteIdx  = 0x104CCE3C;
constexpr uint32_t kRingReadIdx   = 0x104CCE40;
constexpr uint32_t kFrameClock    = 0x106D4D88;  /* u64 read by the pad repeat logic; +8: vblank count */
constexpr uint32_t kTOC           = 0x470540;    /* main TOC (r2) */
constexpr uint32_t kMatchOver     = 0x1008EBD5;  /* u8: 0 during a match, set when it is decided */
constexpr uint32_t kWinsP1        = np::MatchScore::kRoundWinsP1;  /* u8: rounds won by P1 in this match (match_score.h) */
constexpr uint32_t kWinsP2        = np::MatchScore::kRoundWinsP2;  /* u8: rounds won by P2 */
constexpr uint32_t kWinnerIdx     = 0x1008EBD6;  /* u8: 0 = P1, 1 = P2, set together with kMatchOver (seen in the dry run) */
constexpr uint32_t kFnTickCounter = 0x09A204;
constexpr uint32_t kFnPadUpdate   = 0x08F3A4;
constexpr uint32_t kFnRingReset   = 0x120764;
constexpr uint32_t kFnPortMask    = 0x08F6F0;
constexpr uint32_t kFnRingAdvance = 0x12071C;
constexpr uint32_t kFnTickTail    = 0x13F91C;
constexpr uint32_t kFnMtSeed      = 0x066784;    /* init_genrand(s): Mersenne Twister, state 0x10095168 */
constexpr uint32_t kFnSrand       = 0x36921C;    /* srand(s): the C library rand() (0x369228), state 0x1074F218 */
constexpr uint32_t kConfig        = 0x1008EBAC;  /* battle config: +0 game type (4 = VS BATTLE) */
constexpr uint32_t kRoundsToWin   = 0x1008EBD4;  /* battle config +0x28: rounds to win (u8) */
/* The lwmutex the main thread holds across its per-frame wait (it guards the
 * frame clock 0x106D4D88; the keyread tick takes it too). sys_lwmutex_t as the
 * runtime models it: owner (guest tid) at +0, recursion count at +0xC. */
constexpr uint32_t kFrameLwm      = 0x106D4D00;
constexpr uint32_t kFnLwmLock     = 0x3C6F00;    /* sysPrxForUser import stubs: sys_lwmutex_lock(lwm, timeout) */
constexpr uint32_t kFnLwmUnlock   = 0x3C6F20;    /*                             sys_lwmutex_unlock(lwm) */

constexpr uint32_t NID_cellPadInit    = 0x1CF98800;
constexpr uint32_t NID_cellPadGetInfo = 0x3AAAD464;
constexpr uint32_t NID_cellPadGetData = 0x8B72CDA1;

constexpr int SC_SEM_WAIT = 92, SC_SEM_TRYWAIT = 93, SC_SEM_POST = 94, SC_MEM_ALLOC = 348;

/* ---- guest memory (big-endian) -------------------------------------------- */
inline uint32_t rd32(uint32_t a) { uint32_t v; memcpy(&v, vm_base + a, 4); return _byteswap_ulong(v); }
inline uint64_t rd64(uint32_t a) { uint64_t v; memcpy(&v, vm_base + a, 8); return _byteswap_uint64(v); }
inline void wr32(uint32_t a, uint32_t v) { v = _byteswap_ulong(v); memcpy(vm_base + a, &v, 4); }
inline void wr64(uint32_t a, uint64_t v) { v = _byteswap_uint64(v); memcpy(vm_base + a, &v, 8); }
inline void wr16(uint32_t a, uint16_t v) { v = _byteswap_ushort(v); memcpy(vm_base + a, &v, 2); }
inline void wr8(uint32_t a, uint8_t v) { vm_base[a] = v; }
inline uint8_t rd8(uint32_t a) { return vm_base[a]; }

uint64_t fnv64(const uint8_t* p, size_t n, uint64_t h = 1469598103934665603ull)
{
    for (size_t i = 0; i < n; i++) { h ^= p[i]; h *= 1099511628211ull; }
    return h;
}

struct Range { uint32_t addr, len; };
std::vector<Range> parse_ranges(const char* spec)
{
    std::vector<Range> r;
    if (!spec) return r;
    const char* p = spec;
    while (*p) {
        char* e;
        uint32_t a = (uint32_t)strtoul(p, &e, 16); if (e == p || *e != ':') break; p = e + 1;
        uint32_t l = (uint32_t)strtoul(p, &e, 16); if (e == p) break; p = e;
        r.push_back({ a, l });
        while (*p == ',' || *p == ' ') p++;
    }
    return r;
}

/* ---- state ----------------------------------------------------------------- */
np_lv2_fn g_orig_wait = nullptr, g_orig_post = nullptr, g_orig_alloc = nullptr;
std::atomic<bool> g_installed{ false };
std::atomic<bool> g_active{ false };          /* lockstep running: ticks are ours */
std::atomic<bool> g_swallow{ false };         /* vblank wakes of keyread are dropped */
std::atomic<uint32_t> g_kr_enter{ 0 }, g_kr_wake{ 0 };
std::atomic<int> g_kr_in_wait{ 0 };
std::atomic<uint32_t> g_swallowed{ 0 };
std::atomic<int> g_kr_posting{ 0 };           /* keyread posts between the swallow check and the real post */
uint32_t g_takeover_frame = 0;                 /* main loop frame of the take-over (the swallow frame + 1) */
bool g_takeover_test = false;                  /* T5_NET_TAKEOVER_TEST=1: always hand the frame lock over once */
HANDLE g_kr_event = nullptr;                  /* set when keyread re-enters its wait */
uint32_t g_frame = 0;                          /* next lockstep frame (main thread only) */
uint32_t g_scenes = 0;                         /* scene changes so far */
uint32_t g_frame_hashing = 0;                  /* frame whose state is being hashed */
uint64_t g_main_tid = ~0ull;
np::PadInput g_cur[2] = { np::kNeutral, np::kNeutral };
bool g_trace = false;
/* T5_NET_START: when lockstep begins.
 *   boot      (default) the main loop's first frames, right after boot;
 *   external  when the game side calls t5_netplay_start() (the direct-fight
 *             mode, at the frame its fight starts); until then the game runs
 *             on its own with both pads neutral;
 *   frame:N   (tests) at the main loop's N-th frame since boot.
 * A later t5_netplay_start() while lockstep runs (next match in the same
 * process) is a sync point like a scene change. */
enum class StartMode { Boot, External, Frame };
StartMode g_start_mode = StartMode::Boot;
uint32_t g_start_frame = 0;
uint32_t g_boot_frames = 0;                    /* main loop frames since our hooks went in */
std::atomic<bool> g_start_requested{ false };
bool g_passive = false;   /* T5_NET_PASSIVE=1: pad overrides only, keyread untouched (reference runs) */
int  g_pads = 2;          /* T5_NET_PADS: pads reported connected (2 for netplay) */
/* Persistent game (T5_CTL_DIR, docs/DIRECTFIGHT.md "Persistent game"): the
 * hooks are in from boot without a session; sessions come and go with the
 * control channel (t5_netplay_session_begin/end at the end of this file). */
bool g_persistent = false;
bool g_await_load = false;  /* direct fight: the end of the fight's loading is still to come; it is a sync point (on_frame_start) */
/* The end of a fight's loading, as a sync point: the first boundary at which
 * the phase word shows the intros (11, 12) or the fight (17) after a fight
 * start. It used to be the first ring reset after the fight start -- which is
 * "Fight!" itself (phase 17), after the intros: a game whose loading ended 2
 * frames later ran the whole intro 2 frames later and its "Fight!" frame on a
 * random state with 2 frames' fewer draws and a frame clock 2 frames on; the
 * barrier and reseed came only after that frame. For most pairs of fighters it
 * never showed; Asuka vs Law on stage 25 desynced every time a game that had
 * played met a fresh one, in rollback and in lockstep, on main too (reset-fix
 * runs ff_asu_main, ff_asu6, ff_asu6ls: 1,641-4,128 mismatching frames). From
 * the end of the loading the intros run a fixed 28 frames on both PCs. */
bool fight_loaded_now() { const uint32_t p = rd32(0x1008F070u); return p >= 11 && p <= 17; }
bool g_idle = false;      /* ticks are ours (keyread parked) but no lockstep runs: between two sessions */
/* In-game select (docs/DIRECTFIGHT.md "Character select in the game"): between
 * two matches of a session the lockstep pauses -- each player picks on the
 * game's own select screen, which is not lockstep material -- and resumes at the
 * next fight's start. The pause is a sync point (both games at the same frame,
 * every input before it confirmed); while paused the hooks run as between two
 * sessions (g_idle); t5_netplay_start() resumes at the paused frame number with
 * a sync point that also sets the game's frame counters and input ring equal
 * (the two games ran their own number of frames meanwhile). */
std::atomic<bool> g_pause_requested{ false };
bool g_paused = false;
/* Offline (no netplay): the keyread tick on the main thread too (T5_LATE_INPUT,
 * default on, docs/RENDER_PERF.md "Input latency"). The game's own keyread
 * thread reads the pads at the vblank, then waits for the frame lock the main
 * thread holds there, and writes the ring after the main thread has already
 * taken this frame's entry: 5-12 % of presses (more on a busy PC) reached the
 * game a frame late. Run at the top of the frame like netplay's, the pads are
 * read at the frame's start and that frame always sees them. */
bool g_offline = false;
bool g_offline_gave_up = false;
ppu_context* g_frame_wait_ctx = nullptr;   /* the main thread's latest frame-semaphore wait */
std::atomic<const char*> g_session_lost{ nullptr };   /* why the last session ended by itself (df picks it up) */
void persistent_lost(const char* reason);

/* Loader threads drained at the top of every frame (T5_NET_DRAIN, semaphore
 * ids). The ids are the game's own creation order, the same every run:
 *   8  ZsAread   -- the main thread's async read requests; it hands each to
 *                   NU::File::RequestManager (sem 1) and waits for the data
 *                   (sem 11) before it parks again
 *   10 "decoder" -- also fed by the main thread
 * A load the main loop started in frame f is then always finished, as far as
 * the game can tell, when frame f+1 starts -- on both PCs. Without it the
 * frame a load completes in depends on the disk and the OS scheduler.
 * Semaphores 1 and 11 themselves are not drained: the sound streamer feeds
 * them all the time, and waiting for it cost whole seconds per frame.
 * The wait has no time limit while a session runs (drain_wait): a frame that
 * started with its loads still running -- the old 2 s limit -- put the loading
 * and the fight's intros a frame or more apart on the two PCs. */
constexpr int kMaxSem = 64;
bool g_drain[kMaxSem] = {};
std::atomic<bool> g_drain_seen[kMaxSem];   /* a thread has waited on it since our hooks went in */
HANDLE g_drain_event = nullptr;
uint32_t g_drain_notes = 0;                 /* "still busy" lines written (capped) */
uint32_t g_drain_test_ms = 0;               /* T5_TEST_DRAIN_HOLD (tests): see drain_wait */
uint32_t g_drain_test_frame = 0;

std::vector<Range> g_hash_ranges, g_hash_skip, g_dump_ranges;
std::vector<uint32_t> g_dump_frames;
std::vector<uint32_t> g_shot_frames;    /* T5_NET_SHOT: frame-exact screenshots via the renderer's LD_SURF_DUMP_GATE */
std::string g_shot_gate;
uint32_t g_shot_armed = UINT32_MAX;
Range g_page_range = { 0, 0 };
uint32_t g_page_every = 60;

/* What goes into the per-frame state hash by default: memory that follows
 * from the inputs alone. Found by dumping both PCs at the same frames of a
 * fight (T5_NET_DUMP) and keeping what changes over time yet is equal on both
 * (tools/netplay_memdiff.py); see docs/NETPLAY.md. */
const char* kDefaultHash =
    "10099F24:70,"      /* the game's two pad state blocks (56 B each) */
    "104CCDFC:40,"      /* the P1/P2 input ring */
    "106D4D88:8,"       /* the game's frame clock */
    "10095168:9C0,"     /* Mersenne Twister state (624 words) */
    "10053578:4,"       /* ... and its index */
    "10076920:4,"       /* the LCG at 0x1621D0 */
    "1074F218:10C,"     /* C library rand() state and its two lagged generators */
    "1008E000:4000,"    /* round state and both fighters (0x8D0-byte blocks from ~0x1008F800) */
    "10099600:600,"     /* fight state next to the pad blocks */
    "100A0900:200,"
    "100A3B00:300";
/* Words inside those regions that differ between two PCs that are otherwise
 * in step (cosmetic or timing-derived: sound variations, timestamps). */
const char* kDefaultHashSkip =
    "1074F218:4,"                     /* the C library rand() word: a side thread (0x1230AC -> 0x12C558) consumes it at its own pace */
    "1008F088:4,"                     /* the stage id: re-rolled from that rand() at the second round's intro (l0d: 0x13 vs 0x1A), the fight unchanged */
    "10090030:4,10090900:4,"          /* +0x830 of each fighter block: a pointer into 0x10670000 set at a match intro (m50c: 0x10670AF0 vs 0x106707F0), the fight unchanged */
    /* +0x830 of the third and fourth 0x8D0 block (0x100909A0, 0x10091270) and the
     * twenty heap pointers at 0x10091AB8: addresses of objects the character
     * animation update (0x27F904 <- 0x2887E8 <- 0x264B28) takes from a pool at a
     * match intro; which slot it gets depends on what else came and went (the
     * stage's own effects run on a side thread). They differ between two PCs
     * in plain lockstep too (rollback10 run e1lock, no rollback: 0x100911D0
     * 0x106704F0 vs 0x106701F0 from match 2's intro, nothing else), so they are
     * addresses, not match state (docs/ROLLBACK.md section 20) */
    "100911D0:4,10091AA0:4,10091AB8:50,"
    "100A0A00:80,"                    /* an effect record set at a match intro: a unit vector at +0x10 (m0c), a scale at +0x30 (n0c: 1,1,1 vs 0,0,0), the fight unchanged */
    "1008F0D0:4,"                     /* a counter of the battle object that the intro's timing moves (Devil Jin, run dvjf: 0x379 vs 0x378 for frames 190-223) */
    /* (0x1008F0C4, skipped here before as a "timestamp", is the scene's LCG
     * x -> 5x + 3: gameplay -- camera picks, effect variants. In the hash since
     * desync hunt 2; the ambient sound task steps a private copy (rb_rand.cpp)
     * and netplay reseeds it at every sync point (reseed()).) */
    "1008FF00:C,1008FFB0:C,"          /* two xyz points (0xB0 apart) a few units off: secondary motion */
    "1008FFF0:C,"                     /* a third one, 0.1 units off for 13-33 frames under rollback (Christie vs Feng, stage 17; identical builds too: cross-cpu runs inv_v3_vs_v3, inv_native_vs_native) */
    /* Five fields of each fighter block (P2 = P1 + 0x8D0) that drift apart
     * while position, pose, health and timer stay identical (handles, effect
     * and sound counters): +0x1B4, +0x1E0, +0x314, +0x870/+0x874 from P1. */
    "100901B4:4,100901E0:4,10090314:4,10090870:8,"
    "10090A84:4,10090AB0:4,10090BE4:4,10091140:8,"
    /* Two 0x128-byte float blocks (0x1F0 apart) and a counter at +0x638 of the
     * second and third 0x8D0 block: camera-relative copies. The camera floats
     * around 0x10053780 (not hashed) already differ between two PCs; about 20 s
     * into a match (lockstep frame 1229 in different fights) 0x10053590 and
     * these blocks get values from them for exactly 100 frames, then all is
     * equal again, the fight and the final hash unchanged. Seen on main and on
     * fight-polish (build/dp runs rm2, ps3, abl_main4; docs/DIRECTFIGHT.md).
     * The whole two blocks are camera state (0x1F0 each from 0x10099730: a 3x4
     * matrix, positions; the copies above are their tails), and the counter has
     * a second word: from the final KO camera of Bryan vs Steve, stage 28,
     * 0x10099730-0x1009976F, 0x100998C0-0x10099903, the same in the second
     * block and +0x63C differ for 21 frames, then all is equal again and both
     * results match -- identical builds too; in lockstep (1 of 4 runs) and
     * more often under rollback (7 of 9 at RTT 50; 0 of 2 with
     * T5_RB_CUT=none, so the draw cut adds to it). Camera state that follows
     * timing, not input (docs/NETPLAY.md, "Same game state on every CPU"). */
    "10099730:1F0,10099920:1F0,10090708:8,10090FD8:8,"
    /* The renderer's current projection (0x24 bytes from 0x100996B4: type,
     * near, far, aspect, then left/right/top/bottom of an off-centre one):
     * render state, not match state. Only the projection setters write it
     * (0x80A94 perspective, 0x80C94 off-centre, from render passes); during a
     * fight the last one before the frame boundary is the stage-27 shadow
     * pass (0x268418 -> 0x15A974 -> 0x80C94), which sizes the fighters'
     * shadow box from their bone positions. No game code reads it: an access
     * trace of the record over 40 fight frames (T5_RB_RFT, rb_rft.cpp) found
     * reads only inside the two setters themselves (of +0x0..+0x10) and by our
     * own hash; the frustum words +0x14..+0x20 are never read.
     * The 1.1.2 e2e gate voided a stage-27 rollback match for 10 frames of
     * 0x100996C8..D4 alone (+-0.05 of +-600..1050) at the fight's start,
     * frames 226-235. The first of them, the state after frame 225, no
     * rollback can reach (every input up to frame 225 is the intro's neutral
     * one on both PCs; the first press took effect in frame 226): not
     * rollback-made. The fight, the camera, the side flags and the result
     * stayed identical (docs/NETPLAY.md "Stage 27: the shadow box at the
     * fight's start"). */
    "100996B4:24";
/* The fighters' side flags stay IN the hash: +0x1C2/+0x1C3 of the blocks at
 * 0x10090040 and 0x10090910 (bytes 0x10090202/03, 0x10090AD2/D3), written by
 * 0x808D8 from the camera-projected screen x above (+0x6C8, left out): which
 * fighter stands on the left, i.e. which way an up/down tap sidesteps. The
 * camera words are left out as display state, but where the camera decides
 * gameplay, these flags show it at once (desync hunt: the camera drew from the
 * title's TLS generator, which went apart between PCs -- rb_rand.cpp). */

/* T5_NET_DESYNC_DUMP=1: keep the hashed bytes of the last 64 frames and,
 * when the peer reports a different hash for one of them, write them to
 * np_desync_f<frame>.bin -- both PCs do, so the two files diff to the exact
 * words that went apart. */
constexpr uint32_t kSnapFrames = 64;
bool g_desync_dump = false;
std::vector<uint8_t> g_snap[kSnapFrames];
uint32_t g_snap_tag[kSnapFrames];
uint32_t g_desync_dumps = 0;
uint32_t g_desync_dump_max = 20;   /* T5_NET_DESYNC_DUMP=<n> (n > 1): this many files at most (default 20) */

/* ---- the pad, as the game sees it ------------------------------------------ */

void write_pad_data(uint32_t ea, const np::PadInput& in)
{
    const int len = 8;   /* CELL_PAD_LEN_CHANGE_DEFAULT: the title never enables press/sensor mode */
    wr32(ea, (uint32_t)len);
    for (int i = 0; i < 64; i++) wr16(ea + 4 + i * 2, 0);
    wr16(ea + 4 + 1 * 2, (uint16_t)(0x70 | (len / 2)));
    wr16(ea + 4 + 2 * 2, (uint16_t)(in.buttons & 0xFF));         /* DIGITAL1 */
    wr16(ea + 4 + 3 * 2, (uint16_t)(in.buttons >> 8));           /* DIGITAL2 */
    wr16(ea + 4 + 4 * 2, in.rx);
    wr16(ea + 4 + 5 * 2, in.ry);
    wr16(ea + 4 + 6 * 2, in.lx);
    wr16(ea + 4 + 7 * 2, in.ly);
}

/* t5_netplay_inject(): the direct-fight mode drives the game's menus itself
 * (character/stage select between matches). While a port is injected it reads
 * exactly the injected buttons -- before lockstep starts and during it; both
 * PCs inject the same sequence from the same game state, so the input rings
 * stay equal. */
std::atomic<uint32_t> g_inject_on{ 0 };       /* bit per port */
std::atomic<uint16_t> g_inject[2] = { 0, 0 };

void h_cellPadGetData(ppu_context* ctx)
{
    uint32_t port = (uint32_t)ctx->gpr[3], ea = (uint32_t)ctx->gpr[4];
    if (!ea) { ctx->gpr[3] = (uint64_t)(int64_t)(int32_t)0x80121104; return; }   /* INVALID_PARAMETER */
    if (port < 2 && (g_inject_on.load() & (1u << port))) {
        np::PadInput in = np::kNeutral;
        in.buttons = g_inject[port].load();
        write_pad_data(ea, in);
    } else if (g_passive && port < (uint32_t)g_pads) {
        write_pad_data(ea, np::poll_now((int)port));
    } else if (port < 2) {
        write_pad_data(ea, g_active ? g_cur[port] : np::kNeutral);
    } else {
        wr32(ea, 0);   /* nothing connected there */
    }
    ctx->gpr[3] = 0;
}

/* CellPadInfo (v1): max_connect, now_connect, system_info, vendor_id[127] at
 * 0x0C, product_id[127] at 0x10A, status[127] at 0x208. Both instances must
 * see the same pads, so it is always exactly two DUALSHOCK 3s, whatever is
 * plugged into this PC. */
void h_cellPadGetInfo(ppu_context* ctx)
{
    uint32_t ea = (uint32_t)ctx->gpr[3];
    int32_t r = cellPadGetInfo((void*)(uintptr_t)ea);
    if (r == 0 && ea) {
        wr32(ea + 0x04, (uint32_t)g_pads);
        wr32(ea + 0x08, 0);
        for (uint32_t i = 0; i < 7; i++) {
            const bool on = i < (uint32_t)g_pads;
            wr16(ea + 0x00C + i * 2, on ? 0x054C : 0);
            wr16(ea + 0x10A + i * 2, on ? 0x0268 : 0);
            wr8(ea + 0x208 + i, on ? 1 : 0);
        }
    }
    ctx->gpr[3] = (uint64_t)(int64_t)r;
}

/* ---- per-frame hook ---------------------------------------------------------- */

/* The per-frame state hash, plus each region's own hash (32 bits) in
 * `parts` for the frame log: which region diverged first. */
uint64_t state_hash(std::string* parts = nullptr)
{
    uint64_t h = 1469598103934665603ull;
    static std::vector<uint8_t> buf;
    for (const Range& r : g_hash_ranges) {
        buf.assign(vm_base + r.addr, vm_base + r.addr + r.len);
        for (const Range& k : g_hash_skip) {   /* blank the noisy words */
            const uint32_t a = k.addr > r.addr ? k.addr : r.addr;
            const uint32_t e = (k.addr + k.len) < (r.addr + r.len) ? (k.addr + k.len) : (r.addr + r.len);
            for (uint32_t x = a; x < e; x++) buf[x - r.addr] = 0;
        }
        h = fnv64(buf.data(), buf.size(), h);
        if (g_desync_dump && parts) g_snap[g_frame_hashing % kSnapFrames].insert(
            g_snap[g_frame_hashing % kSnapFrames].end(), buf.begin(), buf.end());
        if (parts) {
            uint64_t p = fnv64(buf.data(), buf.size());
            char t[12];
            snprintf(t, sizeof t, " %08x", (uint32_t)(p ^ (p >> 32)));
            *parts += t;
        }
    }
    return h;
}

void page_hashes(uint32_t f)
{
    if (!g_page_range.len || (f % g_page_every) != 0) return;
    std::string line = "P ";
    char tmp[16];
    snprintf(tmp, sizeof tmp, "%08X", g_page_range.addr); line += tmp;
    for (uint32_t a = g_page_range.addr; a < g_page_range.addr + g_page_range.len; a += 0x1000) {
        uint64_t h = fnv64(vm_base + a, 0x1000);
        snprintf(tmp, sizeof tmp, " %08x", (uint32_t)(h ^ (h >> 32)));
        line += tmp;
    }
    np::log_extra(f, line.c_str());
}

/* Screenshots of an exact frame on both PCs: the live renderer dumps its
 * surfaces at the first present after LD_SURF_DUMP_GATE appears. Created at
 * the top of frame f, after frame f-1 has had time to present, so the dump
 * is frame f's picture. */
void shot(uint32_t f)
{
    if (g_shot_gate.empty()) return;
    if (g_shot_armed != UINT32_MAX && f >= g_shot_armed + 30) {
        remove(g_shot_gate.c_str());   /* re-arms the renderer for the next one */
        g_shot_armed = UINT32_MAX;
    }
    for (uint32_t sf : g_shot_frames) {
        if (sf != f || g_shot_armed != UINT32_MAX) continue;
        Sleep(150);
        if (FILE* fp = fopen(g_shot_gate.c_str(), "wb")) { fprintf(fp, "%u", f); fclose(fp); }
        g_shot_armed = f;
        np::note("frame %u: screenshot requested", f);
    }
}

void dump_memory(uint32_t f)
{
    for (uint32_t df : g_dump_frames) {
        if (df != f) continue;
        for (const Range& r : g_dump_ranges) {
            char path[256];
            snprintf(path, sizeof path, "np_dump_f%06u_%08X.bin", f, r.addr);
            FILE* fp = fopen(path, "wb");
            if (!fp) continue;
            static const uint8_t zero[0x1000] = {};
            for (uint32_t a = r.addr; a < r.addr + r.len; a += 0x1000) {
                MEMORY_BASIC_INFORMATION mi;
                const bool ok = VirtualQuery(vm_base + a, &mi, sizeof mi) && mi.State == MEM_COMMIT &&
                                !(mi.Protect & (PAGE_NOACCESS | PAGE_GUARD));
                fwrite(ok ? vm_base + a : zero, 1, 0x1000, fp);
            }
            fclose(fp);
        }
        np::note("frame %u: memory dumped (%zu range(s))", f, g_dump_ranges.size());
    }
}

/* Direct fight: the frames of the game mode's start, the loading and the
 * intros (fight phase word 0x1008F070 at 0..12; 17 = fighting) take no input
 * (the rollback loop sends neutral there, the direct-fight driver holds the
 * pads in lockstep) and their state follows the loading, whose progress may
 * differ between two PCs: a game that has played already loads from its
 * caches faster than one that has just started (build/dp run dm3: the phase
 * word 2 vs 7 at frame 0, until the loading's scene change). Their state hash
 * is a fixed value on both sides instead (rb_net.cpp does the same); a
 * difference that lasts reaches the fight, where every frame is compared. */
constexpr uint64_t kIntroHash = 0x4F52544E49ull;   /* "INTRO" */
bool intro_phase_now() { return rd32(0x1008F070u) <= 12; }
/* the boundaries that take no input: phase 7..12, or anything up to 12 while
 * the game mode runs (its first frames: 0, 2) -- not the select screens (the
 * driver's presses), see rb_net.cpp intro_phase */
bool intro_input_now() { const uint32_t p = rd32(0x1008F070u); return p <= 12 && (p >= 7 || t5_df_game_mode()); }

/* ---- No pause online (docs/NETPLAY.md "No pause online") ---------------------
 * START opens the game's pause menu in a VS fight (RETURN TO GAME PLAY, COMMAND
 * LIST, ...), and online START is an input like any other: either player's START
 * paused the fight in both games (player report, 1.1.1: "the guy spammed pause"
 * in the middle of a combo). In a direct-fight session (every online match, and
 * the replay of one) START is taken out of BOTH players' inputs of every frame
 * right where they go to the game -- live, re-simulated (rollback) and played
 * back (replay) frames alike, after the exchange and after any prediction --
 * except where START skips instead of pausing: the replay after a round's KO,
 * and after the match (the KO replay and the win pose).
 * The rule and why both PCs end up with the same inputs: no_pause.h. Each
 * player's own START never even goes out (netplay_core.cpp device_input); the
 * test inputs (T5_NET_SCRIPT, T5_NET_PADFILE) are not filtered there, so tests
 * can play a modified client. */
bool g_directfight = false;    /* T5_FIGHT / T5_FIGHT_FILE / persistent game / replay: a direct-fight session */
/* The round's state (u32; build/nopause probes p7, s1760, s1900: 2 before round 1, 4 READY/FIGHT, 5
 * fighting, 6 the KO frame, 8 KO slow motion, 9 the replay -- START skips it --, 0xC to the next
 * round, while the fight phase word stays 17) */
constexpr uint32_t kRoundState = 0x1009322C;
np::NoPauseRule g_np_rule;
uint32_t g_np_cut[2], g_np_kept; /* this match: live frames whose START was taken out (per player), kept */
uint32_t g_np_skip;              /* ... and live frames the rule pressed START in (both players had, in a skip part) */
bool     g_np_noted = false;
unsigned g_np_who_noted = 0;     /* the presses last noted (skip part << 2 | who) */
uint32_t g_np_live = UINT32_MAX; /* start_gate: the last live boundary */
uint32_t g_np_part_frames = 0;   /* ... the live frames in the skip part so far */
unsigned g_np_part_live = 0;     /* ... and that part */
uint32_t g_np_test_press[3] = { UINT32_MAX, UINT32_MAX, UINT32_MAX };   /* T5_TEST_SKIP_PRESS, per part */

void no_pause_reset() { g_np_rule.reset(); g_np_live = UINT32_MAX; }   /* frame 0: the frames are numbered anew (the tally stays for its report) */

np::NoPauseRule::State np_state_now()
{
    return { t5_df_game_mode() != 0, rd32(0x1008F070u), rd8(kMatchOver) != 0, t5_df_mode_next(), rd32(kRoundState) };
}

/* in[] = frame f's inputs, game memory = the state at f's boundary. live: the
 * frame is played for the first time (counts for the log only). */
void no_pause_rule(uint32_t f, np::PadInput in[2], bool live)
{
    if (!g_directfight) return;   /* offline and menu-driven test sessions: START as ever */
    const np::NoPauseRule::State st = np_state_now();
    const np::NoPauseRule::Verdict v = g_np_rule.record(f, st, in);
    const bool any = ((in[0].buttons | in[1].buttons) & np::NoPauseRule::kStart) != 0;
    const unsigned cut = np::NoPauseRule::apply(v, in);
    if (!live) return;
    if (v == np::NoPauseRule::kPress) g_np_skip++;
    /* the skip parts: who has pressed START so far (live frames: under rollback a press may still be a
     * prediction that a re-simulation takes back -- the game state is what counts, and it is compared) */
    const unsigned part = g_np_rule.part_at(f), who = g_np_rule.pressed_at(f), key = part << 2 | who;
    if (who && key != g_np_who_noted)
        np::note("frame %u: %s (round state %u): START pressed by %s", f,
                 part == np::NoPauseRule::kIntro ? "the intro" : "after the round", st.round,
                 who == 3 ? "both players -- skipped" : who == 1 ? "P1 (skipped once P2 presses it too)"
                                                                 : "P2 (skipped once P1 presses it too)");
    g_np_who_noted = who ? key : 0;
    if (!any || v == np::NoPauseRule::kPress) return;
    if (v == np::NoPauseRule::kKeep) { g_np_kept++; return; }
    if (cut & 1) g_np_cut[0]++;
    if (cut & 2) g_np_cut[1]++;
    if (!g_np_noted) {
        g_np_noted = true;
        np::note("frame %u: START taken out of %s input (no pause online; phase %u, mode %u)", f,
                 cut == 3 ? "both players'" : cut == 1 ? "P1's" : "P2's", st.phase, t5_df_mode_cur());
    }
}

/* This PC's START goes out (netplay_core.cpp pad_into) only while the game shows
 * a skip part at the live boundary whose sample is taken now -- elsewhere the
 * rule takes it out anyway, and sending it would only make the peer mispredict.
 * T5_TEST_SKIP_PRESS=N[:M] (tests): this PC's player presses START for 3 frames
 * N frames into every intro and M frames (default N) into every part after a
 * round (a scripted press, not filtered; -1 = never). */
void start_gate(uint32_t f)
{
    if (!g_directfight || (g_np_live != UINT32_MAX && f <= g_np_live)) return;   /* live boundaries only (not a re-simulation) */
    g_np_live = f;
    const unsigned part = np::NoPauseRule::part_of(np_state_now());
    np::set_no_start(part == np::NoPauseRule::kNone);
    g_np_part_frames = part && part == g_np_part_live ? g_np_part_frames + 1 : part ? 1 : 0;
    g_np_part_live = part;
    const uint32_t n = g_np_test_press[part];
    if (g_np_test_press[1] != UINT32_MAX || g_np_test_press[2] != UINT32_MAX)
        np::set_test_buttons(part && n != UINT32_MAX && g_np_part_frames > n && g_np_part_frames <= n + 3
                             ? np::NoPauseRule::kStart : 0);
}

/* the tally since the last one: at a match's end (the fight), and at the next
 * sync point after it (the KO replay and win pose: the post-match skip) */
void no_pause_report(uint32_t f, const char* what)
{
    if (!g_directfight || (!g_np_cut[0] && !g_np_cut[1] && !g_np_kept && !g_np_skip && strcmp(what, "the match"))) return;
    np::note("frame %u: no pause online, %s: START taken out on %u frame(s) of P1's input and %u of P2's, kept on %u "
             "(the post-match skip), skipped on %u (both players pressed)", f, what, g_np_cut[0], g_np_cut[1], g_np_kept,
             g_np_skip);
    g_np_cut[0] = g_np_cut[1] = g_np_kept = g_np_skip = 0;
    g_np_noted = false;
}

uint64_t gcall(uint32_t code, uint64_t a0 = 0)
{
    return ppu_guest_call_ct(code, kTOC, a0, 0, 0, 0, 0, 0, 0, 0);
}
uint64_t gcall2(uint32_t code, uint64_t a0, uint64_t a1)
{
    return ppu_guest_call_ct(code, kTOC, a0, a1, 0, 0, 0, 0, 0, 0);
}

/* One keyread tick (the body of the loop at 0x120BE0..0x120C90), run on the
 * MAIN thread at the top of its frame. It cannot be handed to the keyread
 * thread and waited for: the pad update takes the lwmutex at 0x106D4D00
 * (to read the frame clock at 0x106D4D88), which the main thread holds while
 * it waits for its frame. Run here, that lock is a recursive re-lock. The
 * ring store skips the ring's lwmutex: the only other user of the ring is the
 * main thread itself (0x120A78) and the real keyread thread is parked. */
void keyread_tick()
{
    if (rd32(kKeyreadQuit)) return;
    gcall(kFnTickCounter);                       /* 0x9A204: 60-tick countdown */
    wr32(kKeyreadObj + 0x1810, 0);
    gcall(kFnPadUpdate);                         /* 0x8F3A4: cellPadGetInfo/GetData, port states */
    if (rd32(kRingResetFlag)) gcall(kFnRingReset);
    const uint32_t slot = (rd32(kRingWriteIdx) & 15) * 2;
    const uint16_t m0 = (uint16_t)gcall(kFnPortMask, 0);
    wr16(kRing + slot, m0);
    const uint16_t m1 = (uint16_t)gcall(kFnPortMask, 1);
    wr16(kRing + 0x20 + slot, m1);
    gcall(kFnRingAdvance);                       /* 0x12071C: write index++ */
    gcall(kFnTickTail);                          /* 0x13F91C */
}

/* Idle = parked in its semaphore wait with no post pending. A semaphore not
 * created yet, or nobody waiting on it yet, does not hold the frame up. */
bool sem_idle(int id)
{
    const np_sys_semaphore_info& s = g_sys_semaphores[id - 1];
    if (!s.active) return true;
    return *(volatile int32_t*)&s.value == 0 && *(volatile int32_t*)&s.waiters > 0;
}

bool workers_idle()
{
    for (int i = 1; i < kMaxSem; i++)
        if (g_drain[i] && g_drain_seen[i] && !sem_idle(i)) return false;
    return true;
}

/* The keyread thread is parked for good: its wakes are swallowed, no post is
 * half-way through (g_kr_posting), it sits in its semaphore wait (our wrapper
 * says so) and the semaphore holds no token while a waiter is blocked on it.
 * With posts stopped the token count can only fall, so "0 tokens, a waiter"
 * stays true. "In the wait" alone is not enough: a vblank post just before the
 * swallow has already released the thread while it still reads as waiting --
 * that was the boot race (take-over at frame 1, then the thread's own tick
 * running beside ours: lwmutex 0x10752088 vs 0x106D4D00 deadlock). */
bool keyread_parked()
{
    const uint32_t kr = rd32(kKeyreadSemPtr);
    if (!kr || kr > 256 || !g_swallow.load() || g_kr_posting.load() != 0 || !g_kr_in_wait.load()) return false;
    const np_sys_semaphore_info& s = g_sys_semaphores[kr - 1];
    if (!s.active) return false;
    const int32_t v = *(volatile const int32_t*)&s.value;
    const int32_t w = *(volatile const int32_t*)&s.waiters;
    return v == 0 && w > 0 && g_kr_in_wait.load();
}

/* Called at the take-over frame (the frame after the swallow, on both PCs).
 * Usually the keyread thread finished its last tick during the previous frame
 * and is parked. If not (a loaded PC), its tick is blocked on the lwmutex at
 * 0x106D4D00, which this thread holds across its frame wait: hand the lock
 * over for a moment through the game's own sys_lwmutex calls, let the tick
 * finish and park, take the lock back. Never runs a tick beside the thread's. */
bool ensure_keyread_parked(ppu_context* ctx)
{
    const bool parked0 = keyread_parked();
    if (parked0 && !g_takeover_test) return true;
    const uint32_t self = ctx->thread_id ? (uint32_t)ctx->thread_id : 0x7FFFFFFEu;
    uint32_t recur = 0;
    if (rd32(kFrameLwm + 0x0) == self) {
        recur = rd32(kFrameLwm + 0xC);
        for (uint32_t i = 0; i < recur; i++) gcall(kFnLwmUnlock, kFrameLwm);
    }
    const ULONGLONG t0 = GetTickCount64();
    while (!keyread_parked() && GetTickCount64() - t0 < 5000) WaitForSingleObject(g_kr_event, 2);
    const bool parked = keyread_parked();
    if (recur) {
        gcall2(kFnLwmLock, kFrameLwm, 0);
        if (recur > 1) wr32(kFrameLwm + 0xC, recur);
    }
    np::note("take-over: the keyread thread was %s at the take-over frame; %s after %llu ms%s",
             parked0 ? "parked" : "still busy", parked ? "parked" : "STILL NOT PARKED",
             (unsigned long long)(GetTickCount64() - t0), recur ? " (frame lock handed over and taken back)" : "");
    return parked;
}

uint64_t g_drain_us = 0, g_drain_max_us = 0, g_drain_waits = 0;

void drain_stats(uint32_t f)
{
    if (f == 0 || f % 600) return;
    if (g_drain_waits)
        np::note("loader drain: %llu frame(s) waited, %.1f ms total, longest %.1f ms (last 600 frames)",
                 (unsigned long long)g_drain_waits, g_drain_us / 1000.0, g_drain_max_us / 1000.0);
    g_drain_us = g_drain_max_us = g_drain_waits = 0;
}

std::string drain_sems()
{
    std::string st;
    for (int i = 0; i < kMaxSem; i++)
        if (g_drain[i]) { char b[48]; snprintf(b, sizeof b, " sem%d:value%d/waiters%d", i,
                           g_sys_semaphores[i - 1].value, g_sys_semaphores[i - 1].waiters); st += b; }
    return st;
}

/* Wait until the loader threads are parked. Returns the time it waited (ms),
 * or -1 when they were idle already.
 *
 * No time limit (docs/NETPLAY.md "Slow loading"). The frame a load is seen done
 * in must be the same on both PCs, so a frame never starts with its loads still
 * running, however slow this PC's disk or CPU: it used to after 2 s ("loader
 * threads still busy after 2 s, going on"), and on a PC at 0.5 fps that moved
 * the loading's last frames -- the fight-loaded sync point put the frame numbers
 * back together, but the fight's intro then ended a frame earlier on one PC and
 * the whole match ran a frame apart (e2e firewall run, Asuka vs Wang on stage 26:
 * 1,619 of 1,620 frames mismatching, the match voided). The peer waits for this
 * frame's input meanwhile (our PINGs say we are loading, so its stall limits do
 * not count it). Only three things end the wait:
 *   - the loaders are parked (the normal case);
 *   - the session is over (lost, failed, ended): nothing is compared any more;
 *   - one frame waited T5_NET_LOAD_TIMEOUT (default 120 s): a load that hangs.
 *     This side then ends the match with "load_timeout" (the peer is told:
 *     "peer_load_timeout") -- a clean end, never a match played out of step.
 * T5_TEST_DRAIN_HOLD=ms[:frame] (tests): the wait also lasts at least ms at frame
 * `frame` (default 5) of each session -- a loader that is slow at one moment on
 * one PC, for the load-timeout test. */
double drain_wait(uint32_t f)
{
    drain_stats(f);
    const bool hold = g_drain_test_ms && f == g_drain_test_frame;
    if (workers_idle() && !hold) return -1.0;
    LARGE_INTEGER q0, q1, qf;
    QueryPerformanceCounter(&q0);
    const ULONGLONG t0 = GetTickCount64();
    const ULONGLONG limit_ms = (ULONGLONG)np::load_timeout_s() * 1000;
    ULONGLONG next_note = 2000;
    bool told = false;
    for (;;) {
        const ULONGLONG ms = GetTickCount64() - t0;
        if (workers_idle() && !(hold && ms < g_drain_test_ms)) break;
        WaitForSingleObject(g_drain_event, 1);
        if (ms < 1000) continue;
        if (!told) { np::set_loading(true); told = true; }   /* the peer waits for us: our PINGs say why */
        if (np::failure() || np::lost_reason()) {
            np::note("frame %u: the session is over -- stopped waiting for the loaders after %.1f s", f, ms / 1000.0);
            break;
        }
        if (ms >= next_note) {
            next_note += next_note < 10000 ? 3000 : 10000;
            if (g_drain_notes++ < 60)
                np::note("frame %u: loader threads still busy after %.0f s -- the frame waits for them (%s)", f, ms / 1000.0,
                         drain_sems().c_str());
        }
        if (limit_ms && ms >= limit_ms) {
            np::note("frame %u: LOADING TOOK TOO LONG: the loader threads are still busy after %llu s (%s) -- "
                     "this game ends the match (T5_NET_LOAD_TIMEOUT)", f, limit_ms / 1000, drain_sems().c_str());
            np::give_up("load_timeout", "loading took too long on this PC (%llu s for one frame) -- the match ends",
                        limit_ms / 1000);
            break;
        }
    }
    if (told) np::set_loading(false);
    QueryPerformanceCounter(&q1); QueryPerformanceFrequency(&qf);
    const uint64_t us = (uint64_t)((q1.QuadPart - q0.QuadPart) * 1000000 / qf.QuadPart);
    g_drain_us += us; g_drain_waits++; if (us > g_drain_max_us) g_drain_max_us = us;
    if (us >= 2000000 && g_drain_notes++ < 60)
        np::note("frame %u: the loaders were busy for %.1f s; the frame went on once they were done", f, us / 1e6);
    return us / 1000.0;
}

/* The draw side's request managers, drained before every rollback boundary
 * (docs/ROLLBACK.md section 32). NU::Draw::Geometry::RequestManager (thread 5,
 * object 0x10742880, loop 0x35B888) is woken by a post of its semaphore (id at
 * +0x50) for each request queued (0x35BE6C), counts itself busy in +8 while it
 * works through its queue and parks again. The present (0x383C9C -> 0x35BF6C)
 * queues one request and spins until +8 is 0 -- but only until then: the
 * thread may not have woken yet, or the draw manager's sync after it
 * (0x357714) hands it more, so at the boundary it can still be working. A
 * snapshot taken then holds +8 = 1 (and a queue half way through); a rollback
 * to that frame puts the 1 back after the thread has parked, nothing takes it
 * away again (every later wake adds and removes its own 1), and the next
 * present spins on it for good: the host hang of runs FF1/FF2 (main at
 * 0x35C014, the geometry thread parked, the draw manager idle).
 * NU::Draw::RequestManager (thread 4, object 0x1074BE80) is idle at the
 * boundary by construction (0x357714 waits for it); it is only counted. */
constexpr uint32_t kGeomMgr = 0x10742880u;   /* +8 busy count, +0x50 wake semaphore id */
constexpr uint32_t kDrawMgr = 0x1074BE80u;   /* +0x98 wake counter (value u64 at +0xA8): 1 = working through its list */
bool g_side_drain = true;                    /* T5_RB_SIDE_DRAIN=0: count only, do not wait */
std::atomic<uint32_t> g_geom_sem{ 0 };
uint64_t g_sd_geom = 0, g_sd_draw = 0, g_sd_us = 0, g_sd_max_us = 0, g_sd_frames = 0;
uint32_t g_sd_timeouts = 0;

bool geom_idle()
{
    const uint32_t id = rd32(kGeomMgr + 0x50);
    if (!id || id > 256) return true;   /* not created yet */
    g_geom_sem = id;
    const np_sys_semaphore_info& s = g_sys_semaphores[id - 1];
    if (!s.active) return true;
    return *(volatile int32_t*)&s.value == 0 && *(volatile int32_t*)&s.waiters > 0;
}
/* (its request list may hold the next frame's first requests: queued, not taken) */
bool draw_idle() { return rd64(kDrawMgr + 0xA8) == 0; }

void side_drain(uint32_t f)
{
    if (f && f % 600 == 0 && g_sd_frames) {
        np::note("side drain: geometry manager busy at %llu of %llu boundaries (waited %.1f ms, longest %.2f ms), draw manager running at %llu",
                 (unsigned long long)g_sd_geom, (unsigned long long)g_sd_frames, g_sd_us / 1000.0, g_sd_max_us / 1000.0,
                 (unsigned long long)g_sd_draw);
        g_sd_geom = g_sd_draw = g_sd_us = g_sd_max_us = g_sd_frames = 0;
    }
    g_sd_frames++;
    if (!draw_idle()) g_sd_draw++;
    if (geom_idle()) return;
    g_sd_geom++;
    if (!g_side_drain) return;
    LARGE_INTEGER q0, q1, qf;
    QueryPerformanceCounter(&q0);
    const ULONGLONG t0 = GetTickCount64();
    while (!geom_idle()) {
        if (g_drain_event) WaitForSingleObject(g_drain_event, 1); else Sleep(1);
        if (GetTickCount64() - t0 > 2000) {
            if (g_sd_timeouts++ < 10)
                np::note("frame %u: geometry manager still busy after 2 s, going on (count %d, semaphore %u)",
                         f, (int32_t)rd32(kGeomMgr + 8), rd32(kGeomMgr + 0x50));
            break;
        }
    }
    QueryPerformanceCounter(&q1); QueryPerformanceFrequency(&qf);
    const uint64_t us = (uint64_t)((q1.QuadPart - q0.QuadPart) * 1000000 / qf.QuadPart);
    g_sd_us += us; if (us > g_sd_max_us) g_sd_max_us = us;
}

/* lockstep: drain at the top of the frame; the rollback loop is told about the
 * load (it keeps re-simulations clear of loads) */
void drain_workers(uint32_t f)
{
    const double ms = drain_wait(f);
    if (ms >= 0) rb::net::load_seen(f, ms);
}

/* T5_NET_RESULT_FILE, once a match is decided (the lobby reports it). The round
 * state block at 0x1008EBD0: +0x5 stays 0 through every round of a match and
 * turns 1 / 2 / 3 (P1 won, P2 won, a draw) when the match is over (back to 0
 * when the next one starts). The rounds each player won: the fighters' counts
 * (match_score.h; before 1.1.3 the block's +0xA/+0xB, which are not that).
 *
 *   {"match": "<lobby match id>", "winner": 0|1|null, "score": [p1, p2],
 *    "desync": <mismatching frames since this match's sync point>, "frames": <played>,
 *    "hash": "<state hash of the deciding frame>", "fps": <this PC's own speed>}
 *
 * "match" lets the launcher refuse a file left over from another match. The
 * file is written once the deciding frame's hash has been compared with the
 * peer's (a few frames later), so "desync" covers the whole match; "hash" is the
 * same on both PCs when they agree. A match that cannot be played to the end
 * gets "reason" (peer_quit, peer_timeout, peer_stalled, start_timeout,
 * peer_restarted, no_peer, build_mismatch, rejected, bind_failed) and winner null. */
std::string g_result_file;
std::string g_match_id;                       /* T5_NET_MATCH, then t5_netplay_set_match() */
std::string g_last_result_match = "\x01";     /* match id of the last result written */
CRITICAL_SECTION g_result_cs;
bool g_result_done = false;
bool g_match_running = false;                 /* between a match's sync point and its end */
uint32_t g_match_f0 = 0;                      /* lockstep frame of that sync point */
uint32_t g_matches = 0;
struct PendingResult { bool on; uint32_t f; uint8_t w1, w2; uint64_t hash; bool have_hash; ULONGLONG t; };
PendingResult g_pending = {};

std::string json_id(const std::string& id)
{
    if (id.empty()) return "null";
    std::string out = "\"";
    for (char c : id) out += (isalnum((unsigned char)c) || c == '-' || c == '_' || c == '.') ? c : '_';
    return out + "\"";
}

void write_result(const char* winner, unsigned w1, unsigned w2, const char* reason, uint32_t frames,
                  bool have_hash, uint64_t hash, uint32_t at)
{
    /* the replay (docs/REPLAYS.md): the result goes into the recording, or a
     * playback compares it with the recorded one */
    if (np::replaying()) { if (!reason) rp::play_result(winner, w1, w2, frames, have_hash, hash, at); }
    else rp::rec_result(winner, w1, w2, reason, frames, have_hash, hash, np::match_mismatches(), at);
    EnterCriticalSection(&g_result_cs);
    const std::string id = g_match_id;
    g_last_result_match = id;
    LeaveCriticalSection(&g_result_cs);
    char buf[640];
    int n = snprintf(buf, sizeof buf, "{\"match\": %s, \"winner\": %s, \"score\": [%u, %u]", json_id(id).c_str(),
                     winner, w1, w2);
    if (reason) n += snprintf(buf + n, sizeof buf - n, ", \"reason\": \"%s\"", reason);
    n += snprintf(buf + n, sizeof buf - n, ", \"desync\": %u, \"frames\": %u", np::match_mismatches(), frames);
    if (have_hash) n += snprintf(buf + n, sizeof buf - n, ", \"hash\": \"%016llx\"", (unsigned long long)hash);
    const double fps = np::local_fps();
    if (fps > 0) n += snprintf(buf + n, sizeof buf - n, ", \"fps\": %.1f", fps);
    snprintf(buf + n, sizeof buf - n, "}");
    np::note("result: %s", buf);
    if (g_result_file.empty()) return;
    const std::string tmp = g_result_file + ".tmp";
    if (FILE* fp = fopen(tmp.c_str(), "wb")) {
        fputs(buf, fp);
        fclose(fp);
        /* the launcher may have the old file open this very moment (Windows refuses the replace then) */
        for (int i = 0; i < 50 && !MoveFileExA(tmp.c_str(), g_result_file.c_str(), MOVEFILE_REPLACE_EXISTING); i++) Sleep(2);
    }
}

/* A match begins at lockstep frame f (frame 0, or a later sync point). */
void match_begins(uint32_t f)
{
    no_pause_report(f, "after the last match");
    g_match_f0 = f;
    g_match_running = true;
    g_pending.on = false;
    np::match_begin(f);
    if (np::replaying()) rp::play_match_begin(f);
    else rp::rec_match_begin(f);
}

void flush_result(bool now)
{
    if (!g_pending.on) return;
    const PendingResult& p = g_pending;
    if (!now && np::checked_through() <= p.f && GetTickCount64() - p.t < 3000) return;
    g_pending.on = false;
    const char* winner = p.w1 > p.w2 ? "0" : p.w2 > p.w1 ? "1" : "null";
    uint64_t h = p.hash; bool have = p.have_hash;
    if (!have && rb::net::active()) have = rb::net::final_hash(p.f, &h);   /* rollback: the deciding frame's gameplay hash, final */
    write_result(winner, p.w1, p.w2, nullptr, p.f - g_match_f0, have, h, p.f);
}

void watch_match(uint32_t f, bool have_hash = false, uint64_t hash = 0)
{
    const uint8_t over = rd8(kMatchOver);
    const np::MatchScore sc = np::MatchScore::of(rd8(kWinsP1), rd8(kWinsP2), rd8(kMatchOver), rd8(kWinnerIdx), rd8(kRoundsToWin));
    const uint8_t w1 = over ? (uint8_t)sc.p1 : 0, w2 = over ? (uint8_t)sc.p2 : 0;
    if (!over && g_pending.on && rb::net::active() && f < g_pending.f + 600) {
        /* rollback: the match end was seen on a predicted frame and the
         * correction undid it -- not a result */
        np::note("frame %u: the match end seen at frame %u was rolled back -- no result yet", f, g_pending.f);
        g_pending.on = false; g_result_done = false; g_match_running = true; g_matches--;
        return;
    }
    if (!over) {
        if (g_result_done) g_match_running = true;   /* menu-driven play: the next match is on */
        g_result_done = false;
        flush_result(false);
        return;
    }
    if (g_result_done || (w1 == 0 && w2 == 0)) { flush_result(false); return; }
    g_result_done = true;
    g_match_running = false;
    g_matches++;
    np::note("frame %u: match %u over, P1 %u - P2 %u, winner %s", f, g_matches, w1, w2,
             w1 == w2 ? "none (draw)" : (w1 > w2 ? "P1" : "P2"));
    if (!sc.counted)
        np::note("frame %u: the fighters' round counts (%u, %u) do not fit the match (rounds to win %u, decided byte %u, "
                 "winner byte %u): score from the decided byte", f, rd8(kWinsP1), rd8(kWinsP2), rd8(kRoundsToWin),
                 rd8(kMatchOver), rd8(kWinnerIdx));
    no_pause_report(f, "the match");
    g_pending = { true, f, w1, w2, hash, have_hash, GetTickCount64() };
    flush_result(false);
}

/* ---- the end of a session that cannot go on ---------------------------------
 * A failed handshake or a lost peer ends the match: the result file says why
 * (unless this match's result is already out), the peer is told, and the game
 * closes with an exit code the launcher understands. T5_NET_ON_LOST=idle keeps
 * the old behaviour (the peer's player idles) after writing the result. */
bool g_on_lost_idle = false;
bool g_lost_written = false;
std::atomic<bool> g_ending{ false };

int exit_code_for(const char* reason)
{
    if (!strcmp(reason, "build_mismatch")) return 5;
    if (!strcmp(reason, "no_peer") || !strcmp(reason, "rejected") || !strcmp(reason, "start_timeout") ||
        !strcmp(reason, "bind_failed")) return 4;
    return 3;
}

void write_end_result(const char* reason)
{
    flush_result(true);
    EnterCriticalSection(&g_result_cs);
    const bool already = g_last_result_match == g_match_id && !g_match_running;
    LeaveCriticalSection(&g_result_cs);
    if (already) return;               /* this match's result is out; nothing to add */
    const uint32_t frames = g_frame > g_match_f0 ? g_frame - g_match_f0 : 0;
    /* the rounds won so far; none while the last match's decided byte is still up (its counts, until this
     * match's game mode clears them) */
    const bool stale = rd8(kMatchOver) != 0;
    write_result("null", stale ? 0 : rd8(kWinsP1), stale ? 0 : rd8(kWinsP2), reason, frames, false, 0, g_frame);
}

void end_session(const char* reason, bool from_network_thread = false)
{
    if (g_ending.exchange(true)) {
        /* the other thread is ending it: the main thread must not play on meanwhile */
        if (!from_network_thread) for (;;) Sleep(1000);
        return;
    }
    write_end_result(reason);
    np::rec_pump();
    rp::rec_session_end(reason);     /* the replay so far, before the process ends */
    const int code = exit_code_for(reason);
    np::note("the session cannot go on (%s): the game closes (exit code %d)", reason, code);
    np::bye();
    fflush(stdout); fflush(stderr);
    TerminateProcess(GetCurrentProcess(), (UINT)code);
}

/* ---- the player closed the game window (Alt+F4, the X button, Esc) ----------
 * Called by the runtime's ticker thread (boot_main.cpp, patch 0035) before it
 * ends the process. With a netplay session set up, leaving is a quit: the
 * result file gets "quit" (unless this match's result is out already -- a game
 * closed after the KO keeps its result), the peer is told (BYE: peer_quit on
 * its side, at once), and the exit code is 7, which the launcher reports to the
 * lobby as this player's quit -- a loss (docs/RANKED.md). Before, the game ran
 * on without its window at about a frame a second: the opponent stalled and
 * went out of sync, and the match was voided as a desync instead (0.1.9). */
void on_window_closed()
{
    if (g_ending.exchange(true)) {
        Sleep(5000);                 /* a session end in progress: it ends the process with its own code */
        return;
    }
    /* (local mode -- tests, a replay being watched -- is not online: no quit, no question) */
    const bool online = np::enabled() && np::mode() != np::Mode::Local && (g_persistent || !g_offline);
    if (np::replaying()) rp::play_finish("the game window was closed");
    if (online) {
        write_end_result("quit");
        np::rec_pump();
        rp::rec_session_end("quit");
        np::note("the game window was closed: this player leaves the session (quit); the peer is told (exit code 7)");
        np::bye();
    }
    t5_df_window_closed();
    fflush(stdout); fflush(stderr);
    TerminateProcess(GetCurrentProcess(), online ? 7u : 0u);
}
/* Esc closes the game only on a second press while a session is set up. */
int close_guard() { return np::enabled() && np::mode() != np::Mode::Local && !g_offline ? 1 : 0; }

/* The network thread's fallback when the main thread does not get to
 * check_session() (blocked outside the lockstep waits). */
void stuck_handler(const char* reason)
{
    np::note("the main thread did not end the session in time; ending it from the network thread");
    end_session(reason, true);
}

/* Main thread, every frame (before and during lockstep). */
void check_session()
{
    const char* r = np::failure();
    if (!r) r = np::lost_reason();
    if (!r) return;
    if (g_persistent) { persistent_lost(r); return; }   /* the game stays open for the next opponent */
    if (!g_on_lost_idle) { end_session(r); return; }
    if (!g_lost_written) {
        g_lost_written = true;
        write_end_result(r);
        np::note("T5_NET_ON_LOST=idle: playing on with the peer's player idle");
    }
}

/* T5_NET_ROUNDS (menu-driven VS): the rounds-to-win byte both PCs use. The
 * game copies it from each PC's own options when VS starts, so two saves with
 * different settings would play different matches. */
int g_rounds = 0;
/* (g_directfight: above, with the no-pause rule) */
void apply_rounds()
{
    if (g_rounds <= 0 || g_directfight || rd32(kConfig) != 4) return;
    const uint8_t was = rd8(kRoundsToWin);
    if (was == (uint8_t)g_rounds) return;
    wr8(kRoundsToWin, (uint8_t)g_rounds);
    np::note("frame %u: rounds to win %u -> %d (T5_NET_ROUNDS)", g_frame, was, g_rounds);
}

/* A scene barrier made this side skip d frame numbers (it got there first): the
 * game's own per-frame counters move along with it -- the frame clock and three
 * u32 frame counters (0x1008EB9C, 0x1008F07C, 0x1009442C all equal the frame
 * count). */
void skip_frames(uint32_t d)
{
    wr64(kFrameClock, rd64(kFrameClock) + d);
    for (uint32_t a : { 0x1008EB9Cu, 0x1008F07Cu, 0x1009442Cu }) wr32(a, rd32(a) + d);
}

/* The game's per-frame counters and input ring the same on both PCs (a fresh
 * start, and the resume after the in-game select). */
void equal_counters()
{
    wr64(kFrameClock, 0x10000);
    for (uint32_t a : { 0x1008EB9Cu, 0x1008F07Cu, 0x1009442Cu }) wr32(a, 0x10000);
    wr32(kRingResetFlag, 1);
}

/* The lockstep stops at a sync point (in-game select): the hooks run as between
 * two sessions until t5_netplay_start() resumes it at frame f. */
void go_paused(uint32_t f)
{
    g_pause_requested = false;
    g_paused = true;
    g_idle = true;
    g_frame = f;
    g_inject_on = 0;
    np::set_local_inject(false, 0);
    g_cur[0] = g_cur[1] = np::kNeutral;
    no_pause_report(f, "after the last match");
    np::note("frame %u: lockstep paused (in-game select); it resumes at this frame when the next fight starts", f);
}

/* The random generators the game draws from, seeded the same on both PCs: the
 * Mersenne Twister, the C rand(), and the main thread's TLS generator 0x3AFC3C
 * (the scene's draws: camera, move effects, the game mode's set-up; without it
 * a game that had played other opponents began each fight from a different
 * state than one just started -- docs/NETPLAY.md "Desync hunt"). */
uint32_t g_main_tls = 0;   /* the main thread's TLS block (its r13 - 0x7000), from its frame waits */

/* The seed the TLS generator is pinned to while the select mode runs (below,
 * on_frame_start): the session's seed mixed with the number of fights this
 * session has started (the direct-fight driver counts them at FIGHT START, the
 * same on both PCs and in a playback of the session). Mokujin's copy is drawn
 * from it at the game mode's set-up: the same on both PCs, another one in every
 * rematch, and other sessions draw others again. (The random cell draws at its
 * confirm and follows the frame it is pressed on; its pick travels as the
 * fighter it gave, df_fight.cpp.) A replay recorded before
 * the mix (format 3 and older) plays back with one seed for the whole session,
 * as it was recorded (rp::play_select_mix). */
uint32_t select_seed(uint32_t* match_no)
{
    uint32_t k = t5_df_session_matches();
    if (np::replaying() && !rp::play_select_mix()) k = 0;
    *match_no = k;
    return (np::session_seed() ^ 0x7E1EC7EDu) + k * 0x9E3779B9u;
}

/* Offline (no netplay, no direct fight, no replay): the TLS generator starts
 * from the game's own fixed state word at every boot, and nothing that depends
 * on timing moves it any more (rb_rand.cpp isolates it from the effect and
 * stage draws), so Mokujin's copies and the other scene draws could come out
 * the same after every start (runs off2: twice the same copy; only the players'
 * timing made them differ). It is seeded once at the
 * first frame boundary from the OS's random numbers (the game seeds its
 * Mersenne Twister from the clock, 0xAE6C8, but not this one).
 * T5_OFFLINE_SEED=<n> (tests): that seed, and while a select screen runs every
 * generator (the TLS one, the Twister, rand(), the scene's LCG: reseed()) is
 * pinned to n mixed with the number of select screens left so far (as online,
 * select_seed()): how long the players took no longer counts, so the same picks
 * give the same Mokujin copies at every start.
 * =0: not seeded (as before). */
void reseed(uint32_t seed);         /* (below) */
bool g_offline_seeded = false;
uint32_t g_offline_fixed = 0;       /* T5_OFFLINE_SEED=<n> */
void offline_pin()
{
    static uint32_t f = 0, k = 0, was = 0, noted = 0;
    const uint32_t m = t5_df_find_mode(f++);
    if (was == 6 && m != 6) k++;
    was = m;
    if (m != 6) return;
    const uint32_t seed = (g_offline_fixed ^ 0x7E1EC7EDu) + k * 0x9E3779B9u;
    reseed(seed);   /* every generator, as at an online sync point (the Twister is seeded from the clock at boot) */
    if (seed != noted) { noted = seed; np::note("offline: select screen %u, TLS generator pinned to 0x%08X (T5_OFFLINE_SEED)", k + 1, seed); }
}
void offline_seed()
{
    g_offline_seeded = true;
    for (const char* k : { "T5_FIGHT", "T5_FIGHT_FILE", "T5_REPLAY_FILE" }) {
        const char* v = getenv(k);
        if (v && *v) return;      /* a direct fight or a playback: the driver's own seeds */
    }
    uint32_t seed = 0;
    const char* e = getenv("T5_OFFLINE_SEED");
    if (e && *e) {
        seed = (uint32_t)strtoul(e, nullptr, 0);
        if (!seed) { np::note("offline: the scene's random generator starts as the game sets it (T5_OFFLINE_SEED=0)"); return; }
        g_offline_fixed = seed;
    } else {
        LARGE_INTEGER q; QueryPerformanceCounter(&q);
        BCryptGenRandom(nullptr, (PUCHAR)&seed, sizeof seed, BCRYPT_USE_SYSTEM_PREFERRED_RNG);   /* (bcrypt: linked already) */
        seed ^= (uint32_t)q.QuadPart ^ (uint32_t)(q.QuadPart >> 32) ^ (GetCurrentProcessId() * 0x9E3779B9u);
        if (!seed) seed = 0x2545F491u;
    }
    rb::tls_rand_reseed(g_main_tls, seed, true);
    np::note("offline: the scene's random generator seeded with 0x%08X (%s): Mokujin's copies and random picks differ "
             "from start to start", seed, e && *e ? "T5_OFFLINE_SEED" : "this start's");
}
void reseed(uint32_t seed)
{
    gcall(kFnMtSeed, seed);
    gcall(kFnSrand, seed ^ 0x5A5A5A5Au);
    rb::tls_rand_reseed(g_main_tls, seed ^ 0x3C6EF35Fu, true);   /* and the private streams (stage 27's crowd timers) */
    wr32(0x1008F0C4u, seed ^ 0x00003039u);   /* the scene's LCG (x -> 5x + 3, rb_rand.cpp) */
}

/* ---- replays: what happens at a sync point (docs/REPLAYS.md) -----------------
 * A recording keeps every sync point: its kind, the frame this game reached it
 * at and the frame both games went on from, the seed the random generators got
 * and the game's frame counters after it. A playback reaches the same sync
 * points in the same order (they follow the game state and the driver, both
 * the same as live); np::scene_barrier() has told it where the recorded session
 * went on, and here it takes the recorded seed and counters -- the frame its own
 * loading ended at may differ (a fresh game loads the fight slower than one that
 * has played), the state after the sync point may not. */
uint32_t sync_seed(uint32_t kind, uint32_t computed)
{
    if (!np::replaying()) return computed;
    return rp::play_barrier_seed(np::barriers() - 1, kind, computed);
}
void sync_counters()
{
    if (!np::replaying()) return;
    uint64_t clock; uint32_t c[3];
    if (!rp::play_barrier_state(np::barriers() - 1, &clock, c)) return;
    wr64(kFrameClock, clock);
    wr32(0x1008EB9Cu, c[0]); wr32(0x1008F07Cu, c[1]); wr32(0x1009442Cu, c[2]);
}
void sync_record(uint32_t kind, uint32_t f, uint32_t nf, uint32_t seed)
{
    if (!rp::recording()) return;
    rp::Barrier b;
    b.kind = kind; b.f = f; b.nf = nf; b.seed = seed;
    b.has_state = kind != rp::kPause;
    if (b.has_state) {
        b.clock = rd64(kFrameClock);
        b.c[0] = rd32(0x1008EB9Cu); b.c[1] = rd32(0x1008F07Cu); b.c[2] = rd32(0x1009442Cu);
    }
    rp::rec_barrier(b);
}

/* ---- replays: the playback's controls (docs/REPLAYS.md "Watching") ------------
 * The local pad (keyboard or controller) is not a player in a playback; it
 * steers it: START pauses and goes on, SELECT ends the replay. The playback runs
 * at the game's own pace: the frame waits for its vblank tick as always. (Faster
 * was tried -- 2x and the earlier matches of a session as fast as possible, with
 * the frame semaphore not waited for: the game still shows one picture per
 * vblank, its flip waits for it, and such a playback ran at 30-44 frames a
 * second, slower than normal; so there is no faster pace.) */
struct ReplayPace {
    bool inited = false, quit = false;
    uint16_t prev = 0;
    LARGE_INTEGER qf = {};
} g_rp;
constexpr uint16_t kPadSelect = 0x0001, kPadStart = 0x0008;

uint16_t replay_pad()
{
    static int on = -1;   /* T5_REPLAY_CONTROLS=0: the pad does not steer the playback (tests on a PC in use) */
    if (on < 0) { const char* e = getenv("T5_REPLAY_CONTROLS"); on = !(e && *e == '0'); }
    if (!on) return 0;
    HostPadData d = {};
    np::local_player_sample(&d);           /* any of this PC's controllers (local_pad.cpp) */
    if (d.len == 0) return 0;
    return (uint16_t)((d.button[2] & 0xFF) | ((d.button[3] & 0xFF) << 8));
}

/* SELECT while a live stream's data is awaited */
bool replay_quit_poll()
{
    const uint16_t b = replay_pad(), press = (uint16_t)(b & ~g_rp.prev);
    g_rp.prev = b;
    if (press & kPadSelect) g_rp.quit = true;
    return g_rp.quit;
}

/* the frame semaphore's tokens, taken without waiting (they piled up during a pause) */
void replay_take_tokens(ppu_context* ctx)
{
    np_lv2_fn tw = g_lv2_syscalls[SC_SEM_TRYWAIT];
    if (!tw) return;
    const uint64_t r3 = ctx->gpr[3], r4 = ctx->gpr[4];
    for (int i = 0; i < 64; i++) {
        ctx->gpr[3] = rd32(kFrameSemPtr); ctx->gpr[4] = 0;
        if (tw(ctx) != 0 || (int32_t)ctx->gpr[3] != 0) break;
    }
    ctx->gpr[3] = r3; ctx->gpr[4] = r4;
}

void replay_end(const char* why)
{
    rp::play_finish(why);
    static int keep = -1;
    if (keep < 0) { const char* e = getenv("T5_REPLAY_EXIT"); keep = e && *e == '0'; }
    if (keep) return;
    np::note("replay: %s -- the game closes", why);
    fflush(stdout); fflush(stderr);
    TerminateProcess(GetCurrentProcess(), 0);
}

/* The playback's frame wait (main thread, once the lockstep runs): the end, the
 * viewer's buttons, then the frame semaphore wait as always (the direct-fight
 * driver's frame hook runs inside it). */
int64_t replay_frame_wait(ppu_context* ctx)
{
    ReplayPace& r = g_rp;
    if (!r.inited) {
        r.inited = true;
        QueryPerformanceFrequency(&r.qf);
        np::note("replay: START pauses, SELECT ends the replay");
    }
    if (!rp::play_frame(g_frame)) { replay_end(rp::play_live() ? "the live match is over" : "the replay is over"); return g_orig_wait(ctx); }
    if (rp::play_live()) {   /* spectating: the data for the next frames must be here (a short buffer) */
        const int w = rp::play_live_wait(g_frame, replay_quit_poll);
        if (w == 0) { replay_end("ended by the viewer (SELECT)"); return g_orig_wait(ctx); }
        if (w == 2) replay_take_tokens(ctx);   /* no burst of frames after the wait */
    }
    const uint16_t b = replay_pad(), press = (uint16_t)(b & ~r.prev);
    r.prev = b;
    if (press & kPadSelect) r.quit = true;
    if ((press & kPadStart) && !r.quit) {
        np::note("replay: paused at frame %u", g_frame);
        LARGE_INTEGER t0, t1; QueryPerformanceCounter(&t0);
        while (!r.quit) {
            Sleep(15);
            const uint16_t b2 = replay_pad(), p2 = (uint16_t)(b2 & ~r.prev);
            r.prev = b2;
            if (p2 & kPadSelect) r.quit = true;
            if (p2 & kPadStart) break;
        }
        QueryPerformanceCounter(&t1);
        np::note("replay: going on (paused %.1f s)", (double)(t1.QuadPart - t0.QuadPart) / (double)r.qf.QuadPart);
        replay_take_tokens(ctx);   /* no burst of frames to catch up */
    }
    if (r.quit) { replay_end("ended by the viewer (SELECT)"); return g_orig_wait(ctx); }
    return g_orig_wait(ctx);
}

extern "C" void lat_log_(char kind, const char* fmt, ...);   /* ps3recomp patch 0034 (runtime/platform/lat_log.h) */
extern "C" volatile int g_lat_log_on;

/* Offline: the take-over of the boot mode (keyread's vblank wakes stopped, the
 * thread parked, see on_frame_start), then the keyread tick at every frame. */
void offline_frame(ppu_context* ctx)
{
    if (g_offline_gave_up) return;
    if (!g_active) {
        g_boot_frames++;
        if (!rd32(kKeyreadSemPtr)) return;
        if (!g_swallow.load()) {
            g_swallow = true;
            while (g_kr_posting.load() != 0) YieldProcessor();
            g_takeover_frame = g_boot_frames + 1;
            return;
        }
        if (g_boot_frames < g_takeover_frame) return;
        if (!ensure_keyread_parked(ctx)) {
            /* never seen; give the pads back to the game's own thread */
            g_offline_gave_up = true;
            g_swallow = false;
            np::note("late input: the keyread thread does not park -- the game reads the pads itself");
            return;
        }
        g_main_tid = ctx->thread_id;
        g_active = true;
        np::note("late input: the pads are read at the top of each frame by the main thread (main loop frame %u; "
                 "T5_LATE_INPUT=0 leaves it to the game's keyread thread)", g_boot_frames);
    }
    if (ctx->thread_id != g_main_tid) return;
    if (g_lat_log_on) lat_log_('B', "%u", rd32(0x1008EB9Cu));   /* PS3_LATENCY_LOG: the pads are read now */
    keyread_tick();
}

void on_frame_start(ppu_context* ctx)
{
    if (!rb::net::bypass()) t5_training_frame(ctx);   /* src/training: reads the frame that just ran (read only) */
    rb::rand_install();   /* the game-DLL build: once the lifted table is out (no-op after the first time) */
    t5_unlock_install();  /* likewise */
    if (!g_main_tls && ctx->thread_id == (g_main_tid != ~0ull ? g_main_tid : 1) && ctx->gpr[13] >= 0x7000)
        g_main_tls = (uint32_t)ctx->gpr[13] - 0x7000u;   /* the main thread's TLS block (the TLS generator's state) */
    /* Direct fight with a session: while the select mode runs, the TLS generator
     * is pinned to the session's seed at every boundary. The select screen and
     * the game mode's set-up draw from it before lockstep frame 0 reseeds it --
     * the set-up picks Mokujin's fighter for the match (0x121E0C <- 0x5A304 <-
     * 0x53C88, game mode phase 2) -- and how many draws the select screen made
     * depended on how long each PC took there; Mokujin copied Feng on one PC
     * and Kazuya on the other (desync hunt runs v1c/v5: 0x1009094C 0x1001F vs
     * 0x1000F from the first frame). Pinned, the set-up draws the same on both. */
    /* (and since 1.1.4 mixed with the session's match number -- select_seed() --
     * so Mokujin and the random cell draw anew in every rematch) */
    if (g_main_tls && (g_directfight || g_persistent) && np::enabled() && ctx->thread_id == (g_main_tid != ~0ull ? g_main_tid : 1) &&
        t5_df_mode_cur() == 6) {
        static uint32_t noted = 0;
        uint32_t k;
        const uint32_t seed = select_seed(&k);
        rb::tls_rand_reseed(g_main_tls, seed, false);   /* the private streams run on (the select's emitters) */
        if (seed != noted) { noted = seed; np::note("select screen: TLS generator pinned to 0x%08X (session %u, match %u of it)", seed, np::sessions(), k + 1); }
    }
    t5_select_trace();
    if (g_offline) {
        if (!g_offline_seeded && g_main_tls) offline_seed();
        if (g_offline_fixed && ctx->thread_id == (g_main_tid != ~0ull ? g_main_tid : 1)) offline_pin();
        offline_frame(ctx);
        return;
    }
    bool fresh_start = false, resume = false;
    check_session();   /* a failed handshake / lost peer ends the match here (before and during lockstep) */
    if (!g_active) {
        g_boot_frames++;
        if (g_start_mode == StartMode::External && !g_start_requested.load()) return;
        if (g_start_mode == StartMode::Frame && g_boot_frames < g_start_frame) return;
        /* The take-over, at the same frame on both PCs: the frame the start is
         * due (boot: the first frame with a keyread thread; external: the frame
         * t5_netplay_start() was called) stops the keyread thread's vblank
         * wakes; the NEXT frame takes over. A wake posted just before the stop
         * (this frame's vblank) still runs one tick of the thread's own -- it
         * blocks on the lwmutex this thread holds and finishes once the frame
         * lets go of it -- and the thread parks for good after it. At the
         * take-over frame ensure_keyread_parked() checks that (and, should the
         * tick still be pending on a loaded PC, hands the lock over until it is
         * done), so the thread's tick never runs beside ours. */
        if (!rd32(kKeyreadSemPtr)) return;
        if (!g_swallow.load()) {
            g_swallow = true;
            while (g_kr_posting.load() != 0) YieldProcessor();   /* a post that missed the flag is through */
            g_takeover_frame = g_boot_frames + 1;
            /* Diagnostics: what the old rule ("in its wait") would have done
             * here -- taking over now while a wake is already on its way is the
             * boot race (QA run e_bootdeadlock_1). */
            const bool in_wait = g_kr_in_wait.load() != 0, parked = keyread_parked();
            const np_sys_semaphore_info& ks = g_sys_semaphores[(rd32(kKeyreadSemPtr) - 1) & 0xFF];
            np::note("main loop frame %u: keyread wakes stopped (keyread %s; tokens %d, waiters %d)%s", g_boot_frames,
                     parked ? "parked" : in_wait ? "flagged in its wait, but released" : "in a tick",
                     *(volatile const int32_t*)&ks.value, *(volatile const int32_t*)&ks.waiters,
                     in_wait && !parked ? " -- the old rule would have taken over here (the boot race)" : "");
            return;
        }
        if (g_boot_frames < g_takeover_frame) return;
        if (!ensure_keyread_parked(ctx)) {
            np::note("main loop frame %u: the keyread thread does not park -- take-over postponed (the two PCs "
                     "may now start a frame apart)", g_boot_frames);
            return;
        }
        g_main_tid = ctx->thread_id;
        g_active = true;
        g_start_requested = false;
        fresh_start = g_start_mode != StartMode::Boot;
        np::note("keyread thread is parked (sem %u); lockstep from here (main loop frame %u since boot, wakes "
                 "stopped at %u), main thread tid %llu", rd32(kKeyreadSemPtr), g_boot_frames, g_takeover_frame - 1,
                 (unsigned long long)g_main_tid);
    }
    if (ctx->thread_id != g_main_tid) {
        static int n = 0;
        if (n++ < 5) np::note("frame semaphore waited by tid %llu (main is %llu) -- ignored",
                              (unsigned long long)ctx->thread_id, (unsigned long long)g_main_tid);
        return;
    }
    if (g_idle) {
        /* Between two sessions of a persistent game: the keyread thread stays
         * parked, the main thread keeps running its tick with neutral pads (or
         * the direct-fight driver's presses). t5_netplay_start() begins the next
         * session's lockstep here like a fresh external start, at frame 0. */
        if (!g_start_requested.exchange(false) || !np::enabled()) {
            g_cur[0] = g_cur[1] = np::kNeutral;
            keyread_tick();
            return;
        }
        g_idle = false;
        if (g_paused) {
            g_paused = false;
            resume = true;
            np::note("lockstep of session %u resumes at frame %u", np::sessions(), g_frame);
        } else {
            g_frame = 0;
            fresh_start = true;
            np::note("lockstep of session %u from here (the keyread thread is still parked)", np::sessions());
        }
    }
    uint32_t f = g_frame;
    {   /* T5_NET_SCRIPT_FIGHT=1 (tests): scripted presses only while direct fight is in a fight */
        static int gate = -1;
        if (gate < 0) { const char* e = getenv("T5_NET_SCRIPT_FIGHT"); gate = e && *e == '1'; }
        if (gate) np::set_script_gate(t5_df_in_fight() != 0);
    }
    if (fresh_start) {
        /* Lockstep starts in the middle of a running game: what the two
         * games did before (boot, loading, menus at their own pace) must not
         * leave a trace. The per-frame counters get the same value on both
         * sides, the input ring is cleared, the RNGs are reseeded at frame 0
         * below; the handshake at frame 0 is the ready barrier. */
        equal_counters();
    }
    if (resume) {
        /* The end of a pause (in-game select): the two games ran their own
         * select screens for different numbers of frames. Both meet at a sync
         * point at the paused frame number, then get the same counters, input
         * ring and random seeds -- as at a fresh start -- and the next match's
         * mismatch count starts here. The rollback loop, stopped at the pause,
         * starts again from this frame below. */
        const uint32_t f_was = f;
        const uint32_t nf = np::scene_barrier(f);
        f = nf;
        g_frame = f;
        g_scenes++;
        equal_counters();
        sync_counters();
        const uint32_t seed = sync_seed(rp::kResume, np::match_seed() + g_scenes * 0x9E3779B9u);
        reseed(seed);
        sync_record(rp::kResume, f_was, nf, seed);
        apply_rounds();
        match_begins(f);
        g_await_load = g_directfight;
        np::log_extra(f, "resume");
    }
    const bool resync = g_start_requested.exchange(false);   /* next match in the same process */
    const bool pause = g_pause_requested.load() && !resync && !resume;   /* in-game select: stop at a sync point */
    if (rb::net::enabled() && f >= rb::net::start_frame() && f > 0) {
        /* Rollback netplay (T5_RB_MODE=net, src/rollback/rb_net.cpp): the
         * loop commits the state, exchanges inputs, rolls back and re-simulates
         * on a misprediction, and says which frame runs now with which inputs.
         * A scene change is acted on only once every input before it is
         * confirmed (the loop stalls for that), then it is the lockstep's sync
         * point as below and a floor for rollbacks. */
        if (!rb::net::active()) rb::net::start(f);
        /* The game's input-ring resets during a fight are ordinary state here:
         * the rollback restores and replays them, and both peers are frame
         * aligned. Treating them as sync points with an RNG reseed (the
         * lockstep's way) desynced the peers whenever one side saw the reset
         * live (reseed) and the other inside a re-simulation (no reseed):
         * runs d50/d150b, desync from frame 920 after the reset at 919, the
         * whole Mersenne Twister state differing. Only the explicit
         * t5_netplay_start() (the next match) stays a sync point. */
        /* One exception (fight-polish): the end of a fight's loading is a sync
         * point here too (fight_loaded_now()). How long the loading takes
         * depends on the game's caches: a game that has played already ends it
         * frames earlier or later than one that has just started (persistent
         * game, a new opponent: 2 frames, run rb_ps1), and without the barrier
         * the two then fight frames apart. */
        /* (at a resume the ring reset is ours, not the end of the loading) */
        const bool load_end = g_await_load && !rb::net::bypass() && !resume && (fight_loaded_now() || rd32(kRingResetFlag) != 0);
        const bool scene = resync || load_end || (pause && !rb::net::bypass());
        np::PadInput in[2];
        /* The loaders (ZsAread, decoder) are drained before the boundary's
         * snapshot, not after it: the state saved at a boundary is then one
         * with no read in flight, and the reader has posted its completion
         * token before the loop saves that semaphore's count with the
         * boundary (rb_net.cpp reader_sem_save; a restore that could not give
         * a taken token back hung the game mode at the match's end,
         * docs/ROLLBACK.md section 30). */
        const double load_ms = drain_wait(f);
        side_drain(f);   /* the geometry manager parked too (a snapshot or restore beside it hung the present) */
        start_gate(f);   /* this PC's START out only in a skip part (the live sample is taken in the boundary) */
        uint32_t run = rb::net::on_boundary(f, scene, in);
        if (load_ms >= 0) rb::net::load_seen(f, load_ms);
        if (run == f && scene) {
            const uint32_t nf = np::scene_barrier(f);
            const uint32_t kind = pause ? rp::kPause : resync ? rp::kResync : rp::kLoad;
            if (pause) {
                /* every input before f is confirmed and both games are at nf:
                 * the loop stops (its undo logs go), the select screens run on
                 * their own until the next fight */
                sync_seed(kind, 0);
                sync_record(kind, f, nf, 0);
                rb::net::session_reset();
                go_paused(nf);
                keyread_tick();
                return;
            }
            if (nf > f) skip_frames(nf - f);
            sync_counters();
            g_scenes++;
            const uint32_t seed = sync_seed(kind, np::match_seed() + g_scenes * 0x9E3779B9u);
            reseed(seed);
            sync_record(kind, f, nf, seed);
            apply_rounds();
            if (resync) { match_begins(nf); g_await_load = g_directfight; }
            else if (load_end) { g_await_load = false; np::note("frame %u: the fight is loaded (scene barrier, continuing at %u)", f, nf); }
            rb::net::scene_change(nf);
            char t[64];
            snprintf(t, sizeof t, "scene %u", g_scenes);
            np::log_extra(nf, t);
            if (nf > f) run = rb::net::on_boundary(nf, false, in);
        }
        g_frame = run + 1;
        if (np::replaying()) rp::play_inputs(run, in);   /* (a sync point may have renumbered the frames: the recorded frame's inputs) */
        no_pause_rule(run, in, run >= f);   /* (memory: the state at run's boundary, restored if it is re-simulated) */
        g_cur[0] = in[0];
        g_cur[1] = in[1];
        keyread_tick();
        rp::rec_frame(run);
        if (run == f) {
            watch_match(run);
            shot(run);
            dump_memory(run);
        }
        return;
    }
    const bool load_end = g_await_load && fight_loaded_now() && f > 0 && !resume;   /* the end of the fight's loading: a sync point too */
    if (((rd32(kRingResetFlag) && !resume) || resync || load_end || pause) && f > 0) {
        /* The game changed scene during the last frame (every scene start
         * asks keyread to clear the input ring). Scene changes that wait on
         * loading or sound land a frame or two apart on the two PCs, so they
         * are sync points: both sides continue from the same frame number,
         * with the game's frame clock moved along on the side that skipped,
         * and the random generator reseeded the same way on both. */
        const uint32_t nf = np::scene_barrier(f);
        const uint32_t kind = pause ? rp::kPause : resync ? rp::kResync : load_end ? rp::kLoad : rp::kRing;
        if (pause) {   /* in-game select: both games at nf, the lockstep stops there */
            sync_seed(kind, 0);
            sync_record(kind, f, nf, 0);
            go_paused(nf);
            keyread_tick();
            return;
        }
        if (nf > f) skip_frames(nf - f);   /* the game's counters move along by the frames this side skipped */
        sync_counters();
        const uint32_t f_was = f;
        f = nf;
        g_scenes++;
        const uint32_t seed = sync_seed(kind, np::match_seed() + g_scenes * 0x9E3779B9u);
        reseed(seed);
        sync_record(kind, f_was, nf, seed);
        apply_rounds();
        if (resync) { match_begins(f); g_await_load = g_directfight; }   /* the next match in the same process: its desync count starts here */
        else if (load_end) { g_await_load = false; np::note("frame %u: the fight is loaded (scene barrier)", f); }
        char t[64];
        snprintf(t, sizeof t, "scene %u", g_scenes);
        np::log_extra(f, t);
    }
    g_frame = f + 1;
    drain_workers(f);
    if (f == 0) {
        /* The game seeds its Mersenne Twister from the wall clock at boot
         * (0xAE6C8: sys_time_get_current_time -> init_by_array). Reseed it
         * with the seed both peers agreed on, before frame 0 runs. */
        np::connect();
        no_pause_reset();
        g_await_load = g_directfight;   /* the end of the fight's loading is a sync point (fight_loaded_now()) */
        const uint32_t seed = np::match_seed();
        reseed(seed);
        np::note("game RNGs reseeded with 0x%08X", seed);
        /* the replay: the seed, and whether the rollback loop takes over at frame 1 */
        rp::rec_start(seed, rb::net::enabled() && rb::net::start_frame() <= 1, np::delay());
        apply_rounds();
        match_begins(0);
    }
    std::string parts = "H";
    g_frame_hashing = f;
    if (g_desync_dump) { g_snap[f % kSnapFrames].clear(); g_snap_tag[f % kSnapFrames] = f + 1; }
    uint64_t h = state_hash(&parts);
    if (g_directfight && intro_phase_now()) h = kIntroHash;   /* the fight's loading and intros: not compared (below) */
    for (uint32_t mf; g_desync_dump && np::take_mismatch(&mf);) {
        if (g_snap_tag[mf % kSnapFrames] != mf + 1 || g_desync_dumps >= g_desync_dump_max) continue;
        char path[64];
        snprintf(path, sizeof path, "np_desync_f%06u.bin", mf);
        if (FILE* fp = fopen(path, "wb")) {
            fwrite(g_snap[mf % kSnapFrames].data(), 1, g_snap[mf % kSnapFrames].size(), fp);
            fclose(fp);
            g_desync_dumps++;
        }
    }
    np::log_extra(f, parts.c_str());
    page_hashes(f);
    dump_memory(f);
    shot(f);
    np::PadInput in[2];
    /* Direct fight: the game mode's start, loading and intros take no input --
     * not even at the first boundary of a session, which samples the input of
     * frame `delay` while the phase word still says 2 (rb_net.cpp intro rule:
     * a press there made the peer roll back into the fight's loading, which
     * then never finished). The rollback loop applies the same rule from its
     * first frame on; in lockstep it only matters for that first boundary. */
    start_gate(f);   /* this PC's START out only in a skip part */
    np::begin_frame(f, h, in, g_directfight && intro_input_now());
    no_pause_rule(f, in, true);
    g_cur[0] = in[0];
    g_cur[1] = in[1];
    keyread_tick();
    rp::rec_frame(f);   /* (before the match watch: a result written at this frame must find the frame counted) */
    watch_match(f, true, h);
    check_session();   /* the peer may have been lost while we waited for its input */
    char extra[128];
    snprintf(extra, sizeof extra, "R%u W%u S%u T%llu V%llu", rd32(kRingReadIdx), rd32(kRingWriteIdx),
             g_swallowed.load(), (unsigned long long)rd64(kFrameClock), (unsigned long long)rd64(kFrameClock + 8));
    np::log_extra(f, extra);
}

/* ---- syscall wrappers ---------------------------------------------------------- */

/* T5_NET_TRACE: count other blocking syscalls per (thread, object). */
template <int N> struct TraceSc {
    static np_lv2_fn orig;
    static std::atomic<uint32_t> cnt[64][64];
    static int64_t fn(ppu_context* ctx)
    {
        const uint32_t t = (uint32_t)ctx->thread_id, o = (uint32_t)ctx->gpr[3];
        cnt[t & 63][o & 63]++;
        return orig(ctx);
    }
    static void install() { orig = g_lv2_syscalls[N]; g_lv2_syscalls[N] = fn; }
    static void dump(const char* name)
    {
        std::string line = name; line += " (tid:obj calls):";
        for (int t = 0; t < 64; t++) for (int o = 0; o < 64; o++) {
            uint32_t c = cnt[t][o].exchange(0);
            if (c) { char b[32]; snprintf(b, sizeof b, " %d:%d %u", t, o, c); line += b; }
        }
        np::note("%s", line.c_str());
    }
};
template <int N> np_lv2_fn TraceSc<N>::orig = nullptr;
template <int N> std::atomic<uint32_t> TraceSc<N>::cnt[64][64];

/* T5_NET_TRACE: who waits on / posts which semaphore, summarised every 10 s. */
struct SemStat { std::atomic<uint32_t> waits{0}, posts{0}; };
SemStat g_semstat[64][64];   /* [tid][sem] */
void sem_trace_dump()
{
    static ULONGLONG last = 0;
    ULONGLONG now = GetTickCount64();
    if (now - last < 10000) return;
    last = now;
    std::string line = "sem stats (tid:sem waits/posts):";
    for (int t = 0; t < 64; t++)
        for (int m = 0; m < 64; m++) {
            uint32_t w = g_semstat[t][m].waits.exchange(0), p = g_semstat[t][m].posts.exchange(0);
            if (w || p) { char b[48]; snprintf(b, sizeof b, " %d:%d %u/%u", t, m, w, p); line += b; }
        }
    np::note("%s", line.c_str());
    TraceSc<107>::dump("sys_cond_wait");
    TraceSc<130>::dump("sys_event_queue_receive");
    TraceSc<100>::dump("sys_mutex_lock");
    TraceSc<141>::dump("sys_timer_usleep");
}

/* T5_TEST_HITCH=<ms>[:<min>:<max>] (tests, docs/NETPLAY.md "Desync hunt"): the
 * main thread stalls <ms> at a live frame boundary every <min>..<max> frames
 * (default 120..600) while the game's other threads -- the vblank ticker, the
 * sound core, the loaders, the file thread -- run on: a shader compile or a busy
 * PC on one side of a pair. (fight_flow_test --stutter suspends the whole
 * process, which stops those threads as well.) */
struct TestHitch {
    uint32_t ms = 0, lo = 120, hi = 600, next = 0, n = 0;
    uint64_t rng = 0x9E3779B97F4A7C15ull;
    TestHitch()
    {
        const char* e = getenv("T5_TEST_HITCH");
        if (!e || !*e) return;
        unsigned a = 0, b = 0, c = 0;
        const int k = sscanf(e, "%u:%u:%u", &a, &b, &c);
        ms = a;
        if (k == 3 && b && c >= b) { lo = b; hi = c; }
        next = pick();
    }
    uint32_t pick() { rng ^= rng << 13; rng ^= rng >> 7; rng ^= rng << 17; return lo + (uint32_t)(rng % (hi - lo + 1)); }
    void frame()
    {
        if (!ms || --next) return;
        next = pick();
        if (n++ < 3) np::note("T5_TEST_HITCH: the main thread stalls %u ms (every %u..%u frames)", ms, lo, hi);
        Sleep(ms);
    }
} g_test_hitch;

int64_t w_sem_wait(ppu_context* ctx)
{
    if (g_trace) {
        const uint32_t t = (uint32_t)ctx->thread_id, m = (uint32_t)ctx->gpr[3];
        if (t < 64 && m < 64) g_semstat[t][m].waits++;
        sem_trace_dump();
    }
    const uint32_t id = (uint32_t)ctx->gpr[3];
    const uint32_t kr = rd32(kKeyreadSemPtr);
    if (kr && id == kr) {
        g_kr_in_wait = 1;
        g_kr_enter++;
        SetEvent(g_kr_event);
        int64_t r = g_orig_wait(ctx);
        g_kr_in_wait = 0;
        g_kr_wake++;
        return r;
    }
    if (id < (uint32_t)kMaxSem && g_drain[id]) { g_drain_seen[id] = true; SetEvent(g_drain_event); }
    if (id && id == g_geom_sem.load(std::memory_order_relaxed) && g_drain_event) SetEvent(g_drain_event);
    const uint32_t fs = rd32(kFrameSemPtr);
    if (fs && id == fs && ctx->thread_id == g_main_tid) g_frame_wait_ctx = ctx;   /* the boundary's tick wait (early rollback) */
    if (fs && id == fs && ctx->thread_id == g_main_tid && rb::net::bypass()) {
        /* a re-simulated frame: no wait, straight to the next boundary */
        on_frame_start(ctx);
        return 0;
    }
    if (fs && id == fs && ctx->thread_id == g_main_tid && g_active && np::replaying()) {
        /* a replay being watched: its end, pause and SELECT */
        const int64_t r = replay_frame_wait(ctx);
        if (r == 0) on_frame_start(ctx);
        return r;
    }
    if (fs && id == fs && ctx->thread_id == g_main_tid && rb::net::early_pending()) {
        /* early rollback (rb_net.cpp early_check): the boundary runs now and
         * waits for this frame's tick itself (frame_tick_wait) */
        on_frame_start(ctx);
        return 0;
    }
    int64_t r = g_orig_wait(ctx);
    if (fs && id == fs && r == 0) {
        if (ctx->thread_id == g_main_tid) g_test_hitch.frame();
        on_frame_start(ctx);
    }
    return r;
}

int64_t w_sem_post(ppu_context* ctx)
{
    const uint32_t id = (uint32_t)ctx->gpr[3];
    if (g_trace) {
        const uint32_t t = (uint32_t)ctx->thread_id;
        if (t < 64 && id < 64) g_semstat[t][id].posts++;
    }
    const uint32_t kr = rd32(kKeyreadSemPtr);
    if (kr && id == kr) {
        /* g_kr_posting brackets the check and the real post, so the take-over
         * can wait out a post that read the flag just before it was set. */
        g_kr_posting.fetch_add(1);
        if (g_swallow.load() && rd32(kKeyreadQuit) == 0) {
            g_swallowed++;
            g_kr_posting.fetch_sub(1);
            return 0;   /* the vblank's keyread wake: the main loop drives keyread now */
        }
        const int64_t r = g_orig_post(ctx);
        g_kr_posting.fetch_sub(1);
        return r;
    }
    if (rb::net::bypass() && id == rd32(kFrameSemPtr)) {   /* re-simulating: vblank posts must not pile up */
        rb::net::early_tick_posted();   /* ... but an early boundary's tick has come */
        return 0;
    }
    return g_orig_post(ctx);
}

/* The early rollback's wait for the frame's tick: the frame semaphore wait the
 * title made when it went on (its context is the latest one seen). */
void frame_tick_wait(bool came)
{
    ppu_context* c = g_frame_wait_ctx;
    if (!c) return;
    const uint64_t r3 = c->gpr[3], r4 = c->gpr[4];
    c->gpr[3] = rd32(kFrameSemPtr); c->gpr[4] = 0;   /* sys_semaphore_wait(frame semaphore, no timeout) */
    if (!came) {
        g_orig_wait(c);   /* (the direct-fight driver's frame hook runs inside, after the wait) */
    } else {
        /* the tick's post was swallowed during the re-simulation: nothing to
         * wait for -- but a post that slipped through between the early check
         * and the re-simulation's start is still pending: take it (trywait) */
        if (np_lv2_fn tw = g_lv2_syscalls[SC_SEM_TRYWAIT]) tw(c);
        c->gpr[3] = rd32(kFrameSemPtr); c->gpr[4] = 0;
        t5_df_frame_tick(c);
    }
    c->gpr[3] = r3; c->gpr[4] = r4;
}

int64_t w_mem_alloc(ppu_context* ctx)
{
    const uint32_t size = (uint32_t)ctx->gpr[3], out = (uint32_t)ctx->gpr[5];
    int64_t r = g_orig_alloc(ctx);
    if (r == 0 && out) np::note("sys_memory_allocate(0x%X) -> 0x%08X", size, rd32(out));
    return r;
}

void install_syscall_hooks()
{
    bool expected = false;
    if (!g_installed.compare_exchange_strong(expected, true)) return;
    g_kr_event = CreateEventA(nullptr, FALSE, FALSE, nullptr);
    g_orig_wait = g_lv2_syscalls[SC_SEM_WAIT];
    g_orig_post = g_lv2_syscalls[SC_SEM_POST];
    g_lv2_syscalls[SC_SEM_WAIT] = w_sem_wait;
    g_lv2_syscalls[SC_SEM_POST] = w_sem_post;
    rb::net::set_tick_waiter(frame_tick_wait);
    if (g_trace) {
        TraceSc<107>::install();   /* sys_cond_wait */
        TraceSc<130>::install();   /* sys_event_queue_receive */
        TraceSc<100>::install();   /* sys_mutex_lock */
        TraceSc<141>::install();   /* sys_timer_usleep */
        g_orig_alloc = g_lv2_syscalls[SC_MEM_ALLOC];
        g_lv2_syscalls[SC_MEM_ALLOC] = w_mem_alloc;
    }
    np::note("semaphore hooks installed");
}

/* What a session takes from the environment: at boot, and in a persistent game
 * again for every new opponent (the control channel's T5_NET_* / T5_FIGHT). */
void read_session_env()
{
    EnterCriticalSection(&g_result_cs);
    const char* m = t5_env("T5_NET_MATCH");
    g_match_id = m ? m : "";
    LeaveCriticalSection(&g_result_cs);
    { const char* f1 = t5_env("T5_FIGHT"); const char* f2 = t5_env("T5_FIGHT_FILE");
      g_directfight = (f1 && *f1) || (f2 && *f2) || g_persistent || np::replaying(); }   /* (a replay is a direct fight) */
    np::set_no_start(g_directfight);   /* no pause online: this PC's START stays home (no_pause_rule) -- out only in a skip part (start_gate) */
    g_np_part_frames = 0; g_np_live = UINT32_MAX;
    if (const char* tp = t5_env("T5_TEST_SKIP_PRESS")) {   /* tests: see start_gate */
        const int n = atoi(tp); const char* c = strchr(tp, ':'); const int m = c ? atoi(c + 1) : n;
        g_np_test_press[1] = n < 0 ? UINT32_MAX : (uint32_t)n; g_np_test_press[2] = m < 0 ? UINT32_MAX : (uint32_t)m;
        np::note("test: this player presses START %d frames into every intro and %d after every round (-1 = never)", n, m);
    }
    g_rounds = 0;
    if (const char* r = t5_env("T5_NET_ROUNDS")) {
        g_rounds = atoi(r);
        if (g_rounds < 1 || g_rounds > 5) g_rounds = 0;
        if (g_rounds && !g_directfight) np::note("rounds to win: %d (T5_NET_ROUNDS, written at every sync point of a VS game)", g_rounds);
    }
    { const char* r = t5_env("T5_NET_RESULT_FILE"); g_result_file = r ? r : ""; }
    { const char* o = t5_env("T5_NET_ON_LOST"); g_on_lost_idle = o && !_stricmp(o, "idle"); }
    g_start_mode = g_persistent || np::replaying() ? StartMode::External : StartMode::Boot;   /* (a replay starts at its fight, as live) */
    if (const char* st = t5_env("T5_NET_START")) {
        if (!_stricmp(st, "external")) g_start_mode = StartMode::External;
        else if (!_strnicmp(st, "frame:", 6)) { g_start_mode = StartMode::Frame; g_start_frame = (uint32_t)atoi(st + 6); }
        np::note("lockstep starts %s", g_start_mode == StartMode::External ? "when the game calls t5_netplay_start()"
                                       : g_start_mode == StartMode::Frame ? "at a fixed main loop frame" : "at boot");
    }
}

void h_cellPadInit(ppu_context* ctx)
{
    int32_t r = cellPadInit((uint32_t)ctx->gpr[3]);
    ctx->gpr[3] = (uint64_t)(int64_t)r;
    if (g_offline) { install_syscall_hooks(); return; }
    np::init();
    if (!np::enabled() && !g_persistent) return;
    /* The sound library's heap (rb_sndheap.cpp): in every online session,
     * rollback or lockstep (T5_RB_MODE=off too), before the library's first
     * allocation. Where its blocks live changes the layout of the C library
     * heap, which reaches the hashed state: a PC with it and one without
     * desynced in lockstep (rollback-crash run MIX50: 4 233 frames). */
    rb::sndheap_install();
    rb::net::offer();   /* rollback in the HELLO unless T5_RB_MODE=off (rb_net.cpp offered_by_env) */
    const char* hs = getenv("T5_NET_HASH");
    g_hash_ranges = parse_ranges(hs ? hs : kDefaultHash);
    { const char* dd = getenv("T5_NET_DESYNC_DUMP"); const int n = dd ? atoi(dd) : 0;
      g_desync_dump = n >= 1; if (n > 1) g_desync_dump_max = (uint32_t)n; }
    InitializeCriticalSection(&g_result_cs);
    read_session_env();
    { const char* t = getenv("T5_NET_TAKEOVER_TEST"); g_takeover_test = t && *t == '1'; }
    if (!g_on_lost_idle) np::set_stuck_handler(stuck_handler);
    const char* hk = getenv("T5_NET_HASH_SKIP");
    g_hash_skip = parse_ranges(hk ? hk : (hs ? "" : kDefaultHashSkip));
    if (const char* p = getenv("T5_NET_PAGEHASH")) {
        std::vector<Range> pr = parse_ranges(p);
        if (!pr.empty()) {
            g_page_range = pr[0];
            const char* e = strchr(strchr(p, ':') + 1, ':');
            if (e) g_page_every = (uint32_t)strtoul(e + 1, nullptr, 10);
            if (!g_page_every) g_page_every = 60;
        }
    }
    if (const char* d = getenv("T5_NET_SHOT")) {
        for (const char* p = d; *p;) {
            char* e; unsigned long v = strtoul(p, &e, 10);
            if (e == p) break;
            g_shot_frames.push_back((uint32_t)v);
            p = e; while (*p == ',') p++;
        }
        const char* g = getenv("LD_SURF_DUMP_GATE");
        if (g) { g_shot_gate = g; remove(g); }
        else np::note("T5_NET_SHOT needs LD_SURF_DUMP=<dir> and LD_SURF_DUMP_GATE=<file>");
    }
    if (const char* d = getenv("T5_NET_DUMP")) {
        for (const char* p = d; *p;) {
            char* e; unsigned long v = strtoul(p, &e, 10);
            if (e == p) break;
            g_dump_frames.push_back((uint32_t)v);
            p = e; while (*p == ',') p++;
        }
        const char* dr = getenv("T5_NET_DUMP_RANGES");
        g_dump_ranges = parse_ranges(dr ? dr : "10000000:760000");
    }
    {
        const char* d = getenv("T5_NET_DRAIN");
        const char* spec = d ? d : "8,10";
        for (const char* p = spec; *p;) {
            char* e; long v = strtol(p, &e, 10);
            if (e == p) break;
            if (v > 0 && v < kMaxSem) g_drain[v] = true;
            p = e; while (*p == ',' || *p == ' ') p++;
        }
        g_drain_event = CreateEventA(nullptr, FALSE, FALSE, nullptr);
        np::note("draining loader semaphores at each frame: %s (no time limit; T5_NET_LOAD_TIMEOUT ends the match)",
                 *spec ? spec : "(none)");
        if (const char* t = getenv("T5_TEST_DRAIN_HOLD")) {
            unsigned ms = 0, fr = 5;
            sscanf(t, "%u:%u", &ms, &fr);
            g_drain_test_ms = ms; g_drain_test_frame = fr;
            if (ms) np::note("TEST: the loader drain holds frame %u of each session for at least %u ms (T5_TEST_DRAIN_HOLD)", fr, ms);
        }
        if (const char* s = getenv("T5_RB_SIDE_DRAIN")) g_side_drain = *s != '0';
    }
    if (g_passive) { np::note("passive reference mode: %d pad(s), keyread left alone", g_pads); return; }
    install_syscall_hooks();
}

struct Register {
    Register()
    {
        const char* m = getenv("T5_NET_MODE");
        const char* ctl = getenv("T5_CTL_DIR");
        g_persistent = ctl && *ctl;
        if ((!m || !*m) && !g_persistent) {
            /* netplay off: only the offline keyread tick (T5_LATE_INPUT=0: nothing
             * at all); the rollback test modes have their own frame hooks */
            const char* li = getenv("T5_LATE_INPUT");
            const char* rm = getenv("T5_RB_MODE");
            if ((li && *li == '0') || (rm && (!strcmp(rm, "test") || !strcmp(rm, "measure")))) return;
            g_offline = true;
            ps3_hle_register_ctx(NID_cellPadInit, "cellPadInit(late input)", h_cellPadInit);
            return;
        }
        const char* t = getenv("T5_NET_TRACE");
        g_trace = t && *t == '1';
        const char* pv = getenv("T5_NET_PASSIVE");
        g_passive = pv && *pv == '1';
        const char* pd = getenv("T5_NET_PADS");
        if (pd && (*pd == '1' || *pd == '2')) g_pads = *pd - '0';
        ps3_hle_register_ctx(NID_cellPadInit,    "cellPadInit(netplay)",    h_cellPadInit);
        ps3_hle_register_ctx(NID_cellPadGetInfo, "cellPadGetInfo(netplay)", h_cellPadGetInfo);
        ps3_hle_register_ctx(NID_cellPadGetData, "cellPadGetData(netplay)", h_cellPadGetData);
        /* the window closed = this player leaves (quit); Esc asks twice while online (patch 0035) */
        ps3_set_window_closed_handler(on_window_closed);
        ps3_set_window_close_guard(close_guard);
    }
} g_register;

/* ---- persistent game: sessions ----------------------------------------------
 * The session lost its peer or never connected: the result file says why (unless
 * this match's result is out), the socket is closed and the game stays open --
 * the direct-fight driver leaves the fight and waits for the next command. */
void persistent_lost(const char* reason)
{
    write_end_result(reason);
    np::note("the session cannot go on (%s): it ends, the game stays open for the next match", reason);
    rb::net::session_reset();
    np::session_end(reason);
    g_idle = g_active.load();
    g_paused = false;
    g_pause_requested = false;
    g_start_requested = false;
    g_inject_on = 0;
    g_session_lost = reason;
}

} // namespace

/* Persistent game (T5_CTL_DIR): a new session from the T5_NET_* variables the
 * control channel just put into the environment (main thread, at a frame
 * boundary, before t5_netplay_start() of its first fight). Any session still
 * running ends first. Returns 1 when the environment has netplay. */
extern "C" int t5_netplay_session_begin(void)
{
    if (!g_persistent) return 0;
    flush_result(true);
    read_session_env();
    g_frame = 0;
    g_scenes = 0;
    g_result_done = true;          /* the last match's "decided" flag is still up until the new fight clears it */
    g_match_running = false;
    g_match_f0 = 0;
    g_pending.on = false;
    EnterCriticalSection(&g_result_cs);
    g_last_result_match = "\x01";
    LeaveCriticalSection(&g_result_cs);
    g_lost_written = false;
    g_start_requested = false;
    g_paused = false;
    g_pause_requested = false;
    g_inject_on = 0;
    g_cur[0] = g_cur[1] = np::kNeutral;
    g_session_lost = nullptr;
    rb::net::session_reset();
    const bool ok = np::session_begin();
    g_idle = g_active.load();     /* lockstep of this session begins at t5_netplay_start() */
    np::note("session %u set up (%s)%s", np::sessions(), ok ? "handshake running" : "no netplay in the environment",
             g_active.load() ? "; the keyread thread stays parked" : "");
    return ok ? 1 : 0;
}

/* Persistent game: end the session ("idle", "quit" or a new opponent). A pending
 * result goes out first. */
extern "C" void t5_netplay_session_end(const char* why)
{
    if (!g_persistent) return;
    flush_result(true);
    rb::net::session_reset();
    np::session_end(why);
    g_idle = g_active.load();
    g_paused = false;
    g_pause_requested = false;
    g_start_requested = false;
    g_inject_on = 0;
}

/* Persistent game: the reason the session ended by itself (peer lost, no
 * connection), once; nullptr otherwise. */
extern "C" const char* t5_netplay_take_session_lost(void)
{
    return g_session_lost.exchange(nullptr);
}

extern "C" int t5_netplay_persistent(void) { return g_persistent ? 1 : 0; }

/* The direct-fight driver ends the session from this side (a pick that never
 * came): the next frame's check_session() acts on it like on a lost peer. */
extern "C" void t5_netplay_give_up(const char* reason, const char* text) { np::give_up(reason, "%s", text); }

/* A kernel semaphore's count, for the rollback loop (rb_net.cpp: the reader's
 * completion semaphore is part of the state it saves at every boundary and
 * puts back with a restore). -1: no such semaphore. */
extern "C" int32_t t5_sem_count(uint32_t id)
{
    if (id == 0 || id > 256) return -1;
    np_sys_semaphore_info& s = g_sys_semaphores[id - 1];
    if (!s.active) return -1;
    EnterCriticalSection(&s.value_lock);
    const int32_t v = s.value;
    LeaveCriticalSection(&s.value_lock);
    return v;
}
/* Set it -- only while nobody waits on it (the reader's completion semaphore
 * is only ever taken with a trywait by the main thread). */
extern "C" int t5_sem_set_count(uint32_t id, int32_t v)
{
    if (id == 0 || id > 256 || v < 0) return 0;
    np_sys_semaphore_info& s = g_sys_semaphores[id - 1];
    if (!s.active) return 0;
    EnterCriticalSection(&s.value_lock);
    const bool ok = s.waiters == 0 && v <= s.max_value;
    if (ok) s.value = v;
    LeaveCriticalSection(&s.value_lock);
    return ok ? 1 : 0;
}

/* The direct-fight mode calls this on the main thread when its fight starts
 * (both PCs do, for the same match). With T5_NET_START=external it begins
 * lockstep at the next frame; while lockstep runs it makes the next frame a
 * sync point. Harmless when netplay is off. */
extern "C" void t5_netplay_start(void)
{
    g_start_requested = true;
}

/* In-game select: pause the running lockstep at the next frame (a sync point;
 * both games ask at the same game frame). No-op without a running lockstep. */
extern "C" void t5_netplay_pause(void)
{
    if (g_active.load() && !g_idle && np::enabled()) g_pause_requested = true;
}
extern "C" int t5_netplay_paused(void) { return g_paused ? 1 : 0; }

extern "C" void t5_netplay_inject(int port, int on, unsigned buttons)
{
    if (port < 0 || port > 1) return;
    if (g_active.load() && !g_idle) {
        /* in lockstep: the local slot's presses go out as the local input; the
         * other slot is the peer's business (its own direct-fight driver) */
        if (port == np::local_slot()) np::set_local_inject(on != 0, (uint16_t)buttons);
        return;
    }
    g_inject[port] = (uint16_t)buttons;
    if (on) g_inject_on |= (1u << port); else g_inject_on &= ~(1u << port);
}

extern "C" int t5_netplay_enabled(void)
{
    return np::enabled() ? 1 : 0;
}

extern "C" int t5_netplay_lockstep_active(void)
{
    return g_active.load() && !g_idle ? 1 : 0;
}

/* The direct-fight driver (df_fight.cpp) acts on a match end only once this
 * says it is final: under rollback the live frame rests on predicted peer
 * input for up to the prediction window, and a KO seen there can be undone by
 * the next rollback (e2e g2, RTT 250: the driver held its pads and pressed
 * START to skip a replay in a fight that went on -- the peer never saw a KO,
 * the match never ended). Final = this side's match watch has the end
 * (watch_match: g_result_done, taken back by a rollback that undoes it) and
 * every input of the frames up to it is confirmed as simulated -- the frames
 * after the KO do not matter (the post-match rule decides them, and they
 * cannot change the KO); or its result is out already. Not "the whole live
 * state is final": at RTT 250 the last 10-15 frames always rest on
 * predictions. Without rollback: at once. */
extern "C" int t5_netplay_match_end_final(void)
{
    if (!rb::net::active()) return 1;
    if (!g_result_done) return 0;
    return !g_pending.on || rb::net::state_final(g_pending.f) ? 1 : 0;
}

extern "C" int t5_netplay_local_slot(void)
{
    return np::local_slot();
}

extern "C" void t5_netplay_set_match(const char* id)
{
    if (!id || !np::enabled()) return;
    EnterCriticalSection(&g_result_cs);
    if (g_match_id != id) np::note("next match: %s", id);
    g_match_id = id;
    LeaveCriticalSection(&g_result_cs);
}

extern "C" unsigned t5_netplay_match_seed(void)
{
    if (!np::enabled()) return 0;
    np::connect();
    return np::match_seed();
}
