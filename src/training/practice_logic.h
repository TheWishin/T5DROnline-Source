/*
 * T5DR practice suite (1.2.1; docs/TRAINING.md "Practice menu"): the in-game
 * practice menu, the dummy's counter-attack, P1's simulated input delay, the
 * restart positions and the files the recordings and settings are kept in.
 *
 * No game, no screen, no guest memory: practice.cpp reads the game, feeds this
 * and draws the menu; tests/c/practice_test.cpp drives it frame by frame.
 * Everything here works on the game's pad masks (training_logic.h) and Samples.
 */
#pragma once
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>

#include "training_logic.h"

namespace practice {

using namespace training;

/* ---- settings ---------------------------------------------------------------------- */
enum class Counter : uint8_t { Off, AfterBlock, AfterHit, Either, Count };
enum class Restart : uint8_t { RoundStart, Remembered, DummyWallFront, DummyWallBack, PlayerWallFront, PlayerWallBack, Count };

struct Settings {
    DummyMode dummy = DummyMode::Game;
    Counter counter = Counter::Off;
    int counter_every = 1;      /* the counter-attack comes after every Nth block / hit (1..5) */
    int counter_slot = 0;       /* 0: a random recorded slot, 1..8: that slot */
    bool random_play = false;   /* Play / Loop take a random recorded slot */
    Restart restart = Restart::RoundStart;
    bool switched = false;      /* the restart puts P1 where the dummy started and the dummy where P1 started */
    bool back_turned = false;   /* the restart leaves the dummy with its back to P1 */
    int delay = 0;              /* P1's input reaches the game this many frames later (0..6) */
};
constexpr int kMaxDelay = 6;
constexpr int kMaxEvery = 5;

/* the keys of the settings file and T5_PRACTICE_DUMMY (practice.cpp kModeKey is this list) */
inline const char* dummy_key(DummyMode m)
{
    static const char* k[] = { "game", "block", "crouch", "walk", "step", "dash", "backdash", "kbd", "wavedash" };
    return (int)m < (int)(sizeof k / sizeof k[0]) ? k[(int)m] : "game";
}
inline bool dummy_from_key(const char* s, DummyMode* out)
{
    for (int i = 0; i < (int)DummyMode::Count; i++)
        if (!strcmp(s, dummy_key((DummyMode)i))) { *out = (DummyMode)i; return true; }
    return false;
}
inline const char* restart_key(Restart r)
{
    static const char* k[] = { "start", "remembered", "dummy_wall_front", "dummy_wall_back", "wall_front", "wall_back" };
    return (int)r < (int)Restart::Count ? k[(int)r] : "start";
}
inline const char* counter_key(Counter c)
{
    static const char* k[] = { "off", "block", "hit", "either" };
    return (int)c < (int)Counter::Count ? k[(int)c] : "off";
}

/* the settings file (T5_PRACTICE_DIR/settings.txt): "key value" lines; unknown keys and bad values are skipped.
 * The dummy's behaviour is not in it: the launcher's T5_PRACTICE_DUMMY says how it starts. */
inline void write_settings(FILE* f, const Settings& s)
{
    fprintf(f, "T5DR practice settings 1\n");
    fprintf(f, "counter %s\ncounter_every %d\ncounter_slot %d\nrandom_play %d\nrestart %s\nswitched %d\n"
               "back_turned %d\ndelay %d\n",
            counter_key(s.counter), s.counter_every, s.counter_slot, s.random_play ? 1 : 0, restart_key(s.restart),
            s.switched ? 1 : 0, s.back_turned ? 1 : 0, s.delay);
}
inline void parse_settings(const char* text, Settings* s)
{
    if (strncmp(text, "T5DR practice settings 1", 24) != 0) return;
    const char* p = text;
    while ((p = strchr(p, '\n')) != nullptr) {
        p++;
        char key[32] = "", val[32] = "";
        if (sscanf(p, "%31s %31s", key, val) != 2) continue;
        const int n = atoi(val);
        if (!strcmp(key, "counter")) {
            for (int i = 0; i < (int)Counter::Count; i++) if (!strcmp(val, counter_key((Counter)i))) s->counter = (Counter)i;
        } else if (!strcmp(key, "counter_every")) { if (n >= 1 && n <= kMaxEvery) s->counter_every = n; }
        else if (!strcmp(key, "counter_slot")) { if (n >= 0 && n <= Recorder::kSlots) s->counter_slot = n; }
        else if (!strcmp(key, "random_play")) s->random_play = n == 1;
        else if (!strcmp(key, "restart")) {
            /* "remembered" needs a place remembered in this game: a restart that starts there reads the round start */
            for (int i = 0; i < (int)Restart::Count; i++) if (!strcmp(val, restart_key((Restart)i))) s->restart = (Restart)i;
        } else if (!strcmp(key, "switched")) s->switched = n == 1;
        else if (!strcmp(key, "back_turned")) s->back_turned = n == 1;
        else if (!strcmp(key, "delay")) { if (n >= 0 && n <= kMaxDelay) s->delay = n; }
    }
}

/* ---- recordings on disk (T5_PRACTICE_DIR/char<NN>.txt, one file per dummy character) ----
 * "T5DR practice recordings 1", then per recorded slot "slot <1..8> <frames>" and the frames as hex
 * masks (forward = toward the opponent), 20 to a line. */
inline void write_slots(FILE* f, const Recorder& r)
{
    fprintf(f, "T5DR practice recordings 1\n");
    for (int s = 0; s < Recorder::kSlots; s++) {
        const int n = r.length(s);
        if (!n) continue;
        fprintf(f, "slot %d %d\n", s + 1, n);
        const uint16_t* d = r.data(s);
        for (int i = 0; i < n; i++) fprintf(f, "%04X%c", d[i], (i % 20 == 19 || i == n - 1) ? '\n' : ' ');
    }
}
/* the slots of a file into r (the slots it does not name are empty); false: not such a file */
inline bool parse_slots(const char* text, Recorder* r)
{
    if (strncmp(text, "T5DR practice recordings 1", 26) != 0) return false;
    for (int s = 0; s < Recorder::kSlots; s++) r->clear(s);
    static uint16_t buf[Recorder::kMaxFrames];
    const char* p = text;
    while ((p = strstr(p, "\nslot ")) != nullptr) {
        p += 6;
        int s = 0, n = 0;
        if (sscanf(p, "%d %d", &s, &n) != 2 || s < 1 || s > Recorder::kSlots || n < 0) continue;
        const char* q = strchr(p, '\n');
        if (!q) break;
        q++;
        int k = 0;
        while (k < n && k < Recorder::kMaxFrames) {
            while (*q == ' ' || *q == '\n' || *q == '\r') q++;
            char* e;
            const unsigned long v = strtoul(q, &e, 16);
            if (e == q || v > 0xFFFF) break;
            buf[k++] = (uint16_t)v;
            q = e;
        }
        r->set(s - 1, buf, k);
        p = q;
    }
    return true;
}

/* ---- P1's input delay -----------------------------------------------------------------
 * What P1 presses reaches the game d frames later (0..6), as an online match with that
 * delay plays. Changing d starts over: the last mask for every frame in between. */
class InputDelay {
public:
    uint16_t frame(uint16_t in, int d)
    {
        if (d < 0) d = 0;
        if (d > kMaxDelay) d = kMaxDelay;
        if (d != d_) { for (uint16_t& m : ring_) m = last_; d_ = d; }
        last_ = in;
        ring_[w_ & 7] = in;
        const uint16_t out = ring_[(w_ - (uint32_t)d) & 7];
        w_++;
        return out;
    }
    void reset() { *this = InputDelay{}; }

private:
    uint16_t ring_[8] = {};
    uint16_t last_ = 0;
    uint32_t w_ = 0;
    int d_ = 0;
};

/* ---- the dummy's counter-attack ---------------------------------------------------------
 * After the dummy blocked or was hit (every Nth time), it plays a recording at the first
 * frame it can act again -- a reversal, the way a player would press it. A stun is the
 * dummy unable to act while P1 attacks (P1's attack class, +0x15C, 1..0xFFFF) or losing
 * health; it is a hit when health went or the reaction is a hit reaction (class >= 0x10000),
 * else a block. */
class CounterAttack {
public:
    /* every frame (me = P1, d = the dummy, prev_hp = its health a frame ago): true = start
     * the counter-attack now */
    bool frame(Counter when, int every, const Sample& me, const Sample& d, int prev_hp)
    {
        if (when == Counter::Off) { reset(); return false; }
        if (every < 1) every = 1;
        const bool dmg = d.hp < prev_hp;
        const bool p1_attacks = me.cls != 0 && me.cls < 0x10000;
        if (!in_stun_) {
            if (!acts(d) && (p1_attacks || dmg || d.cls >= 0x10000)) {
                in_stun_ = true;
                hit_ = dmg || d.cls >= 0x10000;
            }
            return false;
        }
        if (dmg || d.cls >= 0x10000) hit_ = true;
        if (!acts(d)) return false;
        in_stun_ = false;
        const bool counts = when == Counter::Either || (when == Counter::AfterHit) == hit_;
        last_hit_ = hit_;
        if (!counts) return false;
        if (++count_ < every) return false;
        count_ = 0;
        return true;
    }
    bool last_was_hit() const { return last_hit_; }
    int count() const { return count_; }
    bool in_stun() const { return in_stun_; }
    void reset() { *this = CounterAttack{}; }

private:
    bool in_stun_ = false, hit_ = false, last_hit_ = false;
    int count_ = 0;
};

/* ---- restart places ------------------------------------------------------------------------
 * Round start / remembered: both places, the sides switched when asked (P1 where the dummy
 * was, the dummy where P1 was; both then face away and get the facing tap, practice.cpp).
 * Walls: the Placer (training_logic.h) finds them; false here. */
inline bool restart_places(Restart r, bool switched, const Place start[2], const Place remembered[2], bool have_remembered,
                           Place out[2])
{
    const Place* src;
    if (r == Restart::RoundStart || (r == Restart::Remembered && !have_remembered)) src = start;
    else if (r == Restart::Remembered) src = remembered;
    else return false;
    out[0] = src[switched ? 1 : 0];
    out[1] = src[switched ? 0 : 1];
    return true;
}
inline PAction restart_action(Restart r)
{
    switch (r) {
    case Restart::DummyWallFront: return PAction::DummyWallFront;
    case Restart::DummyWallBack: return PAction::DummyWallBack;
    case Restart::PlayerWallFront: return PAction::PlayerWallFront;
    case Restart::PlayerWallBack: return PAction::PlayerWallBack;
    default: return PAction::ResetRound;
    }
}
/* Back turned: the dummy keeps its facing (the game's own; an angle written to it is undone),
 * so P1 goes behind it instead -- dist units behind its back, looking the way it looks (at its
 * back). */
inline Place behind(const Place& dummy, float dist)
{
    Place p;
    p.x = dummy.x - sinf(dummy.angle) * dist;
    p.z = dummy.z - cosf(dummy.angle) * dist;
    p.angle = dummy.angle;
    return p;
}

/* ---- the menu ------------------------------------------------------------------------------ */
enum Item : uint8_t {
    I_BEHAVIOUR, I_COUNTER, I_COUNTER_EVERY, I_COUNTER_WITH,
    I_SLOT, I_RECORD, I_PLAY, I_LOOP, I_RANDOM, I_CLEAR,
    I_RESTART, I_SIDES, I_FACING, I_REMEMBER, I_RESTART_NOW,
    I_DELAY, I_DISPLAY, I_GAME_MENU, I_CLOSE,
    I_COUNT
};
/* the section that starts at an item ("" = none) */
inline const char* section_at(int i)
{
    switch (i) {
    case I_BEHAVIOUR: return "DUMMY";
    case I_SLOT: return "RECORDING";
    case I_RESTART: return "RESTART";
    case I_DELAY: return "SETTINGS";
    default: return "";
    }
}
inline bool is_action(int i)
{
    return i == I_RECORD || i == I_PLAY || i == I_LOOP || i == I_CLEAR || i == I_REMEMBER || i == I_RESTART_NOW ||
           i == I_GAME_MENU || i == I_CLOSE;
}
inline const char* dummy_name(DummyMode m)
{
    static const char* n[] = { "AS SET IN THE GAME MENU", "BLOCK AFTER THE FIRST HIT", "CROUCH", "WALK FORWARD AND BACK",
                               "SIDESTEP", "DASH IN", "BACKDASH", "BACKDASH CANCEL", "WAVEDASH" };
    return (int)m < (int)DummyMode::Count ? n[(int)m] : "";
}
inline const char* restart_name(Restart r)
{
    static const char* n[] = { "ROUND START", "REMEMBERED POSITION", "DUMMY AT THE WALL AHEAD", "DUMMY AT THE WALL BEHIND",
                               "YOU AT THE WALL AHEAD", "YOU AT THE WALL BEHIND" };
    return (int)r < (int)Restart::Count ? n[(int)r] : "";
}

/* what the menu shows besides the settings (practice.cpp fills it each frame) */
struct View {
    const Settings* s = nullptr;
    const Recorder* rec = nullptr;
    int display = 2;            /* the training overlay: 0 off, 1 inputs, 2 inputs and frame data */
    bool remembered = false;    /* a position is remembered */
    bool clear_armed = false;   /* "delete": press again */
};

inline const char* item_label(int i)
{
    static const char* l[I_COUNT] = {
        "BEHAVIOUR", "COUNTER-ATTACK", "COUNTER EVERY", "COUNTER WITH",
        "SLOT", "RECORD", "PLAY ONCE", "PLAY IN A LOOP", "PLAYBACK", "DELETE THIS SLOT",
        "RESTART AT", "SIDES", "DUMMY FACING", "REMEMBER THIS POSITION", "RESTART NOW",
        "INPUT DELAY (YOU)", "TRAINING DISPLAY", "GAME'S PAUSE MENU", "CLOSE",
    };
    return i >= 0 && i < I_COUNT ? l[i] : "";
}

/* the value column of an item */
inline void item_value(int i, const View& v, char* out, size_t n)
{
    const Settings& s = *v.s;
    out[0] = 0;
    switch (i) {
    case I_BEHAVIOUR: snprintf(out, n, "%s", dummy_name(s.dummy)); break;
    case I_COUNTER: {
        static const char* c[] = { "OFF", "AFTER A BLOCK", "AFTER A HIT", "AFTER A BLOCK OR HIT" };
        snprintf(out, n, "%s", c[(int)s.counter]); break; }
    case I_COUNTER_EVERY:
        if (s.counter_every <= 1) snprintf(out, n, "EVERY TIME");
        else snprintf(out, n, "EVERY %d%s TIME", s.counter_every, s.counter_every == 2 ? "ND" : s.counter_every == 3 ? "RD" : "TH");
        break;
    case I_COUNTER_WITH:
        if (s.counter_slot == 0) snprintf(out, n, "A RANDOM RECORDED SLOT");
        else snprintf(out, n, "SLOT %d%s", s.counter_slot, v.rec && !v.rec->length(s.counter_slot - 1) ? " (EMPTY)" : "");
        break;
    case I_SLOT: {
        const int k = v.rec ? v.rec->slot() : 0, len = v.rec ? v.rec->length(k) : 0;
        if (len) snprintf(out, n, "%d  (%.1fS)", k + 1, len / 60.0);
        else snprintf(out, n, "%d  (EMPTY)", k + 1);
        break; }
    case I_RECORD: snprintf(out, n, "%s", v.rec && v.rec->state() == Recorder::State::Recording ? "STOP" : "YOU PLAY THE DUMMY"); break;
    case I_PLAY: snprintf(out, n, "%s", v.rec && v.rec->state() == Recorder::State::Playing ? "STOP" : ""); break;
    case I_LOOP: snprintf(out, n, "%s", v.rec && v.rec->state() == Recorder::State::Looping ? "STOP" : ""); break;
    case I_RANDOM: snprintf(out, n, "%s", s.random_play ? "A RANDOM RECORDED SLOT" : "THIS SLOT"); break;
    case I_CLEAR: snprintf(out, n, "%s", v.clear_armed ? "PRESS AGAIN TO DELETE" : ""); break;
    case I_RESTART:
        snprintf(out, n, "%s%s", restart_name(s.restart), s.restart == Restart::Remembered && !v.remembered ? " (NONE YET)" : "");
        break;
    case I_SIDES: snprintf(out, n, "%s", s.switched ? "SWITCHED" : "AS STARTED"); break;
    case I_FACING: snprintf(out, n, "%s", s.back_turned ? "BACK TURNED" : "FACING YOU"); break;
    case I_REMEMBER: snprintf(out, n, "SELECT+START"); break;
    case I_RESTART_NOW: snprintf(out, n, "SELECT+3"); break;
    case I_DELAY: snprintf(out, n, "%d FRAME%s", s.delay, s.delay == 1 ? "" : "S"); break;
    case I_DISPLAY: {
        static const char* d[] = { "OFF", "INPUTS", "INPUTS + FRAME DATA" };
        snprintf(out, n, "%s", d[v.display < 0 || v.display > 2 ? 0 : v.display]); break; }
    case I_GAME_MENU: snprintf(out, n, "COMMAND LIST, DUMMY"); break;
    default: break;
    }
}

/* one step of a setting (delta +1 / -1); returns true when it changed. display: the training
 * overlay's mode (practice.cpp passes it on). */
inline bool adjust(int i, int delta, Settings* s, Recorder* rec, int* display)
{
    auto cyc = [delta](int v, int n) { return ((v + delta) % n + n) % n; };
    switch (i) {
    case I_BEHAVIOUR: s->dummy = (DummyMode)cyc((int)s->dummy, (int)DummyMode::Count); return true;
    case I_COUNTER: s->counter = (Counter)cyc((int)s->counter, (int)Counter::Count); return true;
    case I_COUNTER_EVERY: s->counter_every = 1 + cyc(s->counter_every - 1, kMaxEvery); return true;
    case I_COUNTER_WITH: s->counter_slot = cyc(s->counter_slot, Recorder::kSlots + 1); return true;
    case I_SLOT: if (rec) rec->select(delta); return true;
    case I_RANDOM: s->random_play = !s->random_play; return true;
    case I_RESTART: s->restart = (Restart)cyc((int)s->restart, (int)Restart::Count); return true;
    case I_SIDES: s->switched = !s->switched; return true;
    case I_FACING: s->back_turned = !s->back_turned; return true;
    case I_DELAY: {
        const int v = s->delay + delta;
        if (v < 0 || v > kMaxDelay) return false;
        s->delay = v; return true; }
    case I_DISPLAY: *display = cyc(*display, 3); return true;
    default: return false;
    }
}

/* The menu's navigation on P1's pad mask (absolute: the menu does not turn with the fighter):
 * up / down move (held: repeats), left / right change a value, 3 (CROSS) changes a value
 * forward or does an action, 4 (CIRCLE) and START close. */
class Menu {
public:
    enum class Ev : uint8_t { None, Moved, Change, Activate, Close };
    struct Event { Ev ev = Ev::None; int item = 0; int delta = 0; };
    static constexpr int kRepeatAfter = 18, kRepeatEvery = 5;

