/*
 * No pause online (src/netplay/no_pause.h) on its own, for tests/test_no_pause.py. No game, no
 * network: a small model of the game decides what START does, two "PCs" run it the way the netplay
 * does (lockstep, rollback with late inputs and re-simulation, replay playback), and the rule sits
 * where t5_hooks.cpp puts it -- between a frame's two inputs and the game.
 *
 * The model game (one match after another, like a persistent online game):
 *   - a fight: game mode, phase 10 (loading) for 30 frames, then phase 17: the P1 intro (round state
 *     1, 60 frames), the P2 intro (2, 60 frames), first to 2 rounds. A round: READY/FIGHT (round
 *     state 4, 20 frames), the fight (5): attack buttons take health, the first player at 0 loses
 *     the round -- KO slow motion (8, 40 frames), the replay (9, 300 frames), on to the next round
 *     (0xC, 60 frames). The second round won decides the match (the decided byte goes up).
 *   - START opens the pause menu (paused: nothing moves; START again closes it) in the fight (5) --
 *     and, to be harsh, in READY/FIGHT (4) as well (the game itself does not there). That is what
 *     must never happen online. START skips the intros (1, 2: one press each), the replay (9) and
 *     the way to the next round (0xC); it does nothing in the KO slow motion (8).
 *   - after the decision (the KO, the replay, the win pose): START from 30 frames on skips to the
 *     select screen (mode_next 6), else the game gets there by itself after 400 frames.
 *   - the select screen (not the game mode) for 50 frames, then the next fight -- with the decided
 *     byte of the last match still set for its first 200 frames, 170 into the fight phase (the game's own
 *     byte stays set ~230 frames into a rematch's fight), while the pause menu works again.
 *
 * Checks (each prints a line; "PASS <n> checks" at the end, exit code 1 on the first failure):
 *   window      the rule's window: opens 40 frames after a decision seen after a fought frame,
 *               closes at mode_next 6, never on the stale byte, not across a frame gap, reset()
 *   parts       the skip parts: which round states, one player's presses never let START through,
 *               both players' (at different frames) start the rule's presses (3 frames every 20)
 *               until the part ends, a part change counts afresh, no part once the match is decided
 *   symmetry    apply() treats both slots alike: apply(swap(in)) == swap(apply(in)), random inputs
 *   lockstep    START mashed by P1, by P2, by both (a modified client: the rule must hold even
 *               when START reaches the wire): never paused; intros, round replays and the way to
 *               the next round skipped only when both pressed, never by one player; the post-match
 *               part still skipped by START; without the rule the same inputs do open the pause
 *               menu (the model has teeth)
 *   rollback    the same with late inputs (0-9 frames, jitter), predictions (the last input
 *               repeats, START included), rollbacks re-simulating with the rule re-recording
 *               boundaries: both PCs' confirmed timelines equal the lockstep reference
 *   replay      the recorded raw inputs played back through the rule: the same hashes
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <vector>

#include "../../src/netplay/no_pause.h"

using np::PadInput;
using np::NoPauseRule;

static int g_checks = 0;
static void check(bool ok, const char* what, long a = 0, long b = 0)
{
    g_checks++;
    if (ok) return;
    printf("FAIL %s (%ld, %ld)\n", what, a, b);
    exit(1);
}

static uint32_t g_x = 0x9E3779B9u;
static uint32_t rnd() { g_x ^= g_x << 13; g_x ^= g_x >> 17; g_x ^= g_x << 5; return g_x; }

/* ---- the model game ---------------------------------------------------------------------- */
struct Game {
    bool game_mode = true;
    uint32_t phase = 10, mode_next = 14, round = 0;
    bool decided_byte = false;   /* what the rule sees (stale into the next fight) */
    bool post = false;           /* the game's own "the match is over" (KO, replay, win pose) */
    bool paused = false;
    uint32_t t = 0, rt = 0;      /* frames in the current scene / round state */
    uint32_t post_t = 0, stale_left = 0, matches = 0, skips = 0, pauses = 0, replays = 0, replay_skips = 0;
    uint32_t intros = 0, intro_skips = 0, next_skips = 0, wasted = 0;   /* wasted: START in the KO slow motion */
    int hp[2] = { 30, 30 }, wins[2] = { 0, 0 };
    uint16_t prev[2] = { 0, 0 };
    uint64_t hash = 1469598103934665603ull;

