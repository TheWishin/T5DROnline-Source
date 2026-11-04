/*
 * T5DR practice tools (docs/TRAINING.md "Practice tools", "Practice menu"):
 * position resets, the dummy's behaviour and recording slots, steered with
 * SELECT combos on P1's pad, and since 1.3.0 the practice menu (START): the
 * dummy's movement and counter-attack, recordings kept per character on disk,
 * random playback, restart positions (remembered, switched sides, back turned)
 * and a simulated input delay for P1. The logic is in training_logic.h (Combo,
 * Dummy, Recorder) and practice_logic.h (Menu, CounterAttack, InputDelay, the
 * files; unit tested); this file connects it to the game.
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
 *   T5_PRACTICE_DUMMY      the dummy's behaviour at the start: game | block | crouch | walk | step |
 *                          dash | backdash | kbd | wavedash
 *   T5_PRACTICE_MENU=0     START opens the game's pause menu as before (default: the practice menu)
 *   T5_PRACTICE_DIR        folder for the recordings (char<NN>.txt) and the menu's settings
 *                          (settings.txt); default "practice" in the working directory; "-" = keep nothing
 *   T5_PRACTICE_LOG        file: one line per action (tests)
 * Guest memory written (offline Practice only, all through put32): both fighters'
 * places (put_place), the Practice menu's TRAINING DUMMY and where the menu puts
 * it (set_dummy), and P1's / P2's masks in the input ring (t5_hooks.cpp).
 */
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include <string>
#if defined(_WIN32)
#  include <direct.h>          /* _mkdir */
#else
#  include <sys/stat.h>
#endif

#include "ppu_recomp.h"     /* vm_base */
#if !defined(_WIN32)
#  include "msvc_compat.h"     /* _byteswap_* off Windows (as platform/t5_win.h) */
#endif
#include "rsx_overlay.h"    /* ps3recomp patch 0045: the menu is drawn into training.cpp's list */
#include "training_logic.h"
#include "practice_logic.h"

extern "C" int t5_netplay_enabled(void);       /* src/netplay/t5_hooks.cpp */
extern "C" int t5_training_display_get(void);   /* training.cpp: the overlay's mode (0 off, 1 inputs, 2 frame data) */
extern "C" void t5_training_display_set(int mode);

namespace {

using namespace training;
using practice::Settings;
using practice::Restart;

/* ---- guest memory (NPUB30009 v01.00) ------------------------------------------ */
constexpr uint32_t kPhase    = 0x1008F070;   /* 17 = the fight runs */
constexpr uint32_t kGameType = 0x1008EBAC;   /* 10 = Practice */
constexpr uint32_t kGtPractice = 10;
constexpr uint32_t kRunning  = 0x1008F083;   /* u8: 1 while the fight runs, 0 while the pause menu is open (and in its first frame) */
constexpr uint32_t kDummySetting = 0x1008EFF0;   /* low byte (0x1008EFF3): the Practice menu's TRAINING DUMMY (Dummy::setting) */
/* ... and where the menu puts it when it closes (traced: both 9 after "backward roll", both 10 after
 * CONTROLLER, then the dummy plays P2's pad): the dummy acts on these, the menu shows the one above */
constexpr uint32_t kDummyApplied[2] = { 0x1008EC60, 0x1008EC64 };   /* low bytes 0x1008EC63, 0x1008EC67 */
constexpr uint32_t kFighter[2] = { 0x10090030, 0x10090900 };
constexpr uint32_t kRoundState = 0x1009322C;   /* the round's state machine (read for the log: 17 in Practice, rewritten every frame) */
/* the dummy's character, for its recordings' file: the fighter objects (df_costume.cpp kTocFighters), +0x40 the
 * item character index 0..34 (set by the game mode's set-up; read once the fight runs) */
constexpr uint32_t kTocFighters = 0x0046EE20;
constexpr uint32_t kFighterItemChar = 0x40;

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
 * units away moved another 1,273 in the next frame). put_place moves all of
 * them alike. The facing is the game's own: an angle written to all of them is
 * undone by the animation in the next frame, so a fighter left facing away is
 * turned with a tap on its pad instead (t5_practice_pads). */
constexpr uint32_t kPosX = 0x10, kPosZ = 0x18, kAngle = 0x30, kRootX = 0x24, kRootAngle = 0x84;   /* root z: kRootX + 8 */
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
    s.stand    = mv == 0x8001;
    return s;
}

