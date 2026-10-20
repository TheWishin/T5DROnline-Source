/*
 * Custom costumes online: src/directfight/costume_logic.h without the game (tests/test_costumes.py builds
 * and runs it; AddressSanitizer when the LLVM install has it). Prints "PASS <n> checks".
 *
 *   - a SYS-DATA image -> the table of the blocks with something worn (and only those);
 *   - the wire table: exact round trip, every malformed one refused whole (magic, version, count, length,
 *     order, character index, size bound), random bytes never read past their end;
 *   - the block check both PCs make: each rule on its own, the real Lili block of a save that bought and
 *     wears the Lace Hairband (0x33) and item 0x34 passes, a shop-free fresh block passes; with the item
 *     shop's tables (hardening 1.1.4): a part worn in another part's place, a part the costume does not
 *     have, a colour the costume does not have (security review 3: colour 31) are refused, a costume the
 *     character does not have wears nothing;
 *   - the tables as the game keeps them, built here from made-up items (no game data): a data entry
 *     XOR-coded and summed like T55DATA1.BIN's, the pack, PAC nodes named and not, a directory XOR-coded,
 *     the colour file, a model without one; every malformed pack refused whole, random packs never read
 *     past their end;
 *   - FNV-1a 64 against its reference value.
 */
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <utility>
#include <vector>
#include "../../src/directfight/costume_logic.h"

using namespace costume;

static int g_checks = 0, g_fail = 0;
#define CHECK(c, ...) do { g_checks++; if (!(c)) { g_fail++; printf("FAIL line %d: ", __LINE__); printf(__VA_ARGS__); printf("\n"); } } while (0)

static void put16(uint8_t* p, uint16_t v) { p[0] = (uint8_t)(v >> 8); p[1] = (uint8_t)v; }
static void put32(uint8_t* p, uint32_t v) { p[0] = (uint8_t)(v >> 24); p[1] = (uint8_t)(v >> 16); p[2] = (uint8_t)(v >> 8); p[3] = (uint8_t)v; }

/* a block as a fresh save has it: nothing bought or worn */
static void fresh_block(uint8_t* b)
{
    memset(b, 0, kBlock);
    for (int k = 0; k < 3; k++) {
        uint8_t* cs = b + k * kCostume;
        for (int i = 0; i < 4; i++) put16(cs + 0x40 + 2 * i, 0xFFFF);
        for (int i = 0; i < 3; i++) cs[0x54 + i] = 0xFF;
    }
}

/* Lili's block of the unlock agent's save (costume 1: Lace Hairband 0x33 on the head, 0x34 on the body,
 * COLOR1 colour 1 of the bought 0 and 1) */
static void lili_block(uint8_t* b)
{
    fresh_block(b);
    uint8_t* cs = b + 1 * kCostume;
    put16(cs + 0, 0x33); put16(cs + 2, 0x34);
    put16(cs + 0x40, 0x33); put16(cs + 0x44, 0x34);
    put32(cs + 0x48, 3);
    cs[0x54] = 1;
}

static Items lili_items()
{
    const uint16_t ids[] = { 0x3d, 0x3e, 0x44, 0x49, 0x4c, 0x4b, 0x32, 0x3f, 0x48, 0x47, 0x45, 0x40, 0x41, 0x43,
                             0x42, 0x4d, 0x46, 0x33, 0x4a, 0x3c, 0x34, 0x36, 0x35, 0x38, 0x4e, 0x3b, 0x3a };
    Items it;
    for (uint16_t v : ids) it.id[it.n++] = v;
    return it;
}

static void check_save()
{
    std::vector<uint8_t> save(kSaveSize, 0);
    for (int c = 0; c < kChars; c++) fresh_block(&save[kSaveBase + c * kBlock]);
    put32(&save[kSaveBase + 4 * kBlock + kCostume + 0x48], 2);       /* a default colour bit, nothing worn */
    Table t;
    CHECK(from_save(save.data(), save.size(), t) && t.count() == 0, "a fresh save gave %d blocks", t.count());
    lili_block(&save[kSaveBase + 31 * kBlock]);
    CHECK(from_save(save.data(), save.size(), t) && t.count() == 1 && t.have[31], "Lili's block not taken alone");
    CHECK(!memcmp(t.blk[31], &save[kSaveBase + 31 * kBlock], kBlock), "Lili's block changed on the way");
    CHECK(!from_save(save.data(), kSaveBase + 10, t) && t.count() == 0, "a short save was read");
}

