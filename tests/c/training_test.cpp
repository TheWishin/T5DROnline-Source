/*
 * The training overlay without the game (tests/test_training.py builds and runs it):
 *   - src/training/training_logic.h: Tekken notation, the input history, the
 *     frame-data tracker fed frame sequences shaped like the fights traced in
 *     docs/TRAINING.md (jab on block +3 and on hit +9, a whiff, a string, a
 *     defender pressing during block stun, a knockdown, a counter hit, P2
 *     attacking, a trade-free walk);
 *   - ps3recomp patch 0045 libs/video/rsx_overlay.c built with
 *     RSX_OVERLAY_NO_D3D: the font (every character the overlay writes has its
 *     own glyph, no two letters or digits alike) and the layout (whole window
 *     pixels, a whole number of them per font pixel, the letterbox, alignment,
 *     shadows, UTF-8).
 * Prints "PASS <n> checks" and exits 0, or the failed checks and exits 1.
 */
#include <math.h>
#include <stdio.h>
#include <string.h>
#include <vector>

#include "rsx_overlay.h"
#include "training_logic.h"

using namespace training;

static int g_checks = 0, g_fail = 0;
#define CHECK(c) do { g_checks++; if (!(c)) { g_fail++; printf("FAIL %s:%d: %s\n", __FILE__, __LINE__, #c); } } while (0)
#define CHECK_EQ(a, b) do { g_checks++; long long _a = (long long)(a), _b = (long long)(b); \
    if (_a != _b) { g_fail++; printf("FAIL %s:%d: %s == %s (%lld vs %lld)\n", __FILE__, __LINE__, #a, #b, _a, _b); } } while (0)

/* ---- notation and history ----------------------------------------------------- */
static void test_notation()
{
    CHECK_EQ(notation(0, false).dir, 5);
    CHECK_EQ(notation(kRight, false).dir, 6);
    CHECK_EQ(notation(kLeft, false).dir, 4);
    CHECK_EQ(notation(kDown | kRight, false).dir, 3);
    CHECK_EQ(notation(kDown | kLeft, false).dir, 1);
    CHECK_EQ(notation(kUp | kLeft, false).dir, 7);
    CHECK_EQ(notation(kUp | kRight, false).dir, 9);
    CHECK_EQ(notation(kUp, false).dir, 8);
    CHECK_EQ(notation(kDown, false).dir, 2);
    /* the fighter on the right: toward the opponent is LEFT */
    CHECK_EQ(notation(kLeft, true).dir, 6);
    CHECK_EQ(notation(kRight, true).dir, 4);
    CHECK_EQ(notation(kDown | kLeft, true).dir, 3);
    CHECK_EQ(notation(kUp | kRight, true).dir, 7);
    /* left and right together: neither; up and down together: neither */
    CHECK_EQ(notation(kLeft | kRight, false).dir, 5);
    CHECK_EQ(notation(kLeft | kRight | kDown, false).dir, 2);
    CHECK_EQ(notation(kUp | kDown | kRight, false).dir, 6);
    /* buttons: 1 = SQUARE, 2 = TRIANGLE, 3 = CROSS, 4 = CIRCLE */
    CHECK_EQ(notation(kSquare, false).buttons, 1);
    CHECK_EQ(notation(kTriangle, false).buttons, 2);
    CHECK_EQ(notation(kCross, false).buttons, 4);
    CHECK_EQ(notation(kCircle, false).buttons, 8);
    char b[16];
    buttons_text(notation(kSquare | kTriangle, false).buttons, b, sizeof b);
    CHECK(!strcmp(b, "1+2"));
    buttons_text(notation(kSquare | kTriangle | kCross | kCircle, true).buttons, b, sizeof b);
    CHECK(!strcmp(b, "1+2+3+4"));
    buttons_text(notation(kCross | kCircle | kDown, false).buttons, b, sizeof b);
    CHECK(!strcmp(b, "3+4"));
    buttons_text(0, b, sizeof b);
    CHECK(!strcmp(b, ""));
}

static void test_history()
{
    History<4> h;
    CHECK_EQ(h.count, 0);
    h.push(notation(0, false));
    h.push(notation(0, false));
    h.push(notation(0, false));
    CHECK_EQ(h.count, 1);
    CHECK_EQ(h.rows[0].frames, 3);
    h.push(notation(kSquare, false));
    CHECK_EQ(h.count, 2);
    CHECK_EQ(h.rows[0].n.buttons, 1);
    CHECK_EQ(h.rows[0].frames, 1);
    CHECK_EQ(h.rows[1].frames, 3);
    for (int i = 0; i < 10; i++) h.push(notation(i % 2 ? kRight : kLeft, false));
    CHECK_EQ(h.count, 4);                       /* the oldest rows fall off */
    CHECK_EQ(h.rows[0].n.dir, 6);
    CHECK_EQ(h.rows[1].n.dir, 4);
    h.clear();
    CHECK_EQ(h.count, 0);
}

/* ---- frame data ---------------------------------------------------------------- */
/* One fighter's timeline: a list of per-frame states built by the helpers. */
struct Timeline {
    std::vector<Sample> f;
    explicit Timeline(int n) : f((size_t)n) { for (auto& s : f) { s.hp = 170; s.can_act = true; } }
    /* a move starting at `start`: new move, not able to act until `act` */
    void move(int start, uint32_t cls, int act)
    {
        f[(size_t)start].new_move = true;
        for (int t = start; t < act && t < (int)f.size(); t++) { f[(size_t)t].can_act = false; f[(size_t)t].cls = cls; }
        if (act < (int)f.size()) f[(size_t)act].cls = cls;
    }
    void active(int from, int to) { for (int t = from; t <= to; t++) f[(size_t)t].active = true; }
    void damage(int at, int d) { for (int t = at; t < (int)f.size(); t++) f[(size_t)t].hp -= d; }
    void input(int from, int to, uint16_t m) { for (int t = from; t <= to && t < (int)f.size(); t++) f[(size_t)t].input = m; }
    void act_from(int t) { for (int i = t; i < (int)f.size(); i++) f[(size_t)i].can_act = true; }
};

struct Run {
    std::vector<Result> results;
    std::vector<int> at;
};
static Run run(const Timeline& p1, const Timeline& p2)
{
    Tracker tr;
    Run r;
    for (size_t t = 0; t < p1.f.size(); t++) {
        Sample s[2] = { p1.f[t], p2.f[t] };
        if (tr.frame(s)) { r.results.push_back(tr.last()); r.at.push_back((int)t); }
    }
    return r;
}

static void test_jab_block_and_hit()
{
    /* Jin's jab on block (traced): starts at 10, active at 19 (i10), can act
     * from 35; the guard reaction starts at 20, can act from 38 -> +3 */
    {
        Timeline a(80), d(80);
        a.move(10, 7, 35); a.active(19, 19);
        d.move(20, 0, 38);
        const Run r = run(a, d);
        CHECK_EQ(r.results.size(), 1);
        if (r.results.size() == 1) {
            CHECK_EQ(r.results[0].attacker, 0);
            CHECK_EQ(r.results[0].startup, 10);
            CHECK(r.results[0].kind == Kind::Block);
            CHECK_EQ(r.results[0].adv, 3);
            CHECK_EQ(r.at[0], 38);
        }
    }
    /* on hit: 7 damage at the active frame, a hit reaction (class 0x10000) that
     * can act from 44 -> +9 */
    {
        Timeline a(80), d(80);
        a.move(10, 7, 35); a.active(19, 19);
        d.damage(19, 7); d.move(20, 0x10000, 44);
        const Run r = run(a, d);
        CHECK_EQ(r.results.size(), 1);
        if (r.results.size() == 1) {
            CHECK(r.results[0].kind == Kind::Hit);
            CHECK_EQ(r.results[0].startup, 10);
            CHECK_EQ(r.results[0].adv, 9);
        }
    }
    /* the same exchange with P2 attacking P1 */
    {
        Timeline a(80), d(80);
        a.move(10, 7, 35); a.active(19, 19);
        d.move(20, 0, 38);
        const Run r = run(d, a);
        CHECK_EQ(r.results.size(), 1);
        if (r.results.size() == 1) { CHECK_EQ(r.results[0].attacker, 1); CHECK_EQ(r.results[0].adv, 3); }
    }
    /* a slow low on block: startup 16, the attacker can act 15 frames after the defender */
    {
        Timeline a(120), d(120);
        a.move(10, 0xF, 59); a.active(25, 27);
        d.move(26, 0, 44);
        const Run r = run(a, d);
        CHECK_EQ(r.results.size(), 1);
        if (r.results.size() == 1) { CHECK_EQ(r.results[0].startup, 16); CHECK_EQ(r.results[0].adv, -15); }
    }
}

static void test_defender_presses()
{
    /* The defender presses 1 during block stun: the game opens its can-act
     * window early (33 instead of 38) to keep the press, and the jab comes out
     * at 39 -- the frame after the one it could act in. Still +3. */
    Timeline a(90), d(90);
    a.move(10, 7, 35); a.active(19, 19);
    d.move(20, 0, 39);
    d.act_from(33);                       /* the early window ... */
    for (int t = 33; t < 39; t++) d.f[(size_t)t].can_act = true;
    for (int t = 25; t < 39; t += 2) d.input(t, t, kSquare);
    d.move(39, 7, 64);                    /* ... and its jab */
    const Run r = run(a, d);
    CHECK(r.results.size() >= 1);
    if (!r.results.empty()) { CHECK_EQ(r.results[0].adv, 3); CHECK(r.results[0].kind == Kind::Block); }

    /* a press that starts nothing: after kPressWait frames the early window counts */
    Timeline a2(120), d2(120);
    a2.move(10, 7, 35); a2.active(19, 19);
    d2.move(20, 0, 33);
    d2.input(22, 22, kSquare);
    const Run r2 = run(a2, d2);
    CHECK_EQ(r2.results.size(), 1);
    if (r2.results.size() == 1) CHECK_EQ(r2.results[0].adv, -2);
}

static void test_whiff_and_walk()
{
    Timeline a(80), d(80);
    a.move(10, 7, 35); a.active(19, 19);
    const Run r = run(a, d);
    CHECK_EQ(r.results.size(), 1);
    if (r.results.size() == 1) {
        CHECK(r.results[0].kind == Kind::Whiff);
        CHECK_EQ(r.results[0].startup, 10);
        CHECK_EQ(r.results[0].total, 25);
    }
    /* walking and crouching are new moves the fighter can act in: nothing */
    Timeline w(80), i(80);
    for (int t = 10; t < 40; t += 5) w.f[(size_t)t].new_move = true;
    w.input(10, 40, kRight);
    CHECK_EQ(run(w, i).results.size(), 0);
    /* a backdash: a move without active frames: nothing */
    Timeline bd(80), i2(80);
    bd.move(10, 0, 30);
    CHECK_EQ(run(bd, i2).results.size(), 0);
}

static void test_string()
{
    /* 1,2 on block: the second hit cancels the first before the attacker could
     * act; the result is the last hit's advantage with the first hit's startup */
    Timeline a(120), d(120);
    a.move(10, 7, 20); a.active(19, 19);
    a.move(20, 0xC, 60); a.active(29, 29);
    d.move(20, 0, 30);
    d.move(30, 0, 48);
    const Run r = run(a, d);
    CHECK_EQ(r.results.size(), 1);
    if (r.results.size() == 1) {
        CHECK_EQ(r.results[0].startup, 10);
        CHECK(r.results[0].kind == Kind::Block);
        CHECK_EQ(r.results[0].adv, -12);
    }
    /* the attacker mashing the same jab after it could act: two exchanges, +3 each */
    Timeline m(140), g(140);
    m.move(10, 7, 35); m.active(19, 19);
    m.move(36, 7, 61); m.active(45, 45);
    g.move(20, 0, 38);
    g.move(46, 0, 64);
    const Run r2 = run(m, g);
    CHECK_EQ(r2.results.size(), 2);
    if (r2.results.size() == 2) { CHECK_EQ(r2.results[0].adv, 3); CHECK_EQ(r2.results[1].adv, 3); }
}

static void test_down_and_counter()
{
    /* a knockdown: the defender cannot act for a long time */
    Timeline a(300), d(300);
    a.move(10, 0x9, 50); a.active(24, 25);
    d.damage(24, 30); d.move(25, 0x10000, 290);
    const Run r = run(a, d);
    CHECK(!r.results.empty());
    if (!r.results.empty()) {
        CHECK(r.results[0].kind == Kind::Down);
        CHECK_EQ(r.results[0].startup, 15);
        CHECK_EQ(r.at[0], 50 + (int)Tracker::kDownAfter + 1);
    }
    /* a counter hit: the defender was in its own attack when hit */
    Timeline c(100), e(100);
    c.move(10, 7, 35); c.active(19, 19);
    e.move(15, 0x5, 40);
    e.damage(19, 8); e.move(20, 0x10000, 46);
    const Run r2 = run(c, e);
    CHECK(!r2.results.empty());
    if (!r2.results.empty()) { CHECK(r2.results[0].kind == Kind::Counter); CHECK_EQ(r2.results[0].adv, 11); }
}

/* ---- font and layout ------------------------------------------------------------ */
static void test_font()
{
    uint8_t rows[7], other[7];
    const char* must = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz+-()%:./[]!?'";
    for (const char* p = must; *p; p++) {
        CHECK(rsx_overlay_glyph_rows((unsigned char)*p, rows));
        int on = 0;
        for (int r = 0; r < 7; r++) on += rows[r] != 0;
        CHECK(on > 0);
    }
    for (unsigned c = 1; c <= 9; c++) CHECK(rsx_overlay_glyph_rows(c, rows));
    for (unsigned c : { 0x0Bu, 0x0Cu, 0x0Eu, 0x0Fu, 0x10u, 0x11u, 0x12u }) CHECK(rsx_overlay_glyph_rows(c, rows));
    CHECK(rsx_overlay_glyph_rows(' ', rows));
    for (int r = 0; r < 7; r++) CHECK_EQ(rows[r], 0);
    /* no two letters, digits or directions look the same */
    std::vector<unsigned> distinct;
    for (const char* p = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"; *p; p++) distinct.push_back((unsigned char)*p);
    for (unsigned c = 1; c <= 9; c++) distinct.push_back(c);
    for (size_t i = 0; i < distinct.size(); i++)
        for (size_t j = i + 1; j < distinct.size(); j++) {
            rsx_overlay_glyph_rows(distinct[i], rows);
            rsx_overlay_glyph_rows(distinct[j], other);
            if (!memcmp(rows, other, 7)) { g_fail++; printf("FAIL glyphs 0x%02X and 0x%02X are the same\n", distinct[i], distinct[j]); }
            g_checks++;
        }
    CHECK(!rsx_overlay_glyph_rows(0x7F, rows));
    CHECK(!rsx_overlay_glyph_rows(200, rows));
}

static bool whole(float v) { return floorf(v) == v; }

static void test_layout()
{
    static rsx_overlay_quad q[256];
    const uint32_t white = RSX_OVL_RGBA(255, 255, 255, 255);
    rsx_overlay_begin();
    rsx_overlay_text(100, 200, 2, white, 0, "i10");
    rsx_overlay_end();
    int n = rsx_overlay_layout(1280, 720, 1280, 720, q, 256);
    CHECK_EQ(n, 3);
    if (n == 3) {
        CHECK_EQ(q[0].x0, 100); CHECK_EQ(q[0].y0, 200); CHECK_EQ(q[0].x1, 110); CHECK_EQ(q[0].y1, 214);
        CHECK_EQ(q[1].x0, 112); CHECK_EQ(q[2].x0, 124);
        CHECK_EQ(q[0].glyph, 'i'); CHECK_EQ(q[1].glyph, '1'); CHECK_EQ(q[2].glyph, '0');
        CHECK_EQ(q[0].rgba, white);
    }
    /* 1080p window: 3 window pixels per font pixel */
    n = rsx_overlay_layout(1920, 1080, 1280, 720, q, 256);
    CHECK_EQ(n, 3);
    if (n == 3) { CHECK_EQ(q[0].x0, 150); CHECK_EQ(q[0].y0, 300); CHECK_EQ(q[0].x1 - q[0].x0, 15); CHECK_EQ(q[0].y1 - q[0].y0, 21); CHECK_EQ(q[1].x0, 168); }
    /* a 16:10 window: bars above and below, the canvas inside the picture */
    n = rsx_overlay_layout(1920, 1200, 1280, 720, q, 256);
    CHECK_EQ(n, 3);
    if (n == 3) { CHECK_EQ(q[0].x0, 150); CHECK_EQ(q[0].y0, 360); }
    /* odd sizes: everything on whole pixels, glyphs a whole number of pixels per font pixel */
    const uint32_t sizes[][2] = { { 1366, 768 }, { 1600, 900 }, { 2560, 1440 }, { 3440, 1440 }, { 3840, 2160 }, { 800, 600 } };
    for (auto& sz : sizes) {
        n = rsx_overlay_layout(sz[0], sz[1], 1280, 720, q, 256);
        CHECK_EQ(n, 3);
        for (int i = 0; i < n; i++) {
            CHECK(whole(q[i].x0) && whole(q[i].y0) && whole(q[i].x1) && whole(q[i].y1));
            const float w = q[i].x1 - q[i].x0, h = q[i].y1 - q[i].y0;
            CHECK(fmodf(w, 5.0f) == 0.0f && fmodf(h, 7.0f) == 0.0f && w / 5.0f == h / 7.0f && w >= 5.0f);
        }
    }
    /* right / centre alignment, shadow, boxes, spaces, UTF-8 */
    rsx_overlay_begin();
    rsx_overlay_text(1000, 10, 2, white, RSX_OVL_RIGHT, "+3");
    rsx_overlay_text(640, 40, 1, white, RSX_OVL_CENTER | RSX_OVL_SHADOW, "a b");
    rsx_overlay_rect(10.4f, 20.6f, 100.0f, 30.0f, RSX_OVL_RGBA(0, 0, 0, 150));
    rsx_overlay_text(0, 100, 1, white, 0, "\xC3\x84\xC3\x96\xC3\x9C\xC3\xA4\xC3\xB6\xC3\xBC\xC3\x9F\xE2\x82\xAC\x01\x09");
    rsx_overlay_end();
    n = rsx_overlay_layout(1280, 720, 1280, 720, q, 256);
    CHECK_EQ(n, 2 + 4 + 1 + 10);
    if (n == 17) {
        CHECK_EQ(q[1].x1, 1000);                                   /* right edge of "+3" */
        CHECK_EQ(q[0].x0, 1000 - (2 * 6 - 1) * 2);
        CHECK_EQ(q[2].rgba & 0xFFFFFF00u, 0);                      /* shadows first, black */
        CHECK_EQ(q[2].x0 - q[4].x0, 1);                            /* one font pixel down-right */
        CHECK_EQ(q[2].y0 - q[4].y0, 1);
        CHECK_EQ(q[4].x0, 640 - floorf((3 * 6 - 1) * 0.5f + 0.5f));
        CHECK_EQ(q[5].x0 - q[4].x0, 12);                           /* the space is skipped, not drawn */
        CHECK_EQ(q[6].glyph, -1);
        CHECK_EQ(q[6].x0, 10); CHECK_EQ(q[6].y0, 21); CHECK_EQ(q[6].x1, 110); CHECK_EQ(q[6].y1, 51);
        const int want[] = { 0x0B, 0x0C, 0x0E, 0x10, 0x11, 0x12, 0x0F, '?', 1, 9 };
        for (int i = 0; i < 10; i++) CHECK_EQ(q[7 + i].glyph, want[i]);
    }
    CHECK_EQ(rsx_overlay_text_width("+3", 2), 22);
    CHECK_EQ(rsx_overlay_text_width("", 2), 0);
    CHECK_EQ(rsx_overlay_text_width("\xC3\x84x", 1), 11);
    /* a list without end() is not shown; clear() empties it */
    rsx_overlay_begin();
    rsx_overlay_text(0, 0, 1, white, 0, "unpublished");
    CHECK_EQ(rsx_overlay_layout(1280, 720, 1280, 720, q, 256), 17);
    rsx_overlay_end();
    CHECK_EQ(rsx_overlay_layout(1280, 720, 1280, 720, q, 256), 11);
    rsx_overlay_clear();
    CHECK_EQ(rsx_overlay_layout(1280, 720, 1280, 720, q, 256), 0);
    /* the quad budget is respected */
    CHECK_EQ(rsx_overlay_layout(1280, 720, 1280, 720, q, 0), 0);
}

int main()
{
    test_notation();
    test_history();
    test_jab_block_and_hit();
    test_defender_presses();
    test_whiff_and_walk();
    test_string();
    test_down_and_counter();
    test_font();
    test_layout();
    if (g_fail) {
        printf("FAILED %d of %d checks\n", g_fail, g_checks);
        return 1;
    }
    printf("PASS %d checks\n", g_checks);
    return 0;
}