/* ---- settings and state ----------------------------------------------------------- */
struct Cfg {
    bool on = false;
    bool offline = false;     /* started without netplay, replay or spectating */
    bool menu = true;         /* START opens the practice menu (T5_PRACTICE_MENU=0: the game's pause menu) */
    DummyMode dummy0 = DummyMode::Game;
    std::string dir = "practice";   /* T5_PRACTICE_DIR ("" = keep nothing) */
    FILE* log = nullptr;
} g_cfg;
bool g_init = false;

Combo g_combo;
Dummy g_dummy;
Recorder g_rec;
Placer g_placer;
ResetGate g_gate;             /* a reset waits until both fighters stand (training_logic.h ResetGate) */
constexpr int kSetQuickRecovery = 8;   /* the Practice menu's TRAINING DUMMY "quick recovery": while a reset waits */
Place g_start[2];             /* both places at the first frame of the fight: SELECT+3 goes back there */
Settings g_set;               /* the practice menu's settings (g_set.dummy: the dummy's behaviour) */
practice::Menu g_menu;
practice::Latch g_latch;      /* P1 hidden from the game until its pad is neutral, after the menu */
practice::InputDelay g_delay;
practice::CounterAttack g_counter;
Place g_remembered[2];        /* SELECT+START / REMEMBER THIS POSITION */
bool g_have_remembered = false;
bool g_start_pending = false; /* GAME'S PAUSE MENU: a START tap once P1's pad is neutral */
int g_start_tap = 0;
bool g_clear_armed = false;
bool g_menu_restart = false;  /* RESTART NOW: a SELECT+3 for the next frame (through the reset gate) */
bool g_back_turn = false;     /* the last restart leaves the dummy back turned: P1 goes behind it (at g_face_at) */
int g_char = -1;              /* the dummy's item character whose recordings are loaded (-1: none) */
uint16_t g_prev_raw = 0;      /* P1's pad last frame (START's edge) */
Recorder::State g_prev_rec = Recorder::State::Idle;
char g_msg[64] = "";          /* a status line of its own for 2 s ("" = the slot line) */
bool g_in_practice = false;
int g_prev_hp = 0;
uint64_t g_frame = 0;
uint64_t g_msg_until = 0;     /* the status line shows the last change this long */
uint64_t g_check_at = 0;      /* T5_PRACTICE_LOG: the places again 30 frames after a reset (tests) */
/* After a reset the game keeps each fighter's own facing (an angle written to it is
 * undone by the animation); a fighter that ended up with its back to the other one
 * turns at its next move. So two frames after a reset a fighter facing away gets a
 * tap toward the other one on its pad (the dummy on CONTROLLER for it). */
uint64_t g_face_at = 0;       /* the frame to look at the facings */
int g_nudge[2] = { 0, 0 };    /* frames of the tap still to give, per fighter */
/* The tap turns the fighter and takes it a step forward (traced: ~300 units); once both
 * have turned, they go back to the places the reset gave them, as they face now. */
Place g_target[2];            /* the places of the last reset */
uint64_t g_replace_at = 0;
bool g_no_wall = false;      /* the status line says that the last wall reset found no wall */

void init()
{
    g_init = true;
    const char* e = getenv("T5_PRACTICE");
    g_cfg.on = e && *e == '1';
    const char* nm = getenv("T5_NET_MODE");
    const char* ctl = getenv("T5_CTL_DIR");
    const char* rp = getenv("T5_REPLAY_FILE");
    g_cfg.offline = !(nm && *nm) && !(ctl && *ctl) && !(rp && *rp);
    if (const char* d = getenv("T5_PRACTICE_DUMMY")) practice::dummy_from_key(d, &g_cfg.dummy0);
    if (const char* m = getenv("T5_PRACTICE_MENU"); m && *m == '0') g_cfg.menu = false;
    if (const char* d = getenv("T5_PRACTICE_DIR")) g_cfg.dir = strcmp(d, "-") ? d : "";
    if (const char* f = getenv("T5_PRACTICE_LOG"); f && *f) g_cfg.log = fopen(f, "w");
    if (g_cfg.on)
        fprintf(stderr, "[practice] tools on (Practice, offline): SELECT combos%s, dummy %s%s\n",
                g_cfg.menu ? ", START menu" : "", practice::dummy_key(g_cfg.dummy0),
                g_cfg.offline ? "" : " -- not in this game (started for online play, a replay or spectating)");
}

void note(const char* fmt, ...)
{
    if (!g_cfg.log) return;
    fprintf(g_cfg.log, "%llu ", (unsigned long long)g_frame);
    va_list ap;
    va_start(ap, fmt);
    vfprintf(g_cfg.log, fmt, ap);
    va_end(ap);
    fputc('\n', g_cfg.log);
    fflush(g_cfg.log);
}