static void check_wire()
{
    Table t;
    lili_block(t.blk[31]); t.have[31] = true;
    fresh_block(t.blk[0]); put16(t.blk[0] + 0x40, 0x3a); put16(t.blk[0], 0x3a); t.have[0] = true;
    const std::vector<uint8_t> w = to_wire(t);
    CHECK(w.size() == kWireHead + 2 * (1 + kBlock), "wire size %zu", w.size());
    Table u;
    CHECK(from_wire(w.data(), w.size(), u) && u.count() == 2 && u.have[0] && u.have[31], "round trip");
    CHECK(!memcmp(u.blk[31], t.blk[31], kBlock) && !memcmp(u.blk[0], t.blk[0], kBlock), "round trip bytes");
    CHECK(to_wire(u) == w, "to_wire(from_wire(w)) != w");

    Table e;
    const std::vector<uint8_t> we = to_wire(e);
    CHECK(we.size() == kWireHead && from_wire(we.data(), we.size(), u) && u.count() == 0, "the empty table");

    auto refused = [&](std::vector<uint8_t> v, const char* what) {
        Table x; x.have[3] = true;
        CHECK(!from_wire(v.data(), v.size(), x) && x.count() == 0, "accepted: %s", what);
    };
    { auto v = w; v[0] = 'X'; refused(v, "bad magic"); }
    { auto v = w; v[4] = 2; refused(v, "version 2"); }
    { auto v = w; v[5] = 3; refused(v, "count larger than the data"); }
    { auto v = w; v[5] = 1; refused(v, "count smaller than the data"); }
    { auto v = w; v[6] = 1; refused(v, "reserved byte set"); }
    { auto v = w; v.pop_back(); refused(v, "one byte short"); }
    { auto v = w; v.push_back(0); refused(v, "one byte long"); }
    { auto v = w; v[kWireHead] = 31; v[kWireHead + 1 + kBlock] = 0; refused(v, "characters out of order"); }
    { auto v = w; v[kWireHead + 1 + kBlock] = 0; refused(v, "a character twice"); }
    { auto v = w; v[kWireHead + 1 + kBlock] = 35; refused(v, "character index 35"); }
    {
        Table all;
        for (int c = 0; c < kChars; c++) { fresh_block(all.blk[c]); all.have[c] = true; }
        auto v = to_wire(all);
        CHECK(v.size() == kWireMax, "full table %zu bytes, bound %u", v.size(), kWireMax);
        CHECK(from_wire(v.data(), v.size(), u) && u.count() == kChars, "the full table refused");
        v[5] = 36; v.resize(v.size() + 1 + kBlock, 0); v[v.size() - 1 - kBlock] = 34;
        refused(v, "36 entries");
    }
    /* random bytes: never accepted unless they are a table, never read past the end (ASan) */
    uint32_t x = 12345;
    for (int i = 0; i < 20000; i++) {
        x ^= x << 13; x ^= x >> 17; x ^= x << 5;
        std::vector<uint8_t> v(x % (kWireMax + 64));
        for (auto& b : v) { x ^= x << 13; x ^= x >> 17; x ^= x << 5; b = (uint8_t)x; }
        if (v.size() >= 8 && (x & 1)) { memcpy(v.data(), "T5CO", 4); v[4] = 1; v[5] = (uint8_t)(x % 4); v[6] = v[7] = 0; }
        Table r;
        if (from_wire(v.data(), v.size(), r)) CHECK(to_wire(r) == v, "an accepted random table is not canonical");
        else CHECK(r.count() == 0, "a refused table left blocks behind");
    }
}

/* Made-up item shop tables for Lili's block: costume 1 (the one customized) wears 0x33 on the head and 0x34 on
 * the upper body and has 6 colours per place; costume 0 has a few other parts; costume 2 is not one she has.
 * (Not the game's tables -- those stay in the player's game; tests/test_costumes.py has no game data.) */
static CharRules lili_rules()
{
    CharRules r;
    r.k[0].exists = true;
    r.k[0].place[0x3d] = 1; r.k[0].place[0x3e] = 2; r.k[0].place[0x44] = 4; r.k[0].place[0x49] = 8;
    r.k[0].colours[0] = r.k[0].colours[1] = r.k[0].colours[2] = 6;
    r.k[1].exists = true;
    r.k[1].place[0x33] = 1; r.k[1].place[0x3a] = 1; r.k[1].place[0x34] = 4; r.k[1].place[0x3b] = 8; r.k[1].place[0x3c] = 2;
    r.k[1].colours[0] = 6; r.k[1].colours[1] = 9; r.k[1].colours[2] = 3;
    return r;
}

