/*
 * T5DR training overlay -- the logic, without the game or the screen
 * (docs/TRAINING.md). training.cpp fills one Sample per fighter per live
 * frame from the fight blocks (read only) and draws what Tracker keeps;
 * tests/c/training_test.cpp feeds it synthetic frames.
 *
 * Fight block fields (NPUB30009 v01.00; P1 block 0x10090030, P2 0x10090900,
 * 0x8D0 apart), found by tracing scripted fights frame by frame
 * (docs/TRAINING.md "How the frame data is measured"):
 *   +0x15C  u32  attack class of the current move: 0 = none (idle, walk,
 *                a guard); a hit reaction has the hits of the combo in the
 *                upper half (0x10000, 0x20000, ...) -- a hit even without
 *                damage (Bryan's taunt 1+3+4 stuns for 0)
 *   +0x168  u32  the current move/animation; 0x8001xxxx = standing, 0x8002..
 *                0x80FF = the defaults of other stances: 0x8002 crouching,
 *                0x8004 and up lying on the ground after a knockdown, a throw
 *                or a slide (0x8004..0x8007, 0x8009, 0x800A seen)
 *   +0x1D2  u8   1 = this fighter stands on the right side (faces left)
 *   +0x20C  u32  bit 24: a new move (animation) started this frame
 *   +0x214  u32  bits 16-17: the move's attack is active this frame
 *   +0x21C  u32  bit 0, together with
 *   +0x220  u32  the fighter can act: +0x220 low byte 1 and either +0x220 bit
 *                24 (the cancellable end of a move, of a block or of a hit
 *                reaction) or +0x21C bit 0 (idle, walking, crouching). Bit 24
 *                alone (low byte 0) is the window in which a press is kept for
 *                the end of the move: not yet able to act. In a hit
 *                reaction (+0x15C >= 0x10000) only the cancellable end
 *                counts: some reactions set the idle bit long before it
 *                (Bryan's d+4 on hit, reaction 0x0307: +0x21C bit 0 nine
 *                frames in, bit 24 at 29; a jab pressed from frame 9 on
 *                still comes out at 30 -- the game's own answer, so +3 on
 *                hit, not -17).
 *   +0x6BC  i16  health
 *   +0x734  f32  the height of the fighter's root (its hips: row 3 of the root's
 *                world matrix at +0x700): ~1,000-1,150 standing (Kuma ~850),
 *                ~840 crouching, 650-1,100 in the hit and guard reactions that
 *                end on the feet, 140-300 lying on the ground or landing in a
 *                tech roll, up to ~2,400 in the air after a launcher
 *   +0x6D6  u16  the pad input the fighter read this frame (the game's mask:
 *                UP 0x1000 RIGHT 0x2000 DOWN 0x4000 LEFT 0x8000, TRIANGLE 0x10
 *                CIRCLE 0x20 CROSS 0x40 SQUARE 0x80)
 * Frame advantage = the frame the defender can act again minus the frame the
 * attacker can act again; a frame-exact test where both
 * fighters press a jab as early as the game lets them gives exactly that
 * difference.
 */
#pragma once
#include <stdint.h>
#include <string.h>
#include <math.h>
#include <stdio.h>

