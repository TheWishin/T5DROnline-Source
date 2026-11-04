/*
 * The practice suite without the game (tests/test_practice_menu.py builds and runs it):
 * src/training/practice_logic.h -- the practice menu's navigation and texts (every
 * character drawn has a glyph of ps3recomp patch 0045's font, every line fits the
 * panel), its settings, the settings and recordings files, P1's input delay, the
 * dummy's counter-attack, the restart places, random playback and the movement loops
 * of training_logic.h's Dummy.
 * Prints "PASS <n> checks" and exits 0, or the failed checks and exits 1.
 */
#include <math.h>
#include <stdio.h>
#include <string.h>
#include <string>
#include <vector>

#include "rsx_overlay.h"
#include "practice_logic.h"

using namespace training;
using namespace practice;

static int g_checks = 0, g_fail = 0;
#define CHECK(c) do { g_checks++; if (!(c)) { g_fail++; printf("FAIL %s:%d: %s\n", __FILE__, __LINE__, #c); } } while (0)
#define CHECK_EQ(a, b) do { g_checks++; long long _a = (long long)(a), _b = (long long)(b); \
    if (_a != _b) { g_fail++; printf("FAIL %s:%d: %s == %s (%lld vs %lld)\n", __FILE__, __LINE__, #a, #b, _a, _b); } } while (0)

static Menu::Event step(Menu& m, uint16_t in) { return m.frame(in); }

static void test_menu_navigation()
{
    Menu m;
    CHECK(!m.open());
    CHECK(step(m, kStart).ev == Menu::Ev::None);         /* closed: nothing */
    m.show(kStart);                                        /* opened by the START press, still held */
    CHECK(m.open());
    CHECK(step(m, kStart).ev == Menu::Ev::None);          /* the held START does not close it */
    CHECK(step(m, 0).ev == Menu::Ev::None);
    CHECK_EQ(m.cursor(), I_BEHAVIOUR);
    Menu::Event e = step(m, kDown);
    CHECK(e.ev == Menu::Ev::Moved && e.item == I_COUNTER);
    step(m, 0);
    e = step(m, kUp);
    CHECK(e.ev == Menu::Ev::Moved && e.item == I_BEHAVIOUR);
    step(m, 0);
    e = step(m, kUp);                                       /* wraps to the last item */
    CHECK(e.ev == Menu::Ev::Moved && e.item == I_CLOSE);
    step(m, 0);
    e = step(m, kDown);
    CHECK(e.ev == Menu::Ev::Moved && e.item == I_BEHAVIOUR);
    step(m, 0);
    e = step(m, kRight);
    CHECK(e.ev == Menu::Ev::Change && e.item == I_BEHAVIOUR && e.delta == 1);
    step(m, 0);
    e = step(m, kLeft);
    CHECK(e.ev == Menu::Ev::Change && e.delta == -1);
    step(m, 0);
    e = step(m, kCross);                                    /* 3 on a setting: the next value */
    CHECK(e.ev == Menu::Ev::Change && e.delta == 1);
    step(m, 0);
    /* a held direction repeats after kRepeatAfter frames, every kRepeatEvery */
    m.set_cursor(I_BEHAVIOUR);
    int moves = 0;
    for (int i = 0; i < Menu::kRepeatAfter + 3 * Menu::kRepeatEvery; i++)
        if (step(m, kDown).ev == Menu::Ev::Moved) moves++;
    CHECK_EQ(moves, 1 + 3);
    step(m, 0);
    /* actions: 3 activates, left / right do nothing there */
    m.set_cursor(I_RECORD);
    CHECK(step(m, kRight).ev == Menu::Ev::None);
    step(m, 0);
    e = step(m, kCross);
    CHECK(e.ev == Menu::Ev::Activate && e.item == I_RECORD);
    step(m, 0);
    CHECK(step(m, kSquare | kTriangle).ev == Menu::Ev::None);
    step(m, 0);
    e = step(m, kCircle);                                   /* 4 closes */
    CHECK(e.ev == Menu::Ev::Close && !m.open());
    m.show(0);
    e = step(m, kStart);                                    /* a new START press closes */
    CHECK(e.ev == Menu::Ev::Close && !m.open());
    for (int i = 0; i < I_COUNT; i++) {
        CHECK(item_label(i)[0]);
        CHECK(is_action(i) == (i == I_RECORD || i == I_PLAY || i == I_LOOP || i == I_CLEAR || i == I_REMEMBER ||
                               i == I_RESTART_NOW || i == I_GAME_MENU || i == I_CLOSE));
    }
    CHECK(!strcmp(section_at(I_BEHAVIOUR), "DUMMY") && !strcmp(section_at(I_SLOT), "RECORDING") &&
          !strcmp(section_at(I_RESTART), "RESTART") && !strcmp(section_at(I_DELAY), "SETTINGS"));
}

static void test_adjust()
{
    Settings s;
    static Recorder r;
    r.clear_all();
    int disp = 2;
    for (int i = 0; i < (int)DummyMode::Count; i++) CHECK(adjust(I_BEHAVIOUR, 1, &s, &r, &disp));
    CHECK(s.dummy == DummyMode::Game);
    CHECK(adjust(I_BEHAVIOUR, -1, &s, &r, &disp) && s.dummy == DummyMode::Wavedash);
    for (int i = 0; i < 4; i++) adjust(I_COUNTER, 1, &s, &r, &disp);
    CHECK(s.counter == Counter::Off);
    adjust(I_COUNTER, -1, &s, &r, &disp);
    CHECK(s.counter == Counter::Either);
    adjust(I_COUNTER_EVERY, -1, &s, &r, &disp);
    CHECK_EQ(s.counter_every, kMaxEvery);
    adjust(I_COUNTER_EVERY, 1, &s, &r, &disp);
    CHECK_EQ(s.counter_every, 1);
    adjust(I_COUNTER_WITH, -1, &s, &r, &disp);
    CHECK_EQ(s.counter_slot, Recorder::kSlots);
    adjust(I_COUNTER_WITH, 1, &s, &r, &disp);
    CHECK_EQ(s.counter_slot, 0);
    adjust(I_SLOT, -1, &s, &r, &disp);
    CHECK_EQ(r.slot(), Recorder::kSlots - 1);
    CHECK(adjust(I_RANDOM, 1, &s, &r, &disp) && s.random_play);
    for (int i = 0; i < (int)Restart::Count; i++) adjust(I_RESTART, 1, &s, &r, &disp);
    CHECK(s.restart == Restart::RoundStart);
    CHECK(adjust(I_SIDES, -1, &s, &r, &disp) && s.switched);
    CHECK(adjust(I_FACING, 1, &s, &r, &disp) && s.back_turned);
    CHECK(!adjust(I_DELAY, -1, &s, &r, &disp) && s.delay == 0);        /* 0..6, no wrap */
    for (int i = 0; i < 10; i++) adjust(I_DELAY, 1, &s, &r, &disp);
    CHECK_EQ(s.delay, kMaxDelay);
    adjust(I_DISPLAY, 1, &s, &r, &disp);
    CHECK_EQ(disp, 0);
    adjust(I_DISPLAY, -1, &s, &r, &disp);
    CHECK_EQ(disp, 2);
    for (int i : { I_RECORD, I_PLAY, I_LOOP, I_CLEAR, I_REMEMBER, I_RESTART_NOW, I_GAME_MENU, I_CLOSE })
        CHECK(!adjust(i, 1, &s, &r, &disp));
}

/* every text the menu can show: a glyph for each character, and label + value fit the panel */
static void check_text(const char* t)
{
    uint8_t rows[7];
    for (const char* p = t; *p; p++) {
        const bool ok = rsx_overlay_glyph_rows((unsigned char)*p, rows) != 0;
        if (!ok) { g_fail++; printf("FAIL no glyph for '%c' in \"%s\"\n", *p, t); }
        g_checks++;
    }
}
static void test_texts()
{
    static Recorder r;
    r.clear_all();
    const uint16_t one[3] = { kRight, kRight | kSquare, 0 };
    r.set(0, one, 3);
    Settings s;
    View v;
    v.s = &s; v.rec = &r;
    const float kPanelText = 660.0f - 68.0f;     /* practice.cpp: the panel 660 wide, 36 left, 32 right */
    float widest = 0;
    for (int pass = 0; pass < 12; pass++) {
        /* walk every value of every setting */
        s.dummy = (DummyMode)(pass % (int)DummyMode::Count);
        s.counter = (Counter)(pass % (int)Counter::Count);
        s.counter_every = 1 + pass % kMaxEvery;
        s.counter_slot = pass % (Recorder::kSlots + 1);
        s.random_play = pass & 1;
        s.restart = (Restart)(pass % (int)Restart::Count);
        s.switched = pass & 2;
        s.back_turned = pass & 4;
        s.delay = pass % (kMaxDelay + 1);
        v.display = pass % 3;
        v.remembered = pass & 8;
        v.clear_armed = pass & 1;
        r.select_slot(pass % Recorder::kSlots);
        for (int i = 0; i < I_COUNT; i++) {
            char val[64], shown[80];
            item_value(i, v, val, sizeof val);
            snprintf(shown, sizeof shown, "< %s >", val);
            check_text(item_label(i));
            check_text(shown);
            const float w = rsx_overlay_text_width(item_label(i), 2.0f) + 24.0f + rsx_overlay_text_width(shown, 2.0f);
            if (w > widest) widest = w;
            if (w > kPanelText) { g_fail++; printf("FAIL too wide (%.0f): %s %s\n", w, item_label(i), shown); }
            g_checks++;
        }
    }
    printf("widest menu line %.0f of %.0f\n", widest, kPanelText);
    check_text("UP/DOWN CHOOSE   LEFT/RIGHT CHANGE   3 SELECT");
    check_text("POSITION REMEMBERED: SELECT+3 RESTARTS HERE");
    CHECK(rsx_overlay_text_width("UP/DOWN CHOOSE   LEFT/RIGHT CHANGE   3 SELECT", 2.0f) < 660.0f);
    char val[64];
    s.counter_every = 2; item_value(I_COUNTER_EVERY, v, val, sizeof val); CHECK(!strcmp(val, "EVERY 2ND TIME"));
    s.counter_every = 3; item_value(I_COUNTER_EVERY, v, val, sizeof val); CHECK(!strcmp(val, "EVERY 3RD TIME"));
    s.counter_every = 1; item_value(I_COUNTER_EVERY, v, val, sizeof val); CHECK(!strcmp(val, "EVERY TIME"));
    s.counter_slot = 2; item_value(I_COUNTER_WITH, v, val, sizeof val); CHECK(!strcmp(val, "SLOT 2 (EMPTY)"));
    s.counter_slot = 1; item_value(I_COUNTER_WITH, v, val, sizeof val); CHECK(!strcmp(val, "SLOT 1"));
    r.select_slot(0); item_value(I_SLOT, v, val, sizeof val); CHECK(!strcmp(val, "1  (0.1S)"));
    s.delay = 1; item_value(I_DELAY, v, val, sizeof val); CHECK(!strcmp(val, "1 FRAME"));
    s.restart = Restart::Remembered; v.remembered = false; item_value(I_RESTART, v, val, sizeof val);
    CHECK(!strcmp(val, "REMEMBERED POSITION (NONE YET)"));
}

static std::string through_file(void (*w)(FILE*, const void*), const void* arg)
{
    FILE* f = tmpfile();
    w(f, arg);
    fflush(f);
    rewind(f);
    std::string out;
    char b[4096];
    size_t n;
    while ((n = fread(b, 1, sizeof b, f)) > 0) out.append(b, n);
    fclose(f);
    return out;
}

static void test_settings_file()
{
    Settings s;
    s.counter = Counter::AfterHit; s.counter_every = 3; s.counter_slot = 5; s.random_play = true;
    s.restart = Restart::PlayerWallBack; s.switched = true; s.back_turned = true; s.delay = 4;
    s.dummy = DummyMode::Wavedash;
    const std::string t = through_file([](FILE* f, const void* a) { write_settings(f, *(const Settings*)a); }, &s);
    Settings b;
    parse_settings(t.c_str(), &b);
    CHECK(b.counter == Counter::AfterHit && b.counter_every == 3 && b.counter_slot == 5 && b.random_play &&
          b.restart == Restart::PlayerWallBack && b.switched && b.back_turned && b.delay == 4);
    CHECK(b.dummy == DummyMode::Game);              /* the behaviour is the launcher's, not in the file */
    /* broken values are skipped, the rest is kept; not such a file: nothing */
    Settings c;
    parse_settings("T5DR practice settings 1\ndelay 99\ncounter_every 0\ncounter dance\nrestart remembered\nswitched 1\n", &c);
    CHECK(c.delay == 0 && c.counter_every == 1 && c.counter == Counter::Off && c.restart == Restart::Remembered && c.switched);
    Settings d;
    parse_settings("delay 3\n", &d);
    CHECK(d.delay == 0);
    for (int i = 0; i < (int)DummyMode::Count; i++) {
        DummyMode m = DummyMode::Game;
        CHECK(dummy_from_key(dummy_key((DummyMode)i), &m) && (int)m == i);
    }
    DummyMode m = DummyMode::Crouch;
    CHECK(!dummy_from_key("dance", &m) && m == DummyMode::Crouch);
}

static void test_slots_file()
{
    static Recorder a, b;
    a.clear_all(); b.clear_all();
    std::vector<uint16_t> s0, s5;
    for (int i = 0; i < 77; i++) s0.push_back((uint16_t)(i % 3 ? kRight : (kDown | kSquare)));
    for (int i = 0; i < Recorder::kMaxFrames; i++) s5.push_back((uint16_t)(i & 0xF0F0));
    a.set(0, s0.data(), (int)s0.size());
    a.set(5, s5.data(), (int)s5.size());
    const std::string t = through_file([](FILE* f, const void* r) { write_slots(f, *(const Recorder*)r); }, &a);
    const uint16_t junk[2] = { 1, 2 };
    b.set(3, junk, 2);                                        /* replaced by the file: empty */
    CHECK(parse_slots(t.c_str(), &b));
    CHECK_EQ(b.length(0), 77);
    CHECK_EQ(b.length(3), 0);
    CHECK_EQ(b.length(5), Recorder::kMaxFrames);
    CHECK_EQ(b.recorded(), 2);
    CHECK(!memcmp(b.data(0), s0.data(), 77 * 2));
    CHECK(!memcmp(b.data(5), s5.data(), (size_t)Recorder::kMaxFrames * 2));
    /* SELECT / START never get into a slot; a file cut short keeps what it has; others are refused */
    const uint16_t sel[2] = { (uint16_t)(kSelect | kRight), kStart };
    a.set(1, sel, 2);
    CHECK_EQ(a.data(1)[0], kRight); CHECK_EQ(a.data(1)[1], 0);
    CHECK(parse_slots("T5DR practice recordings 1\nslot 2 5\n2000 2000 0080\n", &b));
    CHECK_EQ(b.length(1), 3); CHECK_EQ(b.length(0), 0);
    CHECK(parse_slots("T5DR practice recordings 1\nslot 9 2\n2000 2000\nslot 0 1\n2000\n", &b));
    CHECK_EQ(b.recorded(), 0);
    CHECK(!parse_slots("hello\nslot 1 1\n2000\n", &b));
    CHECK(parse_slots("T5DR practice recordings 1\r\nslot 1 2\r\n2000 4000\r\n", &b));
    CHECK_EQ(b.length(0), 2); CHECK_EQ(b.data(0)[1], 0x4000);
}

static void test_input_delay()
{
    InputDelay d;
    for (uint16_t i = 1; i < 10; i++) CHECK_EQ(d.frame(i, 0), i);
    d.reset();
    std::vector<uint16_t> out;
    for (uint16_t i = 1; i <= 12; i++) out.push_back(d.frame(i, 3));
    /* the first 3 frames: what was held before (nothing), then each input 3 frames late */
    CHECK_EQ(out[0], 0); CHECK_EQ(out[1], 0); CHECK_EQ(out[2], 0);
    for (int i = 3; i < 12; i++) CHECK_EQ(out[(size_t)i], i - 2);
    /* a new delay: the last input held for the frames in between */
    InputDelay e;
    e.frame(kRight, 0);
    CHECK_EQ(e.frame(kSquare, 6), kRight);
    for (int i = 0; i < 5; i++) CHECK_EQ(e.frame(kSquare, 6), kRight);
    CHECK_EQ(e.frame(0, 6), kSquare);
    CHECK_EQ(e.frame(0, 99), kSquare);                        /* bounded to 6: still 6 frames late */
}

static Sample idle() { Sample s; s.hp = 170; s.can_act = true; s.stand = true; return s; }

static void test_counter()
{
    Sample p1 = idle(), att = idle(), d = idle(), stun = idle();
    att.cls = 0x00012345u & 0xFFFF; att.can_act = false;
    stun.can_act = false;
    CounterAttack c;
    /* block: P1 attacks, the dummy cannot act, no health lost; free again -> fires */
    CHECK(!c.frame(Counter::AfterBlock, 1, p1, d, 170));
    CHECK(!c.frame(Counter::AfterBlock, 1, att, stun, 170));
    CHECK(c.in_stun());
    for (int i = 0; i < 10; i++) CHECK(!c.frame(Counter::AfterBlock, 1, p1, stun, 170));
    CHECK(c.frame(Counter::AfterBlock, 1, p1, d, 170));
    CHECK(!c.last_was_hit());
    CHECK(!c.frame(Counter::AfterBlock, 1, p1, d, 170));      /* once */
    /* a hit (health lost) does not count for AfterBlock, does for AfterHit and Either */
    Sample hurt = stun; hurt.hp = 150;
    CounterAttack h;
    CHECK(!h.frame(Counter::AfterBlock, 1, att, hurt, 170));
    hurt.hp = 150;
    CHECK(!h.frame(Counter::AfterBlock, 1, p1, hurt, 150));
    Sample after = d; after.hp = 150;
    CHECK(!h.frame(Counter::AfterBlock, 1, p1, after, 150));
    CHECK(h.last_was_hit());
    CounterAttack h2;
    h2.frame(Counter::AfterHit, 1, att, hurt, 170);
    CHECK(h2.frame(Counter::AfterHit, 1, p1, after, 150));
    CounterAttack h3;
    h3.frame(Counter::Either, 1, att, stun, 170);
    CHECK(h3.frame(Counter::Either, 1, p1, d, 170));
    /* a hit reaction class without damage is a hit */
    Sample react = stun; react.cls = 0x10000;
    CounterAttack h4;
    h4.frame(Counter::AfterHit, 1, p1, react, 170);
    CHECK(h4.frame(Counter::AfterHit, 1, p1, d, 170) && h4.last_was_hit());
    /* every 3rd block */
    CounterAttack e;
    int fired = 0;
    for (int k = 0; k < 9; k++) {
        e.frame(Counter::AfterBlock, 3, att, stun, 170);
        e.frame(Counter::AfterBlock, 3, p1, stun, 170);
        if (e.frame(Counter::AfterBlock, 3, p1, d, 170)) { fired++; CHECK_EQ(k % 3, 2); }
    }
    CHECK_EQ(fired, 3);
    /* the dummy unable to act by itself (no attack, no damage) is no stun; off resets */
    CounterAttack n;
    CHECK(!n.frame(Counter::Either, 1, p1, stun, 170));
    CHECK(!n.in_stun());
    n.frame(Counter::Either, 1, att, stun, 170);
    CHECK(!n.frame(Counter::Off, 1, p1, d, 170));
    CHECK(!n.in_stun());
}

static void test_random_play()
{
    static Recorder r;
    r.clear_all();
    const uint16_t a[2] = { kRight, kRight }, b[3] = { kLeft, kLeft, kLeft };
    r.set(1, a, 2);
    r.set(6, b, 3);
    r.set_rng(12345);
    r.set_random(true);
    int seen[Recorder::kSlots] = {};
    for (int i = 0; i < 200; i++) {
        CHECK(r.play(false));
        CHECK(r.play_slot() == 1 || r.play_slot() == 6);
        seen[r.play_slot()]++;
        uint16_t m;
        int n = 0;
        while (r.next(&m)) n++;
        CHECK_EQ(n, r.play_slot() == 1 ? 2 : 3);
    }
    CHECK(seen[1] > 50 && seen[6] > 50);
    /* a loop takes a new slot for each pass */
    r.toggle_play(true);
    int passes = 0, last = -1, changes = 0;
    uint16_t m;
    for (int i = 0; i < 300 && r.next(&m); i++) {
        if (r.play_slot() != last) { changes++; last = r.play_slot(); }
        if (r.pos() == 1) passes++;
    }
    CHECK(passes > 50 && changes > 10);
    r.stop();
    r.set_random(false);
    r.select_slot(0);
    CHECK(!r.play(false));                                    /* slot 1 is empty */
    CHECK(r.play_once(6) && r.play_slot() == 6);
    CHECK(!r.play_once(0));
    CHECK(r.play_once(-1) && (r.play_slot() == 1 || r.play_slot() == 6));
    CHECK(!r.random());                                       /* play_once(-1) does not turn random on */
    r.clear(1); r.clear(6);
    CHECK(!r.play_once(-1));
    CHECK_EQ(r.recorded(), 0);
}

static void test_movement()
{
    for (DummyMode m : { DummyMode::Dash, DummyMode::Backdash, DummyMode::BackdashCancel, DummyMode::Wavedash }) {
        int n = 0;
        const MoveStep* s = move_script(m, &n);
        CHECK(s && n >= 4);
        CHECK(move_script_frames(m) >= 40 && move_script_frames(m) <= 120);
        for (int i = 0; i < n; i++) CHECK(!(s[i].rel & ~(kUp | kDown | kLeft | kRight)));   /* directions only */
        CHECK_EQ(s[n - 1].rel, 0);                                                          /* a pause at the end */
        Dummy d;
        CHECK_EQ(d.setting(m), Dummy::kSetController);
        /* on the right side forward is LEFT: the mask is turned */
        Sample right = idle(); right.right = true;
        Sample left = idle();
        Dummy a, b;
        for (uint32_t t = 0; t < (uint32_t)move_script_frames(m) * 2; t++) {
            const uint16_t ra = a.frame(m, right, 170), lb = b.frame(m, left, 170);
            CHECK_EQ(ra, flip_lr(lb));
            CHECK_EQ(lb, move_script_mask(m, t));
        }
    }
    CHECK_EQ(move_script_mask(DummyMode::Dash, 0), kRight);         /* forward first */
    CHECK_EQ(move_script_mask(DummyMode::Dash, 2), 0);              /* then neutral: f,f */
    CHECK_EQ(move_script_mask(DummyMode::Dash, 4), kRight);
    CHECK_EQ(move_script_mask(DummyMode::Backdash, 0), kLeft);
    CHECK_EQ(move_script_mask(DummyMode::Backdash, 4), kLeft);
    CHECK_EQ(move_script_mask(DummyMode::BackdashCancel, 7), kUp | kLeft);
    CHECK_EQ(move_script_mask(DummyMode::Wavedash, 4), kDown);
    CHECK_EQ(move_script_mask(DummyMode::Wavedash, 6), kDown | kRight);
    CHECK_EQ(move_script_mask(DummyMode::Crouch, 0), 0);
    int n = 5;
    CHECK(!move_script(DummyMode::Game, &n) && n == 0);
}

static void test_restart_places()
{
    Place start[2] = { { 1000, 0, -1.5708f }, { -1000, 0, 1.5708f } };
    Place rem[2] = { { 300, 400, 0 }, { 300, -700, 3.14159f } };
    Place out[2];
    CHECK(restart_places(Restart::RoundStart, false, start, rem, true, out));
    CHECK(out[0].x == 1000 && out[1].x == -1000);
    CHECK(restart_places(Restart::RoundStart, true, start, rem, true, out));
    CHECK(out[0].x == -1000 && out[1].x == 1000);
    CHECK(restart_places(Restart::Remembered, false, start, rem, true, out));
    CHECK(out[0].z == 400 && out[1].z == -700);
    CHECK(restart_places(Restart::Remembered, true, start, rem, true, out));
    CHECK(out[0].z == -700 && out[1].z == 400);
    CHECK(restart_places(Restart::Remembered, false, start, rem, false, out));     /* nothing remembered: start */
    CHECK(out[0].x == 1000);
    for (Restart w : { Restart::DummyWallFront, Restart::DummyWallBack, Restart::PlayerWallFront, Restart::PlayerWallBack })
        CHECK(!restart_places(w, false, start, rem, true, out));
    CHECK(restart_action(Restart::DummyWallFront) == PAction::DummyWallFront);
    CHECK(restart_action(Restart::PlayerWallBack) == PAction::PlayerWallBack);
    CHECK(restart_action(Restart::RoundStart) == PAction::ResetRound);
    /* behind: the dummy at (-1000, 0) looks along +x (angle pi/2); behind it is -x */
    const Place b = behind(start[1], 2000);
    CHECK(fabsf(b.x - -3000) < 0.5f && fabsf(b.z) < 0.5f && b.angle == start[1].angle);
    /* the dummy then has P1 at its back: P1 looks at the dummy */
    const float toward = face_toward(b.x, b.z, start[1].x, start[1].z);
    CHECK(fabsf(toward - start[1].angle) < 0.01f);
}

static void test_combo_and_latch()
{
    Combo c;
    bool hide = false;
    c.frame(kSelect, false, &hide);
    CHECK(c.frame(kSelect | kStart, false, &hide) == PAction::RememberPos && hide);
    CHECK(c.frame(kSelect | kStart, false, &hide) == PAction::None);      /* once per press */
    c.frame(kStart, false, &hide);
    CHECK(hide);                                                           /* START still held: hidden */
    c.frame(0, false, &hide);
    CHECK(!hide);
    CHECK(c.frame(kStart, false, &hide) == PAction::None && !hide);       /* START alone is no combo */
    Latch l;
    CHECK(!l.frame(kCross));
    l.set();
    CHECK(l.frame(kCross) && l.frame(kStart) && l.on());
    CHECK(!l.frame(0) && !l.on());
    CHECK(!l.frame(kCross));
}

int main()
{
    test_menu_navigation();
    test_adjust();
    test_texts();
    test_settings_file();
    test_slots_file();
    test_input_delay();
    test_counter();
    test_random_play();
    test_movement();
    test_restart_places();
    test_combo_and_latch();
    if (g_fail) {
        printf("FAILED %d of %d checks\n", g_fail, g_checks);
        return 1;
    }
    printf("PASS %d checks\n", g_checks);
    return 0;
}