static void check_valid()
{
    const Items it = lili_items();
    const CharRules rules = lili_rules();
    uint8_t b[kBlock];
    const char* why = nullptr;
    lili_block(b);
    CHECK(block_valid(b, it, rules, &why), "the real Lili block was refused: %s", why);
    fresh_block(b);
    CHECK(block_valid(b, it, rules, &why), "a fresh block was refused: %s", why);
    CHECK(block_valid(b, it, CharRules(), &why), "a fresh block of a character without tables was refused: %s", why);

    auto refused = [&](void (*mod)(uint8_t*), const char* what, const char* expect) {
        uint8_t v[kBlock]; lili_block(v); mod(v);
        const char* w = nullptr;
        CHECK(!block_valid(v, it, rules, &w), "accepted: %s", what);
        CHECK(w && !strcmp(w, expect), "%s: said \"%s\", not \"%s\"", what, w ? w : "", expect);
    };
    refused([](uint8_t* v) { put16(v + kCostume + 0, 0x31); }, "an item Lili does not have", "a part the character has no such item");
    refused([](uint8_t* v) { put16(v + kCostume + 0, 0x133); }, "an id above 0xFF", "a part the character has no such item");
    refused([](uint8_t* v) { put16(v + kCostume + 2, 0x33); }, "a part bought twice", "a part bought twice");
    refused([](uint8_t* v) { put16(v + kCostume + 2, 0); put16(v + kCostume + 4, 0x34); }, "a gap in the bought list",
            "a gap in the bought list");
    refused([](uint8_t* v) { put16(v + kCostume + 0x42, 0x3a); }, "a part worn but not bought", "a part worn but not bought");
    refused([](uint8_t* v) { v[kCostume + 0x55] = 0; }, "a colour worn but not bought", "a colour worn but not bought");
    refused([](uint8_t* v) { v[kCostume + 0x54] = 40; }, "colour index 40", "a colour worn but not bought");
    refused([](uint8_t* v) { v[2 * kCostume + 0x57] = 1; }, "the spare byte set", "the spare byte is not 0");
    /* the item shop's tables (security review 3: the old check let these through) */
    refused([](uint8_t* v) { put16(v + kCostume + 0x40, 0xFFFF); put16(v + kCostume + 0x46, 0x33); },
            "the hairband worn as the lower body", "a part worn in another part's place");
    refused([](uint8_t* v) { put16(v + kCostume + 0x40, 0x34); put16(v + kCostume + 0x44, 0x33); },
            "head and upper body swapped", "a part worn in another part's place");
    refused([](uint8_t* v) { put16(v + kCostume + 4, 0x3d); }, "a part of costume 0 bought for costume 1",
            "a part this costume does not have");
    refused([](uint8_t* v) { put32(v + kCostume + 0x48, 0x80000003); v[kCostume + 0x54] = 31; },
            "colour 31 bought and worn (the review's block)", "a colour bought that the costume does not have");
    refused([](uint8_t* v) { put32(v + kCostume + 0x48, 0x43); }, "a colour bought past the 6 the place has",
            "a colour bought that the costume does not have");
    refused([](uint8_t* v) { put32(v + kCostume + 0x4C, 1u << 9); }, "COLOR2's 10th colour of 9",
            "a colour bought that the costume does not have");
    refused([](uint8_t* v) { put16(v + 2 * kCostume, 0x33); }, "a part bought for a costume she does not have",
            "a part this costume does not have");
    refused([](uint8_t* v) { put32(v + 2 * kCostume + 0x48, 1); }, "a colour bought for a costume she does not have",
            "a colour bought that the costume does not have");
    {
        uint8_t v[kBlock]; lili_block(v);                         /* the last colour of each place: fine */
        put32(v + kCostume + 0x48, 0x23); v[kCostume + 0x54] = 5;
        put32(v + kCostume + 0x4C, 0x100); v[kCostume + 0x55] = 8;
        put32(v + kCostume + 0x50, 0x4); v[kCostume + 0x56] = 2;
        CHECK(block_valid(v, it, rules, &why), "the last colour of each place was refused: %s", why);
        put16(v + kCostume + 4, 0x3a); put16(v + kCostume + 6, 0x3b); put16(v + kCostume + 8, 0x3c);
        put16(v + kCostume + 0x40, 0x3a); put16(v + kCostume + 0x42, 0x3c); put16(v + kCostume + 0x46, 0x3b);
        CHECK(block_valid(v, it, rules, &why), "four parts, each in its place, refused: %s", why);
    }
    Items none;
    lili_block(b);
    CHECK(!block_valid(b, none, rules, &why), "items of a character without an item list were accepted");
    CHECK(!block_valid(b, it, CharRules(), &why), "a block of a character without tables was accepted");
    CHECK(block_custom(b), "Lili's block is customized");
    fresh_block(b);
    CHECK(!block_custom(b), "a fresh block is not customized");
}

