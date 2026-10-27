/*
 * T5DR practice tools (docs/TRAINING.md "Practice tools"): position resets,
 * the dummy's behaviour and five recording slots, steered with SELECT combos
 * on P1's pad. The logic is in training_logic.h (Combo, Dummy, Recorder; unit
 * tested); this file connects it to the game.
 *
 * OFFLINE PRACTICE ONLY. Unlike the overlay (training.cpp, which only reads)
 * this changes the game: P1's and the dummy's pad masks before the game sees
 * them, and the fighters' positions. So it acts only when every one of these
 * holds, checked again in every frame:
 *   - the game was started without netplay (no T5_NET_MODE, no T5_CTL_DIR, no
 *     replay file) and netplay is not on: t5_hooks.cpp calls in only from its
 *     offline keyread tick (g_offline), never in a replay, a spectated match, a
 *     lockstep or rollback session;
 *   - the game type is Practice (10 at 0x1008EBAC) and the fight runs (phase 17);
 *   - T5_PRACTICE=1 (the launcher's Settings -> Practice tools).
 * Online matches therefore run exactly the code they ran before.
 *
 * Environment:
 *   T5_PRACTICE=1          on (the launcher sets 0 or 1; unset = off)
 *   T5_PRACTICE_DUMMY      the dummy's behaviour at the start: game | block | crouch | walk | step
 *   T5_PRACTICE_LOG        file: one line per action (tests)
 */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "ppu_recomp.h"     /* vm_base */
#include "training_logic.h"

extern "C" int t5_netplay_enabled(void);       /* src/netplay/t5_hooks.cpp */