    NoPauseRule::State facts() const { return { game_mode, phase, decided_byte, mode_next, round }; }
    void mix(uint64_t v) { for (int i = 0; i < 8; i++) { hash ^= (v >> (8 * i)) & 0xFF; hash *= 1099511628211ull; } }
    void to_round(uint32_t r) { round = r; rt = 0; }

    void step(const PadInput in[2])
    {
        bool press_start = false;
        for (int p = 0; p < 2; p++) if ((in[p].buttons & NoPauseRule::kStart) && !(prev[p] & NoPauseRule::kStart)) press_start = true;
        if (game_mode) {
            t++;
            if (stale_left && --stale_left == 0) decided_byte = false;
            if (phase == 10 && t >= 30) { phase = 17; to_round(1); intros++; }
            if (phase == 17 && !post) {
                const bool pausable = round == 4 || round == 5;
                if (press_start && (pausable || paused)) { paused = !paused; if (paused) pauses++; }
                if (!paused) {
                    rt++;
                    if (round == 1 && (press_start || rt >= 60)) { if (rt < 60) intro_skips++; to_round(2); }
                    else if (round == 2 && (press_start || rt >= 60)) { if (rt < 60) intro_skips++; to_round(4); }
                    else if (round == 4 && rt >= 20) to_round(5);
                    else if (round == 5) {
                        for (int p = 0; p < 2; p++) hp[1 - p] -= __builtin_popcount(in[p].buttons & 0xF000u);
                        if (hp[0] <= 0 || hp[1] <= 0) {
                            wins[hp[0] <= 0 ? 1 : 0]++;
                            if (wins[0] >= 2 || wins[1] >= 2) { post = true; decided_byte = true; post_t = 0; stale_left = 0; matches++; }
                            to_round(8);
                        }
                    } else if (round == 8) { if (press_start) wasted++; if (rt >= 40) { to_round(9); replays++; } }
                    else if (round == 9 && (press_start || rt >= 300)) { if (rt < 300) replay_skips++; to_round(0xC); }
                    else if (round == 0xC && (press_start || rt >= 60)) { if (rt < 60) next_skips++; hp[0] = hp[1] = 30; to_round(4); }
                }
            } else if (post) {
                post_t++;
                if (mode_next == 14 && ((press_start && post_t >= 30) || post_t >= 400)) {
                    if (post_t < 400) skips++;
                    mode_next = 6;
                } else if (mode_next == 6) {   /* the select screen */
                    game_mode = false; phase = 1; mode_next = 14; t = 0; post = false; paused = false; round = 0;
                }
            }
        } else if (++t >= 50) {                /* the next fight; the decided byte is still up */
            game_mode = true; phase = 10; t = 0; hp[0] = hp[1] = 30; wins[0] = wins[1] = 0; stale_left = 200; round = 0;
        }
        prev[0] = in[0].buttons; prev[1] = in[1].buttons;
        mix(((uint64_t)game_mode << 40) | ((uint64_t)phase << 32) | ((uint64_t)paused << 31) | ((uint64_t)post << 30) |
            ((uint64_t)round << 24) | ((uint64_t)(hp[0] & 0x7FF) << 12) | (uint64_t)(hp[1] & 0x7FF));
        mix(((uint64_t)in[0].buttons << 16) | in[1].buttons | ((uint64_t)wins[0] << 40) | ((uint64_t)wins[1] << 48));
    }
};

/* A player's raw input for frame f: attacks now and then (so matches end), directions, and START
 * mashed at `start_rate` of the frames (0: never) -- a modified client, or the driver's skip
 * presses sent at every frame (the rule must keep only those in the window). */