namespace training {

/* the game's pad mask */
enum : uint16_t {
    kUp = 0x1000, kRight = 0x2000, kDown = 0x4000, kLeft = 0x8000,
    kTriangle = 0x10, kCircle = 0x20, kCross = 0x40, kSquare = 0x80,
};

/* One fighter in one frame (what training.cpp reads). */
struct Sample {
    uint16_t input = 0;      /* +0x6D4 */
    bool     right = false;  /* +0x1D2: on the right side, facing left */
    bool     can_act = true; /* +0x220 / +0x21C, see above */
    bool     end_window = false; /* +0x220 low byte 1 and bit 24: the cancellable end of a move or reaction */
    bool     new_move = false;
    bool     active = false; /* +0x214 bits 16-17 */
    bool     down = false;   /* +0x168 in the 0x8004..0x80FF family: lying on the ground */
    bool     stand = false;  /* +0x168 0x8001: standing (its height is the fighter's own measure) */
    uint32_t cls = 0;        /* +0x15C */
    int      hp = 0;         /* +0x6BC */
    float    y = 0;          /* +0x734: the hips' height (0: not read) */
};

/* Tekken notation for an input: direction 1..9 (numpad, 5 = neutral) as the
 * fighter sees it (6 = toward the opponent), buttons 1 2 3 4 as bits 0..3 in
 * the game's default button setting (1 = SQUARE, 2 = TRIANGLE, 3 = CROSS,
 * 4 = CIRCLE). Left + right together counts as neither. */
struct Notation { uint8_t dir; uint8_t buttons; };
inline Notation notation(uint16_t in, bool facing_left)
{
    const bool up = in & kUp, down = in & kDown;
    bool fwd = in & (facing_left ? kLeft : kRight), back = in & (facing_left ? kRight : kLeft);
    if (fwd && back) fwd = back = false;
    const int col = back ? 0 : fwd ? 2 : 1;
    const int row = (up && !down) ? 2 : (down && !up) ? 0 : 1;
    Notation n;
    n.dir = (uint8_t)(row * 3 + col + 1);
    n.buttons = (uint8_t)(((in & kSquare) ? 1 : 0) | ((in & kTriangle) ? 2 : 0) | ((in & kCross) ? 4 : 0) |
                          ((in & kCircle) ? 8 : 0));
    return n;
}

/* "1+2", "3", "" */
inline void buttons_text(uint8_t b, char* out, size_t n)
{
    size_t k = 0;
    for (int i = 0; i < 4 && k + 2 < n; i++)
        if (b & (1 << i)) {
            if (k) out[k++] = '+';
            out[k++] = (char)('1' + i);
        }
    out[k] = 0;
}

/* ---- input history ---------------------------------------------------------- */
struct HistoryRow { Notation n; uint32_t frames; };

template <int N> struct History {
    HistoryRow rows[N];
    int count = 0;           /* rows in use, rows[0] newest */
    void clear() { count = 0; }
    void push(Notation n)
    {
        if (count && rows[0].n.dir == n.dir && rows[0].n.buttons == n.buttons) {
            if (rows[0].frames < 0xFFFFFFFFu) rows[0].frames++;
            return;
        }
        const int keep = count < N ? count : N - 1;
        memmove(&rows[1], &rows[0], sizeof(HistoryRow) * (size_t)keep);
        rows[0].n = n;
        rows[0].frames = 1;
        count = keep + 1;
    }
};

/* ---- frame data --------------------------------------------------------------- */
enum class Kind : uint8_t { Block, Hit, Counter, Whiff, Down };

struct Result {
    int      attacker = 0;   /* 0 = P1, 1 = P2 */
    int      startup = 0;    /* first active frame of the hit that made contact, counted from the start of
                              * its move (0 = unknown) */
    int      active_end = 0; /* last frame of that active window (the same count; == startup: one frame) */
    Kind     kind = Kind::Block;
    bool     counter = false;/* Down: the knockdown came from a counter hit */
    bool     no_adv = false; /* no advantage of its own (Whiff: no total): a string's (or a juggle's) hit
                              * that the attacker's next hit followed before either could act, or a hit
                              * after which the attacker lies on the ground (Nina's slide d/b+4) */
    int      adv = 0;        /* attacker's frame advantage (Block/Hit/Counter, not no_adv) */
    int      total = 0;      /* Whiff: frames until the attacker could act again */
    uint64_t frame = 0;      /* the frame it was settled in */
};

/* able to act: in a hit reaction only at its cancellable end (see Sample) */
inline bool acts(const Sample& x) { return x.can_act && (x.cls < 0x10000 || x.end_window); }

class Tracker {
public:
    /* knockdowns that were not seen (no height): the defender not able to act this long after the attacker */
    static constexpr uint64_t kDownAfter = 90;
    /* a defender's press that started nothing: its can-act frame after all */
    static constexpr uint64_t kPressWait = 20;
    static constexpr uint16_t kButtons = kSquare | kTriangle | kCross | kCircle;
    /* knocked down: the defender's hips below this share of its standing height (lying, a tech roll:
     * <= 0.3 traced; crouching 0.8, the lowest reaction that ends on the feet 0.75) or above this one
     * (launched: up to 2.3; the highest reaction on the feet 1.1) */
    static constexpr float kLowShare = 0.5f, kAirShare = 1.4f;
    static constexpr int kQueue = 4;