/* ---- files: T5_PRACTICE_DIR/settings.txt and char<NN>.txt (host files only) ----------- */
std::string path_of(const char* name) { return g_cfg.dir.empty() ? std::string() : g_cfg.dir + "/" + name; }
bool make_dir()
{
    if (g_cfg.dir.empty()) return false;
#if defined(_WIN32)
    _mkdir(g_cfg.dir.c_str());
#else
    mkdir(g_cfg.dir.c_str(), 0755);
#endif
    return true;
}
std::string read_file(const std::string& p)
{
    std::string out;
    if (p.empty()) return out;
    FILE* f = fopen(p.c_str(), "rb");
    if (!f) return out;
    char b[4096];
    size_t n;
    while ((n = fread(b, 1, sizeof b, f)) > 0 && out.size() < (1u << 20)) out.append(b, n);
    fclose(f);
    return out;
}
/* written to a .tmp first, then put in place: a crash never leaves half a file */
template <class F> bool write_file(const std::string& p, F body)
{
    if (p.empty() || !make_dir()) return false;
    const std::string tmp = p + ".tmp";
    FILE* f = fopen(tmp.c_str(), "wb");
    if (!f) return false;
    body(f);
    const bool ok = fclose(f) == 0;
    if (ok) { remove(p.c_str()); if (rename(tmp.c_str(), p.c_str()) == 0) return true; }
    remove(tmp.c_str());
    return false;
}
void load_settings()
{
    const std::string t = read_file(path_of("settings.txt"));
    if (!t.empty()) practice::parse_settings(t.c_str(), &g_set);
}
void save_settings()
{
    write_file(path_of("settings.txt"), [](FILE* f) { practice::write_settings(f, g_set); });
}
std::string char_file(int c) { char n[32]; snprintf(n, sizeof n, "char%02d.txt", c); return path_of(n); }
int dummy_char()
{
    const uint32_t arr = rd32(kTocFighters);
    if (arr < 0x10000u || arr >= 0xF0000000u) return -1;
    const uint32_t obj = rd32(arr + 4);
    if (obj < 0x10000000u || obj >= 0xD0000000u) return -1;
    const int c = (int16_t)rd16(obj + kFighterItemChar);
    return c >= 0 && c < 35 ? c : -1;
}
void save_slots()
{
    if (g_char < 0) return;
    const bool ok = write_file(char_file(g_char), [](FILE* f) { practice::write_slots(f, g_rec); });
    note("slots saved for character %d: %d recorded%s", g_char, g_rec.recorded(), ok ? "" : " (not written)");
}
void load_slots(int c)
{
    g_rec.clear_all();
    g_char = c;
    if (c < 0) return;
    const std::string t = read_file(char_file(c));
    const bool ok = !t.empty() && practice::parse_slots(t.c_str(), &g_rec);
    note("slots for character %d: %d recorded%s", c, ok ? g_rec.recorded() : 0, ok ? "" : " (no file)");
}
void say(const char* s) { snprintf(g_msg, sizeof g_msg, "%s", s); g_msg_until = g_frame + 120; g_no_wall = false; }

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

/* T5_PRACTICE_LOG only: what each fighter does around a reset (height of the base +0x14, the move +0x168, its
 * class +0x15C, can act) -- the evidence for "keeps flying / turned around after a reset" */
uint64_t g_trace_from = 0;
void note_state(const char* what)
{
    if (!g_cfg.log) return;
    fprintf(g_cfg.log, "%llu %s round %u phase %u", (unsigned long long)g_frame, what, rd32(kRoundState), rd32(kPhase));
    for (int p = 0; p < 2; p++) {
        const uint32_t b = kFighter[p];
        const Sample s = read_fighter(b);
        fprintf(g_cfg.log, " %s y %.1f hips %.1f move %08X class %08X act %d right %d", p ? "dummy" : "P1", rdf(b + 0x14),
                rdf(b + 0x734), rd32(b + 0x168), s.cls, s.can_act ? 1 : 0, s.right ? 1 : 0);
    }
    fputc('\n', g_cfg.log);
    fflush(g_cfg.log);
}

/* The Practice menu's TRAINING DUMMY: a behaviour sets it (want >= 0) and keeps the
 * player's own choice, which comes back with want -1 (and while the menu is open) */
int g_saved_setting = -1;
void put_low_byte(uint32_t word, int v)
{
    const uint32_t w = rd32(word);
    if ((int)(w & 0xFF) != v) put32(word, (w & ~0xFFu) | (uint32_t)v);
}
void set_dummy(int v)
{
    put_low_byte(kDummySetting, v);
    for (uint32_t a : kDummyApplied) put_low_byte(a, v);
}
void apply_setting(int want)
{
    const int cur = (int)(rd32(kDummySetting) & 0xFF);
    if (want < 0) {
        if (g_saved_setting >= 0 && cur != g_saved_setting) {
            set_dummy(g_saved_setting);
            note("training dummy setting %d (the player's)", g_saved_setting);
        }
        g_saved_setting = -1;
        return;
    }
    if (g_saved_setting < 0) g_saved_setting = cur;
    if (cur != want) {
        set_dummy(want);
        note("training dummy setting %d", want);
    }
}

