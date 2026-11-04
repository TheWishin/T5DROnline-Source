// src/platform/t5_addr.h on its own (tests/test_eu_online_addr.py): this program's address of a US address. Writes
// stand-in ELF files (a header with e_entry, padded to each program's size); prints PASS n checks.
//   eu_addr_test                  the lookup: identity here (no ELF), spans and regions of the EU Online table
//   eu_addr_test <elf>            T5A(the US TOC) as this program sees it: "game N eu 0x... hooks on|off"
//   eu_addr_test <elf> missing    asks for an address the table does not have (EU Online: stops with FATAL)
#include "../../src/platform/t5_addr.h"

#include <cstdio>
#include <cstring>
#include <vector>

static int g_checks = 0, g_fail = 0;
#define CHECK(c) do { g_checks++; if (!(c)) { g_fail++; printf("FAIL line %d: %s\n", __LINE__, #c); } } while (0)

// Pin the takeover's US addresses as well as their EU counterparts. In particular,
// r2 is the OPD's TOC BASE: matching a load from the slot at US r2 gave the wrong
// EU r2 (0x481130), making every takeover helper read unrelated globals.
static void check_keyread(bool eu)
{
    const uint32_t pairs[][2] = {
        {0x470540u, 0x481000u},                 // TOC base, independently given by entry/keyread OPDs
        {0x104CB5C0u, 0x104CBF40u},             // keyread wake semaphore
        {0x104CB5E0u, 0x104CBF60u},             // thread object
        {0x104CCDF4u, 0x104CD774u},             // quit
        {0x104CCDF8u, 0x104CD778u},             // ring reset
        {0x104CCDFCu, 0x104CD77Cu},             // ring
        {0x104CCE3Cu, 0x104CD7BCu},             // write index
        {0x104CCE40u, 0x104CD7C0u},             // read index
        {0x106D4A30u, 0x106DCA30u},             // main frame semaphore
        {0x106D4D00u, 0x106DCD00u},             // recursive frame lock
        {0x106D4D88u, 0x106DCD88u},             // frame clock
        {0x09A204u, 0x09B73Cu},                 // guest countdown (US 60 / EU 50)
        {0x08F3A4u, 0x08F9DCu},                 // pad update, including EU vibration
        {0x120764u, 0x12204Cu},                 // ring reset
        {0x08F6F0u, 0x08FD30u},                 // port mask
        {0x12071Cu, 0x122004u},                 // ring advance
        {0x13F91Cu, 0x1413B8u},                 // tick tail
        {0x3C6F00u, 0x3D7684u},                 // frame lock import
        {0x3C6F20u, 0x3D76A4u},                 // frame unlock import
    };
    for (const auto& pair : pairs) CHECK(T5A(pair[0]) == pair[eu ? 1 : 0]);
}

static void write_elf(const char* name, uint64_t entry, size_t size)
{
    std::vector<unsigned char> b(size, 0);
    b[0] = 0x7F; b[1] = 'E'; b[2] = 'L'; b[3] = 'F'; b[4] = 2; b[5] = 2;
    for (int i = 0; i < 8; i++) b[0x18 + i] = (unsigned char)(entry >> (56 - 8 * i));
    FILE* f = fopen(name, "wb");
    if (f) { fwrite(b.data(), 1, b.size(), f); fclose(f); }
}

int main(int argc, char** argv)
{
    if (argc > 1) {
        const bool ok = t5game::hooks_ok("test module");
        if (argc > 2) { printf("asking\n"); fflush(stdout); uint32_t a = T5A(0x4u); printf("reached %08X\n", a); return 0; }
        printf("game %d eu 0x%08X hooks %s\n", (int)t5game::game(), T5A(0x470540u), ok ? "on" : "off");
        check_keyread(t5game::game() == t5game::Game::EU_ONLINE);
        return g_fail ? 1 : 0;
    }
    write_elf("us.elf", 0x447690, 5294536);
    write_elf("eu_online.elf", 0x457898, 5363592);
    // no ELF at argv[1]: the US addresses themselves
    CHECK(t5game::game() == t5game::Game::Unread);
    check_keyread(false);
    CHECK(T5A(0x1008F070u) == 0x1008F070u);
    CHECK(T5A(0x470540u) == 0x470540u);                           // the US TOC must stay unchanged
    CHECK(T5R(0x1008E000u, 0x4000) == 0x1008E000u);
    CHECK(t5game::region(0x1008E000u, 0xB80).addr == 0x1008E000u && t5game::region(0x1008E000u, 0xB80).len == 0xB80);
    // the EU Online table (the lookup used for that program)
    CHECK(t5game::addr_eu_online(0x470540u, 1) == 0x481000u);        // r2, not a TOC slot's counterpart
    CHECK(t5game::addr_eu_online(0x1008F070u, 4) == 0x1008F878u);    // the fight phase word (+0x808)
    CHECK(t5game::addr_eu_online(0x1009322Cu, 4) == 0x10093A3Cu);    // the round state (+0x810)
    CHECK(t5game::addr_eu_online(0x104CCDFCu, 0x40) == 0x104CD77Cu); // the input ring (+0x980)
    CHECK(t5game::addr_eu_online(0x0004E9DCu, 1) == 0x0004EE4Cu);    // the start-game routine
    // a span's inside maps with it
    CHECK(t5game::addr_eu_online(0x0004E9E0u, 4) == 0x0004EE50u);
    // regions keep their own length
    for (const t5game::Region& r : t5game::kEuOnlineRegions) {
        CHECK(r.uslen && r.eulen);
        if (r.us == 0x1008E000u && r.uslen == 0xB80) CHECK(r.eu == 0x1008E840u && r.eulen == 0xB48);
    }
    // sorted, no overlap
    const size_t n = sizeof(t5game::kEuOnline) / sizeof(t5game::kEuOnline[0]);
    for (size_t i = 1; i < n; i++)
        CHECK(t5game::kEuOnline[i - 1].us + t5game::kEuOnline[i - 1].len <= t5game::kEuOnline[i].us);
    for (size_t i = 0; i < n; i++) {
        const t5game::Span& s = t5game::kEuOnline[i];
        CHECK(t5game::eu_online_find(s.us) == &s);
        CHECK(t5game::eu_online_find(s.us + s.len - 1) == &s);
        CHECK(t5game::addr_eu_online(s.us, s.len) == s.eu);
    }
    printf("%s %d checks\n", g_fail ? "FAIL" : "PASS", g_checks);
    return g_fail ? 1 : 0;
}