/* ---- the tables as the game keeps them, built from made-up items ---- */
static void put32le(std::vector<uint8_t>& v, size_t at, uint32_t x) { for (int i = 0; i < 4; i++) v[at + i] = (uint8_t)(x >> (8 * i)); }
static void push32le(std::vector<uint8_t>& v, uint32_t x) { for (int i = 0; i < 4; i++) v.push_back((uint8_t)(x >> (8 * i))); }
static void align4(std::vector<uint8_t>& v) { while (v.size() & 3) v.push_back(0); }

/* a PAC node with these children (each a byte string), named or not, its directory XOR-coded or not */
static std::vector<uint8_t> pac(const std::vector<std::vector<uint8_t>>& kids, bool named, bool coded)
{
    std::vector<uint8_t> dir;
    std::vector<size_t> fix;                                  /* where each child's offset goes */
    for (size_t k = 0; k < kids.size(); k++) {
        if (named) {
            char name[24];
            snprintf(name, sizeof name, "child_%02zu.bin", k);
            const size_t start = dir.size();
            push32le(dir, 0);
            for (const char* p = name; *p; p++) dir.push_back((uint8_t)*p);
            dir.push_back(0);
            align4(dir);
            push32le(dir, 0);                                 /* the offset, at L - 4 */
            put32le(dir, start, (uint32_t)(dir.size() - start));
            fix.push_back(dir.size() - 4);
            push32le(dir, (uint32_t)kids[k].size());         /* the size, at L */
        } else {
            fix.push_back(dir.size());
            push32le(dir, 0);
            push32le(dir, (uint32_t)kids[k].size());
        }
    }
    const uint32_t size = (uint32_t)(16 + dir.size());
    uint32_t off = size;
    for (size_t k = 0; k < kids.size(); k++) { put32le(dir, fix[k], off); off += (uint32_t)((kids[k].size() + 3) & ~3u); }
    if (coded)
        for (size_t i = 0; i + 4 <= dir.size(); i += 4) { dir[i] ^= 0xFF; dir[i + 1] ^= 0xF0; dir[i + 3] ^= 0xFF; }
    std::vector<uint8_t> v = { 'P', 'A', 'C', 1 };
    push32le(v, (named ? 1u : 0u) | (coded ? 2u : 0u) | 0xC);
    push32le(v, size);
    push32le(v, (uint32_t)kids.size());
    v.insert(v.end(), dir.begin(), dir.end());
    for (const auto& k : kids) { v.insert(v.end(), k.begin(), k.end()); align4(v); }
    return v;
}

static std::vector<uint8_t> item(uint32_t id, uint32_t place_bit)
{
    std::vector<uint8_t> v = { 'I', 'T', 'E', 'M', 'R', 'E', 'C', 0 };
    push32le(v, id); push32le(v, place_bit); push32le(v, 1); push32le(v, 500);
    v.resize(0x40, 0);
    return v;
}

static std::vector<uint8_t> colours(std::vector<uint32_t> counts)
{
    std::vector<uint8_t> v = { 3, 1, 0, (uint8_t)counts.size() };
    for (uint32_t n : counts) {
        push32le(v, 0); push32le(v, n);
        for (uint32_t i = 0; i < n; i++) push32le(v, 100 * (i + 1));
        for (uint32_t i = 0; i < n; i++) { char name[32] = {}; snprintf(name, sizeof name, "colour %u", i); v.insert(v.end(), name, name + 32); }
    }
    return v;
}

