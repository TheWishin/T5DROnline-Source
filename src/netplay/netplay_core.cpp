/*
 * T5DR netplay prototype -- the game-independent core: configuration, local
 * pad sampling, UDP transport, delay-based lockstep and the desync check.
 *
 * Environment:
 *   T5_NET_MODE     host | join | local   (unset = netplay off)
 *   T5_NET_PORT     local UDP port (host default 7000, join default 0 = any)
 *   T5_NET_PEER     ip:port of the host (join; host learns it from the first packet)
 *   T5_NET_DELAY    input delay in frames (host decides, join adopts; default 3)
 *   T5_NET_TIMEOUT  seconds without the peer's input before giving up (default 30)
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
#include <winsock2.h>
#include <ws2tcpip.h>
#include <windows.h>

#include <atomic>
#include <cstdarg>
#include <cstdio>
#include <cstdlib>
#include <cstring>
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
constexpr uint8_t  kVersion  = 1;
constexpr uint32_t kRing     = 1024;          /* frames of history kept */
constexpr uint32_t kMaxBatch = 64;            /* inputs per packet */
constexpr uint32_t kHashes   = 8;             /* recent hashes per packet */
constexpr uint32_t kBarriers = 4096;          /* scene changes kept */
constexpr uint32_t kBarSend  = 4;             /* recent scene changes per packet */

enum : uint8_t { PKT_HELLO = 1, PKT_INPUT = 2, PKT_BYE = 3 };

#pragma pack(push, 1)
struct Hdr      { uint32_t magic; uint8_t type, ver, delay, slot; uint32_t session; };
struct InputHdr { uint32_t ack; uint32_t first; uint8_t count; uint8_t nhash; uint8_t nbar; uint8_t reserved; };
struct WireIn   { uint16_t buttons; uint8_t lx, ly, rx, ry; };
struct WireHash { uint32_t frame; uint64_t hash; };
struct WireBar  { uint32_t index; uint32_t frame; };
struct HelloExt { uint32_t build; uint32_t seed; };   /* follows Hdr in a HELLO */
#pragma pack(pop)

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

struct State {
    std::once_flag once;
    Mode mode = Mode::Off;
    int  delay = 3;
    int  slot = 0;
    int  timeout_s = 30;
    bool localpad = true;              /* T5_NET_LOCALPAD=0: this PC's devices are ignored */
    uint32_t build = 0;                /* FNV-1a of T5_NET_BUILD, 0 = not given */
    uint32_t seed = 0;                 /* T5_NET_SEED (the host's wins), 0 = use the session id */

