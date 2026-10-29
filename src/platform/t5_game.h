/* Which game program this process runs (docs/EU.md).
 *
 * src/ (netplay, rollback, direct fight, training, practice, perf) reads and
 * detours the game at the guest addresses of ONE program: the US PSN release,
 * NPUB30009 v01.00 (decrypted EBOOT.elf SHA-1 be80165b...). The European
 * release, NPEA00019 v01.00, is a different build of the game -- other code
 * (about half of its functions are byte-identical to the US ones, the rest
 * differ), another data layout -- so none of those addresses holds there:
 * detouring the US address of a function patches some other function of the
 * EU program.
 *
 * Every module that touches the game therefore asks t5game::hooks_ok() before
 * it installs anything: true for the US program, false for any other program,
 * which then runs as the game alone (offline modes, its own pad reading).
 *
 * The program is told by its ELF header, read from the file the runtime boots
 * (argv[1], boot_main.cpp) the first time anyone asks -- also from the static
 * constructors that register the hooks, before the runtime has loaded it:
 * e_entry and the file size tell the known programs apart. A file that cannot
 * be read (a test harness without one) keeps the old behaviour (US). */
#pragma once

#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

#if defined(__APPLE__)
/* <crt_externs.h>'s two (declared here: the syntax check builds without the macOS SDK) */
extern "C" int* _NSGetArgc(void);
extern "C" char*** _NSGetArgv(void);
#endif
/* (Windows: __argc and __argv come from <stdlib.h>) */

namespace t5game {

enum class Game : int {
    Unread = 0,   /* no ELF readable at argv[1]: treated as the US program (the old behaviour) */
    US     = 1,   /* NPUB30009 v01.00, US PSN: what src/ is written for */
    EU     = 2,   /* NPEA00019 v01.00, EU PSN (EP9000-NPEA00019_00-0000000000000000) */
    EU_ONLINE = 3,/* NPEA00019 "Online" (UP0700-NPEA00019_00-TEKKEN5DRO000000, PARAM.SFO VERSION 02.00): not built */
    Other  = 4,   /* any other PPU ELF */
};

struct Known { Game game; uint64_t entry; uint64_t size; const char* name; };
/* e_entry and the decrypted ELF's size (tools/build_game.py PROGRAMS pins the SHA-1 of each) */
inline const Known* known_programs()
{
    static const Known k[] = {
        { Game::US,        0x447690u, 5294536u, "NPUB30009 v01.00 (US)" },
        { Game::EU,        0x356980u, 4168760u, "NPEA00019 v01.00 (EU)" },
        { Game::EU_ONLINE, 0x457898u, 5363592u, "NPEA00019 v02.00 Online (EU)" },
        { Game::Other, 0, 0, nullptr },
    };
    return k;
}

inline const char* elf_arg()
{
#if defined(_WIN32)
    return __argc > 1 ? __argv[1] : nullptr;
#elif defined(__APPLE__)
    return *_NSGetArgc() > 1 ? (*_NSGetArgv())[1] : nullptr;
#else
    return nullptr;
#endif
}

/* The program in the ELF file at `path` (public for tests). */
inline Game identify(const char* path, const char** name = nullptr)
{
    if (name) *name = "?";
    if (!path || !*path) return Game::Unread;
    FILE* f = fopen(path, "rb");
    if (!f) return Game::Unread;
    unsigned char h[0x40] = { 0 };
    const size_t got = fread(h, 1, sizeof h, f);
    fseek(f, 0, SEEK_END);
    const long size = ftell(f);
    fclose(f);
    if (got < sizeof h || h[0] != 0x7F || h[1] != 'E' || h[2] != 'L' || h[3] != 'F') return Game::Unread;
    uint64_t entry = 0;
    for (int i = 0; i < 8; i++) entry = (entry << 8) | h[0x18 + i];   /* e_entry, big-endian */
    for (const Known* k = known_programs(); k->name; k++)
        if (k->entry == entry && (uint64_t)size == k->size) {
            if (name) *name = k->name;
            return k->game;
        }
    if (name) *name = "an unknown program";
    return Game::Other;
}

/* This process's program (argv[1]), decided once. */
inline Game game()
{
    static const Game g = identify(elf_arg());
    return g;
}

/* The name of this process's program, for logs. */
inline const char* game_name()
{
    static const char* n = nullptr;
    if (!n) { const char* s = "?"; identify(elf_arg(), &s); n = s; }
    return n;
}

/* May the modules that know the US program's addresses touch this one? Says
 * once on stderr which modules stay off when the answer is no. */
inline bool hooks_ok(const char* module)
{
    const Game g = game();
    if (g == Game::US || g == Game::Unread) return true;
    fprintf(stderr, "[t5] %s: off -- this game is %s; it knows only the addresses of NPUB30009 v01.00 (US). "
                    "The game runs on its own: offline modes only (docs/EU.md)\n", module, game_name());
    return false;
}

} // namespace t5game
