/*
 * Experimental advantage comparison without the game. Synthetic samples only;
 * no guest memory, runtime, renderer or game data is needed. This file is
 * deliberately standalone so a maintainer can compile it independently.
 * The task that added it forbids building/running, so it was not executed here.
 */
#include <stdio.h>
#include <string.h>
#include <vector>

#include "../../src/training/advantage_shadow_logic.h"
#include "../../src/training/training_logic.h"

using namespace training::shadow;

static int g_checks = 0, g_fail = 0;
#define CHECK(c) do { ++g_checks; if (!(c)) { ++g_fail; \
    printf("FAIL %s:%d: %s\n", __FILE__, __LINE__, #c); } } while (0)
#define CHECK_EQ(a, b) do { ++g_checks; const long long av_ = (long long)(a), bv_ = (long long)(b); \
    if (av_ != bv_) { ++g_fail; printf("FAIL %s:%d: %s == %s (%lld vs %lld)\n", \
    __FILE__, __LINE__, #a, #b, av_, bv_); } } while (0)

static Sample sample(const char* name, uint32_t ptr, uint32_t frame = 0,
                     uint16_t length = 100, bool active = false)
{
    Sample s;
    s.valid = true;
    s.move_ptr = ptr;
    s.anim_frame = frame;
    s.anim_length = length;
    s.hitbox_active = active;
    s.char_id = 17;
    s.graph_complete = true;
    snprintf(s.name, sizeof s.name, "%s", name);
    return s;
}

struct Sequence {
    Tracker tracker;
    Sample s[2];
    uint64_t poll = 0;
    std::vector<Result> out;

    Sequence()
    {
        s[0] = sample("sKAM", 0x1000);
        s[1] = sample("sKAM", 0x1100);
    }

    void frame()
    {
        const int count = tracker.frame(s, poll++);
        for (int i = 0; i < count; ++i) out.push_back(tracker.result(i));
    }

    void begin(int attacker = 0, bool contact = true)
    {
        frame();                         // establish the false-hitbox baseline
        s[attacker] = sample("Attack", 0x2000, 1, 10, true);
        s[1 - attacker] = sample(contact ? "sGrd_00" : "sKAM", 0x2100, 1);
        frame();
    }

    void recovery(int attacker = 0, uint32_t anim = 10)
    {
        s[attacker].hitbox_active = false;
        s[attacker].anim_frame = anim;
        ++s[1 - attacker].anim_frame;
        frame();
    }

    void attacker_ready(int attacker = 0)
    {
        s[attacker] = sample("sKAM", 0x3000);
        ++s[1 - attacker].anim_frame;
        frame();
    }

    void defender_ready(int attacker = 0, uint32_t attacker_anim = 3)
    {
        s[attacker].anim_frame = attacker_anim;
        s[1 - attacker] = sample("sKAM", 0x3100);
        frame();
    }
};

static void test_name_groups()
{
    const char* neutral_names[] = { "sKAM", "cKAM", "prefix_sWALK_00", "cWALK", "sDASH",
        "sSTEP", "sJUMP_00", "sRUN", "cr2st", "st2cr", "sGrd_sKAM" };
    for (const char* name : neutral_names) CHECK(neutral(name));
    const char* stun_names[] = { "sGrd_00", "cGrd_00", "sHit_00", "cHit_00", "sDm_00",
        "cDm_00", "Male_00", "sDw_00", "wDm_00", "Ni_crst_00" };
    for (const char* name : stun_names) CHECK(stun(name));
    CHECK(!neutral("sJUMP_01"));
    CHECK(!neutral("Attack"));
    CHECK(!stun("prefix_sGrd_00"));     // stun is a prefix, not substring
    CHECK(!stun("Attack"));
}

static void test_positive_and_per_move_identity()
{
    Sequence q;
    q.begin();
    q.recovery();
    q.attacker_ready();
    CHECK(q.out.empty());
    q.defender_ready(0, 3);
    CHECK_EQ(q.out.size(), 1);
    if (q.out.empty()) return;
    const Result& r = q.out[0];
    CHECK(r.available);
    CHECK_EQ(r.advantage, 3);
    CHECK_EQ(r.attacker, 0);
    CHECK_EQ(r.move_ptr, 0x2000);
    CHECK_EQ(r.char_id, 17);
    CHECK(!strcmp(r.name, "Attack"));
    CHECK_EQ(r.start_poll, 1);
    CHECK_EQ(r.end_poll, 4);
    CHECK(r.flags & kNameEndpoints);
    CHECK(r.flags & kPhaseEstimated);  // move -> neutral phase boundary is inferred
    q.s[0].anim_frame = 4;
    q.frame();
    CHECK_EQ(q.out.size(), 1);         // no duplicate result while idle
}

static void test_negative_zero_and_p2()
{
    Sequence negative;
    negative.begin();
    negative.s[0].hitbox_active = false;
    negative.s[0].anim_frame = 7;
    negative.s[1] = sample("sKAM", 0x3100);
    negative.frame();                 // defender endpoint at attacker frame 7
    negative.recovery();
    negative.attacker_ready();        // attacker endpoint at frame 10
    CHECK_EQ(negative.out.size(), 1);
    if (!negative.out.empty()) {
        CHECK(negative.out[0].available);
        CHECK_EQ(negative.out[0].advantage, -3);
    }

    Sequence zero;
    zero.begin();
    zero.recovery();
    zero.s[0] = sample("sKAM", 0x3000);
    zero.s[1] = sample("sKAM", 0x3100);
    zero.frame();
    CHECK_EQ(zero.out.size(), 1);
    if (!zero.out.empty()) {
        CHECK(zero.out[0].available);
        CHECK_EQ(zero.out[0].advantage, 0);
    }

    Sequence p2;
    p2.begin(1);
    p2.recovery(1);
    p2.attacker_ready(1);
    p2.defender_ready(1, 4);
    CHECK_EQ(p2.out.size(), 1);
    if (!p2.out.empty()) {
        CHECK(p2.out[0].available);
        CHECK_EQ(p2.out[0].attacker, 1);
        CHECK_EQ(p2.out[0].advantage, 4);
    }
}

static void test_pauses_skips_and_phase_reset()
{
    Sequence q;
    q.begin();
    q.recovery();
    q.attacker_ready();
    q.frame();
    q.frame();                        // paused animation contributes zero
    q.s[0].anim_frame = 1;
    q.frame();
    q.frame();                        // repeated poll contributes zero
    q.defender_ready(0, 5);           // skipped frames contribute delta 4
    CHECK_EQ(q.out.size(), 1);
    if (!q.out.empty()) {
        CHECK(q.out[0].available);
        CHECK_EQ(q.out[0].advantage, 5); // seven polls apart, five animation frames
    }

    Sequence phases;
    phases.begin();
    phases.recovery(0, 4);
    phases.s[0].anim_frame = 0;       // same move resets its animation phase
    phases.frame();                   // 10 - 4 + 0 inferred frames
    phases.s[0].anim_frame = 10;
    phases.frame();
    phases.attacker_ready();
    phases.defender_ready(0, 2);
    CHECK_EQ(phases.out.size(), 1);
    if (!phases.out.empty()) {
        CHECK(phases.out[0].available);
        CHECK_EQ(phases.out[0].advantage, 2);
        CHECK(phases.out[0].flags & kPhaseEstimated);
    }
}

static void test_whiff_neutral_first_and_taunt()
{
    Sequence whiff;
    whiff.begin(0, false);
    whiff.recovery();
    whiff.attacker_ready();
    CHECK_EQ(whiff.out.size(), 1);
    if (!whiff.out.empty()) {
        CHECK(!whiff.out[0].available);
        CHECK(!strcmp(whiff.out[0].status, "no-contact"));
    }

    Sequence neutral_first;
    neutral_first.frame();
    neutral_first.s[0] = sample("Attack", 0x2000, 1, 10, true);
    neutral_first.s[1] = sample("sGrd_sKAM", 0x2100, 1);
    neutral_first.frame();             // neutral wins over the stun prefix
    neutral_first.recovery();
    neutral_first.attacker_ready();
    CHECK_EQ(neutral_first.out.size(), 1);
    if (!neutral_first.out.empty()) CHECK(!neutral_first.out[0].available);

    Sequence taunt;
    taunt.frame();
    taunt.s[0] = sample("Bryan_Taunt", 0x2000, 1, 10, true);
    taunt.s[1] = sample("sHit_Taunt", 0x2100, 1);
    taunt.frame();                     // no health/damage field exists or is needed
    taunt.recovery();
    taunt.attacker_ready();
    taunt.defender_ready(0, 6);
    CHECK_EQ(taunt.out.size(), 1);
    if (!taunt.out.empty()) {
        CHECK(taunt.out[0].available);
        CHECK_EQ(taunt.out[0].advantage, 6);
    }
}

static void test_recursive_continuation_and_multiple_edges()
{
    Sequence q;
    q.frame();
    q.s[0] = sample("Root", 0x2000, 1, 10, true);
    q.s[0].continuation_count = 2;
    snprintf(q.s[0].continuation[0], sizeof q.s[0].continuation[0], "RecoveryChild");
    snprintf(q.s[0].continuation[1], sizeof q.s[0].continuation[1], "RecoveryGrandchild");
    q.s[1] = sample("sGrd_00", 0x2100, 1);
    q.frame();
    q.s[0].hitbox_active = false;
    q.s[0].anim_frame = 10;
    q.frame();
    q.s[0] = sample("RecoveryGrandchild", 0x2200, 0, 10);
    q.frame();                         // supplied recursive closure keeps tracking
    CHECK(q.out.empty());
    q.s[0].anim_frame = 1;
    q.s[0].hitbox_active = true;
    q.frame();                         // another hitbox edge in the same continuation
    CHECK(q.out.empty());
    q.recovery();
    q.attacker_ready();
    q.defender_ready(0, 2);
    CHECK_EQ(q.out.size(), 1);
    if (!q.out.empty()) {
        CHECK(q.out[0].available);
        CHECK_EQ(q.out[0].advantage, 2);
        CHECK(q.out[0].flags & kMultiHitMerged);
        CHECK(!strcmp(q.out[0].name, "Root"));
    }

    Sequence neutral_continuation;
    neutral_continuation.frame();
    neutral_continuation.s[0] = sample("Root", 0x2000, 1, 10, true);
    neutral_continuation.s[0].continuation_count = 1;
    snprintf(neutral_continuation.s[0].continuation[0], sizeof neutral_continuation.s[0].continuation[0], "sKAM");
    neutral_continuation.s[1] = sample("sGrd_00", 0x2100, 1);
    neutral_continuation.frame();
    neutral_continuation.recovery();
    neutral_continuation.attacker_ready(); // neutral wins even if recovery graph lists it
    neutral_continuation.defender_ready(0, 1);
    CHECK_EQ(neutral_continuation.out.size(), 1);
    if (!neutral_continuation.out.empty()) CHECK(neutral_continuation.out[0].available);
}

static void test_incomplete_graph_and_missing_endpoints()
{
    Sequence q;
    q.frame();
    q.s[0] = sample("Root", 0x2000, 1, 10, true);
    q.s[0].graph_complete = false;
    q.s[1] = sample("sGrd_00", 0x2100, 1);
    q.frame();
    q.s[0] = sample("UnknownRecovery", 0x2200, 0, 10);
    q.s[0].graph_complete = false;
    q.frame();
    CHECK(q.out.empty());              // unknown graph cannot prove actability
    q.s[0].anim_frame = 10;
    q.frame();
    q.attacker_ready();                // neutral can still prove an endpoint
    q.defender_ready(0, 1);
    CHECK_EQ(q.out.size(), 1);
    if (!q.out.empty()) {
        CHECK(q.out[0].available);
        CHECK(q.out[0].flags & kGraphIncomplete);
    }

    Sequence timeout;
    timeout.begin();
    for (uint64_t i = 0; i < Tracker::kTimeoutPolls; ++i) timeout.frame();
                                      // still stunned; no invented endpoint
    CHECK_EQ(timeout.out.size(), 1);
    if (!timeout.out.empty()) {
        CHECK(!timeout.out[0].available);
        CHECK(!strcmp(timeout.out[0].status, "timeout"));
    }
}

static void test_string_uses_latest_defender_release()
{
    Sequence q;
    q.begin();
    q.s[0].hitbox_active = false;
    q.s[0].anim_frame = 3;
    q.s[1] = sample("sKAM", 0x3100);
    q.frame();                        // defender released after first hit
    q.s[0].hitbox_active = true;
    q.s[0].anim_frame = 4;
    q.s[1] = sample("sGrd_SecondHit", 0x3200);
    q.frame();                        // next edge is still the root move
    CHECK(q.out.empty());
    q.recovery();
    q.attacker_ready();
    CHECK(q.out.empty());             // first hit's release cannot settle second hit
    q.defender_ready(0, 4);
    CHECK_EQ(q.out.size(), 1);
    if (!q.out.empty()) {
        CHECK(q.out[0].available);
        CHECK_EQ(q.out[0].advantage, 4);
        CHECK(q.out[0].flags & kMultiHitMerged);
    }
}

static void test_discontinuity_identity_and_interruptions()
{
    const int jumps[] = { 0, -1, 1 }; // duplicate, backward, missing poll
    for (int jump : jumps) {
        Sequence q;
        q.begin();
        q.poll = (uint64_t)(1 + jump);
        if (jump == 1) ++q.poll;       // next expected is 2; use 3 for a gap
        q.frame();
        CHECK_EQ(q.out.size(), 1);
        if (!q.out.empty()) {
            CHECK(!q.out[0].available);
            CHECK(!strcmp(q.out[0].status, "discontinuity"));
        }
        q.recovery();
        q.attacker_ready();
        q.defender_ready();
        CHECK_EQ(q.out.size(), 1);     // a gap never bridges into a candidate
    }

    Sequence identity;
    identity.begin();
    ++identity.s[1].char_id;
    identity.frame();
    CHECK_EQ(identity.out.size(), 1);
    if (!identity.out.empty()) {
        CHECK(!identity.out[0].available);
        CHECK(!strcmp(identity.out[0].status, "identity-change"));
    }

    Sequence interrupted;
    interrupted.begin();
    interrupted.s[0] = sample("sHit_Interrupted", 0x4100);
    interrupted.frame();
    CHECK_EQ(interrupted.out.size(), 1);
    if (!interrupted.out.empty()) {
        CHECK(!interrupted.out[0].available);
        CHECK(!strcmp(interrupted.out[0].status, "interrupted"));
    }

    Sequence impossible;
    impossible.begin();
    impossible.s[0].anim_frame = impossible.s[0].anim_length + 1;
    impossible.frame();
    CHECK_EQ(impossible.out.size(), 1);
    if (!impossible.out.empty()) CHECK(!impossible.out[0].available);

    Sequence neutral_edge;
    neutral_edge.frame();
    neutral_edge.s[0].hitbox_active = true;
    neutral_edge.s[1] = sample("sGrd_00", 0x2100);
    neutral_edge.frame();
    neutral_edge.recovery();
    neutral_edge.attacker_ready();
    neutral_edge.defender_ready();
    CHECK(neutral_edge.out.empty());   // neutral names never begin an attack
}

static void test_invalid_reset_initial_edge_and_supersession()
{
    Sequence invalid;
    invalid.begin();
    invalid.s[0].valid = false;
    invalid.frame();
    CHECK_EQ(invalid.out.size(), 1);
    if (!invalid.out.empty()) {
        CHECK(!invalid.out[0].available);
        CHECK(!strcmp(invalid.out[0].status, "invalid-sample"));
    }

    Sequence reset;
    reset.begin();
    reset.tracker.reset();
    reset.recovery();
    reset.attacker_ready();
    reset.defender_ready();
    CHECK(reset.out.empty());          // fight/menu/gate reset discards old edge

    Sequence initial;
    initial.s[0] = sample("AlreadyActive", 0x2000, 1, 10, true);
    initial.s[1] = sample("sGrd_00", 0x2100, 1);
    initial.frame();
    initial.recovery();
    initial.attacker_ready();
    initial.defender_ready();
    CHECK(initial.out.empty());        // seeing active is not seeing a rising edge

    Sequence superseded;
    superseded.begin();
    superseded.recovery(0, 2);
    superseded.s[0] = sample("UnrelatedAttack", 0x4000, 1, 10, true);
    superseded.frame();
    CHECK_EQ(superseded.out.size(), 1);
    if (!superseded.out.empty()) {
        CHECK(!superseded.out[0].available);
        CHECK(!strcmp(superseded.out[0].status, "superseded"));
        CHECK(!strcmp(superseded.out[0].name, "Attack"));
    }
    superseded.recovery();
    superseded.attacker_ready();
    superseded.defender_ready();
    CHECK_EQ(superseded.out.size(), 2);
    if (superseded.out.size() == 2) {
        CHECK(superseded.out[1].available);
        CHECK(superseded.out[0].id != superseded.out[1].id);
    }
}

static std::vector<training::Result> legacy_results(bool contact, bool unknown_window, bool diagnose = false)
{
    training::Tracker tracker;
    std::vector<training::Result> results;
    for (int t = 0; t < 80; ++t) {
        training::Sample s[2];
        s[0].hp = s[1].hp = 170;
        if (unknown_window) {
            // The first observed sample was already active: no active window
            // was seen by Tracker, so the anchor must remain unknown (zero).
            s[0].active = t == 0;
            s[0].can_act = t >= 5;
            s[0].cls = 7;
            s[1].new_move = t == 1;
            s[1].can_act = t == 0 || t >= 8;
        } else {
            s[0].new_move = t == 10;
            s[0].can_act = t < 10 || t >= 35;
            s[0].cls = t >= 10 && t < 35 ? 7 : 0;
            s[0].active = t == 19 || t == 20;
            if (contact) {
                s[1].new_move = t == 20;
                s[1].can_act = t < 20 || t >= 38;
            }
        }
        training::Diagnostic diagnostic;
        const int n = tracker.frame(s, diagnose ? &diagnostic : nullptr);
        for (int i = 0; i < n; ++i) results.push_back(tracker.result(i));
    }
    return results;
}

static void test_legacy_result_active_anchor()
{
    // Identity only: the existing result still reports its original advantage,
    // startup and kind. The extra anchor permits exact comparison correlation.
    const std::vector<training::Result> block = legacy_results(true, false);
    CHECK_EQ(block.size(), 1);
    if (!block.empty()) {
        CHECK_EQ(block[0].active_frame, 20); // Tracker domain starts at 1
        CHECK_EQ(block[0].startup, 10);
        CHECK_EQ(block[0].adv, 3);
        CHECK(block[0].kind == training::Kind::Block);
    }
    const std::vector<training::Result> whiff = legacy_results(false, false);
    CHECK_EQ(whiff.size(), 1);
    if (!whiff.empty()) {
        CHECK_EQ(whiff[0].active_frame, 20);
        CHECK_EQ(whiff[0].startup, 10);
        CHECK(whiff[0].kind == training::Kind::Whiff);
    }
    const std::vector<training::Result> unknown = legacy_results(true, true);
    CHECK_EQ(unknown.size(), 1);
    if (!unknown.empty()) {
        CHECK_EQ(unknown[0].active_frame, 0);
        CHECK_EQ(unknown[0].startup, 0);
    }
    // The integrated diagnostic path must keep the same comparison anchor
    // and established tracker values as the path without diagnostics.
    for (int contact = 0; contact < 2; ++contact) {
        for (int unknown = 0; unknown < 2; ++unknown) {
            const auto plain = legacy_results(contact != 0, unknown != 0);
            const auto diagnosed = legacy_results(contact != 0, unknown != 0, true);
            CHECK_EQ(plain.size(), diagnosed.size());
            for (size_t i = 0; i < plain.size() && i < diagnosed.size(); ++i) {
                CHECK_EQ(plain[i].active_frame, diagnosed[i].active_frame);
                CHECK_EQ(plain[i].startup, diagnosed[i].startup);
                CHECK_EQ(plain[i].adv, diagnosed[i].adv);
                CHECK_EQ((int)plain[i].kind, (int)diagnosed[i].kind);
            }
        }
    }
    const training::Result empty;
    CHECK_EQ(empty.active_frame, 0);
}

int main()
{
    test_name_groups();
    test_positive_and_per_move_identity();
    test_negative_zero_and_p2();
    test_pauses_skips_and_phase_reset();
    test_whiff_neutral_first_and_taunt();
    test_recursive_continuation_and_multiple_edges();
    test_incomplete_graph_and_missing_endpoints();
    test_string_uses_latest_defender_release();
    test_invalid_reset_initial_edge_and_supersession();
    test_discontinuity_identity_and_interruptions();
    test_legacy_result_active_anchor();
    if (g_fail) { printf("FAIL %d of %d checks\n", g_fail, g_checks); return 1; }
    printf("PASS %d checks\n", g_checks);
    return 0;
}