    SOCKET sock = INVALID_SOCKET;
    std::mutex mu;                     /* guards everything below */
    sockaddr_in peer{};
    bool peer_known = false;
    bool connected = false;
    bool peer_lost = false;
    uint32_t session = 0;
    HANDLE rx_event = nullptr;

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

const char* env(const char* k) { const char* v = getenv(k); return (v && *v) ? v : nullptr; }

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

/* The local player's input for (effective) frame f. */
PadInput sample_local(uint32_t f)
{
    State& s = S();
    PadInput in = kNeutral;

    if (s.localpad) device_input(0, &in);
    in.buttons |= script_mask(s.script, f);
    in.buttons |= s.padfile.poll(f);
    return in;
}

/* ---- transport --------------------------------------------------------- */

void send_raw(const void* p, int n)
{
    State& s = S();
    if (s.sock == INVALID_SOCKET || !s.peer_known) return;
    /* T5_NET_DROP=<percent>: throw away that share of outgoing packets, to
     * test that the redundant resends cover for a lossy link. */
    static int drop = -1;
    if (drop < 0) { const char* d = getenv("T5_NET_DROP"); drop = d ? atoi(d) : 0; }
    if (drop > 0) {
        static uint32_t x = 0x9E3779B9u ^ GetCurrentProcessId();
        x ^= x << 13; x ^= x >> 17; x ^= x << 5;
        if ((int)(x % 100) < drop) return;
    }
    sendto(s.sock, (const char*)p, n, 0, (const sockaddr*)&s.peer, sizeof s.peer);
    s.packets_out++;
}

void send_hello_locked()
{
    State& s = S();
    struct { Hdr h; HelloExt x; } p = { { kMagic, PKT_HELLO, kVersion, (uint8_t)s.delay, (uint8_t)s.slot, s.session },
                                         { s.build, s.seed } };
    send_raw(&p, sizeof p);
}

/* Inputs the peer may still need, plus our latest hashes. Caller holds mu. */
void send_inputs_locked()
{
    State& s = S();
    if (!s.connected || s.peer_lost) return;
    uint8_t buf[sizeof(Hdr) + sizeof(InputHdr) + kMaxBatch * sizeof(WireIn) + kHashes * sizeof(WireHash)
                + kBarSend * sizeof(WireBar)];
    Hdr* h = (Hdr*)buf;
    *h = { kMagic, PKT_INPUT, kVersion, (uint8_t)s.delay, (uint8_t)s.slot, s.session };
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
    ih->reserved = 0;
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
            if (s.mismatch_queue.size() < 256) s.mismatch_queue.push_back(f);
        }
        s.checked++;
        if (s.checked % 600 == 0)
            note("sync check through frame %u: %u mismatching frame(s)%s", s.checked - 1,
                 s.mismatches, s.mismatches ? "" : " -- in sync");
    }
}

void handle_packet(const uint8_t* p, int n, const sockaddr_in& from)
{
    State& s = S();
    if (n < (int)sizeof(Hdr)) return;
    const Hdr* h = (const Hdr*)p;
    if (h->magic != kMagic || h->ver != kVersion) return;
    std::lock_guard<std::mutex> lk(s.mu);
    s.packets_in++;
    s.last_rx_ms = GetTickCount64();
    if (h->type == PKT_HELLO) {
        HelloExt x = { 0, 0 };
        if (n >= (int)(sizeof(Hdr) + sizeof(HelloExt))) memcpy(&x, h + 1, sizeof x);
        if (x.build && s.build && x.build != s.build) {
            static int said = 0;
            if (!said++) note("the peer runs a different build (T5_NET_BUILD id %08X, ours %08X): not connecting",
                              x.build, s.build);
            return;
        }
        if (s.mode == Mode::Host) {
            if (s.connected && memcmp(&s.peer, &from, sizeof from) != 0) return;   /* a stranger */
            if (!s.peer_known || memcmp(&s.peer, &from, sizeof from) != 0) {
                s.peer = from; s.peer_known = true;
                char ip[64]; inet_ntop(AF_INET, &from.sin_addr, ip, sizeof ip);
                note("peer %s:%u says hello", ip, ntohs(from.sin_port));
            }
            send_hello_locked();
            if (!s.connected && h->session == s.session) {
                s.connected = true;
                note("connected (host, P1), delay %d", s.delay);
                SetEvent(s.rx_event);
            }
        } else if (s.mode == Mode::Join && !s.connected) {
            s.session = h->session;
            if (h->delay != s.delay) note("using the host's input delay %d (was %d)", h->delay, s.delay);
            s.delay = h->delay;
            s.seed = x.seed;   /* the host's seed (none: both use the session id) */
            s.connected = true;
            note("connected (join, P2), delay %d", s.delay);
            send_hello_locked();   /* echoes the session: completes the host's handshake */
            SetEvent(s.rx_event);
        }
        return;
    }
    if (h->type == PKT_BYE) {
        if (h->session == s.session && s.connected && !s.peer_lost) {
            note("peer quit");
            s.peer_lost = true;
            SetEvent(s.rx_event);
        }
        return;
    }
    if (h->type != PKT_INPUT || h->session != s.session) return;
    if (!s.connected && s.mode == Mode::Host) {
        /* The joiner's session echo was lost, but its inputs carry our
         * session id: that completes the handshake as well. */
        s.connected = true;
        note("connected (host, P1), delay %d", s.delay);
    }
    if (!s.connected) return;
    if (n < (int)(sizeof(Hdr) + sizeof(InputHdr))) return;
    const InputHdr* ih = (const InputHdr*)(h + 1);
    if (n < (int)(sizeof(Hdr) + sizeof(InputHdr) + ih->count * sizeof(WireIn) + ih->nhash * sizeof(WireHash)
                  + ih->nbar * sizeof(WireBar)))
        return;
    if (ih->ack > s.peer_ack) s.peer_ack = ih->ack;
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
        sockaddr_in from{}; int fl = sizeof from;
        int n = recvfrom(s.sock, (char*)buf, sizeof buf, 0, (sockaddr*)&from, &fl);
        if (n > 0) { handle_packet(buf, n, from); continue; }
        if (n == SOCKET_ERROR) {
            int e = WSAGetLastError();
            if (e == WSAETIMEDOUT || e == WSAECONNRESET || e == WSAEMSGSIZE) continue;
            note("recvfrom failed (%d); receive thread stops", e);
            return 0;
        }
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
    Hdr h = { kMagic, PKT_BYE, kVersion, (uint8_t)s.delay, (uint8_t)s.slot, s.session };
    for (int i = 0; i < 3; i++) send_raw(&h, sizeof h);
}