/* the restart (SELECT+3, RESTART NOW): where the menu's RESTART AT says, the sides switched when asked */
void restart_now()
{
    Place out[2];
    if (!practice::restart_places(g_set.restart, g_set.switched, g_start, g_remembered, g_have_remembered, out)) {
        /* a wall: the wall reset of that kind */
        Place probe;
        int mover;
        const PAction w = practice::restart_action(g_set.restart);
        if (g_placer.start(w, read_place(0), read_place(1), &mover, &probe)) {
            note_place("wall probe from:");
            put_place(mover, probe);
        }
        g_back_turn = g_set.back_turned && (w == PAction::PlayerWallFront || w == PAction::PlayerWallBack);
        return;
    }
    g_placer.cancel();
    note_state("before reset:");
    g_trace_from = g_frame;
    put_place(0, out[0]);
    put_place(1, out[1]);
    g_target[0] = out[0];
    g_target[1] = out[1];
    note_place(g_set.restart == Restart::Remembered && g_have_remembered ? "reset remembered:" : "reset round start:");
    g_check_at = g_frame + 30;
    g_face_at = g_frame + 2;
    g_back_turn = g_set.back_turned;
}

void act(PAction a)
{
    g_no_wall = false;
    g_msg[0] = 0;
    switch (a) {
    case PAction::ResetRound:
        restart_now();
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
        g_back_turn = false;
        break; }
    case PAction::Record: g_rec.toggle_record(); note("record slot %d", g_rec.slot() + 1); break;
    case PAction::Play: g_rec.toggle_play(false); note("play slot %d", g_rec.play_slot() + 1); break;
    case PAction::Loop: g_rec.toggle_play(true); note("loop slot %d", g_rec.play_slot() + 1); break;
    case PAction::SlotNext: g_rec.select(1); note("slot %d", g_rec.slot() + 1); break;
    case PAction::SlotPrev: g_rec.select(-1); note("slot %d", g_rec.slot() + 1); break;
    case PAction::DummyNext:
    case PAction::DummyPrev: {
        const int n = (int)DummyMode::Count, d = a == PAction::DummyNext ? 1 : n - 1;
        g_set.dummy = (DummyMode)(((int)g_set.dummy + d) % n);
        note("dummy %s", practice::dummy_key(g_set.dummy));
        break; }
    case PAction::RememberPos:
        g_remembered[0] = read_place(0);
        g_remembered[1] = read_place(1);
        g_have_remembered = true;
        g_set.restart = Restart::Remembered;
        save_settings();
        note_place("remembered:");
        say("POSITION REMEMBERED: SELECT+3 RESTARTS HERE");
        break;
    default: break;
    }
    g_msg_until = g_frame + 120;
}

/* one menu event (practice_logic.h Menu) */
void menu_event(const practice::Menu::Event& e)
{
    using practice::Menu;
    if (e.ev == Menu::Ev::None) return;
    if (e.item != practice::I_CLEAR || e.ev != Menu::Ev::Activate) g_clear_armed = false;
    if (e.ev == Menu::Ev::Close) {
        note("menu closed");
        save_settings();
        g_latch.set();
        return;
    }
    if (e.ev == Menu::Ev::Moved) { note("menu at %s", practice::item_label(e.item)); return; }
    if (e.ev == Menu::Ev::Change) {
        int disp = t5_training_display_get();
        const int was = disp;
        if (practice::adjust(e.item, e.delta, &g_set, &g_rec, &disp)) {
            char v[64];
            practice::View view;
            view.s = &g_set; view.rec = &g_rec; view.display = disp; view.remembered = g_have_remembered;
            practice::item_value(e.item, view, v, sizeof v);
            note("menu %s: %s", practice::item_label(e.item), v);
            if (disp != was) t5_training_display_set(disp);
            if (e.item == practice::I_COUNTER || e.item == practice::I_COUNTER_EVERY) g_counter.reset();
        }
        return;
    }
    /* actions */
    note("menu %s", practice::item_label(e.item));
    switch (e.item) {
    case practice::I_RECORD:
    case practice::I_PLAY:
    case practice::I_LOOP: {
        /* starts when the menu has closed and the pad is neutral (the record button is no attack) */
        g_menu.hide();
        g_latch.set();
        save_settings();
        act(e.item == practice::I_RECORD ? PAction::Record : e.item == practice::I_PLAY ? PAction::Play : PAction::Loop);
        break; }
    case practice::I_CLEAR:
        if (!g_clear_armed) { g_clear_armed = true; break; }
        g_clear_armed = false;
        g_rec.clear(g_rec.slot());
        save_slots();
        note("slot %d deleted", g_rec.slot() + 1);
        break;
    case practice::I_REMEMBER:
        g_menu.hide();
        g_latch.set();
        act(PAction::RememberPos);
        break;
    case practice::I_RESTART_NOW:
        g_menu.hide();
        g_latch.set();
        save_settings();
        g_menu_restart = true;
        break;
    case practice::I_GAME_MENU:
        g_menu.hide();
        g_latch.set();
        save_settings();
        g_start_pending = true;
        break;
    case practice::I_CLOSE:
        g_menu.hide();
        g_latch.set();
        save_settings();
        note("menu closed");
        break;
    default: break;
    }
}

} // namespace

