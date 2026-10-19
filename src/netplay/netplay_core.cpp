/*
 * T5DR netplay prototype -- the game-independent core: configuration, local
 * pad sampling, UDP transport, delay-based lockstep and the desync check.
 *
 * Environment:
 *   T5_NET_MODE     host | join | local   (unset = netplay off)
 *   T5_NET_PORT     local UDP port (host default 7000, join default 0 = any)
 *   T5_NET_PEER     ip:port of the host (join). A host given one calls it while waiting (lobby
 *                   punch / relay); either way it takes the first authenticated HELLO as its peer
 *   T5_NET_DELAY    input delay in frames (host decides, join adopts; default 3)
 *   T5_NET_TIMEOUT  seconds the peer may be silent, or stall the match, before it counts
 *                   as lost (default 30; the lobby passes 20)
 *   T5_NET_CONNECT_TIMEOUT  seconds from boot for the handshake (default max(60, 2x
 *                   T5_NET_TIMEOUT); 0 = wait forever)
 *   T5_NET_START_TIMEOUT    seconds to wait at the start of the match for a peer that is
 *                   connected and alive but still loading (default 120)
 *   T5_NET_KEY      match secret (the lobby's): every packet carries a SipHash-2-4 tag
 *                   under it; without it the key comes from T5_NET_MATCH + T5_NET_SEED when
 *                   both are given, else packets are not authenticated
 *   T5_NET_LOCALPAD 0 ignores this PC's devices (tests: scripts only). Otherwise
 *                   the local player is whatever the runtime's controls put on
 *                   port 1 (cellPad_sample_local: pads, sticks, keyboard, remaps)
 *   T5_NET_BUILD    build id; a peer whose HELLO carries a different one is refused
 *   T5_NET_SEED     shared random seed (from the lobby); the host's value is used
 *   T5_NET_MATCH, T5_NET_PATH, T5_NET_RTT_MS   lobby details, logged
 *   T5_NET_SCRIPT   scripted local input: file of "<frame> <frames> <mask>" lines,
 *                   or "@frame:frames:mask,..." inline. Frames are the frames
 *                   the input takes effect in (independent of the delay).
 *   T5_NET_PADFILE  closed-loop local input: a file holding "<mask> [frames]" is
 *                   pressed for that many frames (default 6), then emptied.
 *   T5_NET_SCRIPT2  local mode only: scripted input for P2.
 *   T5_NET_LOG      per-frame log file: frame, both inputs, state hash.
 */
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <winsock2.h>
#include <ws2tcpip.h>
#include <windows.h>
#include <xmmintrin.h>   /* _mm_getcsr: the FP environment line in the log */

#include <atomic>
#include <cstdarg>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <algorithm>
#include <map>
#include <mutex>
#include <string>
#include <vector>

#include "netplay.h"

/* libs/input/cellPad.c (patch 0009): the local input for a PS3 port, host-endian. */
struct HostPadData { int32_t len; uint16_t button[64]; };
extern "C" int32_t cellPad_sample_local(uint32_t port_no, HostPadData* out);

namespace np {
namespace {

constexpr uint32_t kMagic    = 0x504E3554u;   /* "T5NP" little-endian */
/* v2: the header carries the sender's per-process nonce, packets may carry an
 * authentication tag, PING and REJECT exist. A v1 peer is a different build.
 * v3 (latency branch): PING carries a time stamp and the echo of the peer's
 * (round-trip time), PING and INPUT carry the rollback input delay the host
 * picked for the match, HELLO the sender's input delay setting (auto/0/1/2). */
constexpr uint8_t  kVersion  = 3;
constexpr uint32_t kRing     = 1024;          /* frames of history kept */
constexpr uint32_t kMaxBatch = 64;            /* inputs per packet */
constexpr uint32_t kHashes   = 8;             /* recent hashes per packet */
constexpr uint32_t kBarriers = 4096;          /* scene changes kept */
constexpr uint32_t kBarSend  = 4;             /* recent scene changes per packet */
constexpr int      kTag      = 8;             /* SipHash-2-4 tag at the end of every packet when keyed */
constexpr ULONGLONG kPingMs  = 200;           /* keepalive while nothing else is sent */
constexpr int      kMaxDelay = 30;            /* input delay frames, at most (T5_NET_DELAY, and what a joiner takes from the host) */

/* HELLO: handshake (session, delay, build, seed). INPUT: inputs + hashes +
 * scene changes. BYE: leaving. PING: keepalive with the sender's progress.
 * REJECT: "I am in another session / a different build" (fail fast).
 * PICK: the character a player picked on the game's own select screen
 * (in-game select, docs/DIRECTFIGHT.md "Character select in the game"). */
enum : uint8_t { PKT_HELLO = 1, PKT_INPUT = 2, PKT_BYE = 3, PKT_PING = 4, PKT_REJECT = 5, PKT_PICK = 6 };
enum : uint8_t { REJ_BUILD = 1, REJ_SESSION = 2 };

#pragma pack(push, 1)
struct Hdr      { uint32_t magic; uint8_t type, ver, delay, slot; uint32_t session; uint32_t nonce; };   /* nonce: the sender's own per-process id */
struct InputHdr { uint32_t ack; uint32_t first; uint8_t count; uint8_t nhash; uint8_t nbar; int8_t lead; uint8_t rbd; };   /* lead: the sender's frame advantage estimate (rollback time sync); rbd: the host's rollback input delay for the match (0xFF: none) */
struct WireIn   { uint16_t buttons; uint8_t lx, ly, rx, ry; };
struct WireHash { uint32_t frame; uint64_t hash; };
struct WireBar  { uint32_t index; uint32_t frame; };
struct HelloExt { uint32_t build; uint32_t seed; uint32_t flags; };   /* follows Hdr in a HELLO; flags: bit 0 = this side offers rollback, bits 8-15 its input delay setting (0xFF = auto) */
/* flags: PING_STARTED, PING_ROLLBACK; t_us: the sender's clock (microseconds,
 * wraps); echo_us/hold_us: the t_us of the last PING it received and how long
 * it held it -- the receiver's round trip is now - echo_us - hold_us; rbd: the
 * host's rollback input delay for the match once decided (0xFF: not yet) */
struct PingExt  { uint8_t flags; uint32_t frame; uint32_t t_us; uint32_t echo_us; uint32_t hold_us; uint8_t rbd; };
constexpr uint8_t PING_STARTED = 1;    /* the sender's lockstep has begun (frame 0 ran) */
constexpr uint8_t PING_ROLLBACK = 2;   /* the sender offers rollback (as in its HELLO; the first HELLOs may predate the offer) */
struct RejectExt { uint8_t why; };
/* key: the match the pick is for (both games derive it from the lobby's match id);
 * pick: the sender's pick (0 = none yet; packed by the direct-fight code); ack: the
 * key of the peer's pick the sender holds -- the peer stops resending there */
struct PickExt  { uint32_t key; uint32_t pick; uint32_t ack; };
constexpr uint32_t kHelloRollback = 1u;
constexpr int      kRbAuto = 0xFF;    /* T5_RB_NET_DELAY=auto: the input delay follows the measured round trip */
#pragma pack(pop)

/* ---- SipHash-2-4 (Aumasson/Bernstein reference algorithm) ---------------- */
inline uint64_t rotl64(uint64_t x, int b) { return (x << b) | (x >> (64 - b)); }
uint64_t siphash24(const uint8_t key[16], const uint8_t* in, size_t len)
{
    uint64_t k0, k1;
    memcpy(&k0, key, 8); memcpy(&k1, key + 8, 8);
    uint64_t v0 = 0x736f6d6570736575ull ^ k0, v1 = 0x646f72616e646f6dull ^ k1;
    uint64_t v2 = 0x6c7967656e657261ull ^ k0, v3 = 0x7465646279746573ull ^ k1;
    auto round = [&]() {
        v0 += v1; v1 = rotl64(v1, 13); v1 ^= v0; v0 = rotl64(v0, 32);
        v2 += v3; v3 = rotl64(v3, 16); v3 ^= v2;
        v0 += v3; v3 = rotl64(v3, 21); v3 ^= v0;
        v2 += v1; v1 = rotl64(v1, 17); v1 ^= v2; v2 = rotl64(v2, 32);
    };
    const size_t end = len - (len % 8);
    for (size_t i = 0; i < end; i += 8) {
        uint64_t m; memcpy(&m, in + i, 8);
        v3 ^= m; round(); round(); v0 ^= m;
    }
    uint64_t b = (uint64_t)len << 56;
    for (size_t i = 0; i < len % 8; i++) b |= (uint64_t)in[end + i] << (8 * i);
    v3 ^= b; round(); round(); v0 ^= b;
    v2 ^= 0xff;
    round(); round(); round(); round();
    return v0 ^ v1 ^ v2 ^ v3;
}

/* CELL_PAD_CTRL_* (cellPad.h) */
enum : uint16_t {
    B_SELECT = 1 << 0, B_L3 = 1 << 1, B_R3 = 1 << 2, B_START = 1 << 3,
    B_UP = 1 << 4, B_RIGHT = 1 << 5, B_DOWN = 1 << 6, B_LEFT = 1 << 7,
    B_L2 = 1 << 8, B_R2 = 1 << 9, B_L1 = 1 << 10, B_R1 = 1 << 11,
    B_TRIANGLE = 1 << 12, B_CIRCLE = 1 << 13, B_CROSS = 1 << 14, B_SQUARE = 1 << 15,
};

struct ScriptEvent { uint32_t frame, frames; uint16_t mask; };

void note_(const char* fmt, ...);

/* Closed-loop input: a file holding "<mask> [frames]" is pressed for that many
 * frames (default 6), then emptied so the next press can be written. */
struct PadFile {
    std::string path;
    uint16_t mask = 0;
    int left = 0;
    uint16_t poll(uint32_t f)
    {
        if (path.empty()) return 0;
        if (left <= 0) {
            FILE* fp = fopen(path.c_str(), "rb");
            if (fp) {
                char buf[64] = { 0 };
                size_t n = fread(buf, 1, sizeof buf - 1, fp);
                fclose(fp);
                buf[n] = 0;
                char* rest;
                unsigned long m = strtoul(buf, &rest, 0);
                long k = strtol(rest, nullptr, 0);
                if (m) {
                    mask = (uint16_t)m;
                    left = k > 0 ? (int)k : 6;
                    FILE* w = fopen(path.c_str(), "wb"); if (w) fclose(w);
                    note_("%s: press 0x%04X for %d frames from frame %u", path.c_str(), mask, left, f);
                }
            }
        }
        if (left > 0) { left--; return mask; }
        return 0;
    }
};

struct Ring {
    PadInput in[kRing];   uint32_t in_tag[kRing];     /* frame + 1, 0 = empty */
    uint64_t hash[kRing]; uint32_t hash_tag[kRing];
};

/* Everything that belongs to one session with one opponent. A persistent game
 * (T5_CTL_DIR, docs/DIRECTFIGHT.md "Persistent game") plays many sessions in
 * one process: session_end() puts all of this back to these defaults, and
 * session_begin() fills it again from the environment. */
struct Session {
    Mode mode = Mode::Off;
    int  delay = 3;
    int  slot = 0;
    int  timeout_s = 30;
    bool localpad = true;              /* T5_NET_LOCALPAD=0: this PC's devices are ignored */
    uint32_t build = 0;                /* FNV-1a of T5_NET_BUILD, 0 = not given */
    uint32_t seed = 0;                 /* T5_NET_SEED (the host's wins), 0 = use the session id */
    bool rb_peer = false;              /* the peer's HELLO offered rollback */
    /* Rollback input delay (docs/NETPLAY.md "Input delay"): each player's setting
     * (T5_RB_NET_DELAY = auto | 0 | 1 | 2 ..., HELLO flags bits 8-15); the host
     * picks the match's value when its match starts -- the setting both chose,
     * else from the round trip it measured (1 frame up to T5_RB_NET_DELAY_AUTO
     * ms, default 60, 2 above) -- and sends it in every PING and INPUT; the
     * joiner waits for it before its rollback loop starts. */
    int  rb_delay = kRbAuto;           /* this player's setting */
    int  peer_rb_delay = -1;           /* the peer's setting (-1: no HELLO yet) */
    int  rb_decided = -1;              /* host / local: the match's value once picked */
    int  peer_rbd = -1;                /* joiner: the host's pick, once received */
    int  rb_auto_ms = 60;              /* T5_RB_NET_DELAY_AUTO: round trip up to which auto picks 1 frame */
    uint32_t peer_ping_us = 0;         /* t_us of the peer's last PING, and when it arrived (our clock) */
    uint64_t peer_ping_rx_us = 0;
    float rtt_ms[32] = {};             /* round-trip samples from PING echoes */
    uint32_t nrtt = 0;
    int8_t local_lead = 0, peer_lead = 0;   /* frame advantage estimates, ours (sent) and the peer's (received) */
    /* In-game select: this player's pick (sent every 100 ms until the peer has
     * it), the peer's pick, and acknowledgements still owed to the peer. */
    uint32_t pick_key = 0, pick_val = 0, pick_acked = 0;
    uint32_t peer_pick_key = 0, peer_pick_val = 0;
    int pick_acks_owed = 0;
    ULONGLONG pick_sent_ms = 0;