void do_init()
{
    State& s = S();
    const char* m = env("T5_NET_MODE");
    if (!m) return;
    if (!_stricmp(m, "host")) s.mode = Mode::Host;
    else if (!_stricmp(m, "join")) s.mode = Mode::Join;
    else if (!_stricmp(m, "local")) s.mode = Mode::Local;
    else { fprintf(stderr, "[netplay] T5_NET_MODE=%s: expected host, join or local -- netplay off\n", m); return; }
    s.slot = s.mode == Mode::Join ? 1 : 0;
    if (const char* v = env("T5_NET_DELAY")) s.delay = atoi(v);
    if (s.delay < 0) s.delay = 0;
    if (s.delay > 30) s.delay = 30;
    if (const char* v = env("T5_NET_TIMEOUT")) s.timeout_s = atoi(v);
    if (const char* v = env("T5_NET_LOCALPAD")) s.localpad = atoi(v) != 0;
    if (const char* v = env("T5_NET_BUILD")) {
        uint32_t h = 2166136261u;
        for (const char* c = v; *c; c++) { h ^= (uint8_t)*c; h *= 16777619u; }
        s.build = h ? h : 1;
    }
    if (const char* v = env("T5_NET_SEED")) s.seed = (uint32_t)strtoul(v, nullptr, 0);
    if (const char* v = env("T5_NET_MATCH"))
        note("lobby match %s (path %s, measured rtt %s ms)", v,
             env("T5_NET_PATH") ? env("T5_NET_PATH") : "?", env("T5_NET_RTT_MS") ? env("T5_NET_RTT_MS") : "?");
    s.script = parse_script(env("T5_NET_SCRIPT"));
    s.script2 = parse_script(env("T5_NET_SCRIPT2"));
    if (const char* v = env("T5_NET_PADFILE")) s.padfile.path = v;
    if (const char* v = env("T5_NET_PADFILE2")) s.padfile2.path = v;
    if (const char* v = env("T5_NET_LOG")) {
        s.log = fopen(v, "w");
        if (!s.log) fprintf(stderr, "[netplay] cannot write %s\n", v);
    }
    s.rx_event = CreateEventA(nullptr, FALSE, FALSE, nullptr);
    { LARGE_INTEGER q; QueryPerformanceCounter(&q);
      s.session = (uint32_t)(q.QuadPart ^ (q.QuadPart >> 32) ^ (GetCurrentProcessId() << 16)) | 1u; }

    note("mode %s, slot P%d, delay %d, local devices %s, %zu scripted press(es)",
         m, s.slot + 1, s.delay, s.localpad ? "on" : "off", s.script.size());

    if (s.mode == Mode::Local) { s.connected = true; return; }

    WSADATA wsa;
    if (WSAStartup(MAKEWORD(2, 2), &wsa) != 0) { note("WSAStartup failed -- netplay off"); s.mode = Mode::Off; return; }
    s.sock = socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP);
    if (s.sock == INVALID_SOCKET) { note("socket() failed -- netplay off"); s.mode = Mode::Off; return; }
    { DWORD tmo = 200; setsockopt(s.sock, SOL_SOCKET, SO_RCVTIMEO, (const char*)&tmo, sizeof tmo); }
    /* No ICMP port-unreachable resets on Windows UDP sockets: a peer that is
     * not up yet must not break our receive loop. */
    { BOOL off = FALSE; DWORD ret = 0;
      WSAIoctl(s.sock, _WSAIOW(IOC_VENDOR, 12) /* SIO_UDP_CONNRESET */, &off, sizeof off, nullptr, 0, &ret, nullptr, nullptr); }
    int port = s.mode == Mode::Host ? 7000 : 0;
    if (const char* v = env("T5_NET_PORT")) port = atoi(v);
    sockaddr_in local{}; local.sin_family = AF_INET; local.sin_port = htons((u_short)port);
    local.sin_addr.s_addr = htonl(INADDR_ANY);
    if (bind(s.sock, (sockaddr*)&local, sizeof local) != 0) {
        note("bind to UDP port %d failed (%d) -- netplay off", port, WSAGetLastError());
        s.mode = Mode::Off; return;
    }
    if (s.mode == Mode::Join) {
        const char* peer = env("T5_NET_PEER");
        if (!peer || !parse_addr(peer, &s.peer)) {
            note("join needs T5_NET_PEER=<host ip>:<port> -- netplay off");
            s.mode = Mode::Off; return;
        }
        s.peer_known = true;
        note("joining %s", peer);
    } else {
        note("hosting on UDP port %d", port);
        const char* peer = env("T5_NET_PEER");
        if (peer && parse_addr(peer, &s.peer)) {
            s.peer_known = true;
            note("calling %s while waiting (lobby punch / relay path)", peer);
        }
    }
    CreateThread(nullptr, 0, rx_thread, nullptr, 0, nullptr);
    atexit(say_bye);
}

