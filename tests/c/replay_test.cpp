/*
 * The replay file code of the game (src/netplay/replay.cpp, replay_zlib.cpp) on its own, for
 * tests/test_replays.py: it records a made-up session through the same calls the netplay hooks make,
 * reads files back the way a playback does, and prints what it read, so Python's reader
 * (launcher/replays.py) and the game's can be checked against each other.
 *
 *   replay_test write <dir> <frames> <seed>   records a session of two matches into <dir>, prints
 *                                             "FILE <path>" and "DIGEST <hex>" (FNV-1a of every input)
 *   replay_test read <file>                    plays it the way the game does: "DIGEST", "MATCH", "LINE",
 *                                             "BARRIER" lines, or "ERROR <why>" (exit code 2)
 *   replay_test map <file> <frame> ...          the playback frame numbering after the sync points
 */
#include <windows.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string>

#include "../../src/netplay/replay.h"

extern "C" int t5_replay_costumes(unsigned match, unsigned char* out);

/* the netplay core's log line (netplay_core.cpp); here to stdout */
namespace np {
void note(const char* fmt, ...)
{
    va_list ap; va_start(ap, fmt);
    printf("NOTE ");
    vprintf(fmt, ap);
    printf("\n");
    va_end(ap);
}
}

static uint64_t fnv(uint64_t h, uint32_t v)
{
    for (int i = 0; i < 4; i++) { h ^= (v >> (8 * i)) & 0xFF; h *= 1099511628211ull; }
    return h;
}
static uint64_t digest_in(uint64_t h, const np::PadInput& in)
{
    h = fnv(h, in.buttons);
    return fnv(h, (uint32_t)in.lx | ((uint32_t)in.ly << 8) | ((uint32_t)in.rx << 16) | ((uint32_t)in.ry << 24));
}

static uint32_t g_x = 1;
static uint32_t rnd() { g_x ^= g_x << 13; g_x ^= g_x >> 17; g_x ^= g_x << 5; return g_x; }

static int do_write(const char* dir, uint32_t frames, uint32_t seed)
{
    _putenv_s("T5_REPLAY_DIR", dir);
    _putenv_s("T5_REPLAY_HASH_EVERY", "30");
    g_x = seed | 1;
    rp::rec_session_begin(1, "test-build-id", 0x1234ABCD);
    if (!rp::recording()) { printf("ERROR not recording\n"); return 2; }
    rp::rec_start(0x1234ABCD, true, 2);
    rp::rec_rollback_delay(1);
    rp::Fight ft;
    ft.chr[0] = 9; ft.chr[1] = 33; ft.btn[0] = 2; ft.btn[1] = 4; ft.model[0] = 0x1B; ft.model[1] = 0x4E;
    ft.stage = 27; ft.rounds = 2; ft.pick = 30; ft.names[0] = "Alpha One"; ft.names[1] = "B\xC3\xA9ta";
    ft.costumes = true;                            /* format 3: the custom costume blocks of the match */
    for (int i = 0; i < 0x108; i++) ft.cos[0][i] = (uint8_t)(i * 13 + 1);
    rp::rec_fight(ft);
    ft.costumes = false;
    rp::rec_match_begin(0);
    uint64_t dg = 1469598103934665603ull;
    np::PadInput held[2] = { np::kNeutral, np::kNeutral };
    const uint32_t half = frames / 2;
    for (uint32_t f = 0; f < frames; f++) {
        for (int p = 0; p < 2; p++) {
            if (rnd() % 5 == 0) held[p].buttons = (uint16_t)rnd();
            if (rnd() % 9 == 0) { held[p].lx = (uint8_t)rnd(); held[p].ly = (uint8_t)rnd(); }
            if (rnd() % 31 == 0) { held[p].rx = (uint8_t)rnd(); held[p].ry = (uint8_t)rnd(); }
        }
        rp::rec_input(f, held[0], held[1]);
        dg = digest_in(digest_in(dg, held[0]), held[1]);
        rp::rec_frame(f);                          /* (the hooks: frame f ran) */
        rp::rec_hash(f, 0x9E3779B97F4A7C15ull * (f + 1));
        if (f == 200) {
            rp::Barrier b; b.kind = rp::kLoad; b.f = 198; b.nf = 200; b.seed = 0xAAAA0001; b.has_state = true;
            b.clock = 0x10000 + 200; b.c[0] = 0x10000 + 200; b.c[1] = 0x10000 + 200; b.c[2] = 0x10000 + 200;
            rp::rec_barrier(b);
        }
        if (f == half - 10)
            rp::rec_result("1", 0, 2, nullptr, half - 10, true, 0x0123456789ABCDEFull, 0, half - 10);
        if (f == half) {
            rp::Barrier b; b.kind = rp::kPause; b.f = half; b.nf = half; rp::rec_barrier(b);
            rp::Barrier r; r.kind = rp::kResume; r.f = half; r.nf = half; r.seed = 0xBBBB0002; r.has_state = true;
            r.clock = 0x10000; r.c[0] = r.c[1] = r.c[2] = 0x10000;
            rp::rec_barrier(r);
            ft.btn[1] = 1; ft.pick = 0; ft.model[1] = 0x4D;
            rp::rec_fight(ft);
            rp::rec_match_begin(half);
        }
    }
    rp::rec_result("0", 2, 1, nullptr, frames - half - 5, true, 0xFEDCBA9876543210ull, 3, frames - 5);
    rp::rec_session_end("test end");
    WIN32_FIND_DATAA fd;
    const std::string pat = std::string(dir) + "\\*.t5replay";
    HANDLE h = FindFirstFileA(pat.c_str(), &fd);
    if (h == INVALID_HANDLE_VALUE) { printf("ERROR no file\n"); return 2; }
    FindClose(h);
    printf("FILE %s\\%s\n", dir, fd.cFileName);
    printf("DIGEST %016llx\n", (unsigned long long)dg);
    return 0;
}