    int connect_timeout_s = 60;        /* T5_NET_CONNECT_TIMEOUT: handshake deadline from init (0 = none) */
    int start_timeout_s = 120;         /* T5_NET_START_TIMEOUT: wait for a live peer to reach the match start */
    bool keyed = false;                /* packets carry a SipHash tag under `key` */
    uint8_t key[16] = {};
    bool env_peer = false;             /* T5_NET_PEER given (lobby): unauthenticated hellos only from its IP */
    in_addr env_peer_ip{};

    sockaddr_in peer{};
    bool peer_known = false;
    bool connected = false;
    bool peer_lost = false;
    uint32_t session = 0;
    uint32_t nonce = 0;                /* this process's id (every packet carries it) */
    uint32_t peer_nonce = 0;           /* the peer process's id, latched at the handshake */
    bool started = false;              /* begin_frame(0) / rb_begin(0) ran: lockstep frames are being played */
    bool peer_sent_inputs = false;     /* the peer has sent lockstep input (its frame 0 ran) */
    bool peer_started = false;         /* the peer says its lockstep has begun (PING) */
    uint32_t peer_frame = 0;
    std::string fail_reason, lost_reason;
    ULONGLONG init_ms = 0, last_hello_ms = 0, last_wait_note = 0;
    uint32_t relatches = 0, bad_tags = 0, strangers = 0, stale = 0;   /* stale: old copies of the peer's packets from elsewhere */
    ULONGLONG trouble_ms = 0;          /* when failure/loss was first seen (stuck-handler grace) */
    bool stuck_called = false;
    /* per match (match_begin) */
    uint32_t count_from = 0, match_mismatches = 0;
    uint64_t speed_frames = 0, speed_us = 0, speed_wait_us = 0;   /* since match_begin */
    uint64_t last_frame_qpc = 0;
    uint64_t win_frames = 0, win_us = 0, win_wait_us = 0;   /* the 600-frame window in the log line */

    Ring local, remote;
    uint32_t local_max = 0;            /* local inputs known for f < local_max */
    uint32_t local_hash_max = 0;       /* local hashes known for f < this */
    uint32_t remote_contig = 0;        /* remote inputs known for f < remote_contig */
    uint32_t peer_ack = 0;             /* the peer has our inputs for f < peer_ack */
    uint32_t checked = 0;              /* hashes compared for f < checked */
    uint32_t remote_hash_max = 0;      /* highest frame + 1 with a peer hash */
    uint32_t local_bar[kBarriers] = {};   /* frame + 1 of scene change k, 0 = not yet */
    uint32_t remote_bar[kBarriers] = {};
    uint32_t nbar = 0;                 /* scene changes seen here */
    uint32_t mismatches = 0;
    uint32_t first_mismatch = UINT32_MAX;
    std::vector<uint32_t> mismatch_queue;   /* frames reported to the hooks by take_mismatch() */
    uint64_t packets_in = 0, packets_out = 0;
    ULONGLONG last_send_ms = 0, last_rx_ms = 0;