    /* One live frame, both fighters (index 0 = P1). Returns the number of new
     * Results (0 = none): result(0) .. result(n - 1), oldest first; last() is the newest. */
    int frame(const Sample s[2])
    {
        nnew_ = 0;
        const uint64_t t = t_++;
        for (int p = 0; p < 2; p++)
            if (s[p].stand && s[p].y > 0 && acts(s[p])) stand_y_[p] = s[p].y;
        if (!have_prev_) {
            prev_[0] = s[0]; prev_[1] = s[1];
            have_prev_ = true;
            return 0;
        }
        for (int p = 0; p < 2; p++) {
            if (s[p].new_move) anim_[p] = t;
            /* button presses not yet taken by a new move: each new animation started with one is a
             * move of its own (a string's next hit), one without continues the move (its wind-up, its
             * next animation, its recovery). Presses while the fighter can act start its next move. */
            if (acts(s[p])) presses_[p] = 0;
            if (s[p].input & ~prev_[p].input & kButtons) presses_[p]++;
        }
        /* 1. the active windows of each fighter's current move. An attack can also come out of an
         *    animation in which its fighter can act all along (step 3 then saw no move start):
         *    Bryan's taunt 1+3+4 -- cancellable from its first frame to its last active frame, active
         *    28 frames in. Its move began with that animation. */
        for (int p = 0; p < 2; p++) {
            if (!s[p].active) continue;
            Move& m = mv_[p];
            if (!m.live) {
                m = Move{};
                m.start = anim_[p] ? anim_[p] : t;
                m.live = true;
            }
            if (!m.first_active) m.first_active = t;
            if (m.win_end && m.win_end + 1 == t) m.win_end = t;
            else m.win_start = m.win_end = t;
        }
        /* 2. contact: the other one starts a block/hit reaction right after this one's active frame,
         *    or loses health while it is active. (Before step 3: a string's next hit may start in
         *    this frame.) */
        bool hit_now[2] = { false, false };
        for (int p = 0; p < 2; p++) {
            const int o = 1 - p;
            const bool reacts = prev_[p].active && s[o].new_move && !acts(s[o]) && is_reaction_cls(s[o].cls);
            const bool damaged = s[o].hp < prev_[o].hp && (prev_[p].active || s[p].active);
            if (!reacts && !damaged) continue;
            hit_now[o] = true;
            const Move& m = mv_[p];
            const bool known = m.live && m.win_start && m.start;
            /* a hit reaction (+0x15C >= 0x10000, a guard has 0) is a hit even without damage: Bryan's
             * taunt stuns for 0 damage, guard or not */
            const bool stun = s[o].cls >= 0x10000;
            if (ex_.open && ex_.att == p && !ex_.settled) {
                if (!known || m.start != ex_.move || m.win_start != ex_.win) {
                    /* the same attacker's next hit (a string, a juggle) before either could act: the
                     * hit before is shown without an advantage, recoveries start over */
                    emit_part(t);
                    ex_.first = false;
                    ex_.hit = ex_.down = false;
                    start_part(m, known);
                }
                ex_.att_act = ex_.def_act = ex_.def_flag = 0;
                ex_.def_btn = false;
                ex_.contact = t;
            } else {
                ex_ = Exchange{};
                ex_.open = true;
                ex_.first = true;
                ex_.att = p;
                ex_.contact = t;
                /* only the move going on now: an older one's startup is no answer */
                start_part(m, known);
                ex_.counter = !acts(prev_[o]) && is_attack_cls(prev_[o].cls);
            }
            if (stun) ex_.hit = true;
            mv_[p].contacted = true;
        }
        /* the defender's own move ended with the hit (a counter hit) */
        for (int p = 0; p < 2; p++)
            if (hit_now[p]) mv_[p].live = false;
        /* the window of the open hit may go on after the contact (DJ's 1,2,3: the 3 active 7 frames,
         * blocked in its 6th) */
        if (ex_.open && !ex_.settled) {
            const Move& m = mv_[ex_.att];
            if (m.live && m.start == ex_.move && m.win_start == ex_.win && m.win_end >= ex_.win)
                ex_.active_end = (int)(m.win_end - m.start + 1);
        }
        /* 3. moves started by a fighter (not a reaction to the other's attack, not one of its own hit
         *    reactions, not lying down). A new animation without a press for it continues the move:
         *    a wind-up without active frames, then the attack (Bryan's f+1+2: 18 frames of wind-up,
         *    active 3 frames into the second animation), an attack whose active frame opens an
         *    animation (Devil Jin's jab), a recovery. */
        bool started[2] = { false, false };
        for (int p = 0; p < 2; p++) {
            const int o = 1 - p;
            const bool reaction = prev_[o].active && is_reaction_cls(s[p].cls);
            Move& m = mv_[p];
            if (s[p].down && m.live) {                      /* lying on the ground ends the fighter's own move */
                if (m.first_active && !m.contacted) whiff_part(p, t);
                m.live = false;
            }
            if (!s[p].new_move || acts(s[p]) || reaction || s[p].down || s[p].cls >= 0x10000) continue;
            if (s[p].active) continue;                      /* an attack is never active in its own first frame */
            if (m.live && !presses_[p] && !acts(prev_[p])) continue;
            if (presses_[p]) presses_[p]--;
            if (m.live && m.first_active && !m.contacted) whiff_part(p, t);   /* a string's hit into the air, the next one follows */
            started[p] = true;
            m = Move{};
            m.start = t;
            m.live = true;
        }
        /* 4. damage (or a hit reaction, step 2) decides hit or block; the defender's hips on the
         *    ground or in the air: knocked down (a sweep, a launcher, a throw; a tech roll too) */
        if (ex_.open && !ex_.settled) {
            const int d = ex_.def();
            if (s[d].hp < prev_[d].hp) ex_.hit = true;
            if (!acts(s[d]) && (s[d].down || knocked(s[d], stand_y_[d]))) ex_.down = true;
            if (s[ex_.att].down && !acts(s[ex_.att])) ex_.att_down = true;
        }
        /* 5. recoveries. The attacker can act from its can-act frame (a string's next move before it
         *    keeps the exchange going). The defender likewise -- unless it has pressed an attack button
         *    since the contact: the game then opens the can-act window early to keep the press for the
         *    end of the stun, and the move it starts there (one frame after the frame it could act) is
         *    what counts. A defender knocked down: KND, without a number, as soon as it is seen. */
        if (ex_.open && !ex_.settled) {
            const int a = ex_.att, d = ex_.def();
            if (t > ex_.contact && (s[d].input & kButtons)) ex_.def_btn = true;
            if (!ex_.att_act && t > ex_.contact && acts(s[a])) ex_.att_act = t;
            if (!ex_.def_act && t > ex_.contact) {
                if (started[d] && ex_.def_btn) ex_.def_act = t - 1;
                else if (acts(s[d])) {
                    if (!ex_.def_btn) ex_.def_act = t;
                    else if (!ex_.def_flag) ex_.def_flag = t;
                }
                if (!ex_.def_act && ex_.def_flag && t - ex_.def_flag > kPressWait) ex_.def_act = ex_.def_flag;
            }
            if (ex_.down || (ex_.att_act && !ex_.def_act && t - ex_.att_act > kDownAfter)) {
                Result r = part_result(t);
                r.kind = Kind::Down;
                r.counter = ex_.first && ex_.counter;
                push(r);
                ex_.settled = true;
            } else if (ex_.att_act && ex_.def_act) {
                Result r = part_result(t);
                r.adv = (int)((int64_t)ex_.def_act - (int64_t)ex_.att_act);
                push(r);
                ex_.settled = true;
            } else if (ex_.def_act && ex_.att_down) {     /* the attacker on the ground, the defender free: no number */
                Result r = part_result(t);
                r.no_adv = true;
                push(r);
                ex_.settled = true;
            }
        }
        /* 6. whiffs: an attack whose active frames hit nothing, over */
        for (int p = 0; p < 2; p++) {
            Move& m = mv_[p];
            if (!m.live) continue;
            if (acts(s[p]) && !acts(prev_[p])) {
                if (m.first_active && !m.contacted) {
                    Result r;
                    r.attacker = p;
                    r.startup = (int)(m.win_start - m.start + 1);
                    r.active_end = (int)(m.win_end - m.start + 1);
                    r.kind = Kind::Whiff;
                    r.total = (int)(t - m.start);
                    r.frame = t;
                    push(r);
                }
                m.live = false;
            }
        }
        prev_[0] = s[0]; prev_[1] = s[1];
        return nnew_;
    }