namespace {

using namespace training;

/* ---- guest memory (NPUB30009 v01.00) ------------------------------------------ */
constexpr uint32_t kPhase    = 0x1008F070;   /* 17 = the fight runs */
constexpr uint32_t kGameType = 0x1008EBAC;   /* 10 = Practice */
constexpr uint32_t kGtPractice = 10;
constexpr uint32_t kFighter[2] = { 0x10090030, 0x10090900 };

inline uint32_t rd32(uint32_t a) { uint32_t v; memcpy(&v, vm_base + a, 4); return _byteswap_ulong(v); }
inline uint16_t rd16(uint32_t a) { uint16_t v; memcpy(&v, vm_base + a, 2); return _byteswap_ushort(v); }
inline uint8_t  rd8(uint32_t a)  { return vm_base[a]; }

/* A fighter's place (traced in Practice, T5_TRAINING_TRACE): the base x / z at
 * +0x10 / +0x18 and its facing angle at +0x30; the root (the base moved by the
 * animation) at +0x24 / +0x2C and its angle at +0x84; three 4x4 world
 * matrices of the root (this frame and the two before) at +0x700, +0x740 and
 * +0x780: rows 0-2 the rotation (row 2 the facing direction), row 3 the
 * position. The game takes the root's motion from the matrices, so a place
 * written to the base alone springs back or jumps (traced: a fighter put 4,000
 * units away moved another 1,273 in the next frame) and an angle written to
 * +0x30 alone is undone. put_place moves and turns all of them alike. */
constexpr uint32_t kPosX = 0x10, kPosZ = 0x18, kAngle = 0x30, kRootX = 0x24, kRootZ = 0x2C, kRootAngle = 0x84;
constexpr uint32_t kMatrix[3] = { 0x700, 0x740, 0x780 };

inline float rdf(uint32_t a) { const uint32_t u = rd32(a); float f; memcpy(&f, &u, 4); return f; }
/* THE store into guest memory: only from put_place, only behind allowed() (offline Practice) */
inline void put32(uint32_t a, uint32_t v) { v = _byteswap_ulong(v); memcpy(vm_base + a, &v, 4); }
inline void putf(uint32_t a, float f) { uint32_t u; memcpy(&u, &f, 4); put32(a, u); }

Place read_place(int p)
{
    const uint32_t b = kFighter[p];
    Place pl;
    pl.x = rdf(b + kPosX); pl.z = rdf(b + kPosZ); pl.angle = rdf(b + kAngle);
    return pl;
}

inline float wrap_angle(float a)
{
    while (a > 3.14159265f) a -= 6.28318531f;
    while (a <= -3.14159265f) a += 6.28318531f;
    return a;
}

/* a point (x at a, z at a + 8) relative to the old base: turned by d, then put at the new base */
void move_point(uint32_t a, float x0, float z0, const Place& to, float d)
{
    float x = rdf(a) - x0, z = rdf(a + 8) - z0;
    turn(x, z, d);
    putf(a, to.x + x);
    putf(a + 8, to.z + z);
}

void put_place(int p, const Place& to)
{
    const uint32_t b = kFighter[p];
    const float x0 = rdf(b + kPosX), z0 = rdf(b + kPosZ), d = to.angle - rdf(b + kAngle);
    move_point(b + kRootX, x0, z0, to, d);
    for (uint32_t m : kMatrix) {
        for (uint32_t r = 0; r < 3; r++) {             /* the rotation rows: their x / z turn */
            float x = rdf(b + m + r * 16), z = rdf(b + m + r * 16 + 8);
            turn(x, z, d);
            putf(b + m + r * 16, x);
            putf(b + m + r * 16 + 8, z);
        }
        move_point(b + m + 48, x0, z0, to, d);         /* the position row */
    }
    putf(b + kPosX, to.x);
    putf(b + kPosZ, to.z);
    putf(b + kAngle, to.angle);
    putf(b + kRootAngle, wrap_angle(rdf(b + kRootAngle) + d));
}

Sample read_fighter(uint32_t b)
{
    Sample s;
    const uint32_t w220 = rd32(b + 0x220), w21c = rd32(b + 0x21C);
    s.input    = rd16(b + 0x6D6);
    s.right    = rd8(b + 0x1D2) != 0;
    s.can_act  = (w220 & 0xFF) == 1 && ((w220 & 0x01000000u) || (w21c & 1));
    s.end_window = (w220 & 0xFF) == 1 && (w220 & 0x01000000u);
    s.new_move = (rd32(b + 0x20C) >> 24) & 1;
    s.active   = (rd32(b + 0x214) & 0x30000u) != 0;
    s.cls      = rd32(b + 0x15C);
    s.hp       = (int16_t)rd16(b + 0x6BC);
    const uint32_t mv = rd32(b + 0x168) >> 16;
    s.down     = (mv & 0xFF00) == 0x8000 && mv != 0x8001 && mv != 0x8000;
    return s;
}

/* ---- settings and state ----------------------------------------------------------- */
struct Cfg {
    bool on = false;
    bool offline = false;     /* started without netplay, replay or spectating */
    DummyMode dummy0 = DummyMode::Game;
    FILE* log = nullptr;
} g_cfg;
bool g_init = false;

Combo g_combo;
Dummy g_dummy;
Recorder g_rec;
Placer g_placer;
Place g_start[2];             /* both places at the first frame of the fight: SELECT+3 goes back there */
DummyMode g_mode = DummyMode::Game;
bool g_in_practice = false;
int g_prev_hp = 0;
uint64_t g_frame = 0;
uint64_t g_msg_until = 0;     /* the status line shows the last change this long */
uint64_t g_check_at = 0;      /* T5_PRACTICE_LOG: the places again 30 frames after a reset (tests) */

const char* kModeKey[] = { "game", "block", "crouch", "walk", "step" };

void init()
{
    g_init = true;
    const char* e = getenv("T5_PRACTICE");
    g_cfg.on = e && *e == '1';
    const char* nm = getenv("T5_NET_MODE");
    const char* ctl = getenv("T5_CTL_DIR");
    const char* rp = getenv("T5_REPLAY_FILE");
    g_cfg.offline = !(nm && *nm) && !(ctl && *ctl) && !(rp && *rp);
    if (const char* d = getenv("T5_PRACTICE_DUMMY"))
        for (int i = 0; i < (int)DummyMode::Count; i++)
            if (!strcmp(d, kModeKey[i])) g_cfg.dummy0 = (DummyMode)i;
    if (const char* f = getenv("T5_PRACTICE_LOG"); f && *f) g_cfg.log = fopen(f, "w");
    if (g_cfg.on)
        fprintf(stderr, "[practice] tools on (Practice, offline): SELECT combos, dummy %s%s\n", kModeKey[(int)g_cfg.dummy0],
                g_cfg.offline ? "" : " -- not in this game (started for online play, a replay or spectating)");
}

void note(const char* fmt, const char* a = "", int n = 0)
{
    if (!g_cfg.log) return;
    fprintf(g_cfg.log, "%llu ", (unsigned long long)g_frame);
    fprintf(g_cfg.log, fmt, a, n);
    fputc('\n', g_cfg.log);
    fflush(g_cfg.log);
}

bool allowed()
{
    return g_cfg.on && g_cfg.offline && t5_netplay_enabled() == 0 && rd32(kGameType) == kGtPractice && rd32(kPhase) == 17;
}

void note_place(const char* what)
{
    if (!g_cfg.log) return;
    const Place a = read_place(0), b = read_place(1);
    fprintf(g_cfg.log, "%llu %s P1 %.1f %.1f %.3f dummy %.1f %.1f %.3f\n", (unsigned long long)g_frame, what,
            a.x, a.z, a.angle, b.x, b.z, b.angle);
    fflush(g_cfg.log);
}

void act(PAction a)
{
    switch (a) {
    case PAction::ResetRound:
        g_placer.cancel();
        put_place(0, g_start[0]);
        put_place(1, g_start[1]);
        note_place("reset round start:");
        g_check_at = g_frame + 30;
        break;
    case PAction::DummyWallFront:
    case PAction::DummyWallBack:
    case PAction::PlayerWallFront:
    case PAction::PlayerWallBack: {
        Place probe;
        int mover;
        if (g_placer.start(a, read_place(0), read_place(1), &mover, &probe)) {
            note_place("wall probe from:");
            put_place(mover, probe);
        }
        break; }
    case PAction::Record: g_rec.toggle_record(); note("record slot %s%d", "", g_rec.slot() + 1); break;
    case PAction::Play: g_rec.toggle_play(false); note("play slot %s%d", "", g_rec.slot() + 1); break;
    case PAction::Loop: g_rec.toggle_play(true); note("loop slot %s%d", "", g_rec.slot() + 1); break;
    case PAction::SlotNext: g_rec.select(1); note("slot %s%d", "", g_rec.slot() + 1); break;
    case PAction::SlotPrev: g_rec.select(-1); note("slot %s%d", "", g_rec.slot() + 1); break;
    case PAction::DummyNext:
    case PAction::DummyPrev: {
        const int n = (int)DummyMode::Count, d = a == PAction::DummyNext ? 1 : n - 1;
        g_mode = (DummyMode)(((int)g_mode + d) % n);
        note("dummy %s%d", kModeKey[(int)g_mode], 0);
        break; }
    default: break;
    }
    g_msg_until = g_frame + 120;
}

} // namespace