static PadInput player_input(uint32_t seed, uint32_t f, uint32_t start_rate)
{
    uint32_t x = seed * 2654435761u ^ (f * 40503u + 0x5bd1e995u);
    x ^= x >> 15; x *= 0x2c1b3c6dU; x ^= x >> 12; x *= 0x297a2d39U; x ^= x >> 15;
    PadInput in = np::kNeutral;
    if ((x & 7) == 0) in.buttons |= (uint16_t)(0x1000u << ((x >> 3) & 3));   /* one of 1/2/3/4 */
    if (((x >> 6) & 3) == 0) in.buttons |= 0x0010u << ((x >> 8) & 3);           /* a direction */
    if (start_rate && ((x >> 10) % start_rate) == 0) in.buttons |= NoPauseRule::kStart;   /* START, mashed */
    return in;
}

/* ---- window ------------------------------------------------------------------------------- */
static const PadInput kNone2[2] = { np::kNeutral, np::kNeutral };
struct Rec {   /* the window part of the rule: record() with neutral inputs, "START kept" */
    NoPauseRule r;
    bool record(uint32_t f, const NoPauseRule::State& st) { return r.record(f, st, kNone2) == NoPauseRule::kKeep; }
    void reset() { r.reset(); }
};
static void test_window()
{
    Rec r;
    NoPauseRule::State fight = { true, 17, false, 14, 5 }, dec = { true, 17, true, 14, 8 };
    uint32_t f = 0;
    for (; f < 100; f++) check(!r.record(f, fight), "window: closed while fought", f);
    const uint32_t d = f;
    for (; f < d + 40; f++) check(!r.record(f, dec), "window: closed for 40 frames after the decision", f - d);
    for (; f < d + 300; f++) check(r.record(f, dec), "window: open from 40 frames after the decision", f - d);
    check(!r.record(f++, { true, 17, true, 6, 9 }), "window: closed once the select screen is asked for");
    for (int k = 0; k < 50; k++, f++) check(!r.record(f, { false, 1, true, 14, 9 }), "window: closed at the select screen");
    /* the next fight with the last match's byte still set: never open */
    for (int k = 0; k < 30; k++, f++) check(!r.record(f, { true, 10, true, 14, 0 }), "window: stale byte in the loading");
    for (uint32_t rs : { 1u, 2u, 4u, 5u, 6u, 8u, 0xCu })
        for (int k = 0; k < 40; k++, f++) check(!r.record(f, { true, 17, true, 14, rs }), "window: stale byte in the fight", k, rs);
    for (int k = 0; k < 20; k++, f++) check(!r.record(f, fight), "window: the new fight");
    /* a frame gap (a scene barrier jumped) between the fight and the decision: no window */
    f += 5;
    for (int k = 0; k < 100; k++, f++) check(!r.record(f, dec), "window: not across a frame gap", k);
    /* the decision after a gap that came after fought frames: a fresh fought frame first */
    for (int k = 0; k < 10; k++, f++) check(!r.record(f, fight), "window: fought again");
    const uint32_t d2 = f;
    for (; f < d2 + 45; f++) check(r.record(f, dec) == (f - d2 >= 40), "window: second match", f - d2);
    /* reset (frame 0 of a new session): history gone, numbering anew */
    r.reset();
    check(!r.record(0, dec) && !r.record(1, dec), "window: reset");
    /* the same frame number recorded twice (a re-simulation) gives the same answer */
    Rec a;
    for (uint32_t g = 0; g < 50; g++) a.record(g, fight);
    for (uint32_t g = 50; g < 120; g++) a.record(g, dec);
    for (uint32_t g = 95; g < 120; g++) check(a.record(g, dec) == (g - 50 >= 40), "window: re-recorded boundaries", g);
    printf("window ok\n");
}