    std::vector<ScriptEvent> script, script2;
    PadFile padfile, padfile2;
};

/* The process: the session above plus what outlives it. */
struct State : Session {
    std::once_flag once;
    std::mutex mu;                     /* guards the session fields and the socket */
    std::atomic<SOCKET> sock{ INVALID_SOCKET };   /* closed and replaced between sessions (rx_thread follows) */
    bool rb_offer = false;             /* this side offers rollback (HELLO flag); set by the rollback loop */
    /* T5_NET_LOCAL_LAG=n (local mode, tests: tools/rb_equiv_test.py --lag): the
     * second player's input of frame t is known only from the live boundary
     * t - delay + n on, as if it came over a network n frames late -- the
     * rollback loop predicts it before that and rolls back when it differs,
     * on one PC, with the same inputs every run. */
    uint32_t local_lag = 0;
    uint32_t local_live = 0;           /* the latest live boundary (rb_sample_local) */
    uint32_t local_release = 0;        /* frames < this are known: the loop waited for them (rb_wait_remote) */
    void (*stuck_handler)(const char*) = nullptr;
    HANDLE rx_event = nullptr;
    bool net_up = false;               /* WSAStartup done, receive and tick threads running */
    uint32_t sessions = 0;             /* sessions begun in this process */
    FILE* log = nullptr;
    std::mutex log_mu;
};

State& S() { static State s; return s; }

void vlog(const char* fmt, va_list ap)
{
    char buf[1024];
    vsnprintf(buf, sizeof buf, fmt, ap);
    fprintf(stderr, "[netplay] %s\n", buf);
    fflush(stderr);
    State& s = S();
    if (s.log) {
        std::lock_guard<std::mutex> lk(s.log_mu);
        fprintf(s.log, "# %s\n", buf);
        fflush(s.log);
    }
}

void note_(const char* fmt, ...) { va_list ap; va_start(ap, fmt); vlog(fmt, ap); va_end(ap); }

/* The session environment. getenv() cannot change after boot (the runtime
 * caches every value it looked up, ps3recomp boot_main.cpp), so a persistent
 * game's control channel hands each match's variables to this overlay instead
 * (t5_env_overlay_*): a key it has ever set reads from it (a later command
 * without the key reads as unset), every other key from the process
 * environment. Changed only by the main thread between sessions. */
std::mutex g_env_mu;
std::map<std::string, std::pair<bool, std::string>> g_env_over;   /* upper-case key -> (set, value) */

std::string env_key(const char* k) { std::string s(k); for (char& c : s) c = (char)toupper((unsigned char)c); return s; }

const char* env_raw(const char* k)
{
    {
        std::lock_guard<std::mutex> lk(g_env_mu);
        auto it = g_env_over.find(env_key(k));
        if (it != g_env_over.end()) return it->second.first ? it->second.second.c_str() : nullptr;
    }
    return getenv(k);
}

const char* env(const char* k) { const char* v = env_raw(k); return (v && *v) ? v : nullptr; }

/* What decides this PC's floating-point results, for the log: the target the
 * lifted code was compiled for (t5dr_game.dll exports it; a one-exe build has
 * it from CMake) and the guest thread's MXCSR. Both PCs must compute the same
 * bits with any of them (docs/NETPLAY.md, "Same game state on every CPU"). */
void note_fp_env()
{
    const char* arch = nullptr;
    if (HMODULE dll = GetModuleHandleA("t5dr_game.dll"))
        arch = (const char*)GetProcAddress(dll, "t5dr_game_march");   /* tools/gamedll/t5dr_game_dll.c */
#ifdef T5DR_LIFTED_ARCH_NAME
    if (!arch) arch = T5DR_LIFTED_ARCH_NAME;
#endif
    note_("fp: game code -march=%s, main thread MXCSR 0x%04X", arch ? arch : "unknown", _mm_getcsr() & 0xFFC0u);
}

std::vector<ScriptEvent> parse_script(const char* spec)
{
    std::vector<ScriptEvent> ev;
    if (!spec) return ev;
    std::string text;
    if (spec[0] == '@') {
        text = spec + 1;
        for (char& c : text) if (c == ',' || c == ':') c = ' ';
    } else {
        FILE* f = fopen(spec, "rb");
        if (!f) { note("script %s: cannot open", spec); return ev; }
        char line[256];
        while (fgets(line, sizeof line, f)) {
            if (line[0] == '#') continue;
            text += line; text += ' ';
        }
        fclose(f);
    }
    const char* p = text.c_str();
    for (;;) {
        char* e;
        unsigned long fr = strtoul(p, &e, 0); if (e == p) break; p = e;
        unsigned long n  = strtoul(p, &e, 0); if (e == p) break; p = e;
        unsigned long m  = strtoul(p, &e, 0); if (e == p) break; p = e;
        ev.push_back({ (uint32_t)fr, (uint32_t)n, (uint16_t)m });
    }
    return ev;
}

uint16_t script_mask(const std::vector<ScriptEvent>& ev, uint32_t f)
{
    uint16_t m = 0;
    for (const ScriptEvent& e : ev)
        if (f >= e.frame && f < e.frame + e.frames) m |= e.mask;
    return m;
}

/* This PC's devices on local port `port`, through the runtime's own pad layer
 * (cellPad_sample_local: controls.ini mapping, sticks, keyboard, PS3_PAD_FILE). */
void device_input(uint32_t port, PadInput* in)
{
    HostPadData d;
    if (cellPad_sample_local(port, &d) != 0 || d.len == 0) return;
    in->buttons |= (uint16_t)((d.button[2] & 0xFF) | ((d.button[3] & 0xFF) << 8));
    in->rx = (uint8_t)d.button[4]; in->ry = (uint8_t)d.button[5];
    in->lx = (uint8_t)d.button[6]; in->ly = (uint8_t)d.button[7];
}

/* Menu driving by the direct-fight mode while lockstep runs: the local
 * player's sample is exactly these buttons (exchanged with the peer like any
 * input, so both PCs see the same presses at the same frame). */
std::atomic<bool> g_local_inject_on{ false };
std::atomic<uint16_t> g_local_inject{ 0 };
std::atomic<bool> g_script_gate{ true };

/* The local player's input for (effective) frame f. */
PadInput sample_local(uint32_t f)
{
    State& s = S();
    PadInput in = kNeutral;

    if (g_local_inject_on.load()) { in.buttons = g_local_inject.load(); return in; }
    if (s.localpad) device_input(0, &in);
    if (g_script_gate.load()) in.buttons |= script_mask(s.script, f);
    in.buttons |= s.padfile.poll(f);
    return in;
}

/* sample_local(t) for the per-frame sample -- only if frame t's local input
 * is still open. A frame a scene barrier already filled with neutral input
 * (while it waited for the peer, docs/NETPLAY.md) keeps that input, and the
 * sample would be thrown away; reading the pad anyway would also throw away
 * the presses the pad layer's tap latch handed to it (ps3recomp 0025: a tap
 * between two samples is reported once, at the next read). Not reading
 * leaves them latched for the next open frame. Main thread only, like every
 * writer of local_max. */
PadInput sample_local_open(uint32_t t)
{
    State& s = S();
    {
        std::lock_guard<std::mutex> lk(s.mu);
        if (t < s.local_max) return kNeutral;   /* decided: not used */
    }
    return sample_local(t);
}

/* ---- transport --------------------------------------------------------- */

std::string addr_str(const sockaddr_in& a)
{
    char ip[64] = "?";
    inet_ntop(AF_INET, &a.sin_addr, ip, sizeof ip);
    return std::string(ip) + ":" + std::to_string(ntohs(a.sin_port));
}

bool same_addr(const sockaddr_in& a, const sockaddr_in& b)
{
    return a.sin_addr.s_addr == b.sin_addr.s_addr && a.sin_port == b.sin_port;
}

/* Send to `to` (default: the peer). Appends the authentication tag when keyed. */
void send_to(const void* p, int n, const sockaddr_in* to = nullptr)
{
    State& s = S();
    if (s.sock == INVALID_SOCKET) return;
    if (!to) { if (!s.peer_known) return; to = &s.peer; }
    /* T5_NET_DROP=<percent>: throw away that share of outgoing packets, to
     * test that the redundant resends cover for a lossy link. */
    static int drop = -1;
    if (drop < 0) { const char* d = getenv("T5_NET_DROP"); drop = d ? atoi(d) : 0; }
    if (drop > 0) {
        static uint32_t x = 0x9E3779B9u ^ GetCurrentProcessId();
        x ^= x << 13; x ^= x >> 17; x ^= x << 5;
        if ((int)(x % 100) < drop) return;
    }
    uint8_t buf[2048];
    if (n + kTag > (int)sizeof buf) return;
    memcpy(buf, p, (size_t)n);
    if (s.keyed) {
        const uint64_t t = siphash24(s.key, buf, (size_t)n);
        memcpy(buf + n, &t, kTag);
        n += kTag;
    }
    sendto(s.sock, (const char*)buf, n, 0, (const sockaddr*)to, sizeof *to);
    s.packets_out++;
}
void send_raw(const void* p, int n) { send_to(p, n); }

Hdr make_hdr(uint8_t type)
{
    State& s = S();
    return { kMagic, type, kVersion, (uint8_t)s.delay, (uint8_t)s.slot, s.session, s.nonce };
}

void send_hello_locked(const sockaddr_in* to = nullptr)
{
    State& s = S();
    struct { Hdr h; HelloExt x; } p = { make_hdr(PKT_HELLO), { s.build, s.seed, s.rb_offer ? (kHelloRollback | ((uint32_t)(s.rb_delay & 0xFF) << 8)) : 0u } };
    send_to(&p, sizeof p, to);
    s.last_hello_ms = GetTickCount64();
}

uint64_t qpc_us();

void send_ping_locked()
{
    State& s = S();
    const uint64_t now = qpc_us();
    struct { Hdr h; PingExt x; } p = { make_hdr(PKT_PING), { (uint8_t)((s.started ? PING_STARTED : 0) |
                                                                      (s.rb_offer ? PING_ROLLBACK : 0)), s.local_hash_max,
                                                            (uint32_t)now, s.peer_ping_us,
                                                            s.peer_ping_us ? (uint32_t)(now - s.peer_ping_rx_us) : 0u,
                                                            (uint8_t)(s.mode == Mode::Host && s.rb_decided >= 0 ? s.rb_decided : 0xFF) } };
    send_raw(&p, sizeof p);
    s.last_send_ms = GetTickCount64();
}

/* In-game select: our pick (if any) and the acknowledgement of the peer's. */
void send_pick_locked()
{
    State& s = S();
    struct { Hdr h; PickExt x; } p = { make_hdr(PKT_PICK), { s.pick_key, s.pick_val, s.peer_pick_key } };
    send_raw(&p, sizeof p);
    s.pick_sent_ms = GetTickCount64();
}

/* The round trip so far: the median of the PING echo samples, else the
 * lobby's measurement (T5_NET_RTT_MS), else -1. */
float rtt_estimate_locked(int* samples)
{
    State& s = S();
    const uint32_t n = std::min<uint32_t>(s.nrtt, 32);
    *samples = (int)n;
    if (n) {
        float v[32];
        memcpy(v, s.rtt_ms, sizeof(float) * n);
        std::sort(v, v + n);
        return v[n / 2];
    }
    if (const char* e = env("T5_NET_RTT_MS")) { const float r = (float)atof(e); if (r > 0) return r; }
    return -1.0f;
}

/* Host (and local mode), when its match starts: the match's rollback input
 * delay. The value both players set, when they set the same; otherwise from
 * the round trip (auto). Never above the session's lockstep delay. */
void decide_rb_delay_locked()
{
    State& s = S();
    if (s.rb_decided >= 0 || (s.mode != Mode::Host && s.mode != Mode::Local)) return;
    int samples = 0;
    const float rtt = s.mode == Mode::Local ? 0.0f : rtt_estimate_locked(&samples);   /* local: no network */
    const int peer = s.mode == Mode::Local ? s.rb_delay : s.peer_rb_delay;
    int pick;
    char why[160];
    if (s.rb_delay != kRbAuto && s.rb_delay == peer) {
        pick = s.rb_delay;
        snprintf(why, sizeof why, "both players set %d", pick);
    } else {
        pick = (rtt >= 0.0f && rtt <= (float)s.rb_auto_ms) ? 1 : 2;
        snprintf(why, sizeof why, "auto: round trip %.0f ms (%d samples%s) -> %d (1 up to %d ms, 2 above); settings %s / %s",
                 rtt, samples, samples ? "" : ", lobby's measurement", pick, s.rb_auto_ms,
                 s.rb_delay == kRbAuto ? "auto" : std::to_string(s.rb_delay).c_str(),
                 peer < 0 ? "?" : peer == kRbAuto ? "auto" : std::to_string(peer).c_str());
    }
    if (pick > s.delay) pick = s.delay;
    s.rb_decided = pick;
    note("rollback input delay for this match: %d frame(s) (%s)", pick, why);
}

void send_reject(const sockaddr_in& to, uint8_t why)
{
    struct { Hdr h; RejectExt x; } p = { make_hdr(PKT_REJECT), { why } };
    send_to(&p, sizeof p, &to);
}

/* Inputs the peer may still need, plus our latest hashes. Caller holds mu. */
void send_inputs_locked()
{
    State& s = S();
    if (!s.connected || s.peer_lost) return;
    uint8_t buf[sizeof(Hdr) + sizeof(InputHdr) + kMaxBatch * sizeof(WireIn) + kHashes * sizeof(WireHash)
                + kBarSend * sizeof(WireBar)];
    Hdr* h = (Hdr*)buf;
    *h = make_hdr(PKT_INPUT);
    InputHdr* ih = (InputHdr*)(h + 1);
    uint32_t lo = (uint32_t)s.delay;               /* frames < delay are implicitly neutral */
    uint32_t first = s.peer_ack;
    if (s.local_max >= 8 && first > s.local_max - 8) first = s.local_max - 8;   /* redundancy */
    if (first < lo) first = lo;
    uint32_t count = s.local_max > first ? s.local_max - first : 0;
    if (count > kMaxBatch) count = kMaxBatch;
    ih->ack = s.remote_contig;
    ih->first = first;
    ih->count = (uint8_t)count;
    ih->lead = s.local_lead;
    ih->rbd = (uint8_t)(s.mode == Mode::Host && s.rb_decided >= 0 ? s.rb_decided : 0xFF);
    ih->nbar = 0;
    WireIn* wi = (WireIn*)(ih + 1);
    for (uint32_t i = 0; i < count; i++) {
        const PadInput& in = s.local.in[(first + i) % kRing];
        wi[i] = { in.buttons, in.lx, in.ly, in.rx, in.ry };
    }
    WireHash* wh = (WireHash*)(wi + count);
    uint32_t nh = 0;
    uint32_t hf = s.local_hash_max > kHashes ? s.local_hash_max - kHashes : 0;
    for (uint32_t f = hf; f < s.local_hash_max; f++)
        if (s.local.hash_tag[f % kRing] == f + 1)
            wh[nh++] = { f, s.local.hash[f % kRing] };
    ih->nhash = (uint8_t)nh;
    WireBar* wb = (WireBar*)(wh + nh);
    uint32_t nb = 0;
    for (uint32_t k = s.nbar > kBarSend ? s.nbar - kBarSend : 0; k < s.nbar; k++)
        wb[nb++] = { k, s.local_bar[k % kBarriers] - 1 };
    ih->nbar = (uint8_t)nb;
    send_raw(buf, (int)((uint8_t*)(wb + nb) - buf));
    s.last_send_ms = GetTickCount64();
}

void compare_hashes_locked()
{
    State& s = S();
    for (;;) {
        uint32_t f = s.checked, i = f % kRing;
        if (f >= s.local_hash_max) break;
        if (s.local.hash_tag[i] != f + 1) { s.checked++; continue; }   /* fell out of the ring */
        if (s.remote.hash_tag[i] != f + 1) {
            /* The peer's hash for f has not arrived yet -- or never will
             * (packets carry only the latest few). Give up on f once we are
             * far past it. */
            if (s.local_hash_max - f > kRing / 2 || s.remote_hash_max > f + 1) { s.checked++; continue; }
            break;
        }
        if (s.local.hash[i] != s.remote.hash[i]) {
            if (s.mismatches < 10)
                note("DESYNC at frame %u: local state hash %016llx, peer %016llx", f,
                     (unsigned long long)s.local.hash[i], (unsigned long long)s.remote.hash[i]);
            if (s.first_mismatch == UINT32_MAX) s.first_mismatch = f;
            s.mismatches++;
            if (f >= s.count_from) s.match_mismatches++;
            if (s.mismatch_queue.size() < 256) s.mismatch_queue.push_back(f);
        }
        s.checked++;
        if (s.checked % 600 == 0)
            note("sync check through frame %u: %u mismatching frame(s)%s", s.checked - 1,
                 s.mismatches, s.mismatches ? "" : " -- in sync");
    }
}

/* The session is over for good before it began (no peer, wrong build, rejected). */
void fail_locked(const char* reason, const char* fmt, ...)
{
    State& s = S();
    if (!s.fail_reason.empty()) return;
    char buf[512];
    va_list ap; va_start(ap, fmt); vsnprintf(buf, sizeof buf, fmt, ap); va_end(ap);
    s.fail_reason = reason;
    s.peer_lost = true;                /* every lockstep wait returns */
    s.trouble_ms = GetTickCount64();
    note("cannot connect (%s): %s", reason, buf);
    SetEvent(s.rx_event);
}

/* A connected peer is gone. One log line the launcher looks for: "peer lost (<reason>)". */
void lose_locked(const char* reason, const char* fmt, ...)
{
    State& s = S();
    if (s.peer_lost) return;
    char buf[512];
    va_list ap; va_start(ap, fmt); vsnprintf(buf, sizeof buf, fmt, ap); va_end(ap);
    s.lost_reason = reason;
    s.peer_lost = true;
    s.trouble_ms = GetTickCount64();
    note("peer lost (%s): %s", reason, buf);
    SetEvent(s.rx_event);
}

void connect_locked()
{
    State& s = S();
    if (s.connected) return;
    s.connected = true;
    s.last_rx_ms = GetTickCount64();
    note("connected (%s), delay %d, peer %s%s", s.mode == Mode::Host ? "host, P1" : "join, P2", s.delay,
         addr_str(s.peer).c_str(), s.keyed ? ", packets authenticated" : "");
    SetEvent(s.rx_event);
}

/* The peer's packets now come from another address (NAT rebinding, a new
 * relay mapping): answer there. Only called for packets that proved they are
 * the peer's (session + nonce, and the tag when keyed). */
void relatch_locked(const sockaddr_in& from)
{
    State& s = S();
    if (s.relatches++ < 20)
        note("the peer's address changed from %s to %s (NAT rebinding?) -- following it",
             addr_str(s.peer).c_str(), addr_str(from).c_str());
    s.peer = from;
}

/* A new peer process may take the old one's place as long as no lockstep
 * input has been exchanged with the old one (and the match seed cannot change
 * under a lockstep that already began). */
bool can_restart_locked()
{
    State& s = S();
    return !s.peer_sent_inputs && (!s.started || s.seed != 0);
}

void forget_peer_locked()
{
    State& s = S();
    s.connected = false;
    s.peer_nonce = 0;
    s.peer_ack = 0;
    s.peer_started = false;
    s.rb_peer = false;
}

/* A HELLO in another netplay protocol version ends the handshake (build_mismatch) only when it
 * proves it is the opponent's: with a match key its tag must be right (v2 and later append it the
 * same way), without one it must come from the address the lobby named. Before 1.1.2 any 6-byte
 * packet from anybody who guessed the port ended the session before it began. */
bool foreign_hello_trusted_locked(const uint8_t* p, int n, const sockaddr_in& from)
{
    State& s = S();
    if (s.keyed) {
        if (n < 6 + kTag) return false;
        uint64_t t;
        memcpy(&t, p + n - kTag, kTag);
        return t == siphash24(s.key, p, (size_t)(n - kTag));
    }
    return !s.env_peer || from.sin_addr.s_addr == s.env_peer_ip.s_addr;
}

/* Does this packet of the peer's process carry anything not seen yet: a newer PING clock, an input,
 * hash or scene change not known, a newer acknowledgement? A copy of an old packet does not -- and
 * replayed by somebody else from another address it must not make this game follow the peer there
 * (the tag proves who made a packet, not that it is new). n excludes the tag. */
bool fresh_locked(const Hdr* h, int n)
{
    State& s = S();
    if (h->type == PKT_BYE) return true;               /* sent only at the very end: never an old copy */
    if (h->type == PKT_PING) {
        if (n < (int)(sizeof(Hdr) + sizeof(PingExt))) return false;
        PingExt x; memcpy(&x, h + 1, sizeof x);
        return s.peer_ping_us == 0 || (int32_t)(x.t_us - s.peer_ping_us) > 0;
    }
    if (h->type != PKT_INPUT || n < (int)(sizeof(Hdr) + sizeof(InputHdr))) return false;
    const InputHdr* ih = (const InputHdr*)(h + 1);
    if (n < (int)(sizeof(Hdr) + sizeof(InputHdr) + ih->count * sizeof(WireIn) + ih->nhash * sizeof(WireHash)
                  + ih->nbar * sizeof(WireBar)))
        return false;
    if (ih->ack > s.peer_ack) return true;
    for (uint32_t k = 0; k < ih->count; k++) {
        const uint32_t f = ih->first + k;
        if (f >= s.remote_contig && f < s.remote_contig + kRing / 2 && s.remote.in_tag[f % kRing] != f + 1) return true;
    }
    const WireHash* wh = (const WireHash*)((const WireIn*)(ih + 1) + ih->count);
    for (uint32_t k = 0; k < ih->nhash; k++)
        if (wh[k].frame + 1 > s.remote_hash_max) return true;
    const WireBar* wb = (const WireBar*)(wh + ih->nhash);
    for (uint32_t k = 0; k < ih->nbar; k++)
        if (!s.remote_bar[wb[k].index % kBarriers]) return true;
    return false;
}

constexpr ULONGLONG kRelatchSilenceMs = 1000;   /* the peer's address silent this long: follow even an old packet */

void handle_packet(const uint8_t* p, int n, const sockaddr_in& from)
{
    State& s = S();
    if (n < 6) return;
    const Hdr* h = (const Hdr*)p;
    if (h->magic != kMagic) return;
    if (h->ver != kVersion) {
        /* Another netplay protocol: a different build. Only before the
         * handshake (afterwards it can only be a stranger), and only from the opponent. */
        std::lock_guard<std::mutex> lk(s.mu);
        if (!s.connected && h->type == PKT_HELLO && foreign_hello_trusted_locked(p, n, from))
            fail_locked("build_mismatch", "%s speaks netplay protocol v%u, this game v%u (a different build)",
                        addr_str(from).c_str(), h->ver, kVersion);
        else if (s.strangers++ < 5)
            note("packet of netplay protocol v%u from %s ignored (not the opponent's)", h->ver, addr_str(from).c_str());
        return;
    }
    if (n < (int)sizeof(Hdr)) return;
    std::lock_guard<std::mutex> lk(s.mu);
    if (s.keyed) {
        uint64_t t;
        if (n < (int)sizeof(Hdr) + kTag) return;
        n -= kTag;
        memcpy(&t, p + n, kTag);
        if (t != siphash24(s.key, p, (size_t)n)) {
            if (s.bad_tags++ < 5)
                note("packet from %s with a wrong authentication tag dropped (another match, or a stranger)",
                     addr_str(from).c_str());
            return;
        }
    }
    const bool from_peer = s.peer_known && same_addr(from, s.peer);
    /* Without a key the only proof of identity is the session id + nonce; for a
     * lobby match (T5_NET_PEER given) a hello must at least come from that IP. */
    const bool trusted_src = s.keyed || !s.env_peer || from.sin_addr.s_addr == s.env_peer_ip.s_addr;

    if (h->type == PKT_HELLO) {
        if (n < (int)(sizeof(Hdr) + 8)) return;
        HelloExt x = { 0, 0, 0 };
        memcpy(&x, h + 1, (size_t)std::min<int>(n - (int)sizeof(Hdr), (int)sizeof x));
        if (!trusted_src && !s.connected) {
            if (s.strangers++ < 5) note("hello from %s ignored: not the opponent's address", addr_str(from).c_str());
            return;
        }
        if (x.build && s.build && x.build != s.build) {
            if (!s.connected) {
                send_reject(from, REJ_BUILD);
                fail_locked("build_mismatch", "%s runs a different build (T5_NET_BUILD id %08X, ours %08X)",
                            addr_str(from).c_str(), x.build, s.build);
            }
            return;
        }
        if (s.connected && h->nonce != s.peer_nonce) {
            /* Another process at the other end: the peer's game was restarted
             * (or, without a key, a stranger). */
            if (!s.keyed && !from_peer) { s.strangers++; return; }
            if (can_restart_locked()) {
                note("the opponent's game was restarted before the match began (%s); connecting to the new one",
                     addr_str(from).c_str());
                forget_peer_locked();
            } else {
                send_reject(from, REJ_SESSION);
                lose_locked("peer_restarted", "the opponent's game at %s restarted in the middle of the match",
                            addr_str(from).c_str());
                return;
            }
        }
        if (s.connected) {
            /* the same peer process; a HELLO carries nothing new, so from another address it is
             * followed only once the known one has gone quiet (see fresh_locked) */
            if (!from_peer) {
                if (GetTickCount64() - s.last_rx_ms < kRelatchSilenceMs) { s.stale++; return; }
                relatch_locked(from);
            }
            s.last_rx_ms = GetTickCount64();
            if (s.mode == Mode::Host) send_hello_locked();   /* it may have missed ours */
            return;
        }
        s.rb_peer = (x.flags & kHelloRollback) != 0;
        if (s.rb_peer) s.peer_rb_delay = (int)((x.flags >> 8) & 0xFF);
        if (s.mode == Mode::Host) {
            /* Before the handshake the latest valid hello is the candidate; the
             * echo of our session id (the joiner adopted it) completes it. */
            if (!s.peer_known || !from_peer || s.peer_nonce != h->nonce)
                note("peer %s says hello", addr_str(from).c_str());
            s.peer = from; s.peer_known = true; s.peer_nonce = h->nonce;
            send_hello_locked();
            if (h->session == s.session) connect_locked();
        } else if (s.mode == Mode::Join) {
            s.session = h->session;
            const int hd = std::min<int>(h->delay, kMaxDelay);   /* a host never sends more (configure) */
            if (hd != s.delay) note("using the host's input delay %d (was %d)", hd, s.delay);
            s.delay = hd;
            s.seed = x.seed;   /* the host's seed (none: both use the session id) */
            s.peer = from; s.peer_known = true; s.peer_nonce = h->nonce;
            connect_locked();
            send_hello_locked();   /* echoes the session: completes the host's handshake */
        }
        return;
    }
    if (h->type == PKT_REJECT) {
        if (!trusted_src || (s.connected && h->nonce != s.peer_nonce)) return;
        const uint8_t why = n >= (int)(sizeof(Hdr) + 1) ? *(const uint8_t*)(h + 1) : 0;
        if (why == REJ_BUILD) {
            if (!s.connected)
                fail_locked("build_mismatch", "%s refused us: it runs a different build", addr_str(from).c_str());
        } else if (!s.connected || !s.peer_sent_inputs) {
            fail_locked("rejected", "%s is playing another session (its game was not restarted with ours)",
                        addr_str(from).c_str());
        } else {
            lose_locked("peer_restarted", "the opponent's game no longer knows this session");
        }
        return;
    }
    if (h->session != s.session) return;
    if (!s.connected) {
        /* The joiner's session echo was lost, but its packets carry our
         * session id: that completes the handshake as well. */
        if (s.mode != Mode::Host || h->type == PKT_BYE || !trusted_src) return;
        if (s.peer_nonce && h->nonce != s.peer_nonce) return;
        s.peer = from; s.peer_known = true; s.peer_nonce = h->nonce;
        connect_locked();
    }
    if (h->nonce != s.peer_nonce) return;     /* an old process of the peer, or a stranger */
    if (!same_addr(from, s.peer)) {
        /* NAT rebinding or a new relay mapping -- or a recorded packet of the peer played back from
         * somewhere else. Follow only what is new, or anything once the known address went quiet. */
        if (!fresh_locked(h, n) && GetTickCount64() - s.last_rx_ms < kRelatchSilenceMs) {
            if (s.stale++ < 5)
                note("old packet of the opponent's from %s dropped (a copy, not a new address)", addr_str(from).c_str());
            return;
        }
        relatch_locked(from);
    }
    s.packets_in++;
    s.last_rx_ms = GetTickCount64();
    if (h->type == PKT_BYE) {
        lose_locked("peer_quit", "the opponent left (its game was closed)");
        return;
    }
    if (h->type == PKT_PING) {
        if (n >= (int)(sizeof(Hdr) + sizeof(PingExt))) {
            PingExt x; memcpy(&x, h + 1, sizeof x);
            if (x.flags & PING_STARTED) s.peer_started = true;
            if (!s.started) s.rb_peer = (x.flags & PING_ROLLBACK) != 0;   /* settled before lockstep begins */
            s.peer_frame = x.frame;
            const uint64_t now = qpc_us();
            if (x.echo_us) {   /* our earlier PING came back: a round-trip sample */
                const uint32_t rtt_us = (uint32_t)now - x.echo_us - x.hold_us;
                if (rtt_us < 2000000u) s.rtt_ms[s.nrtt++ % 32] = (float)rtt_us / 1000.0f;
            }
            s.peer_ping_us = x.t_us; s.peer_ping_rx_us = now;
            if (x.rbd != 0xFF && s.mode == Mode::Join) s.peer_rbd = x.rbd;
        }
        SetEvent(s.rx_event);
        return;
    }
    if (h->type == PKT_PICK) {
        /* never answered at once (two sides answering each other would not
         * stop): the tick thread sends the acknowledgement, three times */
        if (n >= (int)(sizeof(Hdr) + sizeof(PickExt))) {
            PickExt x; memcpy(&x, h + 1, sizeof x);
            if (x.key && x.pick) {
                if (x.key != s.peer_pick_key || x.pick != s.peer_pick_val)
                    note("the opponent's pick for match key %08X: %08X", x.key, x.pick);
                s.peer_pick_key = x.key; s.peer_pick_val = x.pick;
                s.pick_acks_owed = 3;
            }
            if (s.pick_key && x.ack == s.pick_key) s.pick_acked = s.pick_key;
        }
        SetEvent(s.rx_event);
        return;
    }
    if (h->type != PKT_INPUT) return;
    if (n < (int)(sizeof(Hdr) + sizeof(InputHdr))) return;
    const InputHdr* ih = (const InputHdr*)(h + 1);
    if (n < (int)(sizeof(Hdr) + sizeof(InputHdr) + ih->count * sizeof(WireIn) + ih->nhash * sizeof(WireHash)
                  + ih->nbar * sizeof(WireBar)))
        return;
    if (ih->count) { s.peer_sent_inputs = true; s.peer_started = true; }
    if (ih->ack > s.peer_ack) s.peer_ack = ih->ack;
    s.peer_lead = ih->lead;
    if (ih->rbd != 0xFF && s.mode == Mode::Join) s.peer_rbd = ih->rbd;
    const WireIn* wi = (const WireIn*)(ih + 1);
    for (uint32_t k = 0; k < ih->count; k++) {
        uint32_t f = ih->first + k;
        if (f < s.remote_contig || f >= s.remote_contig + kRing / 2) continue;
        uint32_t i = f % kRing;
        s.remote.in[i] = { wi[k].buttons, wi[k].lx, wi[k].ly, wi[k].rx, wi[k].ry };
        s.remote.in_tag[i] = f + 1;
    }
    while (s.remote.in_tag[s.remote_contig % kRing] == s.remote_contig + 1) s.remote_contig++;
    const WireHash* wh = (const WireHash*)(wi + ih->count);
    for (uint32_t k = 0; k < ih->nhash; k++) {
        uint32_t i = wh[k].frame % kRing;
        s.remote.hash[i] = wh[k].hash;
        s.remote.hash_tag[i] = wh[k].frame + 1;
        if (wh[k].frame + 1 > s.remote_hash_max) s.remote_hash_max = wh[k].frame + 1;
    }
    const WireBar* wb = (const WireBar*)(wh + ih->nhash);
    for (uint32_t k = 0; k < ih->nbar; k++)
        s.remote_bar[wb[k].index % kBarriers] = wb[k].frame + 1;
    compare_hashes_locked();
    SetEvent(s.rx_event);
}

DWORD WINAPI rx_thread(LPVOID)
{
    State& s = S();
    uint8_t buf[2048];
    for (;;) {
        const SOCKET sk = s.sock.load();
        if (sk == INVALID_SOCKET) { Sleep(10); continue; }     /* between two sessions */
        sockaddr_in from{}; int fl = sizeof from;
        int n = recvfrom(sk, (char*)buf, sizeof buf, 0, (sockaddr*)&from, &fl);
        if (n > 0) {
            if (sk == s.sock.load()) handle_packet(buf, n, from);   /* not a late packet of a closed session */
            continue;
        }
        if (n == SOCKET_ERROR) {
            int e = WSAGetLastError();
            if (e == WSAETIMEDOUT || e == WSAECONNRESET || e == WSAEMSGSIZE) continue;
            if (sk != s.sock.load()) continue;                  /* the session's socket was closed: the next one */
            note("recvfrom failed (%d); receive thread stops", e);
            return 0;
        }
    }
}

/* The background half of the session, every 50 ms from init on: the handshake
 * (HELLO every 100 ms until connected, with its deadline), keepalives, and the
 * silence check -- so a missing, mismatched or vanished peer is noticed whether
 * or not the main thread is in a lockstep wait. */
DWORD WINAPI tick_thread(LPVOID)
{
    State& s = S();
    for (;;) {
        Sleep(50);
        void (*stuck)(const char*) = nullptr;
        std::string why;
        {
            std::lock_guard<std::mutex> lk(s.mu);
            const ULONGLONG now = GetTickCount64();
            if (s.mode != Mode::Host && s.mode != Mode::Join) continue;   /* no session (persistent game, idle) */
            if (!s.fail_reason.empty() || (s.connected && s.peer_lost)) {
                /* the main thread ends the match at its next frame; if it does
                 * not get there (blocked elsewhere), the handler does it */
                if (!s.stuck_called && s.stuck_handler && now - s.trouble_ms > 8000) {
                    s.stuck_called = true;
                    stuck = s.stuck_handler;
                    why = !s.fail_reason.empty() ? s.fail_reason : s.lost_reason;
                }
            } else if (!s.connected) {
                if ((s.mode == Mode::Join || s.peer_known) && now - s.last_hello_ms >= 100) send_hello_locked();
                if (now - s.last_wait_note >= 5000) {
                    s.last_wait_note = now;
                    if (now - s.init_ms >= 4000)
                        note("waiting for the opponent's game to answer (%llus)...", (now - s.init_ms) / 1000);
                }
                if (s.connect_timeout_s > 0 && now - s.init_ms >= (ULONGLONG)s.connect_timeout_s * 1000)
                    fail_locked("no_peer", "no answer from the opponent's game within %d s (%s)", s.connect_timeout_s,
                                s.peer_known ? addr_str(s.peer).c_str() : "its address is not known");
            } else {
                if (now - s.last_send_ms >= kPingMs) send_ping_locked();
                if (((s.pick_key && s.pick_acked != s.pick_key) || s.pick_acks_owed > 0) && now - s.pick_sent_ms >= 100) {
                    if (s.pick_acks_owed > 0) s.pick_acks_owed--;
                    send_pick_locked();
                }
                if (s.timeout_s > 0 && now - s.last_rx_ms >= (ULONGLONG)s.timeout_s * 1000)
                    lose_locked("peer_timeout", "nothing from the opponent's game for %d s", s.timeout_s);
            }
        }
        if (stuck) stuck(why.c_str());
    }
}

bool parse_addr(const char* spec, sockaddr_in* out)
{
    std::string str(spec);
    size_t c = str.rfind(':');
    if (c == std::string::npos) return false;
    std::string host = str.substr(0, c);
    int port = atoi(str.c_str() + c + 1);
    memset(out, 0, sizeof *out);
    out->sin_family = AF_INET;
    out->sin_port = htons((u_short)port);
    if (inet_pton(AF_INET, host.c_str(), &out->sin_addr) == 1) return true;
    addrinfo hints{}; hints.ai_family = AF_INET; hints.ai_socktype = SOCK_DGRAM;
    addrinfo* res = nullptr;
    if (getaddrinfo(host.c_str(), nullptr, &hints, &res) != 0 || !res) return false;
    out->sin_addr = ((sockaddr_in*)res->ai_addr)->sin_addr;
    freeaddrinfo(res);
    return true;
}

void say_bye()
{
    State& s = S();
    if (s.sock == INVALID_SOCKET) return;
    std::lock_guard<std::mutex> lk(s.mu);
    if (!s.connected) return;
    Hdr h = make_hdr(PKT_BYE);
    for (int i = 0; i < 3; i++) send_raw(&h, sizeof h);
}

/* 16-byte packet key from a secret string (SipHash under two fixed keys). */
void derive_key(const std::string& secret, uint8_t out[16])
{
    static const uint8_t k1[16] = { 'T','5','N','P','-','k','e','y','-','d','e','r','i','v','e','1' };
    static const uint8_t k2[16] = { 'T','5','N','P','-','k','e','y','-','d','e','r','i','v','e','2' };
    const uint64_t a = siphash24(k1, (const uint8_t*)secret.data(), secret.size());
    const uint64_t b = siphash24(k2, (const uint8_t*)secret.data(), secret.size());
    memcpy(out, &a, 8); memcpy(out + 8, &b, 8);
}

/* Fill the session from the environment (T5_NET_*) and open its socket: at
 * boot (init()), and in a persistent game again for every new opponent
 * (session_begin(), after the control channel put that match's T5_NET_* into
 * the environment). */
void configure()
{
    State& s = S();
    const char* m = env("T5_NET_MODE");
    if (!m) return;
    std::unique_lock<std::mutex> lk(s.mu);
    if (!s.rx_event) s.rx_event = CreateEventA(nullptr, FALSE, FALSE, nullptr);
    if (!_stricmp(m, "host")) s.mode = Mode::Host;
    else if (!_stricmp(m, "join")) s.mode = Mode::Join;
    else if (!_stricmp(m, "local")) s.mode = Mode::Local;
    else { fprintf(stderr, "[netplay] T5_NET_MODE=%s: expected host, join or local -- netplay off\n", m); return; }
    s.slot = s.mode == Mode::Join ? 1 : 0;
    if (const char* v = env("T5_NET_DELAY")) s.delay = atoi(v);
    if (const char* v = env("T5_RB_NET_DELAY"))
        s.rb_delay = (!_stricmp(v, "auto") || !_stricmp(v, "a")) ? kRbAuto : std::max(0, std::min(30, atoi(v)));
    if (const char* v = env("T5_RB_NET_DELAY_AUTO")) s.rb_auto_ms = std::max(0, std::min(1000, atoi(v)));
    if (s.delay < 0) s.delay = 0;
    if (s.delay > kMaxDelay) s.delay = kMaxDelay;
    if (const char* v = env("T5_NET_TIMEOUT")) s.timeout_s = atoi(v);
    s.connect_timeout_s = std::max(60, 2 * s.timeout_s);
    if (const char* v = env("T5_NET_CONNECT_TIMEOUT")) s.connect_timeout_s = atoi(v);
    if (const char* v = env("T5_NET_START_TIMEOUT")) s.start_timeout_s = atoi(v);
    if (const char* v = env("T5_NET_LOCALPAD")) s.localpad = atoi(v) != 0;
    if (const char* v = env("T5_NET_LOCAL_LAG")) {
        s.local_lag = (uint32_t)std::max(0, std::min(8, atoi(v)));
        if (s.local_lag && s.mode == Mode::Local) note("TEST: the second player's input is known %u frame(s) late (T5_NET_LOCAL_LAG)", s.local_lag);
    }
    if (const char* v = env("T5_NET_BUILD")) {
        uint32_t h = 2166136261u;
        for (const char* c = v; *c; c++) { h ^= (uint8_t)*c; h *= 16777619u; }
        s.build = h ? h : 1;
    }
    if (const char* v = env("T5_NET_SEED")) s.seed = (uint32_t)strtoul(v, nullptr, 0);
    if (const char* v = env("T5_NET_MATCH"))
        note("lobby match %s (path %s, measured rtt %s ms)", v,
             env("T5_NET_PATH") ? env("T5_NET_PATH") : "?", env("T5_NET_RTT_MS") ? env("T5_NET_RTT_MS") : "?");
    if (const char* k = env("T5_NET_KEY")) {
        derive_key(std::string("key|") + k, s.key);
        s.keyed = true;
    } else if (env("T5_NET_MATCH") && env("T5_NET_SEED")) {
        derive_key(std::string("match|") + env("T5_NET_MATCH") + "|" + env("T5_NET_SEED"), s.key);
        s.keyed = true;
    }
    s.script = parse_script(env("T5_NET_SCRIPT"));
    s.script2 = parse_script(env("T5_NET_SCRIPT2"));
    if (const char* v = env("T5_NET_PADFILE")) s.padfile.path = v;
    if (const char* v = env("T5_NET_PADFILE2")) s.padfile2.path = v;
    if (const char* v = env("T5_NET_LOG"); v && !s.log) {   /* the first session's file: later sessions add to it */
        s.log = fopen(v, "w");
        if (!s.log) fprintf(stderr, "[netplay] cannot write %s\n", v);
    }
    { LARGE_INTEGER q; QueryPerformanceCounter(&q);
      s.session = (uint32_t)(q.QuadPart ^ (q.QuadPart >> 32) ^ (GetCurrentProcessId() << 16)) | 1u;
      uint64_t x = (uint64_t)q.QuadPart * 0x9E3779B97F4A7C15ull ^ ((uint64_t)GetCurrentProcessId() << 32) ^ GetTickCount64();
      x ^= x >> 29; x *= 0xBF58476D1CE4E5B9ull; x ^= x >> 32;
      s.nonce = (uint32_t)x | 1u; }
    s.init_ms = GetTickCount64();
    s.sessions++;

    note("mode %s, slot P%d, delay %d, local devices %s, %zu scripted press(es)%s",
         m, s.slot + 1, s.delay, s.localpad ? "on" : "off", s.script.size(),
         s.sessions > 1 ? " (a new session in the running game)" : "");

    if (s.mode == Mode::Local) { s.connected = true; return; }

    static bool wsa_ok = false;
    if (!wsa_ok) {
        WSADATA wsa;
        if (WSAStartup(MAKEWORD(2, 2), &wsa) != 0) { note("WSAStartup failed -- netplay off"); s.mode = Mode::Off; return; }
        wsa_ok = true;
    }
    const SOCKET sk = socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP);
    if (sk == INVALID_SOCKET) { note("socket() failed -- netplay off"); s.mode = Mode::Off; return; }
    { DWORD tmo = 200; setsockopt(sk, SOL_SOCKET, SO_RCVTIMEO, (const char*)&tmo, sizeof tmo); }
    /* No ICMP port-unreachable resets on Windows UDP sockets: a peer that is
     * not up yet must not break our receive loop. */
    { BOOL off = FALSE; DWORD ret = 0;
      WSAIoctl(sk, _WSAIOW(IOC_VENDOR, 12) /* SIO_UDP_CONNRESET */, &off, sizeof off, nullptr, 0, &ret, nullptr, nullptr); }
    int port = s.mode == Mode::Host ? 7000 : 0;
    if (const char* v = env("T5_NET_PORT")) port = atoi(v);
    sockaddr_in local{}; local.sin_family = AF_INET; local.sin_port = htons((u_short)port);
    local.sin_addr.s_addr = htonl(INADDR_ANY);
    if (bind(sk, (sockaddr*)&local, sizeof local) != 0) {
        /* The lobby handed us exactly this port: without it there is no match. */
        s.fail_reason = "bind_failed";
        s.peer_lost = true;
        s.trouble_ms = GetTickCount64();
        note("cannot connect (bind_failed): UDP port %d is not free (%d)", port, WSAGetLastError());
        closesocket(sk);
        return;
    }
    s.sock = sk;
    if (s.mode == Mode::Join) {
        const char* peer = env("T5_NET_PEER");
        if (!peer || !parse_addr(peer, &s.peer)) {
            note("join needs T5_NET_PEER=<host ip>:<port> -- netplay off");
            s.sock = INVALID_SOCKET; closesocket(sk);
            s.mode = Mode::Off; return;
        }
        s.peer_known = true;
        s.env_peer = true; s.env_peer_ip = s.peer.sin_addr;
        note("joining %s", peer);
    } else {
        note("hosting on UDP port %d", port);
        const char* peer = env("T5_NET_PEER");
        if (peer && parse_addr(peer, &s.peer)) {
            s.peer_known = true;
            s.env_peer = true; s.env_peer_ip = s.peer.sin_addr;
            note("calling %s while waiting (lobby punch / relay path)", peer);
        }
    }
    note("handshake from %s on: %s, connect timeout %d s, peer timeout %d s, start timeout %d s",
         s.sessions > 1 ? "now" : "boot",
         s.keyed ? "authenticated (match key)" : "not authenticated (no T5_NET_KEY / match id + seed)",
         s.connect_timeout_s, s.timeout_s, s.start_timeout_s);
    lk.unlock();
    if (!s.net_up) {
        s.net_up = true;
        CreateThread(nullptr, 0, rx_thread, nullptr, 0, nullptr);
        CreateThread(nullptr, 0, tick_thread, nullptr, 0, nullptr);
        atexit(say_bye);
    }
}

void do_init() { configure(); }

/* Block until the handshake is done or has failed (frame 0 only). The
 * handshake itself runs in tick_thread from boot on. */
bool wait_connected()
{
    State& s = S();
    ULONGLONG t0 = GetTickCount64(), last_note = t0;
    for (;;) {
        {
            std::lock_guard<std::mutex> lk(s.mu);
            if (s.connected) return true;
            if (!s.fail_reason.empty() || s.mode == Mode::Off) return false;
            ULONGLONG now = GetTickCount64();
            if (now - last_note >= 3000) {
                last_note = now;
                note("waiting for the peer to connect (%llus)...", (now - t0) / 1000);
            }
        }
        WaitForSingleObject(s.rx_event, 50);
    }
}

/* Frame timing for the speed line and local_fps(): this PC's frames per
 * second with the time spent waiting for the peer left out. */
uint64_t qpc_us()
{
    static LARGE_INTEGER f = [] { LARGE_INTEGER x; QueryPerformanceFrequency(&x); return x; }();
    LARGE_INTEGER c; QueryPerformanceCounter(&c);
    return (uint64_t)(c.QuadPart / f.QuadPart) * 1000000ull + (uint64_t)(c.QuadPart % f.QuadPart) * 1000000ull / (uint64_t)f.QuadPart;
}

void account_frame(uint64_t wait_us)
{
    State& s = S();
    const uint64_t now = qpc_us();
    if (s.last_frame_qpc) {
        const uint64_t dt = now - s.last_frame_qpc;
        if (dt < 5000000) {             /* a frame longer than 5 s is a stall, not speed */
            s.speed_frames++; s.speed_us += dt; s.speed_wait_us += wait_us;
            s.win_frames++; s.win_us += dt; s.win_wait_us += wait_us;
        }
    }
    s.last_frame_qpc = now;
    if (s.win_frames >= 600) {
        const double busy = (double)(s.win_us > s.win_wait_us ? s.win_us - s.win_wait_us : 1);
        note("speed: %.1f fps, this PC %.1f fps without the waits for the peer (waited %.1f s of %.1f s)",
             s.win_frames * 1e6 / (double)s.win_us, s.win_frames * 1e6 / busy, s.win_wait_us / 1e6, s.win_us / 1e6);
        s.win_frames = s.win_us = s.win_wait_us = 0;
    }
}

} // namespace

