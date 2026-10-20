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
 *
 * What each costume can wear (hardening 1.1.4): the game's own item shop tables.
 * The shop knows, per costume model, the parts of each place (HEAD, FACE, BODY
 * up, BODY down) and how many colours each colour place has. That data is a pack
 * in the game's T55DATA1.BIN, which the shop loads only while it is open
 * (0x152014: resource 0x25 -> *(0x10538F68)), so the check reads it from the
 * file itself (df_costume.cpp), the way the game decodes its data -- only
 * offsets and logic here, the data stays in the player's game:
 *   entry  the game's data table (in the ELF, 0x10053FB0): 28-byte records
 *          {sector, stored, size, sum, flag, key, ptr}, big-endian; the entry's
 *          bytes at sector * 0x800, `stored` long, little-endian u32 words XORed
 *          with k (k = key at every 0x800 bytes, then k = 5k + 3), the u32 sum of
 *          the decoded words = sum; zlib when stored != size.
 *   pack   LE u32 count (0x56 models: the game's own check), count x {LE offset,
 *          LE size} -> one PAC node per model (0xCD9D8).
 *   PAC    "PAC" 01 | LE flags (1: named children, 2: the directory XOR-coded,
 *          0xFFF000FF per big-endian word) | LE directory size | LE count | the
 *          children {LE offset, LE size}, or, named, {LE length L, the name, at
 *          L - 4 LE offset, at L LE size} with the next at L + 4; offsets from
 *          the node (the game's walker 0x1489E8).
 *   model  child 2 = the parts: four PAC nodes (the places), each child of those
 *          an item record with the LE item id at +8 (0x152470); child 3 = the
 *          colours: 03 01 xx n, then n records {LE default, LE count, count LE
 *          prices, count 32-byte names} -- none when it does not start 03 01
 *          (0x268CC8, 0x26A0EC).
 * Which model a costume is: the game's table per item character (0x10052F04,
 * 0x58FD0: {u32 the models, u16 count, ...}), costume k = models[k] for k <
 * count; the save has three costumes per character, a costume the character
 * does not have can wear nothing.
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

/* ---- the game's item shop tables (see the top) ---- */
constexpr int      kPlaces       = 4;           /* HEAD, FACE, BODY up, BODY down: the worn parts' order */
constexpr int      kColourPlaces = 3;           /* COLOR1..3 */
constexpr uint32_t kPackModels   = 0x56;        /* models in the pack (the game refuses another count) */
constexpr uint32_t kMaxEntry     = 16u << 20;   /* largest data entry taken (the pack is ~0.6 MB) */

inline uint32_t le32(const uint8_t* p) { return (uint32_t)p[0] | ((uint32_t)p[1] << 8) | ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24); }

/* One costume: which place each item id goes in (a bit per place; 0 = not this
 * costume's) and how many colours each colour place has. A costume the character
 * does not have is all zero: it can wear nothing. */
struct CostumeRules { bool exists = false; uint8_t place[256] = {}; uint8_t colours[kColourPlaces] = {}; };
struct CharRules { CostumeRules k[3]; };
struct Rules { bool ok = false; CharRules c[kChars]; };

/* An entry of T55DATA1.BIN as the game decodes it (into `out`); false when the
 * decoded words do not add up to the table's sum. */
inline bool t55_decode(const uint8_t* raw, size_t n, uint32_t key, uint32_t sum, std::vector<uint8_t>& out)
{
    out.assign(raw, raw + n);
    uint32_t s = 0, k = key;
    for (size_t i = 0; i < n; i += 4) {
        if ((i & 0x7FF) == 0) k = key;
        uint8_t* p = out.data() + i;
        const size_t m = n - i < 4 ? n - i : 4;
        for (size_t j = 0; j < m; j++) p[j] ^= (uint8_t)(k >> (8 * j));
        if (m == 4) s += le32(p);
        k = 5 * k + 3;
    }
    return s == sum;
}

/* The children of the PAC node at d + o: {offset from the node, size}. */
struct Kid { uint32_t off, size; };
inline bool pac_kids(const uint8_t* d, size_t n, size_t o, std::vector<Kid>& kids)
{
    kids.clear();
    if (o > n || n - o < 16 || memcmp(d + o, "PAC", 3) || d[o + 3] != 1) return false;
    const uint32_t flags = le32(d + o + 4), size = le32(d + o + 8), count = le32(d + o + 12);
    if (size < 16 || size > n - o || count > 4096) return false;
    std::vector<uint8_t> dir(d + o + 16, d + o + size);
    if (flags & 2)                          /* XOR-coded: 0xFFF000FF per big-endian word, (size >> 2) - 4 words */
        for (size_t i = 0; i + 4 <= dir.size(); i += 4) { dir[i] ^= 0xFF; dir[i + 1] ^= 0xF0; dir[i + 3] ^= 0xFF; }
    size_t p = 0;
    for (uint32_t k = 0; k < count; k++) {
        Kid kid;
        if (flags & 1) {                    /* {L, name, offset at L - 4, size at L}, the next at L + 4 */
            if (dir.size() - p < 4) return false;
            const size_t L = le32(&dir[p]) & ~3u;
            if (L < 8 || L > dir.size() - p || dir.size() - p - L < 4) return false;
            kid.off = le32(&dir[p + L - 4]);
            kid.size = le32(&dir[p + L]);
            p += L + 4;
        } else {
            if (dir.size() - p < 8) return false;
            kid.off = le32(&dir[p]);
            kid.size = le32(&dir[p + 4]);
            p += 8;
        }
        kids.push_back(kid);
    }
    return true;
}