    void reset() { *this = Tracker{}; }
    const Result& last() const { return last_; }
    const Result& result(int i) const { return q_[i]; }

    /* the defender's hips (y) against its own standing height (0: not seen yet) */
    static bool knocked(const Sample& x, float stand)
    {
        return stand > 0 && x.y > 0 && (x.y < kLowShare * stand || x.y > kAirShare * stand);
    }

private:
    static bool is_reaction_cls(uint32_t c) { return c == 0 || c >= 0x10000; }
    static bool is_attack_cls(uint32_t c) { return c != 0 && c < 0x10000; }
    /* a move: from the animation it began with; win_*: its latest active window (frames of the tracker) */
    struct Move { uint64_t start = 0, first_active = 0, win_start = 0, win_end = 0; bool live = false, contacted = false; };
    struct Exchange {
        bool open = false, settled = false, hit = false, counter = false, def_btn = false, down = false, att_down = false;
        bool first = true;    /* the exchange's first hit (a counter hit is decided there) */
        int att = 0, startup = 0, active_end = 0;
        uint64_t move = 0, win = 0;   /* the hit going on: its move's start and its active window's first frame */
        uint64_t contact = 0, att_act = 0, def_act = 0, def_flag = 0;
        int def() const { return 1 - att; }
    };
    void start_part(const Move& m, bool known)
    {
        ex_.move = known ? m.start : 0;
        ex_.win = known ? m.win_start : 0;
        ex_.startup = known ? (int)(m.win_start - m.start + 1) : 0;
        ex_.active_end = known ? (int)(m.win_end - m.start + 1) : 0;
    }
    Result part_result(uint64_t t) const
    {
        Result r;
        r.attacker = ex_.att;
        r.startup = ex_.startup;
        r.active_end = ex_.active_end;
        r.kind = ex_.hit ? (ex_.first && ex_.counter ? Kind::Counter : Kind::Hit) : Kind::Block;
        r.frame = t;
        return r;
    }
    void emit_part(uint64_t t)
    {
        Result r = part_result(t);
        if (ex_.down) { r.kind = Kind::Down; r.counter = ex_.first && ex_.counter; }
        r.no_adv = true;
        push(r);
    }
    void whiff_part(int p, uint64_t t)
    {
        const Move& m = mv_[p];
        Result r;
        r.attacker = p;
        r.startup = (int)(m.win_start - m.start + 1);
        r.active_end = (int)(m.win_end - m.start + 1);
        r.kind = Kind::Whiff;
        r.no_adv = true;
        r.frame = t;
        push(r);
    }
    void push(const Result& r)
    {
        if (nnew_ < kQueue) q_[nnew_++] = r;
        else { memmove(&q_[0], &q_[1], sizeof(Result) * (kQueue - 1)); q_[kQueue - 1] = r; }
        last_ = r;
    }
    Sample prev_[2];
    bool have_prev_ = false;
    uint64_t t_ = 1;          /* frame numbers start at 1: 0 means "not yet" */
    uint64_t anim_[2] = { 0, 0 };   /* the frame each fighter's current animation began */
    int presses_[2] = { 0, 0 };
    float stand_y_[2] = { 0, 0 };   /* each fighter's hips when it last stood idle */
    Move mv_[2];
    Exchange ex_;
    Result q_[kQueue];   /* this frame's results, oldest first */
    int nnew_ = 0;
    Result last_;
};

/* One frame-data line, as the overlay shows it (training.cpp draws it): lead "P1  i13~14  BLOCK",
 * tail "-1" (or "KND", "25F", "" -- a string's hit before the next one has no number of its own).
 * The startup is the first active frame of the hit and ~ its last one, the way Tekken frame data
 * writes an active window. de: German labels. */
enum class Tone : uint8_t { White, Grey, Green, Red, Yellow };
inline void format_result(const Result& r, bool de, char* lead, size_t nl, char* tail, size_t nt, Tone* tone)
{
    const char* who = r.attacker ? "P2" : "P1";
    char su[24] = "";
    if (r.startup > 0 && r.active_end > r.startup) snprintf(su, sizeof su, "  i%d~%d", r.startup, r.active_end);
    else if (r.startup > 0) snprintf(su, sizeof su, "  i%d", r.startup);
    const char* hit = de ? "TREFFER" : "HIT";
    const char* counter = de ? "KONTER" : "COUNTER HIT";
    tail[0] = 0;
    *tone = Tone::White;
    switch (r.kind) {
    case Kind::Whiff:
        snprintf(lead, nl, "%s%s  %s", who, su, de ? "DANEBEN" : "WHIFF");
        if (!r.no_adv) snprintf(tail, nt, "%dF", r.total);
        *tone = Tone::Grey;
        return;
    case Kind::Down:      /* knocked down (KND): no number -- lying, it could act again in many ways */
        snprintf(lead, nl, "%s%s  %s", who, su, r.counter ? counter : hit);
        snprintf(tail, nt, "KND");
        *tone = Tone::Yellow;
        return;
    default: break;
    }
    snprintf(lead, nl, "%s%s  %s", who, su,
             r.kind == Kind::Hit ? hit : r.kind == Kind::Counter ? counter : (de ? "GEBLOCKT" : "BLOCK"));
    if (r.no_adv) return;
    snprintf(tail, nt, "%+d", r.adv);
    *tone = r.adv > 0 ? Tone::Green : r.adv < 0 ? Tone::Red : Tone::White;
}

/* Where the overlay's lists go on its 1280 x 720 canvas (training.cpp; y of the first text line,
 * every panel reaching 4 above it and 4 below its last line). Top (the default): the inputs at the
 * screen's edges under the health bars, the frame data under the timer, the practice status line
 * under it. Bottom (T5_TRAINING_POS=bottom): the same at the bottom edge -- the inputs' panels and the
 * frame data end kBottomGap above it (the frame data grows upward, its newest line still on top), the
 * status line above the frame data's three lines. */
struct Layout { float hist_y, results_y, status_y; };
inline Layout overlay_layout(bool bottom, int rows, int nresults, float row_h)
{
    constexpr float kTopHist = 190.0f, kTopResults = 176.0f, kBottomGap = 24.0f;
    if (!bottom) return { kTopHist, kTopResults, kTopResults + row_h * 3 + 14.0f };
    const float end = 720.0f - kBottomGap - 4.0f;          /* where the last line's panel padding begins */
    return { end - row_h * (float)rows, end - row_h * (float)nresults, end - row_h * 4 - 18.0f };
}

/* ==== Practice tools (offline Practice only; docs/TRAINING.md "Practice tools") ====
 * Everything below works on the game's pad masks (P1's as read from the pad, the
 * dummy's as the game will read it) and on Samples; practice.cpp does the reads,
 * the one write per frame into the input ring and the position writes. */
enum : uint16_t { kSelect = 0x0100, kStart = 0x0800 };

/* forward/back as the fighter sees it <-> the pad's left/right (an involution) */
inline uint16_t flip_lr(uint16_t m) { return (uint16_t)((m & ~(kLeft | kRight)) | ((m & kLeft) ? kRight : 0) | ((m & kRight) ? kLeft : 0)); }
inline uint16_t to_rel(uint16_t m, bool facing_left) { return facing_left ? flip_lr(m) : m; }   /* kRight = forward */
inline uint16_t from_rel(uint16_t m, bool facing_left) { return facing_left ? flip_lr(m) : m; }

enum class PAction : uint8_t {
    None,
    ResetRound,        /* SELECT + 3 */
    DummyWallFront,    /* SELECT + f+3: the dummy against the wall in front of you */
    DummyWallBack,     /* SELECT + b+3: the dummy against the wall behind you (you switch sides) */
    PlayerWallFront,   /* SELECT + df+3: you against the wall in front of you (you switch sides) */
    PlayerWallBack,    /* SELECT + db+3: you against the wall behind you */
    Record,            /* SELECT + 1: record into the current slot / stop */
    Play,              /* SELECT + 2: play the current slot once / stop */
    Loop,              /* SELECT + 4: play the current slot again and again / stop */
    SlotNext,          /* SELECT, tap u */
    SlotPrev,          /* SELECT, tap d */
    DummyNext,         /* SELECT, tap f: the dummy's behaviour */
    DummyPrev,         /* SELECT, tap b */
};

/* P1's SELECT combos. While SELECT is held -- and afterwards until P1's pad is
 * neutral again -- P1's input is hidden from the game, so a combo never makes
 * P1 attack, walk or open a menu. Buttons act on their press (with the
 * direction held then); a direction alone acts when it is released, if no
 * button was pressed while it was held. */
class Combo {
public:
    /* in: P1's pad mask this frame; facing_left: P1 stands on the right.
     * Returns the action of this frame; *hide: give the game a neutral P1. */
    PAction frame(uint16_t in, bool facing_left, bool* hide)
    {
        PAction out = PAction::None;
        const bool sel = (in & kSelect) != 0;
        const uint16_t press = (uint16_t)(in & ~prev_);
        const Notation n = notation(in, facing_left);
        if (sel) {
            latched_ = true;
            const uint16_t btn = press & (kSquare | kTriangle | kCross | kCircle);
            if (btn) {
                tap_ = 0;
                if (btn & kCross) {
                    switch (n.dir) {
                    case 5: out = PAction::ResetRound; break;
                    case 6: out = PAction::DummyWallFront; break;
                    case 4: out = PAction::DummyWallBack; break;
                    case 3: out = PAction::PlayerWallFront; break;
                    case 1: out = PAction::PlayerWallBack; break;
                    default: break;
                    }
                } else if (btn & kSquare) out = PAction::Record;
                else if (btn & kTriangle) out = PAction::Play;
                else if (btn & kCircle) out = PAction::Loop;
            } else if (n.dir != dir_) {
                if (dir_ == 5 && !(in & (kSquare | kTriangle | kCross | kCircle))) tap_ = n.dir;   /* a direction from neutral */
                else if (n.dir == 5) {                                                            /* released */
                    switch (tap_) {
                    case 8: out = PAction::SlotNext; break;
                    case 2: out = PAction::SlotPrev; break;
                    case 6: out = PAction::DummyNext; break;
                    case 4: out = PAction::DummyPrev; break;
                    default: break;
                    }
                    tap_ = 0;
                } else tap_ = 0;                                                                  /* changed: not a tap */
            }
        } else {
            tap_ = 0;
            if (latched_ && in == 0) latched_ = false;   /* neutral again: P1 is P1's again */
        }
        *hide = sel || latched_;
        dir_ = n.dir;
        prev_ = in;
        return out;
    }
    void reset() { *this = Combo{}; }

private:
    uint16_t prev_ = 0;
    uint8_t dir_ = 5, tap_ = 0;
    bool latched_ = false;
};

/* ---- positions ---------------------------------------------------------------------
 * A fighter's place on the floor: x and z (+0x10 / +0x18 of its block; y, +0x14,
 * is 0 on the ground) and the angle it faces (+0x30, radians: it looks along
 * (sin a, cos a)). Round start in Practice: P1 at (1000, 0) facing -pi/2, the
 * dummy at (-1000, 0) facing +pi/2. */
struct Place { float x = 0, z = 0, angle = 0; };

inline float face_toward(float fx, float fz, float tx, float tz) { return atan2f(tx - fx, tz - fz); }

/* A turn by d radians of a floor vector (x, z) -- a direction, or a place relative
 * to the fighter: the sense in which the angle grows, so turning the facing
 * direction (sin a, cos a) by d gives (sin(a + d), cos(a + d)). */
inline void turn(float& x, float& z, float d)
{
    const float c = cosf(d), s = sinf(d), nx = x * c + z * s, nz = z * c - x * s;
    x = nx;
    z = nz;
}

/* The wall resets. The walls are the stage's own collision, so they are found
 * with it, not read from the stage: both fighters slide along the line through
 * them, the one that goes to the wall (the mover) in front, the other kGap
 * behind it -- together, because the game also keeps the two fighters within
 * about 6,300 units of each other (traced: one fighter sliding alone was held
 * there, on a stage without a wall that near) -- starting with the mover kGap
 * past the other one, kStep further each frame. A place past a wall is one the
 * game does not keep: it puts the fighter elsewhere (traced in Practice:
 * somewhere inside the stage, not on the line). The first place it did not
 * keep ends the slide; a few frames of halving between it and the last place it
 * kept find the wall to kStep / 2^kRefine. No wall within kMaxSteps: the places
 * from before. Both end kGap apart at the wall, facing each other. */
class Placer {
public:
    static constexpr float kGap = 1100.0f;      /* the distance at the wall: close, in reach of most moves */
    static constexpr float kStep = 500.0f;      /* the slide: units per frame */
    static constexpr int kMaxSteps = 60;        /* 30,000 units (a second) without a wall: none there */
    static constexpr int kRefine = 5;           /* halvings at the wall: within 500 / 32 < 16 units */
    static constexpr float kKept = 80.0f;       /* the game kept a place: it is still within this (traced: a
                                                 * fighter put down moves up to ~30 units by itself, one put
                                                 * past a wall hundreds or thousands) */