/* one model: places[p] = the item ids of place p; cols = the colour file (empty: none) */
static std::vector<uint8_t> model(const std::vector<std::vector<uint32_t>>& places, const std::vector<uint8_t>& cols,
                                  bool named, bool coded)
{
    std::vector<std::vector<uint8_t>> lists;
    for (size_t p = 0; p < places.size(); p++) {
        std::vector<std::vector<uint8_t>> items;
        for (uint32_t id : places[p]) items.push_back(item(id, 1u << p));
        lists.push_back(pac(items, named, false));
    }
    const std::vector<uint8_t> hdr = pac({ { 1, 2, 3, 4 } }, named, false), names = { 0, 0, 0, 0, 0x29, 0, 0, 0 };
    return pac({ hdr, pac({}, false, false), pac(lists, named, coded), cols, names }, named, coded);
}

/* the pack: kPackModels models; the ones not given are copies of the first */
static std::vector<uint8_t> pack(const std::vector<std::pair<int, std::vector<uint8_t>>>& models)
{
    std::vector<std::vector<uint8_t>> body(kPackModels, models[0].second);
    for (const auto& m : models) body[m.first] = m.second;
    std::vector<uint8_t> v;
    push32le(v, kPackModels);
    for (uint32_t i = 0; i < kPackModels; i++) { push32le(v, 0); push32le(v, 0); }
    for (uint32_t i = 0; i < kPackModels; i++) {
        align4(v);
        put32le(v, 4 + 8 * i, (uint32_t)v.size());
        put32le(v, 8 + 8 * i, (uint32_t)body[i].size());
        v.insert(v.end(), body[i].begin(), body[i].end());
    }
    return v;
}

static void check_entry()
{
    /* encoded the way the game's data is: LE words ^ k, k = key at every 0x800 bytes, then 5k + 3 */
    for (size_t n : { (size_t)0, (size_t)3, (size_t)8, (size_t)0x7FF, (size_t)0x800, (size_t)0x1803, (size_t)0x4000 }) {
        std::vector<uint8_t> plain(n), raw(n), out;
        uint32_t x = 777 + (uint32_t)n;
        for (auto& b : plain) { x = x * 1103515245u + 12345u; b = (uint8_t)(x >> 16); }
        const uint32_t key = 0x2481C6D0u ^ (uint32_t)n;
        uint32_t k = key, sum = 0;
        for (size_t i = 0; i < n; i += 4) {
            if ((i & 0x7FF) == 0) k = key;
            const size_t m = n - i < 4 ? n - i : 4;
            for (size_t j = 0; j < m; j++) raw[i + j] = plain[i + j] ^ (uint8_t)(k >> (8 * j));
            if (m == 4) sum += le32(&plain[i]);
            k = 5 * k + 3;
        }
        CHECK(t55_decode(raw.data(), raw.size(), key, sum, out) && out == plain, "entry of %zu bytes not decoded", n);
        CHECK(!t55_decode(raw.data(), raw.size(), key, sum + 1, out) || n < 4, "a wrong sum passed (%zu bytes)", n);
        if (n >= 0x804) {
            std::vector<uint8_t> bad = raw; bad[0x801] ^= 1;
            CHECK(!t55_decode(bad.data(), bad.size(), key, sum, out), "a changed byte passed the sum");
        }
    }
}