/* ---- parts -------------------------------------------------------------------------------- */
static void test_parts()
{
    /* which round states, only in the game mode's fight phase, not once the select screen is asked for */
    for (uint32_t rs = 0; rs < 40; rs++) {
        const NoPauseRule::Part want = rs == 1 || rs == 2 ? NoPauseRule::kIntro
                                     : rs == 8 || rs == 9 || rs == 0xC ? NoPauseRule::kAfter : NoPauseRule::kNone;
        check(NoPauseRule::part_of({ true, 17, false, 14, rs }) == want, "parts: round states", rs);
        check(NoPauseRule::part_of({ false, 17, false, 14, rs }) == NoPauseRule::kNone, "parts: not outside the game mode", rs);
        check(NoPauseRule::part_of({ true, 12, false, 14, rs }) == NoPauseRule::kNone, "parts: not outside phase 17", rs);
        check(NoPauseRule::part_of({ true, 17, false, 6, rs }) == NoPauseRule::kNone, "parts: not at the select's request", rs);
    }
    PadInput s1[2] = { np::kNeutral, np::kNeutral }, s2[2] = { np::kNeutral, np::kNeutral }, sb[2] = { np::kNeutral, np::kNeutral };
    s1[0].buttons = NoPauseRule::kStart; s2[1].buttons = NoPauseRule::kStart;
    sb[0].buttons = sb[1].buttons = NoPauseRule::kStart;
    for (int who = 0; who < 3; who++) {
        /* one player presses (held, tapped, again and again): START never reaches the game */
        NoPauseRule r;
        uint32_t f = 100;
        for (int k = 0; k < 50; k++, f++) r.record(f, { true, 17, false, 14, 5 }, kNone2);
        for (uint32_t rs : { 1u, 2u, 8u, 9u, 0xCu })
            for (int k = 0; k < 200; k++, f++) {
                PadInput in[2] = { np::kNeutral, np::kNeutral };
                if (k % 7 < (who == 2 ? 7 : 2)) in[who == 1] = who == 0 ? s1[0] : s2[1];
                if (who == 2) { in[0] = s1[0]; in[1] = np::kNeutral; }
                const NoPauseRule::Verdict v = r.record(f, { true, 17, false, 14, rs }, in);
                check(v == NoPauseRule::kCut, "parts: one player never skips", who, k);
                NoPauseRule::apply(v, in);
                check(!(in[0].buttons & NoPauseRule::kStart) && !(in[1].buttons & NoPauseRule::kStart), "parts: START out", who, k);
            }
    }
    /* both, at different frames: the rule presses from the second press on, 3 frames every 20 */
    for (uint32_t rs : { 1u, 2u, 8u, 9u, 0xCu }) {
        NoPauseRule r;
        uint32_t f = 500;
        r.record(f++, { true, 17, false, 14, 5 }, kNone2);
        for (int k = 0; k < 10; k++, f++) check(r.record(f, { true, 17, false, 14, rs }, kNone2) == NoPauseRule::kCut, "parts: nobody", k);
        check(r.record(f++, { true, 17, false, 14, rs }, s2) == NoPauseRule::kCut, "parts: P2 alone");
        for (int k = 0; k < 30; k++, f++) check(r.record(f, { true, 17, false, 14, rs }, kNone2) == NoPauseRule::kCut, "parts: P2 alone, later", k);
        const uint32_t b = f;
        check(r.record(f++, { true, 17, false, 14, rs }, s1) == NoPauseRule::kPress, "parts: P1 too: pressed");
        for (int k = 1; k < 100; k++, f++) {
            const NoPauseRule::Verdict v = r.record(f, { true, 17, false, 14, rs }, (k & 1) ? sb : kNone2);
            check(v == ((f - b) % 20 < 3 ? NoPauseRule::kPress : NoPauseRule::kCut), "parts: the rule's presses", k, v);
            PadInput in[2] = { (k & 1) ? sb[0] : np::kNeutral, np::kNeutral };
            NoPauseRule::apply(v, in);
            check(((in[0].buttons & NoPauseRule::kStart) != 0) == (v == NoPauseRule::kPress) &&
                  ((in[1].buttons & NoPauseRule::kStart) != 0) == (v == NoPauseRule::kPress), "parts: START to both alike", k);
        }
        /* the part ends: no START; the next part counts afresh */
        check(r.record(f++, { true, 17, false, 14, 4 }, sb) == NoPauseRule::kCut, "parts: READY/FIGHT");
        check(r.record(f++, { true, 17, false, 14, rs }, s1) == NoPauseRule::kCut, "parts: afresh");
        /* a frame gap: afresh as well */
        f += 3;
        check(r.record(f++, { true, 17, false, 14, rs }, s2) == NoPauseRule::kCut, "parts: not across a gap");
    }
    /* the intro and the part after a round are different parts: presses do not carry over */
    {
        NoPauseRule r;
        uint32_t f = 900;
        r.record(f++, { true, 17, false, 14, 2 }, s1);
        check(r.record(f++, { true, 17, false, 14, 8 }, s2) == NoPauseRule::kCut, "parts: intro -> after the round");
        /* within one part the round state may change (P1 intro -> P2 intro; slow motion -> replay -> next round) */
        NoPauseRule q;
        f = 1200;
        q.record(f++, { true, 17, false, 14, 1 }, s1);
        check(q.record(f++, { true, 17, false, 14, 2 }, s2) == NoPauseRule::kPress, "parts: P1 intro + P2 intro");
        q.record(f++, { true, 17, false, 14, 5 }, kNone2);
        q.record(f++, { true, 17, false, 14, 8 }, s2);
        check(q.record(f++, { true, 17, false, 14, 9 }, s1) == NoPauseRule::kPress, "parts: slow motion + replay");
    }
    /* once the match is decided in this fight: no part (the post-match window's START instead) */
    {
        NoPauseRule r;
        uint32_t f = 2000;
        for (int k = 0; k < 10; k++, f++) r.record(f, { true, 17, false, 14, 5 }, kNone2);
        for (int k = 0; k < 40; k++, f++) check(r.record(f, { true, 17, true, 14, 8 }, sb) == NoPauseRule::kCut, "parts: decided, before the window", k);
        for (int k = 0; k < 10; k++, f++) check(r.record(f, { true, 17, true, 14, 9 }, sb) == NoPauseRule::kKeep, "parts: decided, the window", k);
        /* a rematch's intros with the last match's byte still set: a part */
        NoPauseRule q;
        f = 3000;
        q.record(f++, { true, 12, true, 14, 0 }, kNone2);
        q.record(f++, { true, 17, true, 14, 1 }, s1);
        check(q.record(f++, { true, 17, true, 14, 1 }, s2) == NoPauseRule::kPress, "parts: a rematch's intro (stale byte)");
    }
    printf("parts ok\n");
}