/* One model of the pack: its parts per place and its colour counts. */
inline bool pack_model(const uint8_t* d, size_t n, uint32_t model, CostumeRules& r)
{
    r = CostumeRules();
    if (n < 4 || model >= le32(d) || (n - 4) / 8 <= model) return false;
    const size_t mo = le32(d + 4 + 8 * (size_t)model);
    std::vector<Kid> top, places, items;
    if (!pac_kids(d, n, mo, top) || top.size() < 4) return false;
    const size_t po = mo + top[2].off;
    if (!pac_kids(d, n, po, places) || places.size() < (size_t)kPlaces) return false;
    for (int pl = 0; pl < kPlaces; pl++) {
        const size_t lo = po + places[pl].off;
        if (!pac_kids(d, n, lo, items)) return false;
        for (const Kid& it : items) {
            const size_t a = lo + it.off;
            if (a > n || n - a < 12) return false;
            const uint32_t id = le32(d + a + 8);
            if (id <= 0xFF) r.place[id] |= (uint8_t)(1u << pl);
        }
    }
    const size_t co = mo + top[3].off;                 /* the colours: none unless it starts 03 01 */
    if (co <= n && n - co >= 4 && d[co] == 3 && d[co + 1] == 1) {
        const int have = (int8_t)d[co + 3];
        size_t p = co + 4;
        for (int j = 0; j < kColourPlaces && j < have; j++) {
            if (p > n || n - p < 8) return false;
            const uint32_t cnt = le32(d + p + 4);
            if (cnt > 32) return false;                /* (a bit each in the save's u32) */
            r.colours[j] = (uint8_t)cnt;
            const uint64_t len = 8 + 36ull * cnt;
            if (len > n - p) return false;
            p += (size_t)len;
        }
    }
    r.exists = true;
    return true;
}

/* All characters' costumes from the pack; models[c][k] = the model of costume k
 * of item character c, -1 = the character has no such costume. Anything the
 * pack does not hold the way the game reads it: not ok (every customized block
 * is refused then -- on both PCs, which read the same game data). */
inline bool rules_from_pack(const uint8_t* d, size_t n, const int (&models)[kChars][3], Rules& r)
{
    r = Rules();
    if (n < 4 || le32(d) != kPackModels) return false;
    for (int c = 0; c < kChars; c++)
        for (int k = 0; k < 3; k++) {
            if (models[c][k] < 0) continue;
            if (!pack_model(d, n, (uint32_t)models[c][k], r.c[c].k[k])) { r = Rules(); return false; }
        }
    r.ok = true;
    return true;
}

/* The check both PCs make on a block before writing it into the game: every
 * bought part one of the character's own items (the price table) and one of
 * that costume's parts, in a compact list without repeats; every worn part
 * none, or one bought that goes in that place; the bought colours only colours
 * the costume has, every worn colour none or one bought; the spare byte 0.
 * One failure anywhere: the whole block is not used (default costumes for that
 * character). */
inline bool block_valid(const uint8_t* b, const Items& items, const CharRules& rules, const char** why = nullptr)
{
    auto no = [&](const char* w) { if (why) *why = w; return false; };
    for (int k = 0; k < 3; k++) {
        const uint8_t* cs = b + k * kCostume;
        const CostumeRules& cr = rules.k[k];
        uint16_t bought[32];
        int nb = 0;
        bool ended = false;
        for (int i = 0; i < 32; i++) {
            const uint16_t v = be16(cs + 2 * i);
            if (v == 0) { ended = true; continue; }
            if (ended) return no("a gap in the bought list");
            if (v > 0xFF || !items.has(v)) return no("a part the character has no such item");
            if (!cr.place[v]) return no("a part this costume does not have");
            for (int j = 0; j < nb; j++) if (bought[j] == v) return no("a part bought twice");
            bought[nb++] = v;
        }
        for (int i = 0; i < kPlaces; i++) {
            const uint16_t w = be16(cs + 0x40 + 2 * i);
            if (w == 0xFFFF || w == 0) continue;
            bool found = false;
            for (int j = 0; j < nb; j++) if (bought[j] == w) found = true;
            if (!found) return no("a part worn but not bought");
            if (!(cr.place[w] & (1u << i))) return no("a part worn in another part's place");
        }
        for (int i = 0; i < kColourPlaces; i++) {
            const uint32_t mask = be32(cs + 0x48 + 4 * i);
            if (cr.colours[i] < 32 && (mask >> cr.colours[i])) return no("a colour bought that the costume does not have");
            const uint8_t w = cs[0x54 + i];
            if (w == 0xFF) continue;
            if (w >= cr.colours[i] || !((mask >> w) & 1)) return no("a colour worn but not bought");
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

/* The tables' hash: logged by both PCs, so two logs show they checked with the same tables. */
inline uint64_t rules_hash(const Rules& r)
{
    uint64_t h = fnv64(nullptr, 0);
    for (int c = 0; c < kChars; c++)
        for (int k = 0; k < 3; k++) {
            const CostumeRules& cr = r.c[c].k[k];
            const uint8_t e = cr.exists;
            h = fnv64(&e, 1, h);
            h = fnv64(cr.place, sizeof cr.place, h);
            h = fnv64(cr.colours, sizeof cr.colours, h);
        }
    return h;
}

} // namespace costume