/* ---- public API --------------------------------------------------------- */

void note(const char* fmt, ...)
{
    va_list ap; va_start(ap, fmt); vlog(fmt, ap); va_end(ap);
}

void init() { State& s = S(); std::call_once(s.once, do_init); }

Mode mode()       { init(); return S().mode; }
bool enabled()    { return mode() != Mode::Off; }
int  local_slot() { init(); return S().slot; }
int  delay()      { init(); return S().delay; }

PadInput poll_now(int player)
{
    init();
    State& s = S();
    static uint32_t calls[2];
    uint32_t f = calls[player & 1]++;
    if (player == 0) return sample_local(f);
    PadInput in = kNeutral;
    in.buttons = script_mask(s.script2, f) | s.padfile2.poll(f);
    return in;
}

uint32_t scene_barrier(uint32_t f)
{
    init();
    State& s = S();
    uint32_t k;
    {
        std::lock_guard<std::mutex> lk(s.mu);
        k = s.nbar++;
        s.local_bar[k % kBarriers] = f + 1;
        if (s.mode == Mode::Local || s.mode == Mode::Off || s.peer_lost) return f;
        send_inputs_locked();
    }
    ULONGLONG t0 = GetTickCount64(), last_note = t0;
    uint32_t peer_f = f;
    for (;;) {
        {
            std::lock_guard<std::mutex> lk(s.mu);
            if (s.remote_bar[k % kBarriers]) { peer_f = s.remote_bar[k % kBarriers] - 1; break; }
            if (s.peer_lost) break;
            /* The peer may still be in the old scene, consuming our input for
             * frames we will never run: keep it fed with neutral input. */
            while (s.local_max < s.remote_contig + 1) {
                uint32_t g = s.local_max++;
                s.local.in[g % kRing] = kNeutral; s.local.in_tag[g % kRing] = g + 1;
            }
            ULONGLONG now = GetTickCount64();
            if (now - s.last_send_ms >= 15) send_inputs_locked();
            if (now - last_note >= 1000) {
                last_note = now;
                note("scene change %u at frame %u: waiting for the peer to get there (%llus)", k, f, (now - t0) / 1000);
            }
            if (s.timeout_s > 0 && now - t0 >= (ULONGLONG)s.timeout_s * 1000) {
                lose_locked("peer_stalled", "the opponent's game never reached scene change %u (%d s)", k, s.timeout_s);
                break;
            }
        }
        WaitForSingleObject(s.rx_event, 2);
    }
    const uint32_t nf = peer_f > f ? peer_f : f;
    if (peer_f != f)
        note("scene change %u: here at frame %u, peer at %u -> both continue at %u", k, f, peer_f, nf);
    return nf;
}

