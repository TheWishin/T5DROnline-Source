/*
 * Read-only adapter for the incomplete RPCS3 overlay notes.
 *
 * IMPORTANT: the claimed MovePtr at P+0x10 conflicts with the FLOAT X position
 * already used by practice.cpp. There is no verified replacement address.
 * read_sample therefore reads scalar diagnostics only and ALWAYS fails closed;
 * it never follows that word, the indirect word, or another claimed pointer.
 * The production path must not call read_fixture_sample: that function exists
 * solely to test the proposed schema against synthetic memory, not game data.
 * No runtime setting can validate or repair the conflicting mapping.
 */
#pragma once

#include <stddef.h>
#include <stdint.h>
#include <string.h>
#include "advantage_shadow_logic.h"

namespace training { namespace shadow {

struct MemoryAccess {
    void* context = nullptr;
    /* Must copy only if the ENTIRE guest span is readable; never write guest
     * memory. Production supplies page/region protection checks. */
    bool (*read)(void*, uint32_t, void*, size_t) = nullptr;
    /* Synthetic graph lookup only. The notes do not establish whether
     * indirect+0x1E0 contains an offset or pointer, nor the array's extent.
     * MISSING ALGORITHM/SCHEMA: production cannot supply this resolver until
     * that information has evidence. Never infer nextMoveId*0x4C here. */
    bool (*resolve_move)(void*, uint32_t, uint16_t, uint32_t*) = nullptr;
};

struct ReadDetails {
    const char* status = "unread";
    uint32_t raw_move_word = 0; /* known position-X bits, NOT a game pointer */
    uint32_t move_base_indirect = 0; /* unverified claim; never dereferenced */
    uint32_t hit_rank = 0, recovery_ptr = 0;
    uint16_t move_id = 0, tech_id = 0, startup_from = 0, startup_to = 0;
    uint8_t raw_hitbox = 0;
    unsigned graph_moves = 0, recovery_entries = 0;
};

/* Bounds below are host safety limits, not newly discovered game addresses. */
constexpr unsigned kMaxGraphMoves = 32;
constexpr unsigned kRecoveryEntries = 16;
constexpr uint32_t kMoveSize = 0x4C, kRecoverySize = 0x18;

namespace reader_detail {

inline bool span(uint32_t address, size_t size)
{
    return address >= 0x10000u && size != 0 && size <= 0xF0000000ull &&
           (uint64_t)address + size <= 0xF0000000ull;
}

inline bool read(const MemoryAccess& mem, uint32_t address, void* out, size_t size)
{
    return mem.read && out && span(address, size) &&
           mem.read(mem.context, address, out, size);
}

inline bool offset(uint32_t base, int32_t displacement, uint32_t& result)
{
    const int64_t sum = (int64_t)base + displacement;
    if (sum < 0 || sum > 0xFFFFFFFFll) return false;
    result = (uint32_t)sum;
    return true;
}

inline uint16_t be16(const uint8_t* bytes)
{
    return (uint16_t)(((uint16_t)bytes[0] << 8) | bytes[1]);
}

inline uint32_t be32(const uint8_t* bytes)
{
    return ((uint32_t)bytes[0] << 24) | ((uint32_t)bytes[1] << 16) |
           ((uint32_t)bytes[2] << 8) | bytes[3];
}

inline bool field(const MemoryAccess& mem, uint32_t base, int32_t displacement,
                  uint8_t* bytes, size_t size)
{
    uint32_t address;
    return offset(base, displacement, address) && read(mem, address, bytes, size);
}

inline bool scalars(const MemoryAccess& mem, uint32_t base, unsigned player,
                    Sample& out, ReadDetails& details)
{
    if (player > 1) return false;
    uint8_t frame[4], length[2], active, move[4], indirect[4], character;
    /* Every field below is an UNVERIFIED RPCS3 claim, interpreted relative to
     * the notes' apparent P2 block 0x10090900. No EU/US shift is applied.
     * AnimFrame is outside the block; HitboxActive differs from known +0x214.
     * The exact supplied MovePtr word is independently contradicted above. */
    const uint32_t character_address[2] = { 0x100947B3u, 0x1009482Bu };
    if (!field(mem, base, -0x1C, frame, sizeof frame) ||
        !field(mem, base, 0xC0, length, sizeof length) ||
        !field(mem, base, 0x144, &active, 1) ||
        !field(mem, base, 0x10, move, sizeof move) ||
        !field(mem, base, 0x0C, indirect, sizeof indirect) ||
        !read(mem, character_address[player], &character, 1)) return false;
    out.anim_frame = be32(frame);
    out.anim_length = be16(length);
    out.hitbox_active = active == 1;
    out.move_ptr = be32(move); /* raw claim for diagnostics, NOT dereferenced */
    out.char_id = character;
    details.raw_move_word = out.move_ptr;
    details.raw_hitbox = active;
    details.move_base_indirect = be32(indirect);
    return true;
}

inline bool structure_pointer(uint32_t address, size_t size)
{
    return (address & 3u) == 0 && span(address, size);
}

inline bool name(const MemoryAccess& mem, uint32_t address, char (&out)[64])
{
    memset(out, 0, sizeof out);
    for (unsigned i = 0; i < sizeof out; ++i) {
        uint32_t current;
        uint8_t byte;
        if (!offset(address, (int32_t)i, current) || !read(mem, current, &byte, 1)) return false;
        if (!byte) return i != 0;
        /* Reject control bytes instead of permitting diagnostic log injection. */
        if (byte < 0x20 || byte > 0x7E) return false;
        out[i] = (char)byte;
    }
    out[sizeof out - 1] = 0;
    return false; /* no ASCIIZ terminator within the safety cap */
}

struct Move {
    char name[64] = {};
    uint32_t hit_rank = 0, recovery = 0;
    uint16_t id = 0, tech = 0, startup_from = 0, startup_to = 0;
};

inline bool move(const MemoryAccess& mem, uint32_t address, Move& out)
{
    uint8_t bytes[kMoveSize];
    if (!structure_pointer(address, sizeof bytes) || !read(mem, address, bytes, sizeof bytes)) return false;
    if (!name(mem, be32(bytes), out.name)) return false;
    /* UNVERIFIED move layout, used only with synthetic fixtures. */
    out.hit_rank = be32(bytes + 0x10);
    out.recovery = be32(bytes + 0x14);
    out.id = be16(bytes + 0x1C);
    out.tech = be16(bytes + 0x1E);
    out.startup_from = be16(bytes + 0x44);
    out.startup_to = be16(bytes + 0x46);
    return true;
}

} // namespace reader_detail

/* Production entry point. Valid stays false even if every scalar is readable:
 * readability cannot turn a known X coordinate into a verified MovePtr. */
inline bool read_sample(const MemoryAccess& mem, uint32_t fighter_base,
                        unsigned player, Sample& out, ReadDetails* details = nullptr)
{
    out = Sample{};
    ReadDetails d;
    d.status = reader_detail::scalars(mem, fighter_base, player, out, d)
        ? "mapping_conflict_position_x" : "unreadable_scalar_claim";
    if (details) *details = d;
    return false;
}

/* SYNTHETIC FIXTURES ONLY. This models the claimed schema so tests can cover
 * the future algorithm without inventing a corrected game address. No runtime
 * path or environment switch may call this function. */
inline bool read_fixture_sample(const MemoryAccess& mem, uint32_t fighter_base,
                                unsigned player, Sample& out, ReadDetails* details = nullptr)
{
    using namespace reader_detail;
    out = Sample{};
    ReadDetails d;
    d.status = "invalid_fixture";
    if (!scalars(mem, fighter_base, player, out, d) ||
        out.anim_frame > out.anim_length || d.raw_hitbox > 1) {
        if (details) *details = d;
        return false;
    }
    if (!out.move_ptr) {
        out.valid = true;
        d.status = "fixture_no_move";
        if (details) *details = d;
        return true;
    }
    Move root;
    if (!move(mem, out.move_ptr, root)) {
        if (details) *details = d;
        return false;
    }
    memcpy(out.name, root.name, sizeof out.name);
    d.hit_rank = root.hit_rank; d.recovery_ptr = root.recovery;
    d.move_id = root.id; d.tech_id = root.tech;
    d.startup_from = root.startup_from; d.startup_to = root.startup_to;
    out.graph_complete = true;
    uint32_t queue[kMaxGraphMoves] = { out.move_ptr };
    unsigned count = 1;
    /* MISSING ALGORITHM: a bounded breadth-first traversal is our provisional
     * interpretation of recursive continuation. Types 0x50/0x41 and frames
     * are decoded but do not filter branches: the notes do not specify how.
     * Names here are candidates; the tracker always checks neutral first. */
    for (unsigned i = 0; i < count; ++i) {
        Move current;
        if (i == 0) current = root;
        else if (!move(mem, queue[i], current)) { out.graph_complete = false; continue; }
        if (i != 0) {
            bool duplicate_name = !strcmp(out.name, current.name);
            for (unsigned n = 0; n < out.continuation_count; ++n)
                if (!strcmp(out.continuation[n], current.name)) duplicate_name = true;
            if (!duplicate_name) {
                memcpy(out.continuation[out.continuation_count++], current.name, sizeof current.name);
            }
        }
        if (!current.recovery) continue;
        if (!structure_pointer(current.recovery, kRecoveryEntries * kRecoverySize)) {
            out.graph_complete = false; continue;
        }
        for (unsigned entry = 0; entry < kRecoveryEntries; ++entry) {
            uint8_t bytes[kRecoverySize];
            uint32_t address;
            if (!offset(current.recovery, (int32_t)(entry * kRecoverySize), address) ||
                !read(mem, address, bytes, sizeof bytes)) {
                out.graph_complete = false; break;
            }
            ++d.recovery_entries;
            const uint16_t id = be16(bytes + 0x08);
            const uint16_t frames = be16(bytes + 0x10), type = be16(bytes + 0x16);
            (void)frames; (void)type;
            if (!id || id >= 0x8000) continue;
            uint32_t next = 0;
            if (!d.move_base_indirect || !mem.resolve_move ||
                !mem.resolve_move(mem.context, d.move_base_indirect, id, &next) ||
                !structure_pointer(next, kMoveSize)) {
                out.graph_complete = false; continue;
            }
            bool seen = false;
            for (unsigned n = 0; n < count; ++n) if (queue[n] == next) seen = true;
            if (seen) continue;
            if (count == kMaxGraphMoves) { out.graph_complete = false; continue; }
            queue[count++] = next;
        }
    }
    d.graph_moves = count;
    out.valid = true;
    d.status = out.graph_complete ? "fixture_complete" : "fixture_graph_incomplete";
    if (details) *details = d;
    return true;
}

} } // namespace training::shadow
