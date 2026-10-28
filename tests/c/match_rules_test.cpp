/*
 * Online training (src/netplay/match_rules.h) on its own, for tests/test_match_rules.py. No game, no network: a
 * small model of a fight, two "PCs" running it the way the netplay does (lockstep, rollback with late inputs and
 * re-simulation, replay playback), the training rule sitting where t5_hooks.cpp puts it -- after a frame's inputs
 * are final for that run, on the game state at the frame's boundary, before the frame runs.
 *
 * The model fight: round state 5 while both have health; an attack button (SQUARE) of a player who can act hits
 * the other (7.0 health, 16.16 fixed point, as d+4 in the game) and stuns them for 20 frames (they cannot act);
 * a fighter at 0 health is KO'd at the next frame (the fight ends, round state 6) -- as the game does with a
 * health word set to 0 at a boundary. The round timer counts down every fought frame; at 0 the round ends too.
 *
 * Checks (each prints a line; "PASS <n> checks" at the end, exit code 1 on the first failure):
 *   rules       pack/unpack, clamps, "no rules" packs to 0 (older replays)
 *   refill      health refills to the maximum after kRefillFrames frames without damage, not before; a
 *               handicapped maximum (72.5) is what it refills to; the timer is held while fighting
 *   no-KO       a combo that never stops (a hit every few frames, 400 frames) on a fighter at 30 % health: the
 *               health goes to 0 again and again and is set back to the floor before the KO check, nobody is KO'd
 *               (without the rule the same combo KOs); a give-up still KOs in the middle of it
 *   give-up     SELECT held kGiveUpFrames frames sets that player's health to 0 (the KO), a shorter hold does
 *               nothing, letting go starts the count again, a sync point clears the counts
 *   symmetry    the rule treats both slots alike: step(swap(state), swap(in)) == swap(step(state, in))
 *   lockstep    two PCs with the same inputs: the same state every frame; without the rule the model KOs
 *               (the rule has teeth), with it nobody is KO'd unless SELECT is held
 *   rollback    late inputs (0-8 frames), predictions (the last input repeats), rollbacks restoring the
 *               model state and re-running the rule from the restored boundary: the confirmed timeline equals
 *               the lockstep reference, on both PCs, with sync points (history cleared) on the way
 *   replay      the recorded inputs played back through the rule: the same states
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <vector>

#include "../../src/netplay/match_rules.h"

using np::MatchRules;
using np::PadInput;
using np::TrainingRule;

static int g_checks = 0;
#define CHECK(c, ...) do { g_checks++; if (!(c)) { printf("FAIL line %d: ", __LINE__); printf(__VA_ARGS__); printf("\n"); exit(1); } } while (0)

static const uint16_t kAttack = 0x8000, kSelect = TrainingRule::kSelect;
static const int32_t kFull = 145 << 16, kHit = 7 << 16;

struct Game {
    bool fighting = true, ko = false;
    int32_t hp[2] = { kFull, kFull }, max[2] = { kFull, kFull };
    uint32_t stun[2] = { 0, 0 };
    uint32_t timer = TrainingRule::kRoundTimer;
    uint64_t hash() const
    {
        uint64_t h = 1469598103934665603ull;
        auto mix = [&](uint64_t v) { h ^= v; h *= 1099511628211ull; };
        mix(fighting); mix(ko); mix((uint32_t)hp[0]); mix((uint32_t)hp[1]); mix(stun[0]); mix(stun[1]); mix(timer);
        return h;
    }
    bool can_act(int p) const { return stun[p] == 0; }
    void run(const PadInput in[2])
    {
        if (!fighting) return;
        if (hp[0] <= 0 || hp[1] <= 0) { fighting = false; ko = true; return; }   /* the KO at the next frame */
        for (int p = 0; p < 2; p++) if (stun[p]) stun[p]--;
        for (int p = 0; p < 2; p++) {
            if ((in[p].buttons & kAttack) && can_act(p) && stun[1 - p] == 0) {
                hp[1 - p] -= kHit;
                if (hp[1 - p] < 0) hp[1 - p] = 0;
                stun[1 - p] = 20;
            }
        }
        if (timer) timer--;
        if (!timer) fighting = false;
    }
};