void connect()
{
    init();
    State& s = S();
    if (s.mode == Mode::Host || s.mode == Mode::Join) wait_connected();
}

const char* failure()
{
    State& s = S();
    std::lock_guard<std::mutex> lk(s.mu);
    return s.fail_reason.empty() ? nullptr : (s.fail_reason == "bind_failed" ? "bind_failed"
         : s.fail_reason == "no_peer" ? "no_peer" : s.fail_reason == "build_mismatch" ? "build_mismatch" : "rejected");
}

const char* lost_reason()
{
    State& s = S();
    std::lock_guard<std::mutex> lk(s.mu);
    if (!s.fail_reason.empty() || !s.peer_lost) return nullptr;
    static const char* const kReasons[] = { "peer_quit", "peer_timeout", "peer_stalled", "start_timeout", "peer_restarted" };
    for (const char* r : kReasons) if (s.lost_reason == r) return r;
    return "peer_lost";
}

bool connected() { State& s = S(); std::lock_guard<std::mutex> lk(s.mu); return s.connected; }

void match_begin(uint32_t f)
{
    State& s = S();
    std::lock_guard<std::mutex> lk(s.mu);
    s.count_from = f;
    s.match_mismatches = 0;
    s.speed_frames = s.speed_us = s.speed_wait_us = 0;
}

