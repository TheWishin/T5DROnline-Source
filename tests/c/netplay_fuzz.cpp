/*
 * The netplay packet parser (src/netplay/netplay_core.cpp handle_packet) under attack, in one process:
 * no socket is opened, nothing is sent (the session's socket stays INVALID_SOCKET, so every reply is
 * dropped before sendto). tests/test_netplay_fuzz.py builds and runs it (clang-cl, AddressSanitizer
 * when the LLVM install has it).
 *
 *   netplay_fuzz.exe [iterations]      unit checks, then a seeded random fuzz; prints "PASS <n> checks"
 *
 * What it checks:
 *   - SipHash-2-4 against the reference vector;
 *   - a third party cannot end a match before it starts with a HELLO of another protocol version
 *     (it used to: any 6-byte packet to the game's port -> build_mismatch);
 *   - packets with a wrong tag change nothing (keyed sessions: every lobby match);
 *   - a recorded packet of the peer played back from another address does not move the session
 *     there (it used to: "the peer's address changed ... following it"), while a real NAT
 *     rebinding (new packets, or the old address gone quiet) is still followed;
 *   - a joiner never takes an input delay above 30 from the host's HELLO;
 *   - random and mutated packets -- also correctly tagged ones, i.e. a hostile opponent -- in every
 *     mode and phase: no crash, no out-of-bounds access (ASan), the receive state only moves forward.
 *
 * Deeper fuzzing by hand (libFuzzer; not part of the test):
 *   clang-cl /std:c++17 /EHsc /O1 /Zi /fsanitize=fuzzer,address /DT5_LIBFUZZER tests/c/netplay_fuzz.cpp
 *            /I src/netplay ws2_32.lib  &&  netplay_fuzz.exe -max_total_time=600
 */
#include <cstdio>
/* netplay's log lines (fprintf(stderr, ...)) go to NUL; the real stderr stays for AddressSanitizer */
static FILE* g_np_log = nullptr;
#undef stderr
#define stderr (g_np_log ? g_np_log : __acrt_iob_func(2))
#include "../../src/netplay/netplay_core.cpp"
/* the replay recorder netplay_core.cpp calls (docs/REPLAYS.md): off here (no T5_REPLAY_DIR), no zlib */
#include "../../src/netplay/replay.cpp"
unsigned char* rp_zlib_compress(const unsigned char*, int, int* n) { *n = 0; return nullptr; }
unsigned char* rp_zlib_decompress(const unsigned char*, int, int* n) { *n = 0; return nullptr; }
#undef stderr
#define stderr (__acrt_iob_func(2))

extern "C" int32_t cellPad_sample_local(uint32_t, HostPadData* out) { out->len = 0; return 0; }

using namespace np;

static int g_checks = 0, g_fail = 0;
#define CHECK(c, ...) do { g_checks++; if (!(c)) { g_fail++; printf("FAIL line %d: ", __LINE__); printf(__VA_ARGS__); printf("\n"); fflush(stdout); } } while (0)

static const uint8_t kKey[16] = { 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16 };
static const uint32_t kHostSession = 0x5E55101Bu, kPeerNonce = 0x0DDBA11u;

static sockaddr_in addr(uint32_t ip, uint16_t port)
{
    sockaddr_in a{};
    a.sin_family = AF_INET;
    a.sin_addr.s_addr = htonl(ip);
    a.sin_port = htons(port);
    return a;
}
static const sockaddr_in A = addr(0xC6336401u, 5000), B = addr(0xC6336402u, 5001),   /* 198.51.100.x */
                         C = addr(0xC6336403u, 5002), D = addr(0xC6336404u, 5003);

