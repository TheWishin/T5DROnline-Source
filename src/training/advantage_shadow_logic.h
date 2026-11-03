/* Experimental RPCS3-notes comparison; host-only, no game-memory access.
 * The contributor supplied no endpoint/phase/string completion algorithm.
 * Every policy marked INFERRED below must be revisited when it arrives.
 * Values are candidates for comparison, never replacement overlay results. */
#pragma once
#include <stdint.h>
#include <string.h>

namespace training { namespace shadow {

constexpr int kNameSize = 64, kContinuations = 32;
struct Sample {
    bool valid = false;
    uint32_t anim_frame = 0;
    uint16_t anim_length = 0;
    bool hitbox_active = false;
    uint32_t move_ptr = 0;
    uint8_t char_id = 0;
    char name[kNameSize] = {};
    bool graph_complete = false;
    uint8_t continuation_count = 0;
    char continuation[kContinuations][kNameSize] = {};
};

inline bool neutral(const char* name)
{
    static const char* const groups[] = { "sKAM", "cKAM", "sWALK", "cWALK", "sDASH", "sSTEP",
        "sJUMP_00", "sRUN", "cr2st", "st2cr" };
    for (const char* group : groups) if (strstr(name, group)) return true;
    return false;
}
inline bool stun(const char* name)
{
    if (neutral(name)) return false; // Contributor: neutral is always checked first.
    static const char* const groups[] = { "sGrd", "cGrd", "sHit", "cHit", "sDm", "cDm",
        "Male_", "sDw", "wDm", "Ni_crst" };
    for (const char* group : groups) if (!strncmp(name, group, strlen(group))) return true;
    return false;
}

enum Flag : uint32_t {
    kNameEndpoints = 1,    // INFERRED: name changes proxy the ability to act.
    kPhaseEstimated = 2,   // INFERRED: phase remainder stitched to the next phase.
    kGraphIncomplete = 4,  // Recovery lookup is unresolved; only neutral can end attacker.
    kMultiHitMerged = 8,   // INFERRED: a continuation's new active edge belongs to this move.
    kStunAtStart = 16      // INFERRED: already-visible stun is provisionally attributed to the edge.
};
struct Result {
    int attacker = 0;
    uint64_t id = 0, start_poll = 0, end_poll = 0;
    uint32_t move_ptr = 0;
    uint8_t char_id = 0;
    char name[kNameSize] = {};
    bool available = false;
    int advantage = 0;
    uint32_t flags = 0;
    const char* status = "unavailable";
};

class Tracker {
public:
    // INFERRED: a poll limit bounds abandoned candidates, never measures advantage.
    static constexpr uint64_t kTimeoutPolls = 600;

    int frame(const Sample s[2], uint64_t poll)
    {
        count_ = 0;
        if (!have_prev_) {
            remember(s, poll);
            return 0; // An initially high hitbox is not an observed rising edge.
        }
        // INFERRED: a missed/out-of-order poll cannot preserve an observed edge or
        // endpoint sequence. Character swaps likewise establish a new baseline.
        const bool discontinuous = prev_poll_ == UINT64_MAX || poll != prev_poll_ + 1;
        const bool identity_changed =
            (good(s[0]) && good(prev_[0]) && s[0].char_id != prev_[0].char_id) ||
            (good(s[1]) && good(prev_[1]) && s[1].char_id != prev_[1].char_id);
        if (discontinuous || identity_changed) {
            for (int p = 0; p < 2; ++p)
                if (pending_[p].live) finish(p, poll, discontinuous ? "discontinuity" : "identity-change");
            remember(s, poll);
            return count_;
        }
        for (int p = 0; p < 2; ++p) {
            Pending& m = pending_[p];
            const int d = 1 - p;
            const bool usable = good(s[p]) && good(s[d]);
            if (m.live && !usable) finish(p, poll, "invalid-sample");
            if (!usable) continue;
            const bool edge = good(prev_[p]) && !prev_[p].hitbox_active && s[p].hitbox_active &&
                !neutral(s[p].name);

            if (m.live) {
                if (!advance(m, prev_[p], s[p])) finish(p, poll, "invalid-clock");
            }
            if (edge) {
                if (m.live && !m.attacker_done && continuation(m, s[p].name)) {
                    // INFERRED: retain the first active edge for a string/recovery chain.
                    m.result.flags |= kMultiHitMerged;
                    // INFERRED: a later hit must establish its own contact/release;
                    // do not reuse an earlier hit's already-finished defender stun.
                    m.contacted = false;
                    m.defender_done = false;
                } else {
                    if (m.live) finish(p, poll, "superseded");
                    start(p, s[p], poll);
                    if (stun(s[d].name)) m.result.flags |= kStunAtStart;
                }
            }
            if (!m.live) continue;
            if (stun(s[p].name)) {
                // INFERRED: interrupted attacks do not have ordinary recovery advantage.
                finish(p, poll, "interrupted");
                continue;
            }
            if (stun(s[d].name)) {
                m.contacted = true; // Includes zero-damage taunts.
                m.defender_done = false; // A renewed reaction supersedes an earlier release.
            }
            else if (m.contacted && !m.defender_done) {
                // INFERRED: first non-stun name is the defender's action endpoint.
                m.defender_done = true;
                m.defender_clock = m.clock;
            }
            if (poll != m.result.start_poll && !m.attacker_done &&
                (neutral(s[p].name) || (m.root.graph_complete && !continuation(m, s[p].name)))) {
                // INFERRED: first neutral/non-continuation name is attacker action endpoint.
                // With unresolved recovery lookup, a new unknown name is NOT enough.
                m.attacker_done = true;
                m.attacker_clock = m.clock;
            }
            if (m.attacker_done && !m.contacted) {
                // INFERRED: no observed stun before recovery is a whiff/unknown contact.
                finish(p, poll, "no-contact");
            } else if (m.attacker_done && m.defender_done) {
                m.result.available = true;
                m.result.advantage = (int)(m.defender_clock - m.attacker_clock);
                finish(p, poll, "candidate");
            } else if (poll - m.result.start_poll >= kTimeoutPolls) {
                finish(p, poll, "timeout");
            }
        }
        remember(s, poll);
        return count_;
    }