/* Block until the handshake is done (frame 0 only). */
void wait_connected()
{
    State& s = S();
    ULONGLONG t0 = GetTickCount64(), last_hello = 0, last_note = t0;
    for (;;) {
        {
            std::lock_guard<std::mutex> lk(s.mu);
            if (s.connected) return;
            ULONGLONG now = GetTickCount64();
            /* The joiner calls the host; a host given T5_NET_PEER (the lobby's
             * punched endpoint or relay) calls out as well, which keeps its NAT
             * mapping open while the other game is still starting. */
            if ((s.mode == Mode::Join || s.peer_known) && now - last_hello >= 100) { send_hello_locked(); last_hello = now; }
            if (now - last_note >= 3000) {
                last_note = now;
                note("waiting for the peer to connect (%llus)...", (now - t0) / 1000);
            }
        }
        WaitForSingleObject(s.rx_event, 50);
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
        if (s.mode == Mode::Local || s.peer_lost) return f;
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
                note("the peer never reached scene change %u -- peer lost", k);
                s.peer_lost = true;
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

void log_extra(uint32_t f, const char* text)
{
    State& s = S();
    if (!s.log) return;
    std::lock_guard<std::mutex> lk(s.log_mu);
    fprintf(s.log, "%u X %s\n", f, text);
}

void begin_frame(uint32_t f, uint64_t state_hash, PadInput out[2])
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
        note("lockstep starts: frame 0, delay %d", s.delay);
    }

    PadInput local = sample_local(f + (uint32_t)s.delay);
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
        for (;;) {
            {
                std::lock_guard<std::mutex> lk(s.mu);
                mine = s.local.in[f % kRing];
                if (s.peer_lost) { theirs = kNeutral; break; }
                if (s.remote.in_tag[f % kRing] == f + 1) { theirs = s.remote.in[f % kRing]; break; }
                ULONGLONG now = GetTickCount64();
                if (now - s.last_send_ms >= 15) send_inputs_locked();   /* resend while stalled */
                if (now - last_note >= 1000) {
                    last_note = now;
                    note("frame %u: waiting for the peer's input (%llus; peer has our inputs up to %u)",
                         f, (now - t0) / 1000, s.peer_ack);
                }
                if (s.timeout_s > 0 && now - t0 >= (ULONGLONG)s.timeout_s * 1000) {
                    note("no input from the peer for %ds -- peer lost, continuing with P%d idle",
                         s.timeout_s, 2 - s.slot);
                    s.peer_lost = true;
                    theirs = kNeutral;
                    break;
                }
            }
            WaitForSingleObject(s.rx_event, 4);
        }
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
    note("rollback mode starts: frame 0, delay %d", s.delay);
}