static void reset(Mode m, bool keyed, bool env_peer = true)
{
    State& s = S();
    static Session fresh;
    static_cast<Session&>(s) = fresh;
    if (!s.rx_event) s.rx_event = CreateEventA(nullptr, FALSE, FALSE, nullptr);
    s.mode = m;
    s.slot = m == Mode::Join ? 1 : 0;
    s.keyed = keyed;
    memcpy(s.key, kKey, 16);
    s.session = m == Mode::Host ? kHostSession : 0x11111111u;
    s.nonce = 0xA11CE001u;
    s.delay = 3;
    s.env_peer = env_peer;
    s.env_peer_ip = A.sin_addr;
    if (m == Mode::Join) { s.peer = A; s.peer_known = true; }
}

/* a packet as the peer process would send it (tag appended when keyed) */
static std::vector<uint8_t> packet(uint8_t type, const void* body, size_t len, bool keyed, uint8_t ver = kVersion,
                                   uint32_t session = kHostSession, uint32_t nonce = kPeerNonce, uint8_t delay = 3)
{
    Hdr h = { kMagic, type, ver, delay, 1, session, nonce };
    std::vector<uint8_t> v((const uint8_t*)&h, (const uint8_t*)&h + sizeof h);
    v.insert(v.end(), (const uint8_t*)body, (const uint8_t*)body + len);
    if (keyed) {
        const uint64_t t = siphash24(kKey, v.data(), v.size());
        v.insert(v.end(), (const uint8_t*)&t, (const uint8_t*)&t + 8);
    }
    return v;
}

static void feed(const std::vector<uint8_t>& v, const sockaddr_in& from) { handle_packet(v.data(), (int)v.size(), from); }

static std::vector<uint8_t> ping(uint32_t t_us, bool keyed)
{
    PingExt x = { 0, 0, t_us, 0, 0, 0xFF };
    return packet(PKT_PING, &x, sizeof x, keyed);
}

static std::vector<uint8_t> input(uint32_t first, uint8_t count, bool keyed, uint32_t ack = 0)
{
    std::vector<uint8_t> b(sizeof(InputHdr) + count * sizeof(WireIn));
    InputHdr ih = { ack, first, count, 0, 0, 0, 0xFF };
    memcpy(b.data(), &ih, sizeof ih);
    for (uint8_t k = 0; k < count; k++) { WireIn w = { (uint16_t)(first + k), 128, 128, 128, 128 }; memcpy(&b[sizeof ih + k * sizeof w], &w, sizeof w); }
    return packet(PKT_INPUT, b.data(), b.size(), keyed);
}

static bool at(const sockaddr_in& a) { return same_addr(S().peer, a); }

/* ------------------------------------------------------------------ unit checks */

static void check_siphash()
{
    uint8_t k[16], m[15];
    for (int i = 0; i < 16; i++) k[i] = (uint8_t)i;
    for (int i = 0; i < 15; i++) m[i] = (uint8_t)i;
    CHECK(siphash24(k, m, 15) == 0xa129ca6149be45e5ull, "SipHash-2-4 reference vector (15 bytes)");
    CHECK(siphash24(k, m, 0) == 0x726fdb47dd0e0e31ull, "SipHash-2-4 reference vector (empty)");
}

static void check_foreign_version_hello()
{
    State& s = S();
    const uint8_t six[6] = { 'T', '5', 'N', 'P', PKT_HELLO, 2 };
    HelloExt x = { 7, 0, 0 };

    reset(Mode::Host, true);
    handle_packet(six, 6, D);                                       /* the old one-packet session kill */
    CHECK(s.fail_reason.empty(), "a stranger's 6-byte v2 HELLO ended a keyed session: %s", s.fail_reason.c_str());
    std::vector<uint8_t> v = packet(PKT_HELLO, &x, sizeof x, false, 2);
    v.resize(v.size() + 8, 0x5A);                                   /* a made-up tag */
    feed(v, D);
    CHECK(s.fail_reason.empty(), "a v2 HELLO with a wrong tag ended a keyed session");
    feed(packet(PKT_HELLO, &x, sizeof x, true, 2), A);              /* the opponent really runs v2 */
    CHECK(s.fail_reason == "build_mismatch", "the opponent's tagged v2 HELLO did not fail fast");

    reset(Mode::Join, false, true);
    feed(packet(PKT_HELLO, &x, sizeof x, false, 2), D);
    CHECK(s.fail_reason.empty(), "unkeyed lobby session: a v2 HELLO from another address ended it");
    feed(packet(PKT_HELLO, &x, sizeof x, false, 2), A);
    CHECK(s.fail_reason == "build_mismatch", "unkeyed lobby session: the named peer's v2 HELLO did not fail fast");
}

