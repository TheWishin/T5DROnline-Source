/* Host transport state for per-match simulation-rule verification. No sockets or game state;
 * fake peers exercise this in match_rules_test.cpp. Session nonce/authentication is checked by
 * netplay_core before receive(). An ordinal is never reused within one session. */
#pragma once
#include <stdint.h>

namespace np {
struct MatchRuleAgreement {
    uint32_t ordinal = 0, rules = 0;
    uint32_t peer_ordinal = 0, peer_rules = 0, acknowledged = 0;

    bool begin(uint32_t next, uint32_t word)
    {
        if (!next || next < ordinal || next > ordinal + 1) return false;
        if (next == ordinal) return word == rules;
        ordinal = next; rules = word; acknowledged = 0;
        return peer_ordinal != ordinal || peer_rules == rules;
    }
    bool receive(uint32_t next, uint32_t word, uint32_t ack)
    {
        if (!next || next < peer_ordinal || next > ordinal + 1) return true;  /* stale / premature */
        if (next == peer_ordinal && word != peer_rules) return false;       /* changed an immutable offer */
        peer_ordinal = next; peer_rules = word;
        if (next == ordinal && word != rules) return false;
        if (next == ordinal && ack == ordinal) acknowledged = ack;
        return true;
    }
    bool ready() const
    {
        return ordinal && peer_ordinal == ordinal && peer_rules == rules && acknowledged == ordinal;
    }
};
} // namespace np