/* the hooks' part: the rule on the boundary's state, its writes into the game */
static void apply_rule(TrainingRule& r, uint32_t f, Game& g, const PadInput in[2], bool on = true)
{
    if (!on) return;
    TrainingRule::State st;
    st.fighting = g.fighting;   /* round state 5, not decided: a fighter at 0 is still fighting until the KO check */
    for (int p = 0; p < 2; p++) { st.f[p].hp = g.hp[p]; st.f[p].max = g.max[p]; }
    const TrainingRule::Action a = r.step(f, st, in);
    if (a.hold_timer) g.timer = TrainingRule::kRoundTimer;
    for (int p = 0; p < 2; p++) if (a.set_hp[p]) g.hp[p] = a.hp[p];
}

static PadInput pad(uint16_t b) { PadInput p = np::kNeutral; p.buttons = b; return p; }

static void test_rules()
{
    MatchRules r;
    CHECK(r.pack() == 0 && !r.any(), "no rules pack to 0");
    CHECK(MatchRules::unpack(0) == r, "0 unpacks to no rules");
    r.training = true; r.life[0] = 70;
    const uint32_t w = r.pack();
    CHECK(w == (1u | 70u << 8 | 100u << 16), "pack 0x%X", w);
    CHECK(MatchRules::unpack(w) == r, "round trip");
    CHECK(MatchRules::clamp_life(0) == MatchRules::kLifeMin && MatchRules::clamp_life(250) == 150, "clamp");
    /* 1.1.7: up to 150 % (a 1.1.6 game clamped the fight line's life= at 100) */
    CHECK(MatchRules::kLifeMax == 150 && MatchRules::clamp_life(150) == 150 && MatchRules::clamp_life(160) == 150,
          "life up to 150");
    for (int v : { 110, 120, 150 }) {
        MatchRules hi; hi.life[0] = v;
        const uint32_t wh = hi.pack();
        CHECK(wh == ((uint32_t)v << 8 | 100u << 16) && MatchRules::unpack(wh) == hi, "%d %% round trip 0x%X", v, wh);
    }
    MatchRules h; h.life[1] = 50;
    CHECK(MatchRules::unpack(h.pack()).life[1] == 50 && !MatchRules::unpack(h.pack()).training, "handicap only");
    printf("rules ok\n");
}

static void test_refill()
{
    TrainingRule r;
    Game g;
    g.max[1] = (72 << 16) | 0x8000; g.hp[1] = g.max[1];   /* P2 at 50 %: 72.5 */
    PadInput in[2] = { pad(0), pad(0) };
    uint32_t f = 0;
    in[0] = pad(kAttack);
    apply_rule(r, f, g, in); g.run(in); f++;
    in[0] = pad(0);
    CHECK(g.hp[1] == g.max[1] - kHit && g.stun[1] == 20, "the hit lands (%d)", g.hp[1]);
    uint32_t refilled_at = 0;
    for (; f < 200 && !refilled_at; f++) {
        const int32_t before = g.hp[1];
        apply_rule(r, f, g, in);
        if (g.hp[1] != before) refilled_at = f;
        CHECK(g.timer == TrainingRule::kRoundTimer, "timer held");
        g.run(in);
    }
    /* the hit in frame 0 shows at frame 1's boundary (the damage); from frame 2 on no damage: the 60th boundary
     * without damage (frame 61) refills */
    CHECK(refilled_at == 1 + TrainingRule::kRefillFrames, "refilled at frame %u", refilled_at);
    CHECK(g.hp[1] == g.max[1], "refilled to the handicapped maximum");
    /* 1.1.7: P1 at 150 % (217.5, above the game's 145.0): a hit, then the refill goes back to 217.5, not 145 */
    {
        TrainingRule r2;
        Game g2;
        g2.max[0] = (217 << 16) | 0x8000; g2.hp[0] = g2.max[0];
        PadInput i2[2] = { pad(0), pad(kAttack) };
        uint32_t f2 = 0;
        apply_rule(r2, f2, g2, i2); g2.run(i2); f2++;
        i2[1] = pad(0);
        CHECK(g2.hp[0] == g2.max[0] - kHit, "the hit lands at 150 %% (%d)", g2.hp[0]);
        for (; f2 < 200; f2++) { apply_rule(r2, f2, g2, i2); g2.run(i2); }
        CHECK(g2.hp[0] == g2.max[0] && g2.hp[0] > kFull, "refilled to the 150 %% maximum (%d)", g2.hp[0]);
    }
    printf("refill ok\n");
}

