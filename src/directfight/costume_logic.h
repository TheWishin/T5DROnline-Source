/*
 * Custom costumes online -- the part without guest memory (docs/DIRECTFIGHT.md
 * "Custom costumes online"): the save's costume blocks, the table each player
 * sends at the start of a netplay session, and the check both PCs make on
 * every block before it reaches the game. Header-only, so tests/c/costume_test.cpp
 * runs it without the game.
 *
 * A character's customization (the game's own layout; SYS-DATA, the system save
 * the title loads from NPUB30009-SYSNET):
 *
 *   SYS-DATA + 0x820 + c * 0x108   c = the item character index (fighter +0x40),
 *                                  0..34; three costumes of 0x58 bytes:
 *     +0x00  32 x u16  parts bought, item id (low byte), in the order bought, 0 = none
 *     +0x40   4 x u16  the part worn per category (HEAD, FACE, BODY up, BODY down), 0xFFFF = none
 *     +0x48   3 x u32  colours bought: a bit per colour of COLOR1..3
 *     +0x54   3 x u8   the colour worn per COLOR1..3, 0xFF = none
 *     +0x57   u8       0
 *
 * The same 0x108 bytes make the first part of each side's VS custom data
 * (0x106C9934 + side * 0x1F4), which the fight's loading reads.
 *
 * Wire table (all big-endian where it matters; built and read only here):
 *   "T5CO" | u8 version (1) | u8 count n (0..35) | u16 0
 *   n x { u8 c | 0x108 bytes }     c strictly increasing, < 35
 * At most 8 + 35 * 0x109 = 9,283 bytes. Anything else is not a table: the
 * receiver takes the sender's whole table as empty (default costumes).
 */
#pragma once
#include <stdint.h>
#include <string.h>
#include <vector>

namespace costume {

constexpr int      kChars      = 35;          /* item character indices 0..34 */
constexpr uint32_t kBlock      = 0x108;       /* one character: three costumes */
constexpr uint32_t kCostume    = 0x58;
constexpr uint32_t kSaveBase   = 0x820;       /* SYS-DATA offset of character 0's block */
constexpr uint32_t kSaveSize   = 0x218C0;     /* SYS-DATA's size */
constexpr uint32_t kWireHead   = 8;
constexpr uint32_t kWireMax    = kWireHead + kChars * (1 + kBlock);
constexpr uint8_t  kWireVer    = 1;
constexpr int      kMaxItems   = 128;         /* longest per-character item list taken */

inline uint16_t be16(const uint8_t* p) { return (uint16_t)((p[0] << 8) | p[1]); }
inline uint32_t be32(const uint8_t* p) { return ((uint32_t)p[0] << 24) | ((uint32_t)p[1] << 16) | ((uint32_t)p[2] << 8) | p[3]; }

struct Table {
    bool have[kChars] = {};
    uint8_t blk[kChars][kBlock] = {};
    int count() const { int n = 0; for (bool h : have) n += h; return n; }
};

/* Something worn in this block (a part or a colour): only those are sent. */
inline bool block_custom(const uint8_t* b)
{
    for (int k = 0; k < 3; k++) {
        const uint8_t* cs = b + k * kCostume;
        for (int i = 0; i < 4; i++) { const uint16_t w = be16(cs + 0x40 + 2 * i); if (w != 0xFFFF && w != 0) return true; }
        for (int i = 0; i < 3; i++) if (cs[0x54 + i] != 0xFF) return true;
    }
    return false;
}

/* The items character c can wear: its list in the game's price table. */
struct Items { int n = 0; uint16_t id[kMaxItems] = {}; bool has(uint16_t v) const { for (int i = 0; i < n; i++) if (id[i] == v) return true; return false; } };

/* The check both PCs make on a block before writing it into the game: every
 * bought part one of the character's own items, in a compact list without
 * repeats; every worn part none or one bought; every worn colour none or one
 * bought; the spare byte 0. One failure anywhere: the whole block is not used
 * (default costumes for that character). */
inline bool block_valid(const uint8_t* b, const Items& items, const char** why = nullptr)
{
    auto no = [&](const char* w) { if (why) *why = w; return false; };
    for (int k = 0; k < 3; k++) {
        const uint8_t* cs = b + k * kCostume;
        uint16_t bought[32];
        int nb = 0;
        bool ended = false;
        for (int i = 0; i < 32; i++) {
            const uint16_t v = be16(cs + 2 * i);
            if (v == 0) { ended = true; continue; }
            if (ended) return no("a gap in the bought list");
            if (v > 0xFF || !items.has(v)) return no("a part the character has no such item");
            for (int j = 0; j < nb; j++) if (bought[j] == v) return no("a part bought twice");
            bought[nb++] = v;
        }
        for (int i = 0; i < 4; i++) {
            const uint16_t w = be16(cs + 0x40 + 2 * i);
            if (w == 0xFFFF || w == 0) continue;
            bool found = false;
            for (int j = 0; j < nb; j++) if (bought[j] == w) found = true;
            if (!found) return no("a part worn but not bought");
        }
        for (int i = 0; i < 3; i++) {
            const uint8_t w = cs[0x54 + i];
            if (w == 0xFF) continue;
            if (w >= 32 || !((be32(cs + 0x48 + 4 * i) >> w) & 1)) return no("a colour worn but not bought");
        }
        if (cs[0x57] != 0) return no("the spare byte is not 0");
    }
    return true;
}

/* A SYS-DATA image -> the blocks with something worn. */
inline bool from_save(const uint8_t* d, size_t n, Table& t)
{
    t = Table();
    if (n < kSaveBase + kChars * kBlock) return false;
    for (int c = 0; c < kChars; c++) {
        const uint8_t* b = d + kSaveBase + c * kBlock;
        if (!block_custom(b)) continue;
        t.have[c] = true;
        memcpy(t.blk[c], b, kBlock);
    }
    return true;
}

inline std::vector<uint8_t> to_wire(const Table& t)
{
    std::vector<uint8_t> w = { 'T', '5', 'C', 'O', kWireVer, (uint8_t)t.count(), 0, 0 };
    for (int c = 0; c < kChars; c++) {
        if (!t.have[c]) continue;
        w.push_back((uint8_t)c);
        w.insert(w.end(), t.blk[c], t.blk[c] + kBlock);
    }
    return w;
}

/* The exact inverse of to_wire; false (and an empty table) for anything else. */
inline bool from_wire(const uint8_t* w, size_t n, Table& t)
{
    t = Table();
    if (n < kWireHead || n > kWireMax || memcmp(w, "T5CO", 4) || w[4] != kWireVer || w[6] || w[7]) return false;
    const int cnt = w[5];
    if (cnt > kChars || n != kWireHead + (size_t)cnt * (1 + kBlock)) return false;
    int last = -1;
    for (int i = 0; i < cnt; i++) {
        const uint8_t* e = w + kWireHead + (size_t)i * (1 + kBlock);
        if (e[0] >= kChars || (int)e[0] <= last) { t = Table(); return false; }
        last = e[0];
        t.have[last] = true;
        memcpy(t.blk[last], e + 1, kBlock);
    }
    return true;
}

/* FNV-1a 64: logged by both PCs for the bytes they wrote, so two logs can be compared. */
inline uint64_t fnv64(const uint8_t* p, size_t n, uint64_t h = 0xcbf29ce484222325ull)
{
    for (size_t i = 0; i < n; i++) { h ^= p[i]; h *= 0x100000001b3ull; }
    return h;
}

} // namespace costume