static void check_wrong_tags_change_nothing()
{
    State& s = S();
    reset(Mode::Host, true);
    HelloExt x = { 0, 0, 0 };
    feed(packet(PKT_HELLO, &x, sizeof x, true), A);
    CHECK(s.connected && at(A), "handshake with a tagged HELLO echoing the session");
    const uint32_t contig = s.remote_contig, ack = s.peer_ack;
    for (int i = 0; i < 2000; i++) {
        std::vector<uint8_t> v = i & 1 ? input((uint32_t)i, 8, true, 500) : ping(9000 + i, true);
        v[v.size() - 1 - (i % 8)] ^= (uint8_t)(1 + (i % 255));      /* the tag no longer fits */
        feed(v, (i & 2) ? A : D);
    }
    CHECK(s.remote_contig == contig && s.peer_ack == ack && at(A) && !s.peer_lost, "badly tagged packets changed the session");
    std::vector<uint8_t> bye = packet(PKT_BYE, nullptr, 0, true);
    bye[0] ^= 1;
    feed(bye, A);
    CHECK(!s.peer_lost, "a broken BYE ended the session");
}

static void check_replays_do_not_move_the_session()
{
    State& s = S();
    for (int keyed = 0; keyed < 2; keyed++) {
        reset(Mode::Host, keyed != 0, keyed == 0);
        HelloExt x = { 0, 0, 0 };
        feed(packet(PKT_HELLO, &x, sizeof x, keyed != 0), A);
        CHECK(s.connected && at(A), "handshake (keyed %d)", keyed);
        const std::vector<uint8_t> p1 = ping(1000, keyed != 0);
        feed(p1, A);
        feed(p1, B);                                                /* a copy, played back from elsewhere */
        CHECK(at(A), "a replayed PING moved the session (keyed %d)", keyed);
        feed(ping(2000, keyed != 0), B);                            /* the peer's NAT rebound: a new PING */
        CHECK(at(B), "a new PING from a new address was not followed (keyed %d)", keyed);
        feed(p1, C);
        CHECK(at(B), "an old PING moved the session back (keyed %d)", keyed);
        const std::vector<uint8_t> i1 = input(0, 6, keyed != 0);
        feed(i1, B);
        feed(i1, C);
        CHECK(at(B), "a replayed INPUT moved the session (keyed %d)", keyed);
        CHECK(s.remote_contig == 6, "inputs 0..5 known (got %u)", s.remote_contig);
        feed(input(6, 2, keyed != 0), C);                           /* new inputs from a new address */
        CHECK(at(C) && s.remote_contig == 8, "new inputs from a new address were not followed (keyed %d)", keyed);
        feed(packet(PKT_HELLO, &x, sizeof x, keyed != 0), D);       /* a HELLO carries nothing new */
        CHECK(at(C), "a replayed HELLO moved the session (keyed %d)", keyed);
        s.last_rx_ms = GetTickCount64() - 2 * kRelatchSilenceMs;   /* C went quiet: the peer moved for good */
        feed(p1, D);
        CHECK(at(D), "after the known address went quiet even an old packet is followed (keyed %d)", keyed);
        feed(packet(PKT_BYE, nullptr, 0, keyed != 0), A);
        CHECK(s.peer_lost && s.lost_reason == "peer_quit", "the peer's BYE (keyed %d)", keyed);
    }
}