static void test_no_ko()
{
    for (int with_rule = 0; with_rule < 2; with_rule++) {
        TrainingRule r;
        Game g;
        g.max[1] = (43 << 16) | 0x8000; g.hp[1] = g.max[1];      /* P2 at 30 %: 43.5 */
        uint32_t floors = 0, f = 0;
        for (; f < 400 && g.fighting; f++) {
            PadInput in[2] = { pad(kAttack), pad(0) };            /* P1 attacks whenever P2 can be hit */
            const int32_t before = g.hp[1];
            apply_rule(r, f, g, in, with_rule != 0);
            if (before == 0 && g.hp[1] == TrainingRule::kFloor) floors++;
            CHECK(g.timer == TrainingRule::kRoundTimer || !with_rule, "timer held");
            g.run(in);
        }
        if (with_rule) {
            CHECK(g.fighting && !g.ko && f == 400, "no KO from damage (frame %u)", f);
            CHECK(floors > 5, "the health went to 0 and came back to the floor %u times", floors);
        } else {
            CHECK(g.ko && f < 400, "without the rule the combo KOs");
        }
    }
    {   /* the give-up in the middle of the combo: that KO stays */
        TrainingRule r;
        Game g;
        uint32_t f = 0;
        for (; f < 400 && g.fighting; f++) {
            PadInput in[2] = { pad(kAttack), pad(f >= 100 && f < 200 ? kSelect : 0) };
            apply_rule(r, f, g, in);
            g.run(in);
        }
        CHECK(g.ko && g.hp[1] == 0 && f == 100 + TrainingRule::kGiveUpFrames, "the give-up KOs during the combo (%u)", f);
    }
    printf("no-KO ok\n");
}

static void test_give_up()
{
    for (uint32_t hold : { TrainingRule::kGiveUpFrames - 1, TrainingRule::kGiveUpFrames, TrainingRule::kGiveUpFrames + 5 }) {
        TrainingRule r;
        Game g;
        uint32_t f = 0;
        for (; f < 300 && g.fighting; f++) {
            PadInput in[2] = { pad(0), pad(f >= 10 && f < 10 + hold ? kSelect : 0) };
            apply_rule(r, f, g, in);
            g.run(in);
        }
        if (hold < TrainingRule::kGiveUpFrames) CHECK(g.fighting && !g.ko, "a hold of %u frames does nothing", hold);
        else CHECK(g.ko && g.hp[1] == 0 && g.hp[0] == kFull && f == 10 + TrainingRule::kGiveUpFrames,
                   "hold %u: KO at %u", hold, f);
    }
    {   /* letting go starts again; a sync point clears the count */
        TrainingRule r;
        Game g;
        for (uint32_t f = 0; f < 400; f++) {
            const bool held = (f >= 10 && f < 50) || (f >= 51 && f < 100) || (f >= 200 && f < 310);
            if (f == 240) r.reset();   /* a sync point at 240: the 40 frames held before it do not count */
            PadInput in[2] = { pad(held ? kSelect : 0), pad(0) };
            apply_rule(r, f, g, in);
            g.run(in);
            if (f < 299) CHECK(g.fighting, "frame %u: no give-up yet", f);
        }
        CHECK(g.ko && g.hp[0] == 0, "the hold after the sync point gives up");
    }
    printf("give-up ok\n");
}