/* t5_hooks.cpp keyread_tick, offline only: P1's (port 0) and P2's (port 1)
 * masks for the frame about to run, before they go into the game's input ring. */
extern "C" void t5_practice_pads(uint16_t* p1, uint16_t* p2)
{
    if (!g_init) init();
    if (!g_cfg.on) return;
    if (!allowed()) {
        if (g_in_practice) {
            /* the player's own TRAINING DUMMY back -- only while this is still offline Practice */
            if (g_cfg.offline && t5_netplay_enabled() == 0 && rd32(kGameType) == kGtPractice) apply_setting(-1);
            g_saved_setting = -1;
            const bool was_recording = g_rec.state() == Recorder::State::Recording;
            if (was_recording) { g_rec.toggle_record(); save_slots(); }   /* keep what was recorded */
            g_combo.reset(); g_dummy.reset(); g_rec.stop(); g_gate.cancel(); g_in_practice = false;
            g_menu.hide(); g_latch = practice::Latch{}; g_delay.reset(); g_counter.reset();
            g_start_pending = false; g_start_tap = 0; g_have_remembered = false; g_back_turn = false; g_menu_restart = false;
            g_prev_rec = Recorder::State::Idle;
        }
        return;
    }
    if (rd8(kRunning) != 1) {       /* the pause menu: nothing injected, the player's own TRAINING DUMMY shown */
        apply_setting(-1);
        g_prev_raw = *p1;
        g_start_tap = 0;
        g_menu.hide();
        return;
    }
    if (!g_in_practice) {
        g_in_practice = true;
        g_set = Settings{};
        load_settings();
        g_set.dummy = g_cfg.dummy0;
        g_prev_hp = 0;
        g_placer.cancel();
        g_gate.cancel();
        g_start[0] = read_place(0);
        g_start[1] = read_place(1);
        g_prev_raw = *p1;
        if (g_set.restart == Restart::Remembered) g_set.restart = Restart::RoundStart;   /* nothing remembered yet */
        const int c = dummy_char();
        if (c != g_char) load_slots(c);
        g_rec.set_rng((uint32_t)(uintptr_t)&g_frame ^ (uint32_t)rd32(kFighter[0] + kPosX));
        note("practice, dummy %s", practice::dummy_key(g_set.dummy));
        note_place("round start:");
        note_state("practice start:");
    }
    g_frame++;
    if (g_placer.pending()) {       /* a wall reset: the game has run a frame from the mover's last place */
        const Placer::Cmd c = g_placer.next(read_place(g_placer.mover()));
        if (c.done) {
            put_place(0, c.out[0]);
            put_place(1, c.out[1]);
            g_target[0] = c.out[0];
            g_target[1] = c.out[1];
            note_place(c.wall ? "wall:" : "no wall there, back to:");
            if (!c.wall) { g_no_wall = true; g_msg[0] = 0; g_msg_until = g_frame + 120; g_back_turn = false; }
            g_check_at = g_frame + 30;
            g_face_at = g_frame + 2;
        } else {
            put_place(g_placer.mover(), c.mover);
            put_place(1 - g_placer.mover(), c.other);
        }
    }
    if (g_check_at && g_frame == g_check_at) { g_check_at = 0; note_place("30 frames later:"); }
    if (g_cfg.log && g_frame % 30 == 0) note_place("places:");   /* tests: the dummy's movement loops */
    if (g_trace_from) {
        const uint64_t k = g_frame - g_trace_from;
        if (k == 1 || k == 3 || k == 8 || k == 15 || k == 30 || k == 60 || k == 120 || k == 240) note_state("after reset:");
        if (k >= 240) g_trace_from = 0;
    }
    if (g_face_at && g_frame == g_face_at) {
        g_face_at = 0;
        if (g_back_turn) {
            /* back turned: the dummy keeps the facing the game gave it; P1 goes behind its back, as far as the
             * restart put them apart, and turns to it */
            g_back_turn = false;
            const Place d = read_place(1), me = read_place(0);
            const float dist = sqrtf((d.x - me.x) * (d.x - me.x) + (d.z - me.z) * (d.z - me.z));
            Place b = practice::behind(d, dist > 400.0f ? dist : 1100.0f);
            b.angle = me.angle;
            put_place(0, b);
            g_target[0] = b;
            g_target[1] = d;
            note_place("back turned:");
            const Place pl0 = read_place(0);
            float dd = pl0.angle - face_toward(pl0.x, pl0.z, d.x, d.z);
            while (dd > 3.14159265f) dd -= 6.28318531f;
            while (dd < -3.14159265f) dd += 6.28318531f;
            if (fabsf(dd) > 1.2f) {
                g_nudge[0] = 2;
                g_replace_at = g_frame + 24;
                note("P1 faces away: a tap toward the dummy");
            }
        } else {
            const Place pl[2] = { read_place(0), read_place(1) };
            for (int p = 0; p < 2; p++) {
                float d = pl[p].angle - face_toward(pl[p].x, pl[p].z, pl[1 - p].x, pl[1 - p].z);
                while (d > 3.14159265f) d -= 6.28318531f;
                while (d < -3.14159265f) d += 6.28318531f;
                if (fabsf(d) > 1.2f) {
                    g_nudge[p] = p ? 6 : 2;
                    g_replace_at = g_frame + 24;
                    note(p ? "dummy faces away: a tap toward P1" : "P1 faces away: a tap toward the dummy");
                }
            }
        }
    }
    if (g_replace_at && g_frame == g_replace_at) {   /* turned: back to the reset's places, facing as now */
        g_replace_at = 0;
        for (int p = 0; p < 2; p++) {
            Place t = g_target[p];
            t.angle = read_place(p).angle;
            put_place(p, t);
        }
        note_place("after the turn, back to:");
    }
    const Sample me = read_fighter(kFighter[0]), dm = read_fighter(kFighter[1]);
    if (!g_prev_hp) g_prev_hp = dm.hp;
    const uint16_t raw = *p1;
    const uint16_t prev_raw = g_prev_raw;
    g_prev_raw = raw;

    /* the practice menu (START): the fight goes on behind it, both pads neutral */
    if (g_menu.open()) {
        menu_event(g_menu.frame(raw));
        if (g_menu.open()) {
            *p1 = 0;
            *p2 = 0;
            g_delay.frame(0, g_set.delay);
            apply_setting(g_dummy.setting(g_set.dummy));
            g_prev_hp = dm.hp;
            return;
        }
    } else if (g_cfg.menu && (raw & kStart) && !(prev_raw & kStart) && !(raw & kSelect) && !g_latch.on() &&
               !g_start_pending && !g_start_tap) {
        if (g_rec.state() == Recorder::State::Recording) g_rec.toggle_record();
        g_rec.stop();
        g_counter.reset();
        g_menu.show(raw);
        g_clear_armed = false;
        note("menu opened");
        *p1 = 0;
        *p2 = 0;
        g_delay.frame(0, g_set.delay);
        apply_setting(g_dummy.setting(g_set.dummy));
        g_prev_hp = dm.hp;
        return;
    }
    const bool latched = g_latch.frame(raw);
    /* GAME'S PAUSE MENU: once P1 let go of everything, a START tap of our own opens the game's menu */
    if (g_start_pending && !latched && !raw) { g_start_pending = false; g_start_tap = 3; note("the game's pause menu"); }
    if (g_start_tap > 0) {
        g_start_tap--;
        *p1 = kStart;
        *p2 = 0;
        g_delay.frame(0, g_set.delay);
        g_prev_hp = dm.hp;
        return;
    }

    bool hide = false;
    PAction a = g_combo.frame(latched ? 0 : raw, me.right, &hide);
    if (a == PAction::None && g_menu_restart) a = PAction::ResetRound;
    g_menu_restart = false;
    const bool is_reset = a == PAction::ResetRound || a == PAction::DummyWallFront || a == PAction::DummyWallBack ||
                          a == PAction::PlayerWallFront || a == PAction::PlayerWallBack;
    if (is_reset) {
        /* the reset waits until both fighters stand (after a launcher the dummy would keep flying / lie at its new
         * place, a fighter in a move would leave it, and the facing tap needs fighters that can act) */
        const PAction now = g_gate.request(a, me, dm);
        if (now != PAction::None) act(now);
        else {
            note_state("reset waits until both stand:");
            g_msg[0] = 0;
            g_msg_until = g_frame + 120;
            g_no_wall = false;
        }
    } else if (a != PAction::None) act(a);
    bool late = false;
    if (!is_reset) {
        const PAction d = g_gate.frame(me, dm, &late);
        if (d != PAction::None) {
            note("reset after waiting %u frames%s", g_gate.waited(), late ? " (they did not stand: anyway)" : "");
            act(d);
        }
    }
    if (latched) hide = true;
    const bool waiting = g_gate.waiting();
    if (hide || waiting) *p1 = 0;      /* while a reset waits: P1's pad neutral (no juggle goes on) */
    /* the input delay (menu SETTINGS): what reaches the game for P1, as an online match with that delay plays */
    const uint16_t undelayed = *p1;
    *p1 = g_delay.frame(*p1, g_set.delay);
    if (g_cfg.log && g_set.delay) {      /* tests: a SQUARE press and when it reaches the game */
        static uint16_t prev_in = 0, prev_out = 0;
        if ((undelayed & kSquare) && !(prev_in & kSquare)) note("delay %d: square pressed", g_set.delay);
        if ((*p1 & kSquare) && !(prev_out & kSquare)) note("delay %d: square reaches the game", g_set.delay);
        prev_in = undelayed;
        prev_out = *p1;
    }
    if (g_nudge[0] > 0) { g_nudge[0]--; *p1 = me.right ? kLeft : kRight; }   /* toward the dummy on the screen */

    /* the dummy: recording (your pad plays it), a recording, its counter-attack, its behaviour, or the game's own */
    g_rec.set_random(g_set.random_play);
    if (waiting) {
        *p2 = 0;                        /* the dummy neutral, a recording paused; the game's quick recovery below */
    } else if (g_rec.state() == Recorder::State::Recording) {
        /* Your pad controls the dummy directly: store forward/back using its current
         * side, not P1's. Decoding with that same side preserves the live pad direction. */
        const uint16_t rel = hide ? 0 : to_rel((uint16_t)(raw & ~(kSelect | kStart)), dm.right);
        g_rec.record(rel);
        *p2 = from_rel(rel, dm.right);
        *p1 = 0;
    } else {
        uint16_t rel;
        if (g_rec.next(&rel)) *p2 = from_rel(rel, dm.right);
        else if (g_counter.frame(g_set.counter, g_set.counter_every, me, dm, g_prev_hp) &&
                 g_rec.play_once(g_set.counter_slot - 1) && g_rec.next(&rel)) {
            note("counter-attack after a %s: slot %d", g_counter.last_was_hit() ? "hit" : "block", g_rec.play_slot() + 1);
            *p2 = from_rel(rel, dm.right);
        }
        else if (g_set.dummy != DummyMode::Game) *p2 = g_dummy.frame(g_set.dummy, dm, g_prev_hp);
    }
    /* a recording that just stopped is kept on disk for this character */
    if (g_prev_rec == Recorder::State::Recording && g_rec.state() != Recorder::State::Recording) save_slots();
    g_prev_rec = g_rec.state();
    const bool tap2 = g_nudge[1] > 0;     /* CONTROLLER for 6 frames, the tap in the last 3 */
    if (tap2) { if (g_nudge[1] <= 3) *p2 = dm.right ? kLeft : kRight; g_nudge[1]--; }   /* toward P1 on the screen */
    /* the game's own TRAINING DUMMY for the behaviour: CONTROLLER (P2's pad) for a recording, the pad
     * behaviours and a tap */
    apply_setting(waiting ? kSetQuickRecovery
                  : g_rec.state() != Recorder::State::Idle || tap2 ? (int)Dummy::kSetController : g_dummy.setting(g_set.dummy));
    g_prev_hp = dm.hp;
}