    struct Cmd {
        bool done = false;      /* finished: out[] holds both places (P1, the dummy) */
        bool wall = false;      /* ... at a wall (false: the places from before) */
        Place mover, other;     /* not done: where the two go this frame */
        Place out[2];
    };

    /* a wall action (DummyWall*, PlayerWall*): returns false for other actions.
     * *mover: 0 = P1, 1 = the dummy; first: where it goes this frame */
    bool start(PAction a, const Place& p1, const Place& dummy, int* mover, Place* first)
    {
        float ux = dummy.x - p1.x, uz = dummy.z - p1.z;
        const float len = sqrtf(ux * ux + uz * uz);
        if (len > 1.0f) { ux /= len; uz /= len; }
        else { ux = sinf(p1.angle); uz = cosf(p1.angle); }   /* on top of each other: where P1 looks */
        float s;
        switch (a) {
        case PAction::DummyWallFront: mover_ = 1; s = 1; break;
        case PAction::DummyWallBack: mover_ = 1; s = -1; break;
        case PAction::PlayerWallFront: mover_ = 0; s = 1; break;
        case PAction::PlayerWallBack: mover_ = 0; s = -1; break;
        default: return false;
        }
        vx_ = ux * s; vz_ = uz * s;
        before_[0] = p1; before_[1] = dummy;
        k_ = 0;
        refine_ = -1;
        lo_ = kGap; hi_ = 0;
        pending_ = true;
        *mover = mover_;
        *first = at(lo_);
        set_r_ = lo_;
        return true;
    }
    bool pending() const { return pending_; }
    int mover() const { return mover_; }