    const Result& result(int i) const { return results_[i]; }
    void reset()
    {
        have_prev_ = false;
        pending_[0] = Pending{};
        pending_[1] = Pending{};
        count_ = 0;
        // Keep id monotonic across Practice/fight/overlay resets in this process.
    }

private:
    struct Pending {
        bool live = false, contacted = false, attacker_done = false, defender_done = false;
        int64_t clock = 0, attacker_clock = 0, defender_clock = 0;
        Sample root;
        Result result;
    };
    Sample prev_[2];
    Pending pending_[2];
    Result results_[4]; // At most superseded+finished for each fighter in one poll.
    int count_ = 0;
    uint64_t next_id_ = 1;
    uint64_t prev_poll_ = 0;
    bool have_prev_ = false;

    static bool good(const Sample& s)
    {
        return s.valid && s.move_ptr && s.name[0] &&
            memchr(s.name, 0, kNameSize) && s.anim_frame <= s.anim_length &&
            s.continuation_count <= kContinuations;
    }
    static bool continuation(const Pending& m, const char* name)
    {
        if (neutral(name)) return false;
        if (!strcmp(name, m.root.name)) return true;
        for (int i = 0; i < m.root.continuation_count; ++i)
            if (memchr(m.root.continuation[i], 0, kNameSize) && !strcmp(name, m.root.continuation[i])) return true;
        return false;
    }
    static bool advance(Pending& m, const Sample& old, const Sample& now)
    {
        if (!good(old)) return false;
        int64_t delta;
        if (old.move_ptr == now.move_ptr && now.anim_frame >= old.anim_frame) {
            // INFERRED: a repeated value is pause/hitstop; skips contribute their full delta.
            delta = (int64_t)now.anim_frame - old.anim_frame;
        } else {
            // INFERRED: phase switch/reset crossed the old phase's remainder.
            // No invented +1 tick: the notes say the runtime range is 0..AnimLength.
            delta = (int64_t)old.anim_length - old.anim_frame + now.anim_frame;
            m.result.flags |= kPhaseEstimated;
        }
        if (delta < 0 || m.clock + delta > 0x3FFFFFFF) return false;
        m.clock += delta;
        return true;
    }
    void start(int p, const Sample& s, uint64_t poll)
    {
        Pending& m = pending_[p];
        m = Pending{};
        m.live = true;
        m.root = s;
        m.result.attacker = p;
        m.result.id = next_id_++;
        m.result.start_poll = poll;
        m.result.move_ptr = s.move_ptr;
        m.result.char_id = s.char_id;
        memcpy(m.result.name, s.name, sizeof m.result.name);
        m.result.flags = kNameEndpoints | (s.graph_complete ? 0u : (uint32_t)kGraphIncomplete);
    }
    void finish(int p, uint64_t poll, const char* status)
    {
        Pending& m = pending_[p];
        m.result.end_poll = poll;
        m.result.status = status;
        if (count_ < 4) results_[count_++] = m.result;
        m.live = false;
    }
    void remember(const Sample s[2], uint64_t poll)
    {
        prev_[0] = s[0]; prev_[1] = s[1]; prev_poll_ = poll; have_prev_ = true;
    }
};

}} // namespace training::shadow