static void check_join_delay_is_clamped()
{
    State& s = S();
    reset(Mode::Join, true);
    HelloExt x = { 0, 0, 0 };
    feed(packet(PKT_HELLO, &x, sizeof x, true, kVersion, kHostSession, kPeerNonce, 200), A);
    CHECK(s.connected && s.delay == kMaxDelay, "the host's delay 200 was taken as %d", s.delay);
    reset(Mode::Join, true);
    feed(packet(PKT_HELLO, &x, sizeof x, true, kVersion, kHostSession, kPeerNonce, 2), A);
    CHECK(s.delay == 2, "the host's delay 2 was taken as %d", s.delay);
}

/* ------------------------------------------------------------------ fuzz */

static uint64_t g_rng = 0x9E3779B97F4A7C15ull;
static uint32_t rnd() { g_rng ^= g_rng << 13; g_rng ^= g_rng >> 7; g_rng ^= g_rng << 17; return (uint32_t)(g_rng >> 11); }

static std::vector<uint8_t> random_packet(bool keyed)
{
    State& s = S();
    const uint32_t kind = rnd() % 10;
    std::vector<uint8_t> body;
    uint8_t type = (uint8_t)(1 + rnd() % 7);
    switch (type) {
    case PKT_HELLO: { HelloExt x = { rnd() % 3 ? 0u : rnd(), rnd(), rnd() }; body.assign((uint8_t*)&x, (uint8_t*)&x + sizeof x); break; }
    case PKT_PING: { PingExt x = { (uint8_t)rnd(), rnd(), rnd(), rnd() % 2 ? 0u : rnd(), rnd(), (uint8_t)rnd() }; body.assign((uint8_t*)&x, (uint8_t*)&x + sizeof x); break; }
    case PKT_PICK: { PickExt x = { rnd() % 4, rnd(), rnd() % 4 }; body.assign((uint8_t*)&x, (uint8_t*)&x + sizeof x); break; }
    case PKT_REJECT: { RejectExt x = { (uint8_t)(rnd() % 4) }; body.assign((uint8_t*)&x, (uint8_t*)&x + sizeof x); break; }
    case PKT_INPUT: {
        const uint8_t count = (uint8_t)(rnd() % 3 ? rnd() % 70 : rnd() % 256);
        const uint8_t nh = (uint8_t)(rnd() % 4 ? rnd() % 9 : rnd() % 256), nb = (uint8_t)(rnd() % 4 ? rnd() % 5 : rnd() % 256);
        uint32_t first = rnd() % 4 ? s.remote_contig + rnd() % 80 - 8 : rnd();
        InputHdr ih = { rnd() % 2 ? s.remote_contig + rnd() % 64 : rnd(), first, count, nh, nb, (int8_t)rnd(), (uint8_t)rnd() };
        body.assign((uint8_t*)&ih, (uint8_t*)&ih + sizeof ih);
        for (uint32_t k = 0; k < count; k++) { WireIn w = { (uint16_t)rnd(), (uint8_t)rnd(), (uint8_t)rnd(), (uint8_t)rnd(), (uint8_t)rnd() }; body.insert(body.end(), (uint8_t*)&w, (uint8_t*)&w + sizeof w); }
        for (uint32_t k = 0; k < nh; k++) { WireHash w = { rnd() % 3 ? s.remote_contig + rnd() % 64 : rnd(), ((uint64_t)rnd() << 32) | rnd() }; body.insert(body.end(), (uint8_t*)&w, (uint8_t*)&w + sizeof w); }
        for (uint32_t k = 0; k < nb; k++) { WireBar w = { rnd() % 3 ? rnd() % 8 : rnd(), rnd() % 3 ? s.remote_contig + rnd() % 64 : rnd() }; body.insert(body.end(), (uint8_t*)&w, (uint8_t*)&w + sizeof w); }
        break;
    }
    default: type = (uint8_t)rnd(); break;                          /* BYE or an unknown type */
    }
    const uint32_t session = rnd() % 8 ? s.session : rnd();
    const uint32_t nonce = rnd() % 8 ? (s.peer_nonce ? s.peer_nonce : kPeerNonce) : rnd();
    const uint8_t ver = (uint8_t)(rnd() % 16 ? kVersion : rnd() % 5);
    if (kind == 0 && !body.empty()) body.resize(rnd() % body.size());                 /* cut short */
    if (kind == 1) for (int k = 0; k < 4 && !body.empty(); k++) body[rnd() % body.size()] ^= (uint8_t)(1 << (rnd() % 8));
    if (kind == 2) body.resize(body.size() + rnd() % 40, (uint8_t)rnd());             /* trailing junk */
    std::vector<uint8_t> v = packet(type, body.data(), body.size(), keyed && rnd() % 16, ver, session, nonce, (uint8_t)rnd());
    if (kind == 3) v.resize(rnd() % (v.size() + 1));                                  /* cut anywhere, even the header */
    if (kind == 4) for (auto& b : v) if (rnd() % 64 == 0) b = (uint8_t)rnd();        /* noise, tag included */
    if (v.size() > 2040) v.resize(2040);                                              /* rx_thread's buffer */
    return v;
}