static void test_symmetry()
{
    srand(5);
    for (int k = 0; k < 2000; k++) {
        TrainingRule a, b;
        TrainingRule::State s, t;
        s.fighting = t.fighting = true;
        for (int p = 0; p < 2; p++) {
            s.f[p].hp = rand() % 146 << 16; s.f[p].max = 145 << 16;
            t.f[1 - p] = s.f[p];
        }
        for (uint32_t f = 0; f < 80; f++) {
            PadInput in[2] = { pad(rand() & 1 ? kSelect : 0), pad(rand() % 3 ? kSelect : 0) };
            PadInput sw[2] = { in[1], in[0] };
            for (int p = 0; p < 2; p++) {   /* now and then a hit */
                if (rand() % 25 == 0) s.f[p].hp -= 7 << 16;
                if (s.f[p].hp < 0) s.f[p].hp = 0;
                t.f[1 - p].hp = s.f[p].hp;
            }
            const TrainingRule::Action x = a.step(f, s, in), y = b.step(f, t, sw);
            for (int p = 0; p < 2; p++)
                CHECK(x.set_hp[p] == y.set_hp[1 - p] && (!x.set_hp[p] || x.hp[p] == y.hp[1 - p]), "swap %d frame %u", k, f);
        }
    }
    printf("symmetry ok\n");
}

/* the inputs of a long session: both attack in bursts (200 frames, then a pause of 100 -- a combo, then the reset),
 * now and then SELECT held (a give-up ends the fight, the model then starts a new one) */
static std::vector<PadInput> script(int p, uint32_t n, unsigned seed)
{
    std::vector<PadInput> v(n, np::kNeutral);
    unsigned x = seed;
    auto rnd = [&]() { x = x * 1103515245u + 12345u; return (x >> 8) & 0xFFFF; };
    for (uint32_t f = 0; f < n; f++) v[f].buttons = (f < 1500 || f % 300 < 200) && rnd() % 4 == 0 ? kAttack : 0;
    for (uint32_t f = 0; f < n; f++) {
        if (rnd() % 1200 == 0) for (uint32_t k = 0; k < 70 && f + k < n; k++) v[f + k].buttons |= kSelect;
        if (rnd() % 200 == 0) for (uint32_t k = 0; k < 40 && f + k < n; k++) v[f + k].buttons |= kSelect;   /* too short */
    }
    (void)p;
    return v;
}

/* sync points (the hooks: training_reset() at every scene barrier); the model's fight restarts after a KO there */
static bool sync_point(uint32_t f) { return f % 1000 == 999; }

struct Timeline { std::vector<uint64_t> h; uint32_t kos = 0; };

static Timeline lockstep(const std::vector<PadInput> in[2], uint32_t n, bool rule = true)
{
    Timeline t;
    TrainingRule r;
    Game g;
    for (uint32_t f = 0; f < n; f++) {
        if (sync_point(f)) { r.reset(); if (!g.fighting) { t.kos += g.ko; g = Game(); } }
        PadInput i[2] = { in[0][f], in[1][f] };
        apply_rule(r, f, g, i, rule);
        g.run(i);
        t.h.push_back(g.hash());
    }
    if (!g.fighting) t.kos += g.ko;
    return t;
}

/* one PC under rollback: its own inputs at once, the other side's `lag(f)` frames late; frames run on a
 * prediction (the last confirmed input repeats) are re-run from the first wrong one with the state restored
 * (the hooks: the undo log), the rule run again on the restored boundary */