static void check_pack()
{
    int models[kChars][3];
    for (auto& c : models) c[0] = c[1] = c[2] = -1;
    models[31][0] = 7; models[31][1] = 8;                     /* Lili: two costumes */
    models[13][0] = 3; models[13][1] = 4; models[13][2] = 5;  /* a character with three, the third without colours */
    const std::vector<uint8_t> m7 = model({ { 0x3d }, { 0x3e }, { 0x44 }, { 0x49 } }, colours({ 6, 6, 6 }), true, true);
    const std::vector<uint8_t> m8 = model({ { 0x33, 0x3a }, { 0x3c }, { 0x34 }, { 0x3b } }, colours({ 6, 9, 3 }), true, false);
    const std::vector<uint8_t> m3 = model({ { 1, 2 }, { 6 }, { 11, 12 }, { 16 } }, colours({ 12, 12 }), false, false);
    const std::vector<uint8_t> m5 = model({ {}, {}, {}, {} }, {}, true, true);
    const std::vector<uint8_t> v = pack({ { 0, m3 }, { 3, m3 }, { 4, m7 }, { 5, m5 }, { 7, m7 }, { 8, m8 } });
    static Rules r;
    CHECK(rules_from_pack(v.data(), v.size(), models, r) && r.ok, "a well-formed pack refused");
    CHECK(!memcmp(r.c[31].k[1].place, lili_rules().k[1].place, 256), "Lili's costume 1 parts read wrong");
    CHECK(r.c[31].k[1].colours[0] == 6 && r.c[31].k[1].colours[1] == 9 && r.c[31].k[1].colours[2] == 3, "colours read wrong");
    CHECK(r.c[31].k[0].place[0x49] == 8 && r.c[31].k[0].exists && !r.c[31].k[2].exists, "costume 0 / 2 read wrong");
    CHECK(r.c[13].k[0].place[12] == 4 && r.c[13].k[0].colours[1] == 12 && r.c[13].k[0].colours[2] == 0,
          "an unnamed node or a file of two colour places read wrong");
    CHECK(r.c[13].k[2].exists && r.c[13].k[2].colours[0] == 0 && !r.c[13].k[2].place[1], "a model without colours read wrong");
    CHECK(!r.c[0].k[0].exists, "a character without models got a costume");
    {
        uint8_t b[kBlock]; lili_block(b);
        const char* why = nullptr;
        CHECK(block_valid(b, lili_items(), r.c[31], &why), "Lili's block refused with the pack's tables: %s", why);
    }
    static Rules again;
    rules_from_pack(v.data(), v.size(), models, again);
    CHECK(rules_hash(r) == rules_hash(again), "the hash of the same tables differs");
    again.c[31].k[1].colours[2] = 4;
    CHECK(rules_hash(r) != rules_hash(again), "the hash did not see a colour count");

    auto refused = [&](std::vector<uint8_t> p, const char* what) {
        static Rules x;
        CHECK(!rules_from_pack(p.data(), p.size(), models, x) && !x.ok, "accepted: %s", what);
    };
    { auto p = v; p[0] = 0x55; refused(p, "a pack of 0x55 models"); }
    { auto p = v; put32le(p, 4 + 8 * 7, (uint32_t)p.size() - 8); refused(p, "a model past the end"); }
    { auto p = v; const uint32_t o = le32(&p[4 + 8 * 7]); p[o] = 'X'; refused(p, "a model without PAC"); }
    { auto p = v; const uint32_t o = le32(&p[4 + 8 * 7]); p[o + 3] = 2; refused(p, "PAC version 2"); }
    { auto p = v; const uint32_t o = le32(&p[4 + 8 * 8]); put32le(p, o + 8, 0x7FFFFFFF); refused(p, "a directory past the end"); }
    { auto p = v; const uint32_t o = le32(&p[4 + 8 * 8]); put32le(p, o + 12, 2); refused(p, "a model with 2 children"); }
    { auto p = v; const uint32_t o = le32(&p[4 + 8 * 8]); put32le(p, o + 16, 0x7FFFFFF0); refused(p, "a name longer than the directory"); }
    {
        auto p = v; const uint32_t o = le32(&p[4 + 8 * 8]);       /* colour count 33 */
        size_t c = o; for (; c + 4 < p.size(); c += 4) if (p[c] == 3 && p[c + 1] == 1 && p[c + 2] == 0 && p[c + 3] == 3) break;
        put32le(p, c + 8, 33); refused(p, "33 colours in a place");
    }
    refused(std::vector<uint8_t>(v.begin(), v.begin() + le32(&v[4 + 8 * 8]) + 40), "a pack cut inside a model");
    refused({}, "nothing");
    /* random changes: never read past the end (ASan), a pack is either read whole or not at all */
    uint32_t x = 99;
    for (int i = 0; i < 3000; i++) {
        auto p = v;
        const int edits = 1 + i % 8;
        for (int e = 0; e < edits; e++) { x ^= x << 13; x ^= x >> 17; x ^= x << 5; p[x % p.size()] ^= (uint8_t)(1 + (x >> 24) % 255); }
        if (i % 5 == 0) { x ^= x << 13; x ^= x >> 17; x ^= x << 5; p.resize(x % p.size()); }
        static Rules y;
        if (!rules_from_pack(p.data(), p.size(), models, y)) CHECK(!y.ok, "a refused pack left tables behind");
    }
}

static void check_hash()
{
    const uint8_t a[] = { 'a' };
    CHECK(fnv64(a, 1) == 0xaf63dc4c8601ec8cull, "FNV-1a 64 of 'a'");
    CHECK(fnv64(nullptr, 0) == 0xcbf29ce484222325ull, "FNV-1a 64 of nothing");
}

int main()
{
    check_save();
    check_wire();
    check_valid();
    check_entry();
    check_pack();
    check_hash();
    if (g_fail) { printf("FAIL %d of %d checks\n", g_fail, g_checks); return 1; }
    printf("PASS %d checks\n", g_checks);
    return 0;
}
