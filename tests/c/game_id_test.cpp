// src/platform/t5_game.h on its own (tests/test_game_id.py): which program an ELF file is, and whether the
// modules that know the US program's addresses may touch it. Writes small stand-in ELF files (a header with
// e_entry, padded to each program's size); prints PASS n checks.
#include "../../src/platform/t5_game.h"

#include <cstdio>
#include <cstring>
#include <string>
#include <vector>

static int g_checks = 0, g_fail = 0;
#define CHECK(c) do { g_checks++; if (!(c)) { g_fail++; printf("FAIL line %d: %s\n", __LINE__, #c); } } while (0)

static const char* write_elf(const char* name, uint64_t entry, size_t size, bool magic = true)
{
    std::vector<unsigned char> b(size, 0);
    if (size >= 0x40) {
        if (magic) { b[0] = 0x7F; b[1] = 'E'; b[2] = 'L'; b[3] = 'F'; b[4] = 2; b[5] = 2; }
        for (int i = 0; i < 8; i++) b[0x18 + i] = (unsigned char)(entry >> (56 - 8 * i));
    }
    FILE* f = fopen(name, "wb");
    if (!f) { printf("cannot write %s\n", name); return name; }
    if (!b.empty()) fwrite(b.data(), 1, b.size(), f);
    fclose(f);
    return name;
}

int main(int argc, char** argv)
{
    using t5game::Game;
    if (argc > 1) {   // as the runtime is started: argv[1] is the ELF (boot_main.cpp)
        const bool ok = t5game::hooks_ok("test module");
        printf("game %d %s hooks %s\n", (int)t5game::game(), t5game::game_name(), ok ? "on" : "off");
        return 0;
    }
    const char* n = nullptr;
    CHECK(t5game::identify(write_elf("us.elf", 0x447690, 5294536), &n) == Game::US);
    CHECK(strstr(n, "NPUB30009") != nullptr);
    CHECK(t5game::identify(write_elf("eu.elf", 0x356980, 4168760), &n) == Game::EU);
    CHECK(strstr(n, "NPEA00019 v01.00") != nullptr);
    CHECK(t5game::identify(write_elf("eu2.elf", 0x457898, 5363592), &n) == Game::EU_ONLINE);
    // the US entry with another size, another entry: some other program
    CHECK(t5game::identify(write_elf("other.elf", 0x447690, 5294540)) == Game::Other);
    CHECK(t5game::identify(write_elf("other2.elf", 0x10230, 5294536)) == Game::Other);
    // nothing readable: the old behaviour (the US program)
    CHECK(t5game::identify(nullptr) == Game::Unread);
    CHECK(t5game::identify("") == Game::Unread);
    CHECK(t5game::identify("does-not-exist.elf") == Game::Unread);
    CHECK(t5game::identify(write_elf("short.elf", 0, 16)) == Game::Unread);
    CHECK(t5game::identify(write_elf("notelf.elf", 0x447690, 5294536, false)) == Game::Unread);
    // this process: argv[1] is no ELF here, so the hooks stay as they always were
    CHECK(t5game::game() == Game::Unread);
    CHECK(t5game::hooks_ok("test"));
    printf("%s %d checks\n", g_fail ? "FAIL" : "PASS", g_checks);
    return g_fail ? 1 : 0;
}
