/*
 * Custom costumes online: src/directfight/costume_logic.h without the game (tests/test_costumes.py builds
 * and runs it; AddressSanitizer when the LLVM install has it). Prints "PASS <n> checks".
 *
 *   - a SYS-DATA image -> the table of the blocks with something worn (and only those);
 *   - the wire table: exact round trip, every malformed one refused whole (magic, version, count, length,
 *     order, character index, size bound), random bytes never read past their end;
 *   - the block check both PCs make: each rule on its own, the real Lili block of a save that bought and
 *     wears the Lace Hairband (0x33) and item 0x34 passes, a shop-free fresh block passes;
 *   - FNV-1a 64 against its reference value.
 */
#include <cstdio>
#include <cstdlib>
#include <cstring>
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

static void check_valid()
{
    const Items it = lili_items();
    uint8_t b[kBlock];
    const char* why = nullptr;
    lili_block(b);
    CHECK(block_valid(b, it, &why), "the real Lili block was refused: %s", why);
    fresh_block(b);
    CHECK(block_valid(b, it, &why), "a fresh block was refused: %s", why);

    auto refused = [&](void (*mod)(uint8_t*), const char* what) {
        uint8_t v[kBlock]; lili_block(v); mod(v);
        const char* w = nullptr;
        CHECK(!block_valid(v, it, &w), "accepted: %s", what);
    };
    refused([](uint8_t* v) { put16(v + kCostume + 0, 0x31); }, "an item Lili does not have");
    refused([](uint8_t* v) { put16(v + kCostume + 0, 0x133); }, "an id above 0xFF");
    refused([](uint8_t* v) { put16(v + kCostume + 2, 0x33); }, "a part bought twice");
    refused([](uint8_t* v) { put16(v + kCostume + 2, 0); put16(v + kCostume + 4, 0x34); }, "a gap in the bought list");
    refused([](uint8_t* v) { put16(v + kCostume + 0x42, 0x3d); }, "a part worn but not bought");
    refused([](uint8_t* v) { v[kCostume + 0x55] = 0; }, "a colour worn but not bought");
    refused([](uint8_t* v) { v[kCostume + 0x54] = 40; }, "colour index 40");
    refused([](uint8_t* v) { v[2 * kCostume + 0x57] = 1; }, "the spare byte set");
    Items none;
    lili_block(b);
    CHECK(!block_valid(b, none, &why), "items of a character without an item list were accepted");
    CHECK(block_custom(b), "Lili's block is customized");
    fresh_block(b);
    CHECK(!block_custom(b), "a fresh block is not customized");
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
    check_hash();
    if (g_fail) { printf("FAIL %d of %d checks\n", g_fail, g_checks); return 1; }
    printf("PASS %d checks\n", g_checks);
    return 0;
}