/* training.cpp: the practice status line (empty: nothing to show) */
extern "C" int t5_practice_status(char* out, unsigned n, int de)
{
    out[0] = 0;
    if (!g_cfg.on || !g_in_practice) return 0;
    static const char* en_modes[] = { "GAME", "BLOCK AFTER HIT", "CROUCH", "WALK", "STEP", "DASH", "BACKDASH",
                                      "BACKDASH CANCEL", "WAVEDASH" };
    static const char* de_modes[] = { "SPIEL", "BLOCKT NACH TREFFER", "DUCKT", "GEHT", "SEITSCHRITT", "DASH", "BACKDASH",
                                      "BACKDASH-CANCEL", "WAVEDASH" };
    const char* mode = (de ? de_modes : en_modes)[(int)g_set.dummy];
    const int slot = g_rec.slot() + 1;
    if (g_menu.open()) return 0;
    switch (g_rec.state()) {
    case Recorder::State::Recording:
        snprintf(out, n, "REC %d  %.1fs", slot, g_rec.length(g_rec.slot()) / 60.0);
        return 1;
    case Recorder::State::Playing:
    case Recorder::State::Looping:
        snprintf(out, n, "%s %d  %.1f/%.1fs", g_rec.state() == Recorder::State::Looping ? "LOOP" : "PLAY", g_rec.play_slot() + 1,
                 g_rec.pos() / 60.0, g_rec.length(g_rec.play_slot()) / 60.0);
        return 1;
    default: break;
    }
    if (g_gate.waiting()) {
        snprintf(out, n, "%s", de ? "RESET, SOBALD BEIDE STEHEN" : "RESET WHEN BOTH STAND");
        return 1;
    }
    if (g_frame < g_msg_until && g_no_wall) {
        snprintf(out, n, "%s", de ? "KEINE WAND IN DIESER RICHTUNG" : "NO WALL THAT WAY");
        return 1;
    }
    if (g_frame < g_msg_until && g_msg[0]) {
        snprintf(out, n, "%s", g_msg);
        return 1;
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

extern "C" int t5_practice_menu_open(void)
{
    return g_cfg.on && g_in_practice && g_menu.open() ? 1 : 0;
}

/* training.cpp publish(), between rsx_overlay_begin and _end, while the menu is open: the menu panel
 * (canvas 1280 x 720, our own 5 x 7 font; texts in English like the overlay's own) */
extern "C" void t5_practice_menu_draw(void)
{
    if (!t5_practice_menu_open()) return;
    constexpr float kPx = 2.0f, kRow = 22.0f, kHead = 28.0f, kW = 660.0f, kX = 640.0f - kW / 2;
    const uint32_t panel = RSX_OVL_RGBA(8, 10, 18, 248), gold = RSX_OVL_RGBA(255, 214, 72, 255),
                   white = RSX_OVL_RGBA(240, 240, 240, 255), grey = RSX_OVL_RGBA(150, 150, 160, 255),
                   sel = RSX_OVL_RGBA(52, 58, 92, 255), cyan = RSX_OVL_RGBA(130, 200, 255, 255);
    int heads = 0;
    for (int i = 0; i < practice::I_COUNT; i++) heads += practice::section_at(i)[0] ? 1 : 0;
    const float h = 50.0f + kRow * (float)practice::I_COUNT + kHead * (float)heads + 34.0f;
    const float y0 = (720.0f - h) / 2;
    rsx_overlay_rect(kX, y0, kW, h, panel);
    rsx_overlay_rect(kX, y0, kW, 4, gold);
    rsx_overlay_text(kX + 20, y0 + 16, 3.0f, gold, RSX_OVL_SHADOW, "PRACTICE");
    rsx_overlay_text(kX + kW - 20, y0 + 22, kPx, grey, RSX_OVL_RIGHT, "START / 4: CLOSE");
    practice::View view;
    view.s = &g_set; view.rec = &g_rec; view.display = t5_training_display_get();
    view.remembered = g_have_remembered; view.clear_armed = g_clear_armed;
    float y = y0 + 50.0f;
    for (int i = 0; i < practice::I_COUNT; i++) {
        const char* sec = practice::section_at(i);
        if (sec[0]) {
            rsx_overlay_text(kX + 20, y + 8, kPx, cyan, RSX_OVL_SHADOW, sec);
            rsx_overlay_rect(kX + 20, y + 25, kW - 40, 1, RSX_OVL_RGBA(70, 80, 110, 255));
            y += kHead;
        }
        const bool cur = g_menu.cursor() == i;
        if (cur) rsx_overlay_rect(kX + 12, y - 3, kW - 24, kRow, sel);
        rsx_overlay_text(kX + 36, y, kPx, cur ? white : grey, RSX_OVL_SHADOW, practice::item_label(i));
        char v[64];
        practice::item_value(i, view, v, sizeof v);
        if (v[0]) {
            char shown[80];
            if (cur && !practice::is_action(i)) snprintf(shown, sizeof shown, "< %s >", v);
            else snprintf(shown, sizeof shown, "%s", v);
            rsx_overlay_text(kX + kW - 32, y, kPx, cur ? gold : white, RSX_OVL_RIGHT | RSX_OVL_SHADOW, shown);
        }
        y += kRow;
    }
    rsx_overlay_text(640.0f, y + 10, kPx, grey, RSX_OVL_CENTER,
                     "UP/DOWN CHOOSE   LEFT/RIGHT CHANGE   3 SELECT");
}