static int do_read(const char* file, int argc, char** argv, bool map)
{
    if (!rp::play_load(file)) { printf("ERROR %s\n", rp::play_error()); return 2; }
    printf("SLOT %d DELAY %d ROLLBACK %d SEED %08x MATCHSEED %08x\n", rp::play_slot(), rp::play_delay(),
           rp::play_rollback() ? 1 : 0, rp::play_session_seed(), rp::play_match_seed());
    if (map) {
        /* argv: pairs "k:f" -- the k-th sync point reached at playback frame f */
        for (int i = 0; i < argc; i++) {
            unsigned k = 0, f = 0;
            if (sscanf(argv[i], "%u:%u", &k, &f) != 2) continue;
            printf("MAP %u %u %u\n", k, f, rp::play_barrier(k, f));
        }
        return 0;
    }
    uint64_t dg = 1469598103934665603ull;
    /* every frame the playback runs: the recorded ones (play_frame ends it there) */
    for (uint32_t f = 0; f < 10000000; f++) {
        if (!rp::play_frame(f)) break;
        np::PadInput in[2];
        rp::play_inputs(f, in);
        dg = digest_in(digest_in(dg, in[0]), in[1]);
    }
    printf("DIGESTPLUS %016llx\n", (unsigned long long)dg);
    for (uint32_t m = 1;; m++) {
        std::string line;
        if (!rp::play_fight_line(m, &line)) break;
        printf("LINE %u %s\n", m, line.c_str());
    }
    for (uint32_t m = 1; m < 10; m++) {
        unsigned char cos[2 * 0x108];
        std::string ln;
        if (!rp::play_fight_line(m, &ln)) break;
        if (!t5_replay_costumes(m, cos)) { printf("COSTUMES %u none\n", m); continue; }
        uint64_t h = 1469598103934665603ull;
        for (unsigned char v : cos) { h ^= v; h *= 1099511628211ull; }
        printf("COSTUMES %u %016llx\n", m, (unsigned long long)h);
    }
    for (uint32_t k = 0;; k++) {
        uint64_t clock = 0; uint32_t c[3] = {};
        const bool st = rp::play_barrier_state(k, &clock, c);
        const uint32_t seed = rp::play_barrier_seed(k, 0, 0xFFFFFFFFu);
        if (seed == 0xFFFFFFFFu && !st) break;
        printf("BARRIER %u seed %08x state %d clock %llx\n", k, seed, st ? 1 : 0, (unsigned long long)clock);
        if (k > 100) break;
    }
    return 0;
}

int main(int argc, char** argv)
{
    setvbuf(stdout, nullptr, _IONBF, 0);
    if (argc >= 5 && !strcmp(argv[1], "write")) return do_write(argv[2], (uint32_t)atoi(argv[3]), (uint32_t)strtoul(argv[4], nullptr, 0));
    if (argc >= 3 && !strcmp(argv[1], "read")) return do_read(argv[2], 0, nullptr, false);
    if (argc >= 3 && !strcmp(argv[1], "map")) return do_read(argv[2], argc - 3, argv + 3, true);
    printf("usage: replay_test write <dir> <frames> <seed> | read <file> | map <file> k:f ...\n");
    return 1;
}