/* ---- symmetry ----------------------------------------------------------------------------- */
static void test_symmetry()
{
    for (int i = 0; i < 200000; i++) {
        PadInput in[2] = { { (uint16_t)rnd(), (uint8_t)rnd(), 128, 128, 128 }, { (uint16_t)rnd(), 128, (uint8_t)rnd(), 128, 128 } };
        const NoPauseRule::Verdict v = (NoPauseRule::Verdict)(rnd() % 3);
        PadInput a[2] = { in[0], in[1] }, b[2] = { in[1], in[0] };
        const unsigned ca = NoPauseRule::apply(v, a), cb = NoPauseRule::apply(v, b);
        check(a[0] == b[1] && a[1] == b[0], "symmetry: swapped slots", i);
        check(((ca & 1) << 1 | (ca >> 1)) == cb, "symmetry: cut mask", ca, cb);
        for (int p = 0; p < 2; p++) {
            check(v == NoPauseRule::kKeep ? a[p] == in[p] : v == NoPauseRule::kPress ? (a[p].buttons & NoPauseRule::kStart) != 0
                                                                                    : !(a[p].buttons & NoPauseRule::kStart),
                  "apply: START", p);
            check((a[p].buttons | NoPauseRule::kStart) == (in[p].buttons | NoPauseRule::kStart) && a[p].lx == in[p].lx &&
                  a[p].ly == in[p].ly, "apply: nothing else changes", p);
        }
    }
    printf("symmetry ok\n");
}