static Timeline rollback(const std::vector<PadInput> in[2], uint32_t n, int me, unsigned seed)
{
    struct Snap { Game g; };
    std::vector<Snap> snap(n + 1);
    std::vector<PadInput> used(n);           /* the remote input each frame last ran with */
    std::vector<uint32_t> arrive(n);
    unsigned x = seed;
    for (uint32_t f = 0; f < n; f++) { x = x * 1103515245u + 12345u; arrive[f] = f + ((x >> 10) % 9); }
    TrainingRule r;
    Game g;
    Timeline t;
    t.h.assign(n, 0);
    uint32_t kos = 0;
    const int other = 1 - me;
    uint32_t confirmed = 0;                  /* remote inputs known for frames < confirmed */
    auto run_frame = [&](uint32_t f, uint32_t now) {
        snap[f].g = g;
        if (sync_point(f)) { r.reset(); if (!g.fighting) { kos += g.ko; g = Game(); } }
        PadInput i[2];
        i[me] = in[me][f];
        if (f < confirmed) i[other] = in[other][f];
        else i[other] = confirmed ? in[other][confirmed - 1] : np::kNeutral;   /* prediction */
        used[f] = i[other];
        apply_rule(r, f, g, i);
        g.run(i);
        t.h[f] = g.hash();
        (void)now;
    };
    for (uint32_t now = 0; now < n; now++) {
        uint32_t c = confirmed;
        while (c < n && arrive[c] <= now) c++;
        /* a sync point is acted on only once every input before it is confirmed (the loop stalls for them): it is
         * a floor for rollbacks, so no re-run ever crosses the history's reset */
        if (sync_point(now) && c < now) c = now;
        uint32_t wrong = UINT32_MAX;
        for (uint32_t f = confirmed; f < c && f < now; f++)
            if (!(used[f] == in[other][f])) { wrong = f; break; }
        confirmed = c;
        if (wrong != UINT32_MAX) {
            /* the KOs counted in frames being re-run do not count (the model resets at sync points only) */
            g = snap[wrong].g;
            for (uint32_t f = wrong; f < now; f++) run_frame(f, now);
        }
        run_frame(now, now);
    }
    /* the end: every input confirmed, the frames since the first prediction re-run */
    uint32_t wrong = UINT32_MAX;
    for (uint32_t f = 0; f < n; f++) if (!(used[f] == in[other][f])) { wrong = f; break; }
    confirmed = n;
    if (wrong != UINT32_MAX) { g = snap[wrong].g; for (uint32_t f = wrong; f < n; f++) run_frame(f, n); }
    (void)kos;
    return t;
}

static void test_netplay()
{
    const uint32_t n = 6000;
    std::vector<PadInput> in[2] = { script(0, n, 11), script(1, n, 23) };
    const Timeline ref = lockstep(in, n);
    const Timeline raw = lockstep(in, n, false);
    CHECK(raw.kos > 0, "without the rule the model KOs (%u)", raw.kos);
    /* the same inputs without SELECT: nobody is ever KO'd with the rule */
    std::vector<PadInput> calm[2] = { in[0], in[1] };
    for (auto& v : calm) for (auto& p : v) p.buttons &= (uint16_t)~kSelect;
    CHECK(lockstep(calm, n).kos == 0 && lockstep(calm, n, false).kos > 0, "endless health");
    CHECK(ref.kos > 0, "the SELECT holds give up (%u)", ref.kos);
    const Timeline ref2 = lockstep(in, n);
    CHECK(ref.h == ref2.h, "lockstep is repeatable");
    printf("lockstep ok\n");
    for (unsigned s = 1; s <= 6; s++) {
        for (int me = 0; me < 2; me++) {
            const Timeline t = rollback(in, n, me, s * 7 + me);
            for (uint32_t f = 0; f < n; f++) CHECK(t.h[f] == ref.h[f], "rollback seed %u PC %d: frame %u differs", s, me, f);
        }
    }
    printf("rollback ok\n");
    /* a replay: the recorded (confirmed) inputs through the same loop */
    std::vector<PadInput> rec[2] = { in[0], in[1] };
    const Timeline rp = lockstep(rec, n);
    CHECK(rp.h == ref.h, "the replay plays the same states");
    printf("replay ok\n");
}

int main()
{
    test_rules();
    test_refill();
    test_no_ko();
    test_give_up();
    test_symmetry();
    test_netplay();
    printf("PASS %d checks\n", g_checks);
    return 0;
}