    /* every frame while pending: the mover's place now (the game ran a frame from the place set last) */
    Cmd next(const Place& now)
    {
        Cmd c;
        const Place want = at(set_r_);
        const float dx = now.x - want.x, dz = now.z - want.z;
        const bool kept = dx * dx + dz * dz <= kKept * kKept;
        if (refine_ < 0) {                       /* sliding */
            if (kept) {
                lo_ = set_r_;
                if (++k_ > kMaxSteps) return finish(false);
                set_r_ = kGap + kStep * (float)k_;
            } else {
                if (set_r_ <= kGap) return finish(true);   /* a wall right behind the other one */
                hi_ = set_r_;
                refine_ = 0;
                set_r_ = (lo_ + hi_) * 0.5f;
            }
        } else {                                 /* halving between the last kept and the first lost place */
            if (kept) lo_ = set_r_; else hi_ = set_r_;
            if (++refine_ >= kRefine) return finish(true);
            set_r_ = (lo_ + hi_) * 0.5f;
        }
        c.mover = at(set_r_);
        c.other = at(set_r_ - kGap);
        c.other.angle = before_[1 - mover_].angle;
        return c;
    }
    void cancel() { pending_ = false; }

private:
    /* the mover's place r past the other fighter, along the line */
    Place at(float r) const
    {
        const Place& o = before_[1 - mover_];
        return Place{ o.x + vx_ * r, o.z + vz_ * r, before_[mover_].angle };
    }
    Cmd finish(bool wall)
    {
        Cmd c;
        pending_ = false;
        c.done = true;
        c.wall = wall;
        if (!wall) { c.out[0] = before_[0]; c.out[1] = before_[1]; return c; }
        const int o = 1 - mover_;
        c.out[mover_] = at(lo_);
        c.out[o] = Place{ c.out[mover_].x - vx_ * kGap, c.out[mover_].z - vz_ * kGap, 0 };
        c.out[mover_].angle = face_toward(c.out[mover_].x, c.out[mover_].z, c.out[o].x, c.out[o].z);
        c.out[o].angle = face_toward(c.out[o].x, c.out[o].z, c.out[mover_].x, c.out[mover_].z);
        return c;
    }
    bool pending_ = false;
    int mover_ = 1, k_ = 0, refine_ = -1;
    float vx_ = 0, vz_ = 0, lo_ = 0, hi_ = 0, set_r_ = 0;
    Place before_[2];
};

/* ---- the dummy's behaviour ------------------------------------------------------ */
enum class DummyMode : uint8_t {
    Game,           /* the game's own dummy (Practice menu), nothing injected */
    BlockAfterHit,  /* stands without guarding; from the first hit on it guards (the game's own) until idle a while */
    Crouch,         /* holds down */
    Walk,           /* walks forward and back */
    Step,           /* sidesteps, one way and then the other */
    Count
};

class Dummy {
public:
    static constexpr int kGuardIdle = 30;     /* BlockAfterHit: guards until it could act this many frames in a row */
    static constexpr int kWalkFrames = 45;    /* Walk: frames each way */
    static constexpr int kStepEvery = 50;     /* Step: a tap of up or down every this many frames */
    static constexpr int kStepTap = 2;

