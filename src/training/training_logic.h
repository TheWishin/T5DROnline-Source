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
 *                block/hit reactions have 0 or >= 0x10000)
 *   +0x168  u32  the current move/animation; 0x8001xxxx = standing, 0x8002..
 *                0x80FF = the defaults of other stances, among them lying on
 *                the ground after a knockdown or a throw (0x8004..0x8007 seen)
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
 *   +0x6D4  u16  the pad input the fighter read this frame (the game's mask:
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
    bool     down = false;   /* +0x168 in the 0x8002..0x80FF family: lying on the ground */
    uint32_t cls = 0;        /* +0x15C */
    int      hp = 0;         /* +0x6BC */
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
    int      startup = 0;    /* first active frame of the move that made contact (0 = unknown) */
    Kind     kind = Kind::Block;
    int      adv = 0;        /* attacker's frame advantage (Block/Hit/Counter) */
    int      total = 0;      /* Whiff: frames until the attacker could act again */
    uint64_t frame = 0;      /* the frame it was settled in */
};

class Tracker {
public:
    /* knockdowns: the defender not able to act this long after the attacker */
    static constexpr uint64_t kDownAfter = 90;
    /* a defender's press that started nothing: its can-act frame after all */
    static constexpr uint64_t kPressWait = 20;
    static constexpr uint16_t kButtons = kSquare | kTriangle | kCross | kCircle;

    /* One live frame, both fighters (index 0 = P1). Returns true when a new
     * Result is in last(). */
    bool frame(const Sample s[2])
    {
        bool out = false;
        const uint64_t t = t_++;
        if (!have_prev_) {
            prev_[0] = s[0]; prev_[1] = s[1];
            have_prev_ = true;
            return false;
        }
        /* 1. first active frame of each fighter's current move */
        for (int p = 0; p < 2; p++)
            if (s[p].active && mv_[p].live && !mv_[p].first_active) mv_[p].first_active = t;
        /* 2. contact: the other one starts a block/hit reaction right after
         *    this one's active frame, or loses health while it is active.
         *    (Before step 3: a string's next move may start in this frame.) */
        for (int p = 0; p < 2; p++) {
            const int o = 1 - p;
            const bool reacts = prev_[p].active && s[o].new_move && !acts(s[o]) && is_reaction_cls(s[o].cls);
            const bool damaged = s[o].hp < prev_[o].hp && (prev_[p].active || s[p].active);
            if (!reacts && !damaged) continue;
            if (ex_.open && ex_.att == p && !ex_.settled) {
                /* the same attacker again (a string, a juggle): recoveries start over */
                ex_.att_act = ex_.def_act = ex_.def_flag = 0;
                ex_.def_btn = false;
                ex_.contact = t;
            } else {
                ex_ = Exchange{};
                ex_.open = true;
                ex_.att = p;
                ex_.contact = t;
                ex_.startup = mv_[p].first_active && mv_[p].start ? (int)(mv_[p].first_active - mv_[p].start + 1) : 0;
                ex_.counter = !acts(prev_[o]) && is_attack_cls(prev_[o].cls);
            }
            mv_[p].contacted = true;
        }
        /* 3. moves started by a fighter (not a reaction to the other's attack) */
        bool started[2] = { false, false };
        for (int p = 0; p < 2; p++) {
            const int o = 1 - p;
            const bool reaction = prev_[o].active && is_reaction_cls(s[p].cls);
            if (s[p].new_move && !acts(s[p]) && !reaction && !s[p].down) {   /* lying down is no move of its own */
                started[p] = true;
                mv_[p] = Move{};
                mv_[p].start = t;
                mv_[p].live = true;
            }
        }
        /* 4. damage decides hit or block */
        if (ex_.open && !ex_.settled && s[ex_.def()].hp < prev_[ex_.def()].hp) ex_.hit = true;
        if (ex_.open && !ex_.settled && s[ex_.def()].down) ex_.down = true;   /* knocked down or thrown */
        /* 5. recoveries. The attacker can act from its can-act frame (a
         *    string's next move before it keeps the exchange going). The
         *    defender likewise -- unless it has pressed an attack button since
         *    the contact: the game then opens the can-act window early to keep
         *    the press for the end of the stun, and the move it starts there
         *    (one frame after the frame it could act) is what counts. */
        if (ex_.open && !ex_.settled) {
            const int a = ex_.att, d = ex_.def();
            if (t > ex_.contact && (s[d].input & kButtons)) ex_.def_btn = true;
            if (!ex_.att_act && t > ex_.contact && acts(s[a])) ex_.att_act = t;
            if (!ex_.def_act && t > ex_.contact) {
                if (started[d]) ex_.def_act = t - 1;
                else if (acts(s[d])) {
                    if (!ex_.def_btn) ex_.def_act = t;
                    else if (!ex_.def_flag) ex_.def_flag = t;
                }
                if (!ex_.def_act && ex_.def_flag && t - ex_.def_flag > kPressWait) ex_.def_act = ex_.def_flag;
            }
            if (ex_.att_act && ex_.def_act) {
                last_ = Result{};
                last_.attacker = a;
                last_.startup = ex_.startup;
                last_.kind = ex_.down ? Kind::Down : ex_.hit ? (ex_.counter ? Kind::Counter : Kind::Hit) : Kind::Block;
                last_.adv = ex_.down ? 0 : (int)((int64_t)ex_.def_act - (int64_t)ex_.att_act);
                last_.frame = t;
                ex_.settled = true;
                out = true;
            } else if (ex_.att_act && t - ex_.att_act > kDownAfter) {
                last_ = Result{};
                last_.attacker = a;
                last_.startup = ex_.startup;
                last_.kind = Kind::Down;
                last_.frame = t;
                ex_.settled = true;
                out = true;
            }
        }
        /* 6. whiffs: an attack whose active frames hit nothing, over */
        for (int p = 0; p < 2; p++) {
            if (!mv_[p].live) continue;
            if (acts(s[p]) && !acts(prev_[p])) {
                if (mv_[p].first_active && !mv_[p].contacted) {
                    last_ = Result{};
                    last_.attacker = p;
                    last_.startup = (int)(mv_[p].first_active - mv_[p].start + 1);
                    last_.kind = Kind::Whiff;
                    last_.total = (int)(t - mv_[p].start);
                    last_.frame = t;
                    out = true;
                }
                mv_[p].live = false;
            }
        }
        prev_[0] = s[0]; prev_[1] = s[1];
        return out;
    }

    void reset() { *this = Tracker{}; }
    const Result& last() const { return last_; }

private:
    static bool is_reaction_cls(uint32_t c) { return c == 0 || c >= 0x10000; }
    /* able to act: in a hit reaction only at its cancellable end (see Sample) */
    static bool acts(const Sample& x) { return x.can_act && (x.cls < 0x10000 || x.end_window); }
    static bool is_attack_cls(uint32_t c) { return c != 0 && c < 0x10000; }
    struct Move { uint64_t start = 0, first_active = 0; bool live = false, contacted = false; };
    struct Exchange {
        bool open = false, settled = false, hit = false, counter = false, def_btn = false, down = false;
        int att = 0, startup = 0;
        uint64_t contact = 0, att_act = 0, def_act = 0, def_flag = 0;
        int def() const { return 1 - att; }
    };
    Sample prev_[2];
    bool have_prev_ = false;
    uint64_t t_ = 1;          /* frame numbers start at 1: 0 means "not yet" */
    Move mv_[2];
    Exchange ex_;
    Result last_;
};

} // namespace training