uint32_t match_mismatches() { State& s = S(); std::lock_guard<std::mutex> lk(s.mu); return s.match_mismatches; }
uint32_t checked_through() { State& s = S(); std::lock_guard<std::mutex> lk(s.mu); return s.checked; }

/* The rollback loop's live frames (it does not go through begin_frame):
 * wait_us = the time this frame waited for the peer (stalls, time-sync sleeps). */
void rb_account_frame(uint64_t wait_us) { account_frame(wait_us); }

double local_fps()
{
    State& s = S();
    std::lock_guard<std::mutex> lk(s.mu);
    if (s.speed_frames < 60 || s.speed_us <= s.speed_wait_us) return 0.0;
    return s.speed_frames * 1e6 / (double)(s.speed_us - s.speed_wait_us);
}

void bye() { say_bye(); }

void set_stuck_handler(void (*fn)(const char* reason))
{
    State& s = S();
    std::lock_guard<std::mutex> lk(s.mu);
    s.stuck_handler = fn;
}

bool take_mismatch(uint32_t* frame)
{
    State& s = S();
    std::lock_guard<std::mutex> lk(s.mu);
    if (s.mismatch_queue.empty()) return false;
    *frame = s.mismatch_queue.front();
    s.mismatch_queue.erase(s.mismatch_queue.begin());
    return true;
}