    /* The dummy's pad mask for this frame (0 = neutral), from what the dummy did
     * in the frame that just ran. d: the dummy, prev_hp: its health one frame
     * earlier. Mode Game returns 0 (practice.cpp then injects nothing). */
    uint16_t frame(DummyMode m, const Sample& d, int prev_hp)
    {
        if (m != mode_) { mode_ = m; t_ = 0; guard_ = false; idle_ = 0; }
        const uint16_t back = d.right ? kRight : kLeft, fwd = d.right ? kLeft : kRight;
        uint16_t out = 0;
        switch (m) {
        case DummyMode::BlockAfterHit: {
            const bool hit = d.hp < prev_hp || (d.new_move && d.cls >= 0x10000);
            if (hit) { guard_ = true; idle_ = 0; }
            else if (guard_) {
                idle_ = acts(d) ? idle_ + 1 : 0;
                if (idle_ >= kGuardIdle) guard_ = false;
            }
            out = 0;     /* the game guards (setting()) */
            break; }
        case DummyMode::Crouch: out = kDown; break;
        case DummyMode::Walk: out = (t_ / kWalkFrames) % 2 ? back : fwd; break;
        case DummyMode::Step: {
            const int k = t_ % kStepEvery;
            if (k < kStepTap) out = (t_ / kStepEvery) % 2 ? kDown : kUp;
            break; }
        default: break;
        }
        t_++;
        return out;
    }
    bool guarding() const { return guard_; }
    void reset() { *this = Dummy{}; }