/* ---- lockstep / rollback / replay ----------------------------------------------------------- */
struct Timeline { std::vector<uint64_t> hash; std::vector<PadInput> raw0, raw1; Game end; };

/* The reference: inputs known before every frame (lockstep), the rule in front of the game. */
static Timeline run_lockstep(uint32_t frames, uint32_t rate0, uint32_t rate1, uint32_t s0, uint32_t s1)
{
    Timeline tl;
    Game g; NoPauseRule r;
    for (uint32_t f = 0; f < frames; f++) {
        PadInput in[2] = { player_input(s0, f, rate0), player_input(s1, f, rate1) };
        tl.raw0.push_back(in[0]); tl.raw1.push_back(in[1]);
        NoPauseRule::apply(r.record(f, g.facts(), in), in);
        g.step(in);
        check(!g.paused, "lockstep: the pause menu opened", f);
        tl.hash.push_back(g.hash);
    }
    tl.end = g;
    return tl;
}

/* One PC under rollback: its own inputs at once, the peer's `lat` frames late (with jitter);
 * missing ones predicted as the last known one repeats (START included, as rb_net does); a
 * late input that differs from the prediction rolls the game back to that frame's boundary
 * (the snapshot -- the rule's records are NOT in it) and re-simulates up to the live frame,
 * calling the rule at every boundary again, as t5_hooks.cpp does. */
static std::vector<uint64_t> run_rollback(const Timeline& ref, int slot, uint32_t seed_lat, uint32_t* rollbacks)
{
    const uint32_t frames = (uint32_t)ref.hash.size();
    const std::vector<PadInput>& mine = slot == 0 ? ref.raw0 : ref.raw1;
    const std::vector<PadInput>& theirs = slot == 0 ? ref.raw1 : ref.raw0;
    std::vector<uint32_t> arrive(frames);
    uint32_t x = seed_lat;
    for (uint32_t f = 0; f < frames; f++) {
        x = x * 1103515245u + 12345u;
        const uint32_t lat = (x >> 16) % 10;               /* 0-9 frames late */
        arrive[f] = f + lat;
        if (f > 0 && arrive[f] < arrive[f - 1]) arrive[f] = arrive[f - 1];   /* in order */
    }
    std::vector<Game> snap(frames + 1);
    std::vector<PadInput> used(frames);
    std::vector<uint64_t> hash(frames);
    NoPauseRule r;
    Game g;
    uint32_t known = 0;                                    /* peer inputs known for frames < known */
    PadInput last = np::kNeutral;
    auto run = [&](uint32_t f) {
        snap[f] = g;
        PadInput rem = f < known ? theirs[f] : last;
        used[f] = rem;
        PadInput in[2];
        in[slot] = mine[f]; in[1 - slot] = rem;
        NoPauseRule::apply(r.record(f, g.facts(), in), in);
        g.step(in);
        hash[f] = g.hash;
    };
    for (uint32_t t = 0; t < frames; t++) {
        uint32_t first_wrong = UINT32_MAX;
        while (known < frames && arrive[known] <= t) {
            if (known < t && !(used[known] == theirs[known]) && first_wrong == UINT32_MAX) first_wrong = known;
            last = theirs[known];
            known++;
        }
        if (first_wrong != UINT32_MAX) {
            (*rollbacks)++;
            g = snap[first_wrong];
            for (uint32_t f = first_wrong; f < t; f++) run(f);
        }
        run(t);
    }
    /* the end: every input known, the last frames re-run if they were predicted wrong */
    known = frames;
    for (uint32_t f = 0; f < frames; f++)
        if (!(used[f] == theirs[f])) { (*rollbacks)++; g = snap[f]; for (uint32_t h = f; h < frames; h++) run(h); break; }
    return hash;
}