/* t5_hooks.cpp keyread_tick, offline only: P1's (port 0) and P2's (port 1)
 * masks for the frame about to run, before they go into the game's input ring. */
extern "C" void t5_practice_pads(uint16_t* p1, uint16_t* p2)
{
    if (!g_init) init();
    if (!g_cfg.on) return;
    if (!allowed()) {
        if (g_in_practice) { g_combo.reset(); g_dummy.reset(); g_rec.stop(); g_in_practice = false; }
        return;
    }
    if (!g_in_practice) {
        g_in_practice = true;
        g_mode = g_cfg.dummy0;
        g_prev_hp = 0;
        g_placer.cancel();
        g_start[0] = read_place(0);
        g_start[1] = read_place(1);
        note("practice %s%d", kModeKey[(int)g_mode], 0);
        note_place("round start:");
    }
    g_frame++;
    if (g_placer.pending()) {       /* a wall reset: the game has run a frame from the mover's last place */
        const Placer::Cmd c = g_placer.next(read_place(g_placer.mover()));
        if (c.done) {
            put_place(0, c.out[0]);
            put_place(1, c.out[1]);
            note_place(c.wall ? "wall:" : "no wall there, back to:");
            g_check_at = g_frame + 30;
        } else {
            put_place(g_placer.mover(), c.mover);
        }
    }
    if (g_check_at && g_frame == g_check_at) { g_check_at = 0; note_place("30 frames later:"); }
    const Sample me = read_fighter(kFighter[0]), dm = read_fighter(kFighter[1]);
    if (!g_prev_hp) g_prev_hp = dm.hp;
    const uint16_t raw = *p1;
    bool hide = false;
    const PAction a = g_combo.frame(raw, me.right, &hide);
    if (a != PAction::None) act(a);
    if (hide) *p1 = 0;

    /* the dummy: recording (your pad plays it), a recording, its behaviour, or the game's own */
    if (g_rec.state() == Recorder::State::Recording) {
        const uint16_t rel = hide ? 0 : to_rel((uint16_t)(raw & ~(kSelect | kStart)), me.right);
        g_rec.record(rel);
        *p2 = from_rel(rel, dm.right);
        *p1 = 0;
    } else {
        uint16_t rel;
        if (g_rec.next(&rel)) *p2 = from_rel(rel, dm.right);
        else if (g_mode != DummyMode::Game) *p2 = g_dummy.frame(g_mode, dm, g_prev_hp);
    }
    g_prev_hp = dm.hp;
}

/* training.cpp: the practice status line (empty: nothing to show) */
extern "C" int t5_practice_status(char* out, unsigned n, int de)
{
    out[0] = 0;
    if (!g_cfg.on || !g_in_practice) return 0;
    static const char* en_modes[] = { "GAME", "BLOCK AFTER HIT", "CROUCH", "WALK", "STEP" };
    static const char* de_modes[] = { "SPIEL", "BLOCKT NACH TREFFER", "DUCKT", "GEHT", "SEITSCHRITT" };
    const char* mode = (de ? de_modes : en_modes)[(int)g_mode];
    const int slot = g_rec.slot() + 1;
    switch (g_rec.state()) {
    case Recorder::State::Recording:
        snprintf(out, n, "REC %d  %.1fs", slot, g_rec.length(g_rec.slot()) / 60.0);
        return 1;
    case Recorder::State::Playing:
    case Recorder::State::Looping:
        snprintf(out, n, "%s %d  %.1f/%.1fs", g_rec.state() == Recorder::State::Looping ? "LOOP" : "PLAY", slot,
                 g_rec.pos() / 60.0, g_rec.length(g_rec.slot()) / 60.0);
        return 1;
    default: break;
    }
    if (g_frame < g_msg_until) {
        snprintf(out, n, "%s %d (%.1fs)  DUMMY: %s", de ? "PLATZ" : "SLOT", slot, g_rec.length(g_rec.slot()) / 60.0, mode);
        return 1;
    }
    return 0;
}

extern "C" int t5_practice_on(void)
{
    if (!g_init) init();
    return g_cfg.on && g_cfg.offline;
}