    /* The game's own TRAINING DUMMY setting (Practice menu; 0x1008EFF3, traced:
     * 0 stand without guarding, 1 stand while guarding, 2 crouch without
     * guarding, 3 crouch while guarding, 4 guard against all attacks, 5 standard
     * auto guard, 6/7 quick roll fore/background, 8 quick recovery, 9 backward
     * roll, 10 CONTROLLER: "control with opponent controller", the dummy plays
     * P2's pad) that a behaviour needs this frame, or -1: leave the player's
     * choice. Blocking after the first hit is the game's own guard (it guards
     * lows too): it stands without guarding until the hit, then guards against
     * all attacks; crouching, walking and sidestepping are the dummy's pad
     * (frame()) on CONTROLLER. */
    enum : int { kSetStand = 0, kSetGuardAll = 4, kSetController = 10 };
    int setting(DummyMode m) const
    {
        switch (m) {
        case DummyMode::BlockAfterHit: return guard_ ? kSetGuardAll : kSetStand;
        case DummyMode::Crouch:
        case DummyMode::Walk:
        case DummyMode::Step: return kSetController;
        default: return -1;
        }
    }

private:
    DummyMode mode_ = DummyMode::Game;
    uint32_t t_ = 0;
    bool guard_ = false;
    int idle_ = 0;
};

/* ---- recordings: 5 slots of the dummy's input -------------------------------------
 * Stored as the dummy sees it (forward = toward the opponent), so a recording
 * plays the same from either side. */
class Recorder {
public:
    static constexpr int kSlots = 5;
    static constexpr int kMaxFrames = 60 * 20;   /* 20 s per slot */
    enum class State : uint8_t { Idle, Recording, Playing, Looping };

    int slot() const { return slot_; }
    State state() const { return st_; }
    int length(int s) const { return len_[s]; }
    int pos() const { return pos_; }

    void select(int delta)
    {
        if (st_ != State::Idle) stop();
        slot_ = ((slot_ + delta) % kSlots + kSlots) % kSlots;
    }
    /* SELECT+1: start recording the current slot (its old content goes), or stop */
    void toggle_record()
    {
        if (st_ == State::Recording) { stop(); trim(slot_); return; }
        stop();
        st_ = State::Recording;
        len_[slot_] = 0;
        pos_ = 0;
    }
    /* SELECT+2 / SELECT+4: play once / in a loop, or stop. An empty slot does nothing. */
    void toggle_play(bool loop)
    {
        const State want = loop ? State::Looping : State::Playing;
        if (st_ == want) { stop(); return; }
        stop();
        if (!len_[slot_]) return;
        st_ = want;
        pos_ = 0;
    }
    void stop() { st_ = State::Idle; pos_ = 0; }

    /* Recording: one frame of the recorder's pad (rel: forward = kRight). Stops by itself when the slot is full. */
    void record(uint16_t rel)
    {
        if (st_ != State::Recording) return;
        data_[slot_][len_[slot_]++] = (uint16_t)(rel & ~(kSelect | kStart));
        if (len_[slot_] >= kMaxFrames) { stop(); trim(slot_); }
    }
    /* Playing: the next frame (rel), or false when nothing plays (a single play ends after its last frame) */
    bool next(uint16_t* rel)
    {
        if (st_ != State::Playing && st_ != State::Looping) return false;
        if (pos_ >= len_[slot_]) {
            if (st_ == State::Looping && len_[slot_]) pos_ = 0;
            else { stop(); return false; }
        }
        *rel = data_[slot_][pos_++];
        return true;
    }
    void clear_all() { *this = Recorder{}; }

private:
    /* the neutral frames before the first input go (letting go of the SELECT combo); the
     * rest stays, so a loop keeps its pause at the end */
    void trim(int s)
    {
        int k = 0;
        while (k < len_[s] && !data_[s][k]) k++;
        if (k == len_[s]) { len_[s] = 0; return; }
        memmove(&data_[s][0], &data_[s][k], sizeof(uint16_t) * (size_t)(len_[s] - k));
        len_[s] -= k;
    }
    uint16_t data_[kSlots][kMaxFrames] = {};
    int len_[kSlots] = {};
    int slot_ = 0, pos_ = 0;
    State st_ = State::Idle;
};

} // namespace training