static void test_netplay()
{
    const uint32_t frames = 30000;
    uint32_t total_matches = 0, total_skips = 0, total_replay_skips = 0;
    for (int k = 0; k < 6; k++) {
        const uint32_t s0 = 11 + k * 7, s1 = 23 + k * 13;
        /* START from P1 only, from P2 only, from both; mashed hard or now and then */
        const uint32_t rate = k < 3 ? 5 : 40;
        const uint32_t rate0 = k % 3 == 1 ? 0 : rate, rate1 = k % 3 == 0 ? 0 : rate;
        Timeline ref = run_lockstep(frames, rate0, rate1, s0, s1);
        /* without the rule the same inputs open the pause menu (the model is not toothless) */
        {
            Game g; uint32_t opened = 0;
            for (uint32_t f = 0; f < frames; f++) { PadInput in[2] = { ref.raw0[f], ref.raw1[f] }; g.step(in); opened += g.paused; }
            check(opened > 0 && g.pauses > 0, "model: START pauses without the rule", k);
        }
        check(ref.end.matches >= 3, "lockstep: matches end", (long)ref.end.matches);
        check(ref.end.replays >= ref.end.matches, "lockstep: round replays", (long)ref.end.replays);
        if (!rate0 || !rate1)   /* one player pressing never skips anything in a round */
            check(!ref.end.replay_skips && !ref.end.intro_skips && !ref.end.next_skips, "lockstep: one player skipped", k,
                  (long)(ref.end.replay_skips + ref.end.intro_skips + ref.end.next_skips));
        else
            check(ref.end.intro_skips > 0 && ref.end.replay_skips > 0 && ref.end.next_skips > 0, "lockstep: both players skip", k);
        total_matches += ref.end.matches; total_skips += ref.end.skips; total_replay_skips += ref.end.replay_skips;
        uint32_t rb0 = 0, rb1 = 0;
        const std::vector<uint64_t> a = run_rollback(ref, 0, 1000 + k, &rb0);
        const std::vector<uint64_t> b = run_rollback(ref, 1, 2000 + k, &rb1);
        check(rb0 > 100 && rb1 > 100, "rollback: rollbacks happened", rb0, rb1);
        for (uint32_t f = 0; f < frames; f++) {
            check(a[f] == ref.hash[f], "rollback: P1's PC differs from the reference", f, k);
            check(b[f] == ref.hash[f], "rollback: P2's PC differs from the reference", f, k);
        }
        /* replay: the raw inputs from the file, the rule in front of the game */
        {
            Game g; NoPauseRule r;
            for (uint32_t f = 0; f < frames; f++) {
                PadInput in[2] = { ref.raw0[f], ref.raw1[f] };
                NoPauseRule::apply(r.record(f, g.facts(), in), in);
                g.step(in);
                check(g.hash == ref.hash[f], "replay: differs", f, k);
            }
        }
        printf("run %d (START from %s): %u frames, %u matches (%u ends skipped by START), %u intros (%u skips), %u round "
               "replays (%u skipped, %u ways to the next round skipped), %u / %u rollbacks, same hash on both PCs\n", k,
               rate0 && rate1 ? "both" : rate0 ? "P1" : "P2", frames, ref.end.matches, ref.end.skips, ref.end.intros,
               ref.end.intro_skips, ref.end.replays, ref.end.replay_skips, ref.end.next_skips, rb0, rb1);
    }
    check(total_skips > 0, "the post-match skip by START still works", total_skips, total_matches);
    check(total_replay_skips > 0, "a round's replay is skipped by both players' START", total_replay_skips);
    printf("lockstep, rollback, replay ok\n");
}

int main()
{
    test_window();
    test_parts();
    test_symmetry();
    test_netplay();
    printf("PASS %d checks\n", g_checks);
    return 0;
}