void rb_sample_local(uint32_t f)
{
    State& s = S();
    if (s.mode == Mode::Off) return;
    PadInput local = sample_local(f + (uint32_t)s.delay);
    std::lock_guard<std::mutex> lk(s.mu);
    const uint32_t t = f + (uint32_t)s.delay;
    for (uint32_t g = s.local_max; g <= t; g++) {   /* hold the sample over any gap; a decided input never changes */
        s.local.in[g % kRing] = local; s.local.in_tag[g % kRing] = g + 1;
    }
    if (t + 1 > s.local_max) s.local_max = t + 1;
    if (s.mode == Mode::Local) {
        /* no peer: the second player is this PC's port 2 / script, confirmed at once */
        PadInput theirs = kNeutral;
        if (s.localpad) device_input(1, &theirs);
        theirs.buttons |= script_mask(s.script2, t) | s.padfile2.poll(t);
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

bool rb_remote(uint32_t f, PadInput* out)
{
    State& s = S();
    std::lock_guard<std::mutex> lk(s.mu);
    if (s.remote.in_tag[f % kRing] != f + 1) return false;
    *out = s.remote.in[f % kRing];
    return true;
}

uint32_t rb_remote_contig()
{
    State& s = S();
    std::lock_guard<std::mutex> lk(s.mu);
    return s.remote_contig;
}

uint32_t rb_wait_remote(uint32_t f, uint32_t ms)
{
    State& s = S();
    const ULONGLONG t0 = GetTickCount64();
    for (;;) {
        {
            std::lock_guard<std::mutex> lk(s.mu);
            if (s.remote_contig > f || s.peer_lost || s.mode == Mode::Local) return s.remote_contig;
            const ULONGLONG now = GetTickCount64();
            if (now - s.last_send_ms >= 15) send_inputs_locked();
            if (now - t0 >= ms) return s.remote_contig;
            if (s.timeout_s > 0 && now - s.last_rx_ms >= (ULONGLONG)s.timeout_s * 1000 && s.last_rx_ms) {
                note("no packet from the peer for %ds -- peer lost, continuing with P%d idle", s.timeout_s, 2 - s.slot);
                s.peer_lost = true;
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

bool rb_peer_lost() { State& s = S(); std::lock_guard<std::mutex> lk(s.mu); return s.peer_lost; }
uint32_t rb_mismatches() { State& s = S(); std::lock_guard<std::mutex> lk(s.mu); return s.mismatches; }
uint32_t rb_peer_ack() { State& s = S(); std::lock_guard<std::mutex> lk(s.mu); return s.peer_ack; }

} // namespace np