uint32_t match_seed()
{
    State& s = S();
    std::lock_guard<std::mutex> lk(s.mu);
    return s.seed ? s.seed : s.session;
}
uint32_t session_seed()
{
    State& s = S();
    std::lock_guard<std::mutex> lk(s.mu);
    return s.seed;
}

void log_extra(uint32_t f, const char* text)
{
    State& s = S();
    if (!s.log) return;
    std::lock_guard<std::mutex> lk(s.log_mu);
    fprintf(s.log, "%u X %s\n", f, text);
}

void begin_frame(uint32_t f, uint64_t state_hash, PadInput out[2], bool neutral_local)
{
    init();
    State& s = S();
    out[0] = out[1] = kNeutral;
    if (s.mode == Mode::Off) return;

    if (f == 0) {
        if (s.mode != Mode::Local) wait_connected();
        std::lock_guard<std::mutex> lk(s.mu);
        for (uint32_t k = 0; k < (uint32_t)s.delay; k++) {
            s.local.in[k] = kNeutral;  s.local.in_tag[k] = k + 1;
            s.remote.in[k] = kNeutral; s.remote.in_tag[k] = k + 1;
        }
        if (s.local_max < (uint32_t)s.delay) s.local_max = (uint32_t)s.delay;
        while (s.remote.in_tag[s.remote_contig % kRing] == s.remote_contig + 1) s.remote_contig++;
        s.started = true;
        if (s.rb_offer && (s.rb_peer || s.mode == Mode::Local)) decide_rb_delay_locked();   /* the rollback loop takes over at frame 1 */
        if (s.connected && !s.peer_lost) send_ping_locked();   /* tell the peer at once */
        note("lockstep starts: frame 0, delay %d", s.delay);
        note_fp_env();
    }

    PadInput local = neutral_local ? kNeutral : sample_local_open(f + (uint32_t)s.delay);
    {
        std::lock_guard<std::mutex> lk(s.mu);
        uint32_t i = f % kRing;
        s.local.hash[i] = state_hash; s.local.hash_tag[i] = f + 1;
        if (f + 1 > s.local_hash_max) s.local_hash_max = f + 1;
        uint32_t t = f + (uint32_t)s.delay;
        /* After a scene-change jump frames may have been skipped: hold this
         * sample over the gap. An input already decided (and maybe sent) for
         * a frame is never changed. */
        for (uint32_t g = s.local_max; g <= t; g++) {
            s.local.in[g % kRing] = local; s.local.in_tag[g % kRing] = g + 1;
        }
        if (t + 1 > s.local_max) s.local_max = t + 1;
        send_inputs_locked();
    }

    PadInput mine = kNeutral, theirs = kNeutral;
    if (s.mode == Mode::Local) {
        std::lock_guard<std::mutex> lk(s.mu);
        mine = s.local.in[f % kRing];
        theirs = kNeutral;
        if (s.localpad) device_input(1, &theirs);
        theirs.buttons |= script_mask(s.script2, f) | s.padfile2.poll(f);
        s.remote.hash[f % kRing] = state_hash; s.remote.hash_tag[f % kRing] = f + 1;
    } else {
        ULONGLONG t0 = GetTickCount64(), last_note = t0;
        const uint64_t w0 = qpc_us();
        for (;;) {
            {
                std::lock_guard<std::mutex> lk(s.mu);
                mine = s.local.in[f % kRing];
                if (s.peer_lost) { theirs = kNeutral; break; }
                if (s.remote.in_tag[f % kRing] == f + 1) { theirs = s.remote.in[f % kRing]; break; }
                ULONGLONG now = GetTickCount64();
                if (now - s.last_send_ms >= 15) send_inputs_locked();   /* resend while stalled */
                /* At the start of the match the peer may still be loading: as
                 * long as it is alive (its keepalives arrive; silence is the tick
                 * thread's peer_timeout) it gets T5_NET_START_TIMEOUT. Once it
                 * plays, a stall of T5_NET_TIMEOUT ends the match. */
                const bool at_start = !s.peer_started;
                const int limit = at_start ? s.start_timeout_s : s.timeout_s;
                if (now - last_note >= 1000) {
                    last_note = now;
                    note("frame %u: waiting for the peer's input (%llus; peer has our inputs up to %u%s)",
                         f, (now - t0) / 1000, s.peer_ack, at_start ? "; it has not started the match yet" : "");
                }
                if (limit > 0 && now - t0 >= (ULONGLONG)limit * 1000) {
                    if (at_start)
                        lose_locked("start_timeout", "the opponent's game did not reach the start of the match within %d s", limit);
                    else
                        lose_locked("peer_stalled", "no input from the opponent for %d s at frame %u", limit, f);
                    theirs = kNeutral;
                    break;
                }
            }
            WaitForSingleObject(s.rx_event, 4);
        }
        std::lock_guard<std::mutex> lk(s.mu);
        account_frame(qpc_us() - w0);
    }
    out[s.slot] = mine;
    out[1 - s.slot] = theirs;

    {
        std::lock_guard<std::mutex> lk(s.mu);
        compare_hashes_locked();
    }
    if (s.log) {
        std::lock_guard<std::mutex> lk(s.log_mu);
        fprintf(s.log, "%u I %04X%02X%02X%02X%02X %04X%02X%02X%02X%02X %016llx\n", f,
                out[0].buttons, out[0].lx, out[0].ly, out[0].rx, out[0].ry,
                out[1].buttons, out[1].lx, out[1].ly, out[1].rx, out[1].ry,
                (unsigned long long)state_hash);
        if ((f % 60) == 0) fflush(s.log);
    }
}

/* ---- rollback mode ------------------------------------------------------ */

void rb_begin(uint32_t f)
{
    init();
    State& s = S();
    if (s.mode == Mode::Off || f != 0) return;
    if (s.mode != Mode::Local) wait_connected();
    std::lock_guard<std::mutex> lk(s.mu);
    for (uint32_t k = 0; k < (uint32_t)s.delay; k++) {
        s.local.in[k] = kNeutral;  s.local.in_tag[k] = k + 1;
        s.remote.in[k] = kNeutral; s.remote.in_tag[k] = k + 1;
    }
    if (s.local_max < (uint32_t)s.delay) s.local_max = (uint32_t)s.delay;
    while (s.remote.in_tag[s.remote_contig % kRing] == s.remote_contig + 1) s.remote_contig++;
    s.started = true;
    if (s.rb_offer && (s.rb_peer || s.mode == Mode::Local)) decide_rb_delay_locked();
    if (s.connected && !s.peer_lost) send_ping_locked();
    note("rollback mode starts: frame 0, delay %d", s.delay);
    note_fp_env();
}

void rb_sample_local(uint32_t f, bool neutral, const PadInput* forced)
{
    State& s = S();
    if (s.mode == Mode::Off) return;
    /* neutral: the frame takes no input (the fight intro, rb_net.cpp); the
     * devices are not read, so a tap stays latched for the next real sample */
    /* forced: a frame whose input the rollback loop decides from the game state
     * (the post-match rule, rb_net.cpp): the same input on both PCs */
    PadInput local = forced ? *forced : neutral ? kNeutral : sample_local_open(f + (uint32_t)s.delay);
    std::lock_guard<std::mutex> lk(s.mu);
    const uint32_t t = f + (uint32_t)s.delay;
    for (uint32_t g = s.local_max; g <= t; g++) {   /* hold the sample over any gap; a decided input never changes */
        s.local.in[g % kRing] = local; s.local.in_tag[g % kRing] = g + 1;
    }
    if (t + 1 > s.local_max) s.local_max = t + 1;
    if (s.mode == Mode::Local) {
        s.local_live = f;
        /* no peer: the second player is this PC's port 2 / script, confirmed at once
         * (T5_NET_LOCAL_LAG: known `local_lag` frames later, see local_horizon_locked) */
        PadInput theirs = kNeutral;
        if (s.localpad) device_input(1, &theirs);
        theirs.buttons |= script_mask(s.script2, t) | s.padfile2.poll(t);
        /* the second player follows the same rules a peer's game applies at
         * this boundary (the intro takes no input, the post-match input is a
         * rule): a real peer never presses there, and with T5_NET_LOCAL_LAG a
         * press there would roll the game back into the fight's loading */
        if (forced) theirs = *forced;
        else if (neutral) theirs = kNeutral;
        for (uint32_t g = s.remote_contig; g <= t; g++) { s.remote.in[g % kRing] = theirs; s.remote.in_tag[g % kRing] = g + 1; }
        while (s.remote.in_tag[s.remote_contig % kRing] == s.remote_contig + 1) s.remote_contig++;
        return;
    }
    send_inputs_locked();
}

