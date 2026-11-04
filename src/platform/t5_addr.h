/* The guest addresses src/ uses, for each program it knows (docs/EU.md "EU Online").
 *
 * src/ is written against the US program, NPUB30009 v01.00: every address in
 * it is a US address. The European "Online" edition (NPEA00019 v02.00 and
 * v02.01: the same program but for three bytes) is another build of the same
 * game -- the fight's code and the fighters' data the same, everything moved
 * by small per-unit shifts. For it, every US address src/ uses goes through
 * T5A() (one address) or T5R() (a range), which looks it up in the table
 * below:
 *
 *   { us, len, eu }   the US bytes [us, us + len) are the EU bytes [eu, eu + len)
 *
 * Code spans are whole functions whose instructions are the same in both
 * programs (the immediates -- addresses, offsets -- masked: tools/addr_map.py's
 * function match and the whole-text alignment of the two instruction streams),
 * so an address inside one is the same instruction in the other. Data spans
 * are proven by the programs' own code: the same instruction of a matched
 * function computes the US address in one and the EU address in the other
 * (lis/addi/ori, a load or store displacement, a TOC slot); a span is only as
 * long as such pairs with one and the same shift bracket it (a structure that
 * changed size in between would show as another shift). Nothing is guessed
 * and no neighbour's shift is borrowed: an address with no span is missing,
 * and asking for it stops the game with a line on stderr (it never falls back
 * to the US address, which in the EU program is some other variable). The
 * table holds facts about the two programs' layouts only -- no code, no game
 * data.
 *
 * For the US program (and a test harness without an ELF, t5_game.h Unread)
 * T5A(x) is x: one predictable branch, the US build behaves as before. */
#pragma once

#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

#include "t5_game.h"

namespace t5game {

struct Span { uint32_t us, len, eu; };
struct Region { uint32_t us, uslen, eu, eulen; };
struct Range32 { uint32_t addr, len; };

/* NPEA00019 v02.00 / v02.01 ("Online", EU PSN), decrypted EBOOT.elf SHA-1 a26bc6e0... / ff07efe0... (both in
 * tools/build_game.py EU_ONLINE_PROGRAMS). Sorted by `us`, no overlaps (tests/test_eu_online_addr.py). */
#include "t5_addr_eu_online.inc"

inline const Span* eu_online_find(uint32_t us)
{
    size_t lo = 0, hi = sizeof(kEuOnline) / sizeof(kEuOnline[0]);
    while (lo < hi) {   /* the last span starting at or below `us` */
        const size_t mid = (lo + hi) / 2;
        if (kEuOnline[mid].us <= us) lo = mid + 1; else hi = mid;
    }
    return lo ? &kEuOnline[lo - 1] : nullptr;
}

[[noreturn]] inline void addr_missing(uint32_t us, uint32_t len)
{
    fprintf(stderr, "[t5] FATAL: no %s address for the US address 0x%08X (+0x%X): src/platform/t5_addr_eu_online.inc "
                    "does not have it; stopping rather than touching another variable (docs/EU.md)\n",
            game_name(), us, len);
    fflush(stderr);
    abort();
}

/* The EU Online address of the US bytes [us, us + len). */
inline uint32_t addr_eu_online(uint32_t us, uint32_t len)
{
    const Span* s = eu_online_find(us);
    if (!s || len == 0 || (uint64_t)us + len > (uint64_t)s->us + s->len) addr_missing(us, len);
    return s->eu + (us - s->us);
}

/* Is this program the one src/'s addresses are written for (the US one, or no ELF: a test harness)? */
inline bool addr_identity()
{
    static const bool id = game() == Game::US || game() == Game::Unread;
    return id;
}

/* This program's address of the US bytes [us, us + len) (the US program: us itself). */
inline uint32_t addr(uint32_t us, uint32_t len = 1)
{
    if (addr_identity()) return us;
    if (game() != Game::EU_ONLINE) addr_missing(us, len);   /* hooks_ok() keeps every other program away */
    return addr_eu_online(us, len);
}

/* This program's counterpart of the US range [us, us + len) as "these objects": its own length where a structure in
 * it changed size (kEuOnlineRegions; hash masks and state lists only), else T5R(us, len) with the same length. */
inline Range32 region(uint32_t us, uint32_t len)
{
    if (addr_identity()) return { us, len };
    for (const Region& r : kEuOnlineRegions)
        if (r.us == us && r.uslen == len) return { r.eu, r.eulen };
    return { addr(us, len), len };
}

} // namespace t5game

/* One US address / the US range [x, x + n) in this program (t5_addr.h). */
#define T5A(x) (::t5game::addr((uint32_t)(x)))
#define T5R(x, n) (::t5game::addr((uint32_t)(x), (uint32_t)(n)))
/* A US address in a path that runs for the US program only (behind t5game::us_only(): developer tools). */
#define T5_US(x) ((uint32_t)(x))
/* For an initializer { addr, len } of a range list: this program's counterpart of the US range (t5game::region). */
#define T5REG(x, n) ::t5game::region((uint32_t)(x), (uint32_t)(n)).addr, ::t5game::region((uint32_t)(x), (uint32_t)(n)).len