static void fuzz(uint32_t iterations)
{
    State& s = S();
    const sockaddr_in from[] = { A, B, C, D };
    const Mode modes[] = { Mode::Host, Mode::Join };
    uint32_t i = 0;
    while (i < iterations) {
        const bool keyed = rnd() % 4 != 0;
        reset(modes[rnd() % 2], keyed, rnd() % 2 != 0);
        if (rnd() % 2) { HelloExt x = { 0, 0, 0 }; feed(packet(PKT_HELLO, &x, sizeof x, keyed), A); }   /* connected first */
        uint32_t contig = s.remote_contig;
        for (uint32_t k = 0; k < 400 && i < iterations; k++, i++) {
            const std::vector<uint8_t> v = random_packet(keyed);
            feed(v, from[rnd() % 4]);
            CHECK(s.remote_contig >= contig, "remote_contig went back %u -> %u", contig, s.remote_contig);
            /* (peer_ack may start again: a restarted peer process before any input was exchanged) */
            CHECK(s.delay >= 0 && s.delay <= kMaxDelay, "delay %d", s.delay);
            contig = s.remote_contig;
            if (g_fail > 20) return;
        }
    }
}

#ifdef T5_LIBFUZZER
extern "C" int LLVMFuzzerTestOneInput(const uint8_t* data, size_t size)
{
    if (!g_np_log) fopen_s(&g_np_log, "NUL", "w");
    if (size < 1) return 0;
    const bool keyed = data[0] & 1;
    reset(data[0] & 2 ? Mode::Join : Mode::Host, keyed, (data[0] & 4) != 0);
    if (data[0] & 8) { HelloExt x = { 0, 0, 0 }; feed(packet(PKT_HELLO, &x, sizeof x, keyed), A); }
    std::vector<uint8_t> v(data + 1, data + size);
    if (keyed && v.size() >= 6) { const uint64_t t = siphash24(kKey, v.data(), v.size()); v.insert(v.end(), (uint8_t*)&t, (uint8_t*)&t + 8); }
    if (v.size() > 2048) v.resize(2048);
    handle_packet(v.data(), (int)v.size(), data[0] & 16 ? B : A);
    return 0;
}
#else
int main(int argc, char** argv)
{
    const uint32_t iterations = argc > 1 ? (uint32_t)strtoul(argv[1], nullptr, 0) : 300000u;
    fopen_s(&g_np_log, "NUL", "w");                     /* the [netplay] log lines */
    check_siphash();
    check_foreign_version_hello();
    check_wrong_tags_change_nothing();
    check_replays_do_not_move_the_session();
    check_join_delay_is_clamped();
    const int unit = g_checks;
    fuzz(iterations);
    printf("unit checks %d, fuzz iterations %u\n", unit, iterations);
    if (g_fail) { printf("FAIL %d of %d checks\n", g_fail, g_checks); return 1; }
    printf("PASS %d checks\n", g_checks);
    return 0;
}
#endif