PadInput rb_local(uint32_t f)
{
    State& s = S();
    std::lock_guard<std::mutex> lk(s.mu);
    return s.local.in_tag[f % kRing] == f + 1 ? s.local.in[f % kRing] : kNeutral;
}

/* local lag: inputs of frames >= this are not known yet (T5_NET_LOCAL_LAG) */
static uint32_t local_horizon_locked(const State& s)
{
    const uint32_t h = s.local_live + (uint32_t)s.delay + 1;
    const uint32_t lagged = h > s.local_lag ? h - s.local_lag : 0;
    return lagged > s.local_release ? lagged : s.local_release;   /* a wait for the peer = its inputs came */
}

bool rb_remote(uint32_t f, PadInput* out)
{
    State& s = S();
    std::lock_guard<std::mutex> lk(s.mu);
    if (s.remote.in_tag[f % kRing] != f + 1) return false;
    if (s.mode == Mode::Local && s.local_lag && f >= local_horizon_locked(s)) return false;
    *out = s.remote.in[f % kRing];
    return true;
}

uint32_t rb_remote_contig()
{
    State& s = S();
    std::lock_guard<std::mutex> lk(s.mu);
    if (s.mode == Mode::Local && s.local_lag) return std::min(s.remote_contig, local_horizon_locked(s));
    return s.remote_contig;
}

uint32_t rb_wait_remote(uint32_t f, uint32_t ms)
{
    State& s = S();
    const ULONGLONG t0 = GetTickCount64();
    for (;;) {
        {
            std::lock_guard<std::mutex> lk(s.mu);
            if (s.mode == Mode::Local && s.local_lag) {   /* the loop waits for the peer's input up to f: here it comes */
                if (f + 1 > s.local_release) s.local_release = f + 1;
                return std::min(s.remote_contig, local_horizon_locked(s));
            }
            if (s.remote_contig > f || s.peer_lost || s.mode == Mode::Local) return s.remote_contig;
            const ULONGLONG now = GetTickCount64();
            if (now - s.last_send_ms >= 15) send_inputs_locked();
            if (now - t0 >= ms) return s.remote_contig;
            if (s.timeout_s > 0 && now - s.last_rx_ms >= (ULONGLONG)s.timeout_s * 1000 && s.last_rx_ms) {
                lose_locked("peer_timeout", "nothing from the opponent's game for %d s", s.timeout_s);
                return s.remote_contig;
            }
        }
        WaitForSingleObject(s.rx_event, 2);
    }
}

void rb_push_hash(uint32_t f, uint64_t h)
{
    State& s = S();
    std::lock_guard<std::mutex> lk(s.mu);
    const uint32_t i = f % kRing;
    if (s.log) {   /* "f F <hash>": the final hash, what the peers compare (tools/cross_build_test.py) */
        std::lock_guard<std::mutex> lk2(s.log_mu);
        fprintf(s.log, "%u F %016llx\n", f, (unsigned long long)h);
    }
    s.local.hash[i] = h; s.local.hash_tag[i] = f + 1;
    if (f + 1 > s.local_hash_max) s.local_hash_max = f + 1;
    if (s.mode == Mode::Local) { s.remote.hash[i] = h; s.remote.hash_tag[i] = f + 1; }
    compare_hashes_locked();
}

void rb_poll()
{
    State& s = S();
    if (s.mode == Mode::Off || s.mode == Mode::Local) return;
    std::lock_guard<std::mutex> lk(s.mu);
    const ULONGLONG now = GetTickCount64();
    if (s.connected && !s.peer_lost && now - s.last_send_ms >= 15) send_inputs_locked();
    compare_hashes_locked();
}

void rb_log_frame(uint32_t f, const PadInput in[2], uint64_t hash, bool predicted, bool confirmed)
{
    State& s = S();
    if (!s.log) return;
    std::lock_guard<std::mutex> lk(s.log_mu);
    fprintf(s.log, "%u I %04X%02X%02X%02X%02X %04X%02X%02X%02X%02X %016llx %c %c\n", f,
            in[0].buttons, in[0].lx, in[0].ly, in[0].rx, in[0].ry,
            in[1].buttons, in[1].lx, in[1].ly, in[1].rx, in[1].ry,
            (unsigned long long)hash, predicted ? 'P' : 'R', confirmed ? 'C' : 'U');
    if ((f % 60) == 0) fflush(s.log);
}
bool rb_peer_lost() { State& s = S(); std::lock_guard<std::mutex> lk(s.mu); return s.peer_lost; }
void rb_offer(bool on) { State& s = S(); std::lock_guard<std::mutex> lk(s.mu); s.rb_offer = on; }
bool rb_negotiated()
{
    State& s = S();
    std::lock_guard<std::mutex> lk(s.mu);
    if (s.mode == Mode::Local) return s.rb_offer;
    return s.rb_offer && s.rb_peer && s.connected;
}
/* Rollback agreed: the input delay drops to the match's rollback delay -- the
 * host's pick (decide_rb_delay_locked), never above the lockstep delay the
 * session was set up with (the lobby picks that from the measured latency for
 * the lockstep; rollback predicts the latency away instead). Both PCs apply
 * the same value at the same point (the loop's start), so the time sync's
 * frame estimate stays right: the joiner waits here for the host's pick (any
 * PING or INPUT of the host's after its match started carries it). Inputs
 * already decided under the old delay keep their frames: the next samples
 * just wait until they are past them. */
int rb_apply_delay()
{
    State& s = S();
    const ULONGLONG t0 = GetTickCount64();
    for (;;) {
        {
            std::lock_guard<std::mutex> lk(s.mu);
            if (s.mode != Mode::Join || s.peer_rbd >= 0 || s.peer_lost || s.mode == Mode::Off) break;
            if (s.start_timeout_s > 0 && GetTickCount64() - t0 > (ULONGLONG)s.start_timeout_s * 1000) {
                note("the host's rollback input delay did not arrive -- keeping %d", s.delay);
                break;
            }
        }
        WaitForSingleObject(s.rx_event, 10);
    }
    std::lock_guard<std::mutex> lk(s.mu);
    if (s.mode == Mode::Host || s.mode == Mode::Local) decide_rb_delay_locked();   /* (already done at frame 0) */
    const int rbd = s.mode == Mode::Join ? (s.peer_rbd >= 0 ? s.peer_rbd : s.delay) : (s.rb_decided >= 0 ? s.rb_decided : s.delay);
    const int nd = std::min(s.delay, rbd);
    if (nd != s.delay) {
        note("rollback agreed: input delay %d -> %d (%s)", s.delay, nd, s.mode == Mode::Join ? "the host's pick" : "this match's");
        s.delay = nd;
    }
    return s.delay;
}
int rb_rtt_ms() { State& s = S(); std::lock_guard<std::mutex> lk(s.mu); int n = 0; return (int)(rtt_estimate_locked(&n) + 0.5f); }
void rb_set_lead(int lead) { State& s = S(); std::lock_guard<std::mutex> lk(s.mu); s.local_lead = (int8_t)std::max(-100, std::min(100, lead)); }
int  rb_peer_lead() { State& s = S(); std::lock_guard<std::mutex> lk(s.mu); return s.peer_lead; }
uint32_t rb_mismatches() { State& s = S(); std::lock_guard<std::mutex> lk(s.mu); return s.mismatches; }
uint32_t rb_peer_ack() { State& s = S(); std::lock_guard<std::mutex> lk(s.mu); return s.peer_ack; }

void set_local_inject(bool on, uint16_t buttons) { g_local_inject = buttons; g_local_inject_on = on; }

void pick_set(uint32_t key, uint32_t val)
{
    State& s = S();
    std::lock_guard<std::mutex> lk(s.mu);
    if (s.pick_key == key && s.pick_val == val) return;
    s.pick_key = val ? key : 0; s.pick_val = val; s.pick_acked = 0;
    if (val) note("this player's pick for match key %08X: %08X", key, val);
    if (val && s.connected && !s.peer_lost) send_pick_locked();
}

bool pick_peer(uint32_t key, uint32_t* val)
{
    State& s = S();
    std::lock_guard<std::mutex> lk(s.mu);
    if (!key || s.peer_pick_key != key || !s.peer_pick_val) return false;
    if (val) *val = s.peer_pick_val;
    return true;
}
void set_script_gate(bool on) { g_script_gate = on; }

/* ---- sessions in a persistent game (T5_CTL_DIR) -------------------------- */

void session_end(const char* why)
{
    State& s = S();
    std::lock_guard<std::mutex> lk(s.mu);
    if (s.mode == Mode::Off) return;
    if (s.connected && !s.peer_lost) {
        Hdr h = make_hdr(PKT_BYE);
        for (int i = 0; i < 3; i++) send_raw(&h, sizeof h);
    }
    note("session %u ends (%s): %llu packets in, %llu out, %u mismatching frame(s)", s.sessions, why ? why : "",
         (unsigned long long)s.packets_in, (unsigned long long)s.packets_out, s.mismatches);
    const SOCKET sk = s.sock.exchange(INVALID_SOCKET);
    if (sk != INVALID_SOCKET) closesocket(sk);         /* frees the UDP port for the launcher's next punch */
    static const Session kFresh{};
    static_cast<Session&>(s) = kFresh;                 /* mode Off: every wait returns, the tick thread rests */
    g_local_inject_on = false; g_local_inject = 0;
    SetEvent(s.rx_event);
}

bool session_begin()
{
    State& s = S();
    bool first = false;
    std::call_once(s.once, [&] { first = true; configure(); });
    if (!first) {
        session_end("a new session");
        configure();
    }
    std::lock_guard<std::mutex> lk(s.mu);
    return s.mode != Mode::Off;
}

uint32_t sessions() { State& s = S(); std::lock_guard<std::mutex> lk(s.mu); return s.sessions; }

} // namespace np

extern "C" void t5_env_overlay_begin(void)
{
    std::lock_guard<std::mutex> lk(np::g_env_mu);
    for (auto& kv : np::g_env_over) kv.second = { false, std::string() };
}

extern "C" void t5_env_overlay_set(const char* key, const char* value)
{
    if (!key || !*key) return;
    std::lock_guard<std::mutex> lk(np::g_env_mu);
    np::g_env_over[np::env_key(key)] = { value != nullptr, value ? value : "" };
}

extern "C" const char* t5_env(const char* key)
{
    return np::env_raw(key);
}

/* In-game select (src/directfight): this player's pick for a match, and the peer's. */
extern "C" void t5_netplay_pick_send(unsigned key, unsigned pick) { np::pick_set(key, pick); }
extern "C" int  t5_netplay_pick_peer(unsigned key, unsigned* pick) { return np::pick_peer(key, pick) ? 1 : 0; }
extern "C" int  t5_netplay_connected(void) { return np::connected() ? 1 : 0; }