    bool open() const { return open_; }
    int cursor() const { return cur_; }
    /* opened with the START press still held: it counts as pressed already */
    void show(uint16_t held) { open_ = true; prev_ = held; hold_ = 0; }
    void hide() { open_ = false; }
    void set_cursor(int i) { if (i >= 0 && i < I_COUNT) cur_ = i; }

    Event frame(uint16_t in)
    {
        Event e;
        if (!open_) { prev_ = in; return e; }
        const uint16_t press = (uint16_t)(in & ~prev_);
        const uint16_t vert = in & (kUp | kDown);
        const uint16_t horiz = in & (kLeft | kRight);
        uint16_t rep = 0;                                   /* a held direction repeats */
        if ((vert || horiz) && (in & (kUp | kDown | kLeft | kRight)) == (prev_ & (kUp | kDown | kLeft | kRight))) {
            if (++hold_ >= kRepeatAfter && (hold_ - kRepeatAfter) % kRepeatEvery == 0) rep = (uint16_t)(vert ? vert : horiz);
        } else hold_ = 0;
        const uint16_t go = (uint16_t)(press | rep);
        prev_ = in;
        if (press & (uint16_t)(kStart | (uint16_t)kCircle)) { open_ = false; e.ev = Ev::Close; return e; }
        if (go & kUp) { cur_ = (cur_ + I_COUNT - 1) % I_COUNT; e.ev = Ev::Moved; e.item = cur_; return e; }
        if (go & kDown) { cur_ = (cur_ + 1) % I_COUNT; e.ev = Ev::Moved; e.item = cur_; return e; }
        if (!is_action(cur_) && (go & (kLeft | kRight))) {
            e.ev = Ev::Change; e.item = cur_; e.delta = (go & kRight) ? 1 : -1; return e;
        }
        if (press & kCross) {
            e.item = cur_;
            if (is_action(cur_)) e.ev = Ev::Activate;
            else { e.ev = Ev::Change; e.delta = 1; }
            return e;
        }
        return e;
    }

private:
    bool open_ = false;
    int cur_ = 0;
    uint16_t prev_ = 0;
    int hold_ = 0;
};

/* After the menu closes, or around START taken for it, P1's pad stays hidden from the game until
 * it is neutral (as after a SELECT combo): the press that closed the menu is no attack. */
class Latch {
public:
    void set() { on_ = true; }
    bool frame(uint16_t in) { if (on_ && !in) on_ = false; return on_; }
    bool on() const { return on_; }
private:
    bool on_ = false;
};

} // namespace practice
