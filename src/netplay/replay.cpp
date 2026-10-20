/*
 * Replays -- see replay.h and docs/REPLAYS.md.
 *
 * File (<T5_REPLAY_DIR>/T5R-<local date>-<time>-<xxxx>.t5replay):
 *   line 1   "T5REPLAY 1"
 *   line 2   one line of JSON: what the launcher lists (date, fighters, result, names, build id)
 *   rest     a zlib stream (Python's zlib reads it) of the binary below -- everything the
 *            game needs to play the session back; the JSON is only a view of it
 *
 * Binary, little-endian:
 *   "T5RP" u32 version (2)
 *   u32 flags (bit 0: rollback), slot, delay, rollback delay (0xFFFFFFFF: unknown)
 *   u32 session seed (T5_NET_SEED), match seed, frames N, hash interval, the last frame the
 *       recording game ran (the inputs reach the input delay past it; format 1 had no such field)
 *   u32 matches, each: u32 start, end, frames, hash frame, desync, flags (bit 0 result,
 *       bit 1 hash, bit 2 complete); i32 p1, p2, b1, b2, m1, m2, stage, rounds, pick,
 *       winner (-1: none), score1, score2; u64 hash; str name1, name2 (u16 length + bytes)
 *   u32 sync points, each: u32 kind, frame, continued at, seed, flags (bit 0 counters);
 *       u64 frame clock; u32 counters[3]
 *   u32 hashes, each: u32 frame, u64 hash
 *   12 columns of N bytes: P1 buttons low, high, lx, ly, rx, ry, then P2 -- each byte XORed
 *       with the frame before (frame 0 with the neutral pad), so held inputs are zero runs
 */
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>

#include <algorithm>
#include <atomic>
#include <cctype>
#include <cstdarg>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <memory>
#include <mutex>
#include <string>
#include <thread>
#include <vector>

#include "replay.h"

unsigned char* rp_zlib_compress(const unsigned char* data, int len, int* out_len);     /* replay_zlib.cpp */
unsigned char* rp_zlib_decompress(const unsigned char* data, int len, int* out_len);

namespace rp {
namespace {

constexpr uint32_t kVersion = 2;   /* 2: the last frame the recording game ran (after the hash interval) */
constexpr char kMagic[] = "T5REPLAY 1\n";

struct Match {
    uint32_t start = 0, end = 0, frames = 0, hash_frame = 0, desync = 0;
    Fight ft;
    bool have_result = false, have_hash = false, complete = false;
    int winner = -1, score[2] = { 0, 0 };
    uint64_t hash = 0;
    std::string reason, started, ended;
};

struct Data {
    int slot = 0, delay = 0, rb_delay = -1;
    bool rollback = false;
    uint32_t session_seed = 0, match_seed = 0, hash_every = 60;
    uint32_t last = 0;            /* the last frame the recording game ran (its inputs go `delay` frames further) */
    std::string build, created;
    std::vector<np::PadInput> in[2];
    std::vector<std::pair<uint32_t, uint64_t>> hashes;
    std::vector<Barrier> bars;
    std::vector<Match> matches;
};

void note(const char* fmt, ...)
{
    char buf[768];
    va_list ap; va_start(ap, fmt); vsnprintf(buf, sizeof buf, fmt, ap); va_end(ap);
    np::note("replay: %s", buf);
}

std::string utc_now()
{
    SYSTEMTIME st; GetSystemTime(&st);
    char b[40];
    snprintf(b, sizeof b, "%04u-%02u-%02uT%02u:%02u:%02uZ", st.wYear, st.wMonth, st.wDay, st.wHour, st.wMinute, st.wSecond);
    return b;
}

/* ---- the binary ------------------------------------------------------------ */
void put32(std::vector<uint8_t>& b, uint32_t v) { for (int i = 0; i < 4; i++) b.push_back((uint8_t)(v >> (8 * i))); }
void put64(std::vector<uint8_t>& b, uint64_t v) { for (int i = 0; i < 8; i++) b.push_back((uint8_t)(v >> (8 * i))); }
void putstr(std::vector<uint8_t>& b, const std::string& s)
{
    const size_t n = std::min<size_t>(s.size(), 64);
    b.push_back((uint8_t)n); b.push_back(0);
    b.insert(b.end(), s.begin(), s.begin() + n);
}

uint8_t col(const np::PadInput& in, int c)
{
    switch (c) {
    case 0: return (uint8_t)(in.buttons & 0xFF);
    case 1: return (uint8_t)(in.buttons >> 8);
    case 2: return in.lx; case 3: return in.ly; case 4: return in.rx; default: return in.ry;
    }
}
void set_col(np::PadInput& in, int c, uint8_t v)
{
    switch (c) {
    case 0: in.buttons = (uint16_t)((in.buttons & 0xFF00) | v); break;
    case 1: in.buttons = (uint16_t)((in.buttons & 0x00FF) | (v << 8)); break;
    case 2: in.lx = v; break; case 3: in.ly = v; break; case 4: in.rx = v; break; default: in.ry = v; break;
    }
}

void put_match(std::vector<uint8_t>& b, const Match& m)
{
    put32(b, m.start); put32(b, m.end); put32(b, m.frames); put32(b, m.hash_frame); put32(b, m.desync);
    put32(b, (m.have_result ? 1u : 0u) | (m.have_hash ? 2u : 0u) | (m.complete ? 4u : 0u));
    for (int v : { m.ft.chr[0], m.ft.chr[1], m.ft.btn[0], m.ft.btn[1], m.ft.model[0], m.ft.model[1], m.ft.stage,
                   m.ft.rounds, m.ft.pick, m.winner, m.score[0], m.score[1] })
        put32(b, (uint32_t)v);
    put64(b, m.hash);
    putstr(b, m.ft.names[0]); putstr(b, m.ft.names[1]);
}

void put_barrier(std::vector<uint8_t>& b, const Barrier& x)
{
    put32(b, x.kind); put32(b, x.f); put32(b, x.nf); put32(b, x.seed); put32(b, x.has_state ? 1u : 0u);
    put64(b, x.clock); put32(b, x.c[0]); put32(b, x.c[1]); put32(b, x.c[2]);
}

/* the inputs of frame f for player p: Data's vectors (a loaded file) or the
 * recorder's chunks (Store below) */
struct InputSource {
    virtual np::PadInput get(int p, uint32_t f) const = 0;
    virtual uint32_t frames() const = 0;
};
struct DataInputs : InputSource {
    const Data& d;
    explicit DataInputs(const Data& x) : d(x) {}
    np::PadInput get(int p, uint32_t f) const override { return d.in[p][f]; }
    uint32_t frames() const override { return (uint32_t)std::min(d.in[0].size(), d.in[1].size()); }
};

std::vector<uint8_t> to_binary(const Data& d, const InputSource& src)
{
    std::vector<uint8_t> b;
    b.insert(b.end(), { 'T', '5', 'R', 'P' });
    put32(b, kVersion);
    put32(b, d.rollback ? 1u : 0u);
    put32(b, (uint32_t)d.slot); put32(b, (uint32_t)d.delay); put32(b, (uint32_t)d.rb_delay);
    put32(b, d.session_seed); put32(b, d.match_seed);
    const uint32_t n = src.frames();
    put32(b, n); put32(b, d.hash_every); put32(b, d.last);
    put32(b, (uint32_t)d.matches.size());
    for (const Match& m : d.matches) put_match(b, m);
    put32(b, (uint32_t)d.bars.size());
    for (const Barrier& x : d.bars) put_barrier(b, x);
    put32(b, (uint32_t)d.hashes.size());
    for (const auto& h : d.hashes) { put32(b, h.first); put64(b, h.second); }
    for (int p = 0; p < 2; p++)
        for (int c = 0; c < 6; c++) {
            uint8_t prev = col(np::kNeutral, c);
            for (uint32_t f = 0; f < n; f++) {
                const uint8_t v = col(src.get(p, f), c);
                b.push_back((uint8_t)(v ^ prev));
                prev = v;
            }
        }
    return b;
}

struct Reader {
    const uint8_t* p; size_t n, i = 0; bool bad = false;
    uint32_t u32() { if (i + 4 > n) { bad = true; return 0; } uint32_t v = 0; for (int k = 0; k < 4; k++) v |= (uint32_t)p[i + k] << (8 * k); i += 4; return v; }
    uint64_t u64() { const uint64_t lo = u32(); return lo | ((uint64_t)u32() << 32); }
    std::string str()
    {
        if (i + 2 > n) { bad = true; return {}; }
        const size_t len = p[i] | (p[i + 1] << 8); i += 2;
        if (i + len > n) { bad = true; return {}; }
        std::string s((const char*)p + i, len); i += len;
        return s;
    }
};

Match get_match(Reader& r)
{
    Match m;
    m.start = r.u32(); m.end = r.u32(); m.frames = r.u32(); m.hash_frame = r.u32(); m.desync = r.u32();
    const uint32_t fl = r.u32();
    m.have_result = fl & 1; m.have_hash = (fl & 2) != 0; m.complete = (fl & 4) != 0;
    int* v[] = { &m.ft.chr[0], &m.ft.chr[1], &m.ft.btn[0], &m.ft.btn[1], &m.ft.model[0], &m.ft.model[1], &m.ft.stage,
                 &m.ft.rounds, &m.ft.pick, &m.winner, &m.score[0], &m.score[1] };
    for (int* x : v) *x = (int)r.u32();
    m.hash = r.u64();
    m.ft.names[0] = r.str(); m.ft.names[1] = r.str();
    return m;
}

Barrier get_barrier(Reader& r)
{
    Barrier x;
    x.kind = r.u32(); x.f = r.u32(); x.nf = r.u32(); x.seed = r.u32(); x.has_state = (r.u32() & 1) != 0;
    x.clock = r.u64(); x.c[0] = r.u32(); x.c[1] = r.u32(); x.c[2] = r.u32();
    return x;
}

bool from_binary(const uint8_t* p, size_t n, Data& d, std::string* why)
{
    Reader r{ p, n };
    if (n < 8 || memcmp(p, "T5RP", 4)) { *why = "not a replay payload"; return false; }
    r.i = 4;
    const uint32_t ver = r.u32();
    if (ver < 1 || ver > kVersion) { *why = "replay format " + std::to_string(ver) + " (this game reads 1 to " + std::to_string(kVersion) + ")"; return false; }
    d.rollback = (r.u32() & 1) != 0;
    d.slot = (int)r.u32(); d.delay = (int)r.u32(); d.rb_delay = (int)r.u32();
    d.session_seed = r.u32(); d.match_seed = r.u32();
    const uint32_t frames = r.u32(); d.hash_every = r.u32();
    if (ver >= 2) d.last = r.u32();
    else {   /* format 1 (development files) had no last frame: the inputs reach the input delay past it */
        const int dl = d.rollback && d.rb_delay >= 0 ? d.rb_delay : d.delay;
        d.last = frames > (uint32_t)dl + 1 ? frames - (uint32_t)dl - 1 : 0;   /* (raised to the last match's end below) */
    }
    const uint32_t nm = r.u32();
    if (nm > 10000) { *why = "broken match table"; return false; }
    for (uint32_t k = 0; k < nm && !r.bad; k++) d.matches.push_back(get_match(r));
    const uint32_t nb = r.u32();
    if (nb > 100000) { *why = "broken sync point table"; return false; }
    for (uint32_t k = 0; k < nb && !r.bad; k++) d.bars.push_back(get_barrier(r));
    const uint32_t nh = r.u32();
    if (nh > 10000000) { *why = "broken hash table"; return false; }
    for (uint32_t k = 0; k < nh && !r.bad; k++) { const uint32_t f = r.u32(); d.hashes.push_back({ f, r.u64() }); }
    if (r.bad || r.i + (size_t)frames * 12 > n) { *why = "the file is cut short"; return false; }
    for (int pl = 0; pl < 2; pl++) {
        d.in[pl].assign(frames, np::kNeutral);
        for (int c = 0; c < 6; c++) {
            uint8_t prev = col(np::kNeutral, c);
            for (uint32_t f = 0; f < frames; f++) {
                prev = (uint8_t)(prev ^ p[r.i++]);
                set_col(d.in[pl][f], c, prev);
            }
        }
    }
    std::sort(d.hashes.begin(), d.hashes.end());
    /* never before a recorded match's end (format 1: the estimate, its rollback delay may be unknown;
     * a file written at the very frame of a result, before that frame was counted) */
    for (const Match& m : d.matches) if (m.have_result && m.end > d.last && m.end < frames) d.last = m.end;
    return true;
}

/* ---- the JSON line (what the launcher lists) ---------------------------------- */
std::string jstr(const std::string& s)
{
    std::string o = "\"";
    for (unsigned char c : s) {
        if (c == '"' || c == '\\') { o += '\\'; o += (char)c; }
        else if (c < 0x20) { char b[8]; snprintf(b, sizeof b, "\\u%04x", c); o += b; }
        else o += (char)c;
    }
    return o + "\"";
}

std::string to_json(const Data& d, bool names, uint32_t frames)
{
    char b[512];
    std::string j = "{";
    snprintf(b, sizeof b, "\"format\": %u, \"build\": %s, \"created\": %s, \"mode\": \"%s\", \"slot\": %d, \"delay\": %d, "
                          "\"rb_delay\": %d, \"seed\": %u, \"match_seed\": %u, \"frames\": %zu, \"last_frame\": %u, \"hash_every\": %u, "
                          "\"sync_points\": %zu, \"hashes\": %zu, \"matches\": [",
             kVersion, jstr(d.build).c_str(), jstr(d.created).c_str(), d.rollback ? "rollback" : "lockstep", d.slot, d.delay,
             d.rb_delay, d.session_seed, d.match_seed, (size_t)frames, d.last, d.hash_every,
             d.bars.size(), d.hashes.size());
    j += b;
    for (size_t k = 0; k < d.matches.size(); k++) {
        const Match& m = d.matches[k];
        snprintf(b, sizeof b, "%s{\"n\": %zu, \"start\": %u, \"end\": %u, \"p1\": %d, \"p2\": %d, \"b1\": %d, \"b2\": %d, "
                              "\"m1\": %d, \"m2\": %d, \"stage\": %d, \"rounds\": %d, \"pick\": %d, \"winner\": %s, "
                              "\"score\": [%d, %d], \"frames\": %u, \"desync\": %u, \"complete\": %s",
                 k ? ", " : "", k + 1, m.start, m.end, m.ft.chr[0], m.ft.chr[1], m.ft.btn[0], m.ft.btn[1], m.ft.model[0],
                 m.ft.model[1], m.ft.stage, m.ft.rounds, m.ft.pick,
                 !m.have_result || m.winner < 0 ? "null" : m.winner == 0 ? "0" : "1", m.score[0], m.score[1], m.frames, m.desync,
                 m.complete ? "true" : "false");
        j += b;
        if (m.have_hash) { snprintf(b, sizeof b, ", \"hash\": \"%016llx\"", (unsigned long long)m.hash); j += b; }
        if (!m.reason.empty()) j += ", \"reason\": " + jstr(m.reason);
        j += ", \"started\": " + jstr(m.started) + ", \"ended\": " + (m.ended.empty() ? std::string("null") : jstr(m.ended));
        if (names && (!m.ft.names[0].empty() || !m.ft.names[1].empty()))
            j += ", \"names\": [" + jstr(m.ft.names[0]) + ", " + jstr(m.ft.names[1]) + "]";
        j += "}";
    }
    return j + "]}";
}

/* ---- recording -------------------------------------------------------------
 * The inputs go into chunks that never move once allocated: the main thread only
 * appends (and publishes the frame count after the frame is written), the writer
 * thread reads frames below the published count without a lock. Everything else
 * of the session (matches, sync points, hashes) is small and taken under the
 * mutex. A write is a request to the one writer thread (an event); only the
 * session's end writes on the calling thread. */
constexpr uint32_t kChunk = 4096, kMaxChunks = 4096;   /* up to 16.7 M frames: 77 hours */
struct Chunk { np::PadInput in[2][kChunk]; };
struct Store : InputSource {
    Data d;                                        /* everything but the inputs (d.in stays empty) */
    std::vector<std::unique_ptr<Chunk>> chunks;    /* reserved up front: the pointers never move */
    std::atomic<uint32_t> n{ 0 };                  /* frames recorded */
    std::atomic<uint32_t> last{ 0 };               /* the last live frame this game ran (rec_frame) */
    std::string path;
    bool names = true;
    /* the live stream (T5_REPLAY_LIVE): records appended by the writer thread */
    std::string live_path;
    HANDLE live_h = INVALID_HANDLE_VALUE;          /* g_live_mu */
    uint32_t live_n = 0, live_last = 0;            /* g_live_mu: inputs / last frame written */
    np::PadInput live_prev[2] = { np::kNeutral, np::kNeutral };
    uint64_t live_bytes = 0;
    bool live_started = false;                     /* mu: the SESSION record is out (the handshake, or rec_start) */
    std::vector<uint8_t> live_pend;                /* mu: records waiting for the writer */
    Store() { chunks.reserve(kMaxChunks); }
    np::PadInput get(int p, uint32_t f) const override { return chunks[f / kChunk]->in[p][f % kChunk]; }
    uint32_t frames() const override { return n.load(std::memory_order_acquire); }
};
/* a store's frame count frozen for one write */
struct Frozen : InputSource {
    const Store& st; uint32_t n;
    Frozen(const Store& s, uint32_t k) : st(s), n(k) {}
    np::PadInput get(int p, uint32_t f) const override { return st.get(p, f); }
    uint32_t frames() const override { return n; }
};

struct Rec {
    std::mutex mu;                       /* the store's Data */
    std::shared_ptr<Store> cur;          /* this session's (kept after its end until the next one begins) */
    std::atomic<Store*> live{ nullptr }; /* cur while recording: rec_input's lock-free way in */
    bool on = false, have_fight = false;
    Fight fight;
    uint32_t flush_at = UINT32_MAX, next_periodic = 0;
    HANDLE ev = nullptr;                 /* the writer thread's wake-up */
    std::shared_ptr<Store> want;         /* the store it writes next */
};
Rec& R() { static Rec r; return r; }

/* What recording costs the frame (main thread): the time inside the rec_* calls of
 * one live frame, summed up and logged at the session's end. */
struct Cost { LONGLONG acc = 0, sum = 0, max = 0, qf = 0; uint32_t frames = 0; } g_cost;
struct Timed {
    LARGE_INTEGER t0;
    Timed() { QueryPerformanceCounter(&t0); }
    ~Timed() { LARGE_INTEGER t1; QueryPerformanceCounter(&t1); g_cost.acc += t1.QuadPart - t0.QuadPart; }
};
void cost_note();
void cost_frame()
{
    g_cost.sum += g_cost.acc;
    if (g_cost.acc > g_cost.max) g_cost.max = g_cost.acc;
    g_cost.acc = 0;
    if (++g_cost.frames >= 3600) cost_note();   /* once a minute, and at the session's end */
}
void cost_note()
{
    if (!g_cost.frames) return;
    if (!g_cost.qf) { LARGE_INTEGER f; QueryPerformanceFrequency(&f); g_cost.qf = f.QuadPart; }
    note("recording cost the frame %.2f us on average, %.1f us at most, over %u frames", 1e6 * (double)g_cost.sum / (double)g_cost.frames / (double)g_cost.qf,
         1e6 * (double)g_cost.max / (double)g_cost.qf, g_cost.frames);
    g_cost = Cost();
}

std::mutex g_write_mu;          /* one write at a time */
std::atomic<uint32_t> g_seq{ 0 };
uint32_t g_written_seq = 0;     /* an older snapshot never overwrites a newer one */

/* Write the store's file: its Data copied under the mutex (small), the inputs up
 * to the frame count read from the chunks. */
void write_store(const std::shared_ptr<Store>& st, uint32_t seq)
{
    Rec& r = R();
    Data d;
    uint32_t n;
    {
        std::lock_guard<std::mutex> lk(r.mu);
        d = st->d;
        n = st->frames();
        d.last = st->last.load(std::memory_order_relaxed);
    }
    if (d.matches.empty() || st->path.empty()) return;
    std::lock_guard<std::mutex> wk(g_write_mu);
    if (seq < g_written_seq) return;
    g_written_seq = seq;
    LARGE_INTEGER q0, q1, qf; QueryPerformanceCounter(&q0);
    const std::vector<uint8_t> bin = to_binary(d, Frozen(*st, n));
    int zlen = 0;
    unsigned char* z = rp_zlib_compress(bin.data(), (int)bin.size(), &zlen);
    if (!z) { note("cannot compress %s", st->path.c_str()); return; }
    if (!st->names) for (Match& m : d.matches) m.ft.names[0].clear(), m.ft.names[1].clear();
    const std::string json = to_json(d, st->names, n) + "\n";
    const std::string tmp = st->path + ".tmp";
    bool ok = false;
    if (FILE* fp = fopen(tmp.c_str(), "wb")) {
        ok = fwrite(kMagic, 1, sizeof kMagic - 1, fp) == sizeof kMagic - 1 && fwrite(json.data(), 1, json.size(), fp) == json.size() &&
             fwrite(z, 1, (size_t)zlen, fp) == (size_t)zlen;
        ok = (fclose(fp) == 0) && ok;
    }
    free(z);
    if (ok) for (int i = 0; i < 50 && !MoveFileExA(tmp.c_str(), st->path.c_str(), MOVEFILE_REPLACE_EXISTING); i++) Sleep(2);
    QueryPerformanceCounter(&q1); QueryPerformanceFrequency(&qf);
    note("%s %s: %zu matches, %u frames, %zu bytes (inputs and hashes %zu -> %d compressed), %.1f ms", ok ? "written" : "COULD NOT WRITE",
         st->path.c_str(), d.matches.size(), n, (size_t)(sizeof kMagic - 1) + json.size() + (size_t)zlen, bin.size(), zlen,
         1000.0 * (double)(q1.QuadPart - q0.QuadPart) / (double)qf.QuadPart);
}

/* ---- the live stream ---------------------------------------------------------
 * <T5_REPLAY_LIVE> (a spectator's game reads it while it grows, docs/SPECTATE.md):
 *   "T5LIVE 1", newline, then records: u8 type, u32 payload length, payload (little-endian)
 *   SESSION  u32 version 1, flags (bit 0 rollback), slot, delay, rollback delay, session seed,
 *            match seed, hash interval; str build, created (again when the rollback delay is
 *            known: the latest counts)
 *   INPUTS   u32 first frame, count; 12 columns of `count` bytes (P1 buttons low, high, lx, ly,
 *            rx, ry, then P2), each byte XORed with the frame before (the last frame of the
 *            record before; neutral before frame 0)
 *   HASH     u32 frame, u64 hash          (a frame sent again replaces it)
 *   BARRIER  a sync point, as in the replay binary
 *   MATCH    u32 index (0-based), the match as in the replay binary (sent again with its result)
 *   LAST     u32 the last frame the game ran, u64 the wall clock then (ms since 1970)
 *   END      str why -- the session is over
 * Only the writer thread appends (every 200 ms), and the session's end on its own thread;
 * the frame only queues the small records under the mutex it takes for them anyway. */
constexpr char kLiveMagic[] = "T5LIVE 1\n";
enum LiveRec : uint8_t { L_SESSION = 1, L_INPUTS = 2, L_HASH = 3, L_BARRIER = 4, L_MATCH = 5, L_LAST = 6, L_END = 7 };
constexpr uint32_t kLiveMaxRecord = 1u << 24;
std::mutex g_live_mu;

void live_rec(std::vector<uint8_t>& out, uint8_t type, const std::vector<uint8_t>& payload)
{
    out.push_back(type);
    put32(out, (uint32_t)payload.size());
    out.insert(out.end(), payload.begin(), payload.end());
}

std::vector<uint8_t> session_payload(const Data& d)
{
    std::vector<uint8_t> b;
    put32(b, 1); put32(b, d.rollback ? 1u : 0u);
    put32(b, (uint32_t)d.slot); put32(b, (uint32_t)d.delay); put32(b, (uint32_t)d.rb_delay);
    put32(b, d.session_seed); put32(b, d.match_seed); put32(b, d.hash_every);
    putstr(b, d.build); putstr(b, d.created);
    return b;
}

/* caller holds mu */
void live_queue_locked(Store& st, uint8_t type, const std::vector<uint8_t>& payload)
{
    if (st.live_path.empty() || !st.live_started) return;
    live_rec(st.live_pend, type, payload);
}

uint64_t unix_ms()
{
    FILETIME ft; GetSystemTimeAsFileTime(&ft);
    const uint64_t t = ((uint64_t)ft.dwHighDateTime << 32) | ft.dwLowDateTime;
    return t / 10000 - 11644473600000ull;
}

/* Append what is new to the live file: the queued records, the inputs since the last
 * append, the last frame (and END at the session's end). */
void live_append(const std::shared_ptr<Store>& st, const char* end_why)
{
    Rec& r = R();
    std::lock_guard<std::mutex> lk(g_live_mu);
    if (st->live_h == INVALID_HANDLE_VALUE) return;
    std::vector<uint8_t> out;
    uint32_t n, last;
    {
        std::lock_guard<std::mutex> rk(r.mu);
        if (!st->live_started && !end_why) return;
        out.swap(st->live_pend);
        n = st->frames();
        last = st->last.load(std::memory_order_relaxed);
    }
    while (n > st->live_n) {
        const uint32_t first = st->live_n, cnt = std::min<uint32_t>(n - first, 3600);   /* a minute per record at most */
        std::vector<uint8_t> b;
        put32(b, first); put32(b, cnt);
        for (int p = 0; p < 2; p++)
            for (int c = 0; c < 6; c++) {
                uint8_t prev = col(st->live_prev[p], c);
                for (uint32_t f = first; f < first + cnt; f++) {
                    const uint8_t v = col(st->get(p, f), c);
                    b.push_back((uint8_t)(v ^ prev));
                    prev = v;
                }
            }
        for (int p = 0; p < 2; p++) st->live_prev[p] = st->get(p, first + cnt - 1);
        st->live_n = first + cnt;
        live_rec(out, L_INPUTS, b);
    }
    if (last != st->live_last || end_why) {
        std::vector<uint8_t> b;
        put32(b, last); put64(b, unix_ms());
        live_rec(out, L_LAST, b);
        st->live_last = last;
    }
    if (end_why) { std::vector<uint8_t> b; putstr(b, end_why); live_rec(out, L_END, b); }
    if (!out.empty()) {
        DWORD wr = 0;
        if (!WriteFile(st->live_h, out.data(), (DWORD)out.size(), &wr, nullptr) || wr != out.size()) {
            note("live stream %s: cannot write (error %lu) -- no more live data", st->live_path.c_str(), GetLastError());
            CloseHandle(st->live_h);
            st->live_h = INVALID_HANDLE_VALUE;
            return;
        }
        st->live_bytes += out.size();
    }
    if (end_why) {
        note("live stream %s ended (%s): %llu bytes, %u frames", st->live_path.c_str(), end_why, (unsigned long long)st->live_bytes,
             st->live_n);
        CloseHandle(st->live_h);
        st->live_h = INVALID_HANDLE_VALUE;
    }
}

DWORD WINAPI writer_thread(LPVOID)
{
    Rec& r = R();
    for (;;) {
        bool live;
        {
            std::lock_guard<std::mutex> lk(r.mu);
            live = r.on && r.cur && !r.cur->live_path.empty();
        }
        WaitForSingleObject(r.ev, live ? 200 : INFINITE);
        std::shared_ptr<Store> st, lst;
        uint32_t seq;
        {
            std::lock_guard<std::mutex> lk(r.mu);
            st.swap(r.want);
            seq = ++g_seq;
            if (r.on && r.cur && !r.cur->live_path.empty()) lst = r.cur;
        }
        if (lst) live_append(lst, nullptr);
        if (st) write_store(st, seq);
    }
}

void ensure_writer_locked(Rec& r)
{
    if (r.ev) return;
    r.ev = CreateEventA(nullptr, FALSE, FALSE, nullptr);
    if (HANDLE th = CreateThread(nullptr, 0, writer_thread, nullptr, 0, nullptr)) {
        SetThreadPriority(th, THREAD_PRIORITY_BELOW_NORMAL);
        CloseHandle(th);
    }
}

/* ask the writer thread for the file (the frame never waits for the disk); caller holds mu */
void request_write_locked(Rec& r)
{
    if (!r.on || !r.cur || r.cur->d.matches.empty()) return;
    r.want = r.cur;
    ensure_writer_locked(r);
    SetEvent(r.ev);
}

const char* env(const char* k) { const char* v = getenv(k); return v && *v ? v : nullptr; }

std::string hexq(bool have, uint64_t h)   /* "\"0123456789abcdef\"" or null */
{
    if (!have) return "null";
    char b[24];
    snprintf(b, sizeof b, "\"%016llx\"", (unsigned long long)h);
    return b;
}

/* ---- playback ---------------------------------------------------------------- */
struct MatchCheck {
    bool seen = false, result = false, same = false, settled = false;   /* settled: compared with a recorded result */
    int winner = -1, score[2] = { 0, 0 }; uint64_t hash = 0; bool have_hash = false;
};
struct Play {
    bool on = false;
    std::string error;
    Data d;
    std::string path, result_path;
    int64_t offset = 0;
    uint32_t compared = 0, mismatched = 0;
    int64_t first_bad = -1;
    uint32_t bar_seen = 0, bar_bad = 0, seed_bad = 0;
    uint32_t begun = 0, target = 0, tail = 360;
    uint32_t end_at = UINT32_MAX, last_p = 0;
    std::vector<MatchCheck> mc;
    bool finished = false;
    std::string end_why;
    uint32_t model_bad = 0;
    /* a live stream (spectating): the file grows while it plays */
    bool live = false, live_end = false, have_session = false, buffering = true;
    bool session_new = false;                  /* the SESSION came after the netplay core was set up: tell it */
    HANDLE lh = INVALID_HANDLE_VALUE;
    std::vector<uint8_t> lbuf;                 /* bytes read, not yet a whole record */
    np::PadInput lprev[2] = { np::kNeutral, np::kNeutral };
    uint64_t lbytes = 0;
    std::string live_why;                      /* the END record's reason */
    uint32_t buffer = 120, poll_tick = 0, stalls = 0, live_bad = 0;
    double stall_s = 0;
    ULONGLONG grew_ms = 0;                     /* when the file last grew */
    uint32_t timeout_s = 300;                  /* (between matches nothing comes while the players decide) */
    std::vector<std::pair<uint32_t, uint64_t>> pend_hash;    /* the playback's hashes whose recorded one has not come yet */
    std::vector<std::pair<uint32_t, uint64_t>> clock;        /* LAST records: (frame, wall clock ms), the last few */
    double delay_sum = 0, delay_max = 0; uint32_t delay_n = 0; double delay_now = -1;
    std::string status_path;
    ULONGLONG status_ms = 0;
    /* the last frame to play: the last one the recording game ran (its inputs reach `delay` frames further);
     * a live stream has none until it ends */
    uint32_t end_frame() const
    {
        if (live && !live_end) return UINT32_MAX;
        const uint32_t n = (uint32_t)d.in[0].size();
        return d.last && d.last < n ? d.last : (n ? n - 1 : 0);
    }
};
Play& P() { static Play p; return p; }

/* ---- the live stream, read while it grows (spectating) ------------------------- */
void settle_match(Play& p, uint32_t k)   /* k: 0-based; a result the playback has, against the recorded one once it is there */
{
    if (k >= p.mc.size() || k >= p.d.matches.size()) return;
    MatchCheck& c = p.mc[k];
    const Match& m = p.d.matches[k];
    if (!c.result || c.settled || !m.have_result) return;
    c.settled = true;
    c.same = m.complete && c.winner == m.winner && c.score[0] == m.score[0] && c.score[1] == m.score[1] &&
             (!m.have_hash || (c.have_hash && c.hash == m.hash));
    note("match %u: winner %s, %d-%d, hash %016llx -- recorded: winner %s, %d-%d, hash %016llx: %s", k + 1,
         c.winner < 0 ? "none" : c.winner == 0 ? "P1" : "P2", c.score[0], c.score[1], (unsigned long long)c.hash,
         m.winner < 0 ? "none" : m.winner == 0 ? "P1" : "P2", m.score[0], m.score[1], (unsigned long long)m.hash,
         c.same ? "THE SAME" : "DIFFERENT");
}

void compare_hash(Play& p, uint32_t r, uint64_t h, uint64_t rec)
{
    p.compared++;
    if (rec == h) return;
    p.mismatched++;
    if (p.first_bad < 0 || (int64_t)r < p.first_bad) p.first_bad = r;
    if (p.mismatched <= 10)
        note("HASH MISMATCH at recorded frame %u: %016llx, recorded %016llx", r, (unsigned long long)h, (unsigned long long)rec);
}

/* one whole record of the live stream */
bool live_record(Play& p, uint8_t type, const uint8_t* b, uint32_t n)
{
    Reader r{ b, n };
    Data& d = p.d;
    switch (type) {
    case L_SESSION: {
        if (r.u32() != 1) return false;
        const bool rb = (r.u32() & 1) != 0;
        const int slot = (int)r.u32(), delay = (int)r.u32(), rb_delay = (int)r.u32();
        const uint32_t sseed = r.u32(), mseed = r.u32(), every = r.u32();
        if (r.bad) return false;
        if (!p.have_session && p.on) p.session_new = true;
        if (p.have_session && (rb != d.rollback || slot != d.slot || delay != d.delay || sseed != d.session_seed ||
                               mseed != d.match_seed)) {
            /* the playback runs with what the first SESSION said (the handshake's): the players' games
             * changed it later (a reconnect before frame 0) -- this playback cannot follow */
            p.model_bad++;
            note("live stream: the session changed after the playback began (%s, delay %d, seeds %08X/%08X -> %s, delay %d, "
                 "seeds %08X/%08X)", d.rollback ? "rollback" : "lockstep", d.delay, d.session_seed, d.match_seed,
                 rb ? "rollback" : "lockstep", delay, sseed, mseed);
        }
        d.rollback = rb; d.slot = slot; d.delay = delay; d.rb_delay = rb_delay;
        d.session_seed = sseed; d.match_seed = mseed; d.hash_every = every ? every : 60;
        d.build = r.str(); d.created = r.str();
        p.have_session = true;
        break;
    }
    case L_INPUTS: {
        const uint32_t first = r.u32(), cnt = r.u32();
        if (r.bad || first != d.in[0].size() || (size_t)cnt * 12 != n - 8) return false;
        const uint8_t* q = b + 8;
        for (int pl = 0; pl < 2; pl++) {
            d.in[pl].resize((size_t)first + cnt, np::kNeutral);
            for (int c = 0; c < 6; c++) {
                uint8_t prev = col(p.lprev[pl], c);
                for (uint32_t f = 0; f < cnt; f++) {
                    prev = (uint8_t)(prev ^ *q++);
                    set_col(d.in[pl][first + f], c, prev);
                }
            }
            if (cnt) p.lprev[pl] = d.in[pl][first + cnt - 1];
        }
        break;
    }
    case L_HASH: {
        const uint32_t f = r.u32(); const uint64_t h = r.u64();
        auto& hs = d.hashes;
        if (hs.empty() || hs.back().first < f) hs.push_back({ f, h });
        else {
            auto it = std::lower_bound(hs.begin(), hs.end(), std::make_pair(f, (uint64_t)0));
            if (it != hs.end() && it->first == f) it->second = h;
            else hs.insert(it, { f, h });
        }
        break;
    }
    case L_BARRIER: d.bars.push_back(get_barrier(r)); break;
    case L_MATCH: {
        const uint32_t k = r.u32();
        Match m = get_match(r);
        if (r.bad || k > d.matches.size()) return false;
        if (k == d.matches.size()) d.matches.push_back(m); else d.matches[k] = m;
        if (p.mc.size() < d.matches.size()) p.mc.resize(d.matches.size());
        settle_match(p, k);
        break;
    }
    case L_LAST: {
        const uint32_t f = r.u32(); const uint64_t ms = r.u64();
        if (f > d.last) d.last = f;
        p.clock.push_back({ f, ms });
        if (p.clock.size() > 64) p.clock.erase(p.clock.begin(), p.clock.begin() + 32);
        break;
    }
    case L_END: p.live_end = true; p.live_why = r.str(); break;
    default: break;   /* (a newer writer's record: skipped) */
    }
    return !r.bad;
}

/* read what the file got since the last call; true if it grew */
bool live_poll(Play& p)
{
    if (p.lh == INVALID_HANDLE_VALUE) return false;
    uint8_t buf[65536];
    bool grew = false;
    for (;;) {
        DWORD got = 0;
        if (!ReadFile(p.lh, buf, sizeof buf, &got, nullptr) || got == 0) break;
        p.lbuf.insert(p.lbuf.end(), buf, buf + got);
        p.lbytes += got;
        grew = true;
    }
    if (!grew) return false;
    p.grew_ms = GetTickCount64();
    size_t i = 0;
    if (p.lbytes == p.lbuf.size()) {   /* the start of the file: the magic */
        const size_t ml = sizeof kLiveMagic - 1;
        if (p.lbuf.size() < ml) return true;
        if (memcmp(p.lbuf.data(), kLiveMagic, ml)) { p.live_bad++; p.live_end = true; p.live_why = "not a live stream"; return true; }
        i = ml;
    }
    while (p.lbuf.size() - i >= 5) {
        const uint8_t type = p.lbuf[i];
        uint32_t len = 0;
        for (int k = 0; k < 4; k++) len |= (uint32_t)p.lbuf[i + 1 + k] << (8 * k);
        if (len > kLiveMaxRecord) { p.live_bad++; p.live_end = true; p.live_why = "damaged live data"; break; }
        if (p.lbuf.size() - i - 5 < len) break;
        if (!live_record(p, type, p.lbuf.data() + i + 5, len) && p.live_bad++ < 5)
            note("live stream: record type %u (%u bytes) does not fit -- skipped", type, len);
        i += 5 + (size_t)len;
    }
    p.lbuf.erase(p.lbuf.begin(), p.lbuf.begin() + (ptrdiff_t)i);
    /* the hashes the playback computed before their recorded ones came */
    if (!p.pend_hash.empty()) {
        const auto& hs = p.d.hashes;
        size_t w = 0;
        for (const auto& x : p.pend_hash) {
            auto it = std::lower_bound(hs.begin(), hs.end(), std::make_pair(x.first, (uint64_t)0));
            if (it != hs.end() && it->first == x.first) compare_hash(p, x.first, x.second, it->second);
            else p.pend_hash[w++] = x;
        }
        p.pend_hash.resize(w);
    }
    return true;
}

/* the wall-clock delay behind the live game at recorded frame r (seconds; -1: unknown) */
double live_delay(const Play& p, int64_t r)
{
    const std::pair<uint32_t, uint64_t>* best = nullptr;
    for (const auto& c : p.clock) if ((int64_t)c.first <= r && (!best || c.first > best->first)) best = &c;
    if (!best) return -1;
    const double live_ms = (double)best->second + (double)(r - best->first) * (1000.0 / 59.94);
    return ((double)unix_ms() - live_ms) / 1000.0;
}

void write_status(Play& p, uint32_t pf, bool force)
{
    if (p.status_path.empty()) return;
    const ULONGLONG now = GetTickCount64();
    if (!force && now - p.status_ms < 1000) return;
    p.status_ms = now;
    char b[512];
    snprintf(b, sizeof b, "{\"frame\": %u, \"received\": %zu, \"match\": %u, \"matches\": %zu, \"delay\": %.1f, \"buffering\": %s, "
                          "\"ended\": %s, \"hashes_compared\": %u, \"hash_mismatches\": %u}",
             pf, p.d.in[0].size(), p.begun, p.d.matches.size(), p.delay_now, p.buffering ? "true" : "false",
             p.live_end ? "true" : "false", p.compared, p.mismatched);
    const std::string tmp = p.status_path + ".tmp";
    if (FILE* fp = fopen(tmp.c_str(), "wb")) {
        fputs(b, fp);
        fclose(fp);
        MoveFileExA(tmp.c_str(), p.status_path.c_str(), MOVEFILE_REPLACE_EXISTING);
    }
}

/* wait (polling the file) until `ok` holds, the stream ends, the viewer quits or nothing came for timeout_s */
template <class Ok, class Quit>
bool live_block(Play& p, Ok ok, Quit quit, const char* what)
{
    if (ok() || p.live_end) return true;
    LARGE_INTEGER t0, t1, qf; QueryPerformanceCounter(&t0); QueryPerformanceFrequency(&qf);
    if (!p.grew_ms) p.grew_ms = GetTickCount64();
    p.stalls++;
    bool told = false;
    for (;;) {
        live_poll(p);
        if (ok() || p.live_end) break;
        if (quit && quit()) return false;
        if (GetTickCount64() - p.grew_ms > (ULONGLONG)p.timeout_s * 1000) {
            p.live_end = true;
            p.live_why = "the live data stopped coming";
            note("live stream: nothing new for %u s -- the end", p.timeout_s);
            break;
        }
        if (!told && p.stalls <= 20) { note("live stream: waiting for %s", what); told = true; }
        Sleep(10);
    }
    QueryPerformanceCounter(&t1);
    const double s = (double)(t1.QuadPart - t0.QuadPart) / (double)qf.QuadPart;
    p.stall_s += s;
    if (told) note("live stream: went on after %.2f s", s);
    return true;
}

} // namespace

/* ======================================================================= recording */
bool recording() { return R().on; }

namespace {
/* the session's newest match to the live stream (caller holds mu) */
void live_match_locked(Rec& r)
{
    Store& st = *r.cur;
    if (st.live_path.empty() || st.d.matches.empty()) return;
    std::vector<uint8_t> b;
    put32(b, (uint32_t)(st.d.matches.size() - 1));
    Match m = st.d.matches.back();
    if (!st.names) m.ft.names[0].clear(), m.ft.names[1].clear();
    put_match(b, m);
    live_queue_locked(st, L_MATCH, b);
}
} // namespace
uint32_t hash_every()
{
    Store* st = R().live.load(std::memory_order_acquire);
    return st && st->d.hash_every ? st->d.hash_every : 60;
}

/* the session's end: the file now, on this thread (the process may end right after) */
void end_locked_then_write(std::unique_lock<std::mutex>& lk, const char* why)
{
    Rec& r = R();
    if (!r.on) return;
    for (Match& m : r.cur->d.matches)
        if (!m.have_result) { m.reason = why ? why : "session_end"; m.ended = utc_now(); }
    r.on = false;
    r.live = nullptr;
    r.want.reset();
    std::shared_ptr<Store> st = r.cur;
    lk.unlock();
    if (!st->live_path.empty()) live_append(st, why ? why : "session_end");
    write_store(st, ++g_seq);
    cost_note();
    lk.lock();
}

void rec_session_begin(int slot, const char* build, uint32_t session_seed)
{
    Rec& r = R();
    std::unique_lock<std::mutex> lk(r.mu);
    end_locked_then_write(lk, "a new session");
    r.cur.reset();
    r.have_fight = false;
    r.flush_at = UINT32_MAX;
    const char* dir = env("T5_REPLAY_DIR");
    const char* live = t5_env("T5_REPLAY_LIVE");   /* (a persistent game: this session's overlay) */
    if (live && !*live) live = nullptr;
    if (!dir && !live) return;
    auto st = std::make_shared<Store>();
    if (dir) CreateDirectoryA(dir, nullptr);
    { const char* n = env("T5_REPLAY_NAMES"); st->names = !(n && *n == '0'); }
    if (const char* h = env("T5_REPLAY_HASH_EVERY")) { const int v = atoi(h); if (v >= 1 && v <= 600) st->d.hash_every = (uint32_t)v; }
    st->d.slot = slot;
    st->d.build = build ? build : "";
    st->d.session_seed = session_seed;
    st->d.created = utc_now();
    SYSTEMTIME tm; GetLocalTime(&tm);
    LARGE_INTEGER q; QueryPerformanceCounter(&q);
    const uint32_t tag = (uint32_t)(q.QuadPart ^ (q.QuadPart >> 20) ^ GetCurrentProcessId()) & 0xFFFF;
    char name[96];
    snprintf(name, sizeof name, "T5R-%04u%02u%02u-%02u%02u%02u-%04x.t5replay", tm.wYear, tm.wMonth, tm.wDay, tm.wHour, tm.wMinute,
             tm.wSecond, tag);
    if (dir) {
        st->path = dir;
        if (!st->path.empty() && st->path.back() != '\\' && st->path.back() != '/') st->path += '\\';
        st->path += name;
    }
    if (live) {
        st->live_h = CreateFileA(live, GENERIC_WRITE, FILE_SHARE_READ | FILE_SHARE_DELETE, nullptr, CREATE_ALWAYS,
                                 FILE_ATTRIBUTE_NORMAL, nullptr);
        DWORD wr = 0;
        if (st->live_h != INVALID_HANDLE_VALUE &&
            WriteFile(st->live_h, kLiveMagic, (DWORD)(sizeof kLiveMagic - 1), &wr, nullptr) && wr == sizeof kLiveMagic - 1) {
            st->live_path = live;
            st->live_bytes = wr;
        } else {
            note("live stream %s: cannot create it (error %lu)", live, GetLastError());
            if (st->live_h != INVALID_HANDLE_VALUE) CloseHandle(st->live_h);
            st->live_h = INVALID_HANDLE_VALUE;
            if (!dir) return;
        }
    }
    r.next_periodic = 3600;
    r.cur = st;
    r.live = st.get();
    r.on = true;
    if (dir) note("recording this session to %s (player names %s)", st->path.c_str(), st->names ? "kept" : "left out");
    if (!st->live_path.empty()) {
        note("live stream for spectators: %s", st->live_path.c_str());
        ensure_writer_locked(r);
        SetEvent(r.ev);   /* (the writer thread's next wait has the 200 ms timeout) */
    }
}

void rec_session_end(const char* why)
{
    Rec& r = R();
    std::unique_lock<std::mutex> lk(r.mu);
    end_locked_then_write(lk, why);
}

/* The session's parameters as soon as the two games have shaken hands (netplay_core connect_locked):
 * the same values rec_start() records at frame 0 -- the seeds and the delay are the host's, rollback is
 * what both offered. The live stream's SESSION goes out now, so a spectator's game can boot while the
 * players' games still load the fight (it then waits at the select screen for the first fight). */
void rec_session_known(uint32_t match_seed, bool rollback, int delay)
{
    Rec& r = R();
    std::lock_guard<std::mutex> lk(r.mu);
    if (!r.on || r.cur->live_path.empty() || r.cur->live_started) return;
    r.cur->d.match_seed = match_seed;
    r.cur->d.rollback = rollback;
    r.cur->d.delay = delay;
    r.cur->live_started = true;
    live_queue_locked(*r.cur, L_SESSION, session_payload(r.cur->d));
    note("live stream: the session is known at the handshake (%s, delay %d)", rollback ? "rollback" : "lockstep", delay);
}

void rec_start(uint32_t match_seed, bool rollback, int delay)
{
    Rec& r = R();
    std::lock_guard<std::mutex> lk(r.mu);
    if (!r.on) return;
    r.cur->d.match_seed = match_seed;
    r.cur->d.rollback = rollback;
    r.cur->d.delay = delay;
    r.cur->live_started = !r.cur->live_path.empty();
    live_queue_locked(*r.cur, L_SESSION, session_payload(r.cur->d));
}

void rec_rollback_delay(int d)
{
    Rec& r = R();
    std::lock_guard<std::mutex> lk(r.mu);
    if (!r.on) return;
    r.cur->d.rb_delay = d;
    live_queue_locked(*r.cur, L_SESSION, session_payload(r.cur->d));
}

/* main thread, frames in order (no lock: see Store) */
void rec_input(uint32_t f, const np::PadInput& p1, const np::PadInput& p2)
{
    Store* st = R().live.load(std::memory_order_acquire);
    if (!st) return;
    Timed t;
    uint32_t n = st->n.load(std::memory_order_relaxed);
    if (f < n) {                                   /* (never seen: the netplay core hands each frame over once) */
        Chunk* c = st->chunks[f / kChunk].get();
        c->in[0][f % kChunk] = p1; c->in[1][f % kChunk] = p2;
        return;
    }
    while (n <= f) {
        if (n / kChunk >= st->chunks.size()) {
            if (st->chunks.size() >= kMaxChunks) return;
            st->chunks.push_back(std::make_unique<Chunk>());
        }
        Chunk* c = st->chunks[n / kChunk].get();
        c->in[0][n % kChunk] = n == f ? p1 : np::kNeutral;
        c->in[1][n % kChunk] = n == f ? p2 : np::kNeutral;
        n++;
    }
    st->n.store(n, std::memory_order_release);
}

void rec_hash(uint32_t f, uint64_t h)
{
    Rec& r = R();
    if (!r.on || (f % hash_every()) != 0) return;
    Timed t;
    std::lock_guard<std::mutex> lk(r.mu);
    if (!r.on) return;
    if (!r.cur->live_path.empty()) { std::vector<uint8_t> b; put32(b, f); put64(b, h); live_queue_locked(*r.cur, L_HASH, b); }
    auto& hs = r.cur->d.hashes;
    if (!hs.empty() && hs.back().first == f) { hs.back().second = h; return; }
    if (!hs.empty() && hs.back().first > f) {
        for (auto& x : hs) if (x.first == f) { x.second = h; return; }
        hs.push_back({ f, h });
        std::sort(hs.begin(), hs.end());
        return;
    }
    hs.push_back({ f, h });
}

void rec_barrier(const Barrier& b)
{
    Rec& r = R();
    Timed t;
    std::lock_guard<std::mutex> lk(r.mu);
    if (!r.on) return;
    r.cur->d.bars.push_back(b);
    if (!r.cur->live_path.empty()) { std::vector<uint8_t> x; put_barrier(x, b); live_queue_locked(*r.cur, L_BARRIER, x); }
}

void rec_fight(const Fight& ft)
{
    Rec& r = R();
    std::lock_guard<std::mutex> lk(r.mu);
    if (!r.on) return;
    r.fight = ft;
    r.have_fight = true;
}

void rec_match_begin(uint32_t f)
{
    Rec& r = R();
    std::lock_guard<std::mutex> lk(r.mu);
    if (!r.on || !r.have_fight) return;
    Match m;
    m.start = f;
    m.ft = r.fight;
    m.started = utc_now();
    r.cur->d.matches.push_back(m);
    r.have_fight = false;
    live_match_locked(r);
}

void rec_result(const char* winner, unsigned w1, unsigned w2, const char* reason, uint32_t frames, bool have_hash, uint64_t hash,
                uint32_t desync, uint32_t at_frame)
{
    Rec& r = R();
    Timed t;
    std::lock_guard<std::mutex> lk(r.mu);
    if (!r.on || r.cur->d.matches.empty()) return;
    Match& m = r.cur->d.matches.back();
    if (m.have_result) return;
    m.have_result = true;
    m.winner = !winner || !strcmp(winner, "null") ? -1 : atoi(winner);
    m.score[0] = (int)w1; m.score[1] = (int)w2;
    m.frames = frames;
    m.desync = desync;
    m.have_hash = have_hash; m.hash = hash;
    m.hash_frame = at_frame;
    m.end = at_frame;
    m.complete = reason == nullptr;
    if (reason) m.reason = reason;
    m.ended = utc_now();
    live_match_locked(r);
    request_write_locked(r);
    r.flush_at = at_frame + 420;    /* again once the frames after the KO are in (the playback shows them) */
}

void rec_frame(uint32_t f)
{
    Rec& r = R();
    if (!r.on) return;
    {
        Timed t;
        if (Store* st = r.live.load(std::memory_order_relaxed)) if (f > st->last.load(std::memory_order_relaxed)) st->last.store(f, std::memory_order_relaxed);
        if (f >= r.flush_at || f >= r.next_periodic) {
            std::lock_guard<std::mutex> lk(r.mu);
            if (f >= r.flush_at) r.flush_at = UINT32_MAX;
            else r.next_periodic = f + 3600;
            request_write_locked(r);
        }
    }
    cost_frame();
}

/* ======================================================================== playback */
bool playing() { return P().on; }
int  play_slot() { return P().d.slot; }
int  play_delay() { return P().d.delay; }
/* a live stream whose SESSION has not come yet: rollback, the lobby's netcode (rb_net.cpp offers it at the
 * game's start; netplay_core replay_session_known() takes the offer back for a lockstep session) */
bool play_rollback() { const Play& p = P(); return p.live && !p.have_session ? true : p.d.rollback; }
uint32_t play_session_seed() { return P().d.session_seed; }
uint32_t play_match_seed() { return P().d.match_seed; }
uint32_t play_target() { return P().target; }
uint32_t play_match_index() { return P().begun; }
const char* play_error() { return P().error.c_str(); }

bool peek_rollback(const char* path)
{
    if (!path || !*path) return false;
    FILE* fp = fopen(path, "rb");
    if (!fp) return false;
    char buf[4096] = {};
    const size_t n = fread(buf, 1, sizeof buf - 1, fp);
    fclose(fp);
    buf[n] = 0;
    if (n >= sizeof kLiveMagic - 1 && !memcmp(buf, kLiveMagic, sizeof kLiveMagic - 1)) {
        /* a live stream: its first record is the SESSION (u32 version, u32 flags). Not there yet (the
         * spectator's game starts before the players' handshake): rollback, the lobby's netcode -- this
         * only turns the write watch on during static initialisation; a lockstep session plays fine
         * with it (rb_net.cpp asks the file again once it is loaded) */
        const unsigned char* q = (const unsigned char*)buf + sizeof kLiveMagic - 1;
        if (n < sizeof kLiveMagic - 1 + 13) return true;
        return q[0] == L_SESSION && (q[9] & 1) != 0;
    }
    if (strncmp(buf, kMagic, sizeof kMagic - 1)) return false;
    char* nl = strchr(buf + sizeof kMagic - 1, 10);   /* the end of the JSON line */
    if (nl) *nl = 0;
    return strstr(buf, "\"mode\": \"rollback\"") != nullptr;
}

/* A live stream (spectating): its session and first match must be there (the launcher
 * starts the game once they are; up to T5_REPLAY_LIVE_WAIT seconds, default 60). */
bool live_load(const char* path)
{
    Play& p = P();
    p.live = true;
    p.lh = CreateFileA(path, GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE, nullptr, OPEN_EXISTING,
                       FILE_ATTRIBUTE_NORMAL, nullptr);
    if (p.lh == INVALID_HANDLE_VALUE) { p.error = "the live data cannot be opened"; return false; }
    if (const char* b = env("T5_REPLAY_LIVE_BUFFER")) { const int v = atoi(b); if (v >= 0 && v <= 3600) p.buffer = (uint32_t)v; }
    if (const char* t = env("T5_REPLAY_LIVE_TIMEOUT")) { const int v = atoi(t); if (v >= 5 && v <= 3600) p.timeout_s = (uint32_t)v; }
    if (const char* st = env("T5_REPLAY_STATUS")) p.status_path = st;
    /* The game starts at Watch, usually before the players' games have shaken hands: it boots to the
     * select screen meanwhile (like theirs) and waits there for the first fight's line. The session's
     * parameters come before that line (the handshake): netplay_core takes them then
     * (replay_session_known); until then rollback is assumed (play_rollback). */
    live_poll(p);
    if (p.live_bad) { p.error = "the live data is damaged"; return false; }
    if (p.mc.size() < p.d.matches.size()) p.mc.resize(p.d.matches.size());
    p.target = UINT32_MAX;     /* every match the stream brings */
    p.tail = 0;
    if (const char* rf = env("T5_REPLAY_RESULT")) p.result_path = rf;
    p.on = true;
    note("watching the live stream %s: %s, recorded on P%d's PC, %zu match(es) and %zu frames so far, a buffer of %u frames",
         path, p.d.rollback ? "rollback" : "lockstep", p.d.slot + 1, p.d.matches.size(), p.d.in[0].size(), p.buffer);
    return true;
}

bool play_live() { return P().live; }

int play_live_wait(uint32_t pf, bool (*quit)())
{
    Play& p = P();
    if (!p.live || p.finished) return 1;
    const int64_t r = (int64_t)pf - p.offset;
    constexpr int64_t kMargin = 16;   /* the frames past this one the loop may read (input delay) */
    if (++p.poll_tick >= 8 || (int64_t)p.d.in[0].size() <= r + kMargin) { p.poll_tick = 0; live_poll(p); }
    bool waited = false;
    if (!p.live_end && (p.buffering || (int64_t)p.d.in[0].size() <= r + kMargin)) {
        /* (re)fill the buffer: playing on frame by frame as the data trickles in would stutter */
        p.buffering = true;
        const int64_t want = r + kMargin + (int64_t)p.buffer;
        if ((int64_t)p.d.in[0].size() < want) {
            waited = true;
            if (!live_block(p, [&] { return (int64_t)p.d.in[0].size() >= want; }, quit, "the live data")) return 0;
        }
        p.buffering = false;
    }
    if (pf % 60 == 0) {
        const double dl = live_delay(p, r);
        if (dl >= 0) { p.delay_now = dl; p.delay_sum += dl; p.delay_n++; if (dl > p.delay_max) p.delay_max = dl; }
    }
    write_status(p, pf, waited);
    return waited ? 2 : 1;
}

bool play_load(const char* path)
{
    Play& p = P();
    p.path = path ? path : "";
    FILE* fp = path ? fopen(path, "rb") : nullptr;
    if (!fp) { p.error = "the file cannot be opened"; return false; }
    {
        char head[sizeof kLiveMagic] = {};
        const size_t hn = fread(head, 1, sizeof kLiveMagic - 1, fp);
        if (hn == sizeof kLiveMagic - 1 && !memcmp(head, kLiveMagic, hn)) { fclose(fp); return live_load(path); }
        rewind(fp);
    }
    std::vector<uint8_t> all;
    uint8_t buf[65536];
    for (size_t k; (k = fread(buf, 1, sizeof buf, fp)) > 0;) all.insert(all.end(), buf, buf + k);
    fclose(fp);
    const size_t ml = sizeof kMagic - 1;
    if (all.size() < ml || memcmp(all.data(), kMagic, ml)) { p.error = "not a T5DR replay"; return false; }
    size_t i = ml;
    while (i < all.size() && all[i] != '\n') i++;
    if (i >= all.size()) { p.error = "no data after the header"; return false; }
    i++;
    int blen = 0;
    unsigned char* bin = rp_zlib_decompress(all.data() + i, (int)(all.size() - i), &blen);
    if (!bin) { p.error = "the data is damaged"; return false; }
    std::string why;
    const bool ok = from_binary(bin, (size_t)blen, p.d, &why);
    free(bin);
    if (!ok) { p.error = why; return false; }
    if (p.d.matches.empty()) { p.error = "no match in it"; return false; }
    const uint32_t nm = (uint32_t)p.d.matches.size();
    const char* tm = env("T5_REPLAY_MATCH");
    p.target = tm ? (uint32_t)atoi(tm) : 0;
    if (p.target == 0 || p.target > nm) p.target = nm;     /* 0 / unset: every match of the session */
    if (const char* t = env("T5_REPLAY_TAIL")) p.tail = (uint32_t)atoi(t);
    if (const char* rf = env("T5_REPLAY_RESULT")) p.result_path = rf;
    p.mc.assign(nm, MatchCheck());
    p.on = true;
    note("playing %s: %s, %u match(es), %zu frames, %zu sync points, %zu hashes (every %u frames), recorded on P%d's PC, "
         "match %u is watched", p.path.c_str(), p.d.rollback ? "rollback" : "lockstep", nm, p.d.in[0].size(), p.d.bars.size(),
         p.d.hashes.size(), p.d.hash_every, p.d.slot + 1, p.target);
    return true;
}

void play_inputs(uint32_t pf, np::PadInput out[2])
{
    Play& p = P();
    out[0] = out[1] = np::kNeutral;
    const int64_t r = (int64_t)pf - p.offset;
    if (p.live && !p.live_end && r >= (int64_t)p.d.in[0].size()) {   /* (play_live_wait keeps ahead of this) */
        live_block(p, [&] { return r < (int64_t)p.d.in[0].size(); }, (bool (*)())nullptr, "the inputs of the next frame");
    }
    if (r < 0 || r >= (int64_t)p.d.in[0].size()) return;
    out[0] = p.d.in[0][(size_t)r];
    out[1] = p.d.in[1][(size_t)r];
}

uint32_t play_barrier(uint32_t k, uint32_t f)
{
    Play& p = P();
    p.bar_seen = k + 1;
    if (p.live && k >= p.d.bars.size())   /* the live game may not have sent it yet */
        live_block(p, [&] { return k < p.d.bars.size(); }, (bool (*)())nullptr, "the next sync point");
    if (k >= p.d.bars.size()) {
        /* at the recording's last frame the live game may simply not have got there before the session ended */
        if ((int64_t)f - p.offset >= (int64_t)p.end_frame()) return f;
        if (p.bar_bad++ < 5) note("sync point %u at playback frame %u: the recording has only %zu -- not the same game any more", k, f, p.d.bars.size());
        return f;
    }
    const Barrier& b = p.d.bars[k];
    const int64_t r = (int64_t)f - p.offset;
    uint32_t nf;
    if (r <= (int64_t)b.nf) nf = (uint32_t)((int64_t)b.nf + p.offset);   /* this game got there first: on to the recorded frame */
    else { p.offset = (int64_t)f - (int64_t)b.nf; nf = f; }              /* later than the recording (a slower load): frames renumbered */
    if (r != (int64_t)b.f || nf != f)
        note("sync point %u (kind %u): playback frame %u = recorded frame %lld (recorded: %u -> %u), continuing at %u (offset %lld)", k,
             b.kind, f, (long long)r, b.f, b.nf, nf, (long long)p.offset);
    return nf;
}

uint32_t play_barrier_seed(uint32_t k, uint32_t kind, uint32_t computed)
{
    Play& p = P();
    if (k >= p.d.bars.size()) return computed;
    const Barrier& b = p.d.bars[k];
    if (b.kind != kind && p.bar_bad++ < 5) note("sync point %u is a kind %u here, kind %u in the recording", k, kind, b.kind);
    if (kind == kPause) return computed;
    if (b.seed != computed && p.seed_bad++ < 5) note("sync point %u: reseed 0x%08X from the recording (here 0x%08X)", k, b.seed, computed);
    return b.seed;
}

bool play_barrier_state(uint32_t k, uint64_t* clock, uint32_t c[3])
{
    Play& p = P();
    if (k >= p.d.bars.size() || !p.d.bars[k].has_state) return false;
    *clock = p.d.bars[k].clock;
    for (int i = 0; i < 3; i++) c[i] = p.d.bars[k].c[i];
    return true;
}

void play_hash(uint32_t pf, uint64_t h)
{
    Play& p = P();
    const int64_t r = (int64_t)pf - p.offset;
    if (r < 0) return;
    const auto& hs = p.d.hashes;
    auto it = std::lower_bound(hs.begin(), hs.end(), std::make_pair((uint32_t)r, (uint64_t)0));
    if (it == hs.end() || it->first != (uint32_t)r) {
        /* live: the recorded hash of this frame may still be on its way (compared when it comes) */
        if (p.live && !p.live_end && p.have_session && (uint32_t)r % p.d.hash_every == 0) {
            if (!p.pend_hash.empty() && p.pend_hash.back().first == (uint32_t)r) p.pend_hash.back().second = h;
            else if (p.pend_hash.size() < 100000) p.pend_hash.push_back({ (uint32_t)r, h });
        }
        return;
    }
    p.compared++;
    if (it->second == h) return;
    p.mismatched++;
    if (p.first_bad < 0) p.first_bad = r;
    if (p.mismatched <= 10)
        note("HASH MISMATCH at recorded frame %lld (playback frame %u): %016llx, recorded %016llx", (long long)r, pf,
             (unsigned long long)h, (unsigned long long)it->second);
}

void play_match_begin(uint32_t pf)
{
    Play& p = P();
    p.begun++;
    const uint32_t k = p.begun;
    if (k > p.d.matches.size()) { note("match %u began at playback frame %u: the recording has %zu", k, pf, p.d.matches.size()); return; }
    const Match& m = p.d.matches[k - 1];
    const int64_t r = (int64_t)pf - p.offset;
    note("match %u of %zu begins at playback frame %u (recorded frame %lld, recorded start %u)%s", k, p.d.matches.size(), pf,
         (long long)r, m.start, k == p.target ? " -- the match being watched" : "");
    p.mc[k - 1].seen = true;
}

void play_fight(const Fight& ft, uint32_t match)
{
    Play& p = P();
    if (match < 1 || match > p.d.matches.size()) return;
    const Fight& rec = p.d.matches[match - 1].ft;
    if (ft.model[0] != rec.model[0] || ft.model[1] != rec.model[1] || ft.stage != rec.stage) {
        p.model_bad++;
        note("match %u: FIGHT START with models 0x%X / 0x%X on stage %d, the recording had 0x%X / 0x%X on stage %d", match,
             ft.model[0], ft.model[1], ft.stage, rec.model[0], rec.model[1], rec.stage);
    }
}

bool play_fight_line(uint32_t match, std::string* line)
{
    Play& p = P();
    /* live: the direct fight asks at the select screen (every 15 frames) until the players' games got to
     * that fight -- nothing else reads the file there */
    if (p.on && p.live && match > p.d.matches.size()) live_poll(p);
    if (p.session_new) {   /* (before the fight's line: the select's TLS pin and frame 0 use what it says) */
        p.session_new = false;
        np::replay_session_known();
    }
    if (!p.on || match < 1 || match > p.d.matches.size()) return false;
    const Fight& f = p.d.matches[match - 1].ft;
    char b[256];
    snprintf(b, sizeof b, "%d,%d,%d,%d buttons=%d|%d", f.chr[0], f.chr[1], f.stage, f.rounds, f.btn[0], f.btn[1]);
    *line = b;
    if (f.pick > 0) *line += " pick=" + std::to_string(f.pick);
    if (!f.names[0].empty() || !f.names[1].empty()) {
        auto enc = [](const std::string& s) {
            std::string o;
            for (unsigned char c : s) {
                if (isalnum(c) || c == '-' || c == '_' || c == '.') o += (char)c;
                else { char x[4]; snprintf(x, sizeof x, "%%%02X", c); o += x; }
            }
            return o;
        };
        *line += " names=" + enc(f.names[0]) + "|" + enc(f.names[1]);
    }
    return true;
}

void play_result(const char* winner, unsigned w1, unsigned w2, uint32_t frames, bool have_hash, uint64_t hash, uint32_t pf)
{
    Play& p = P();
    const uint32_t k = p.begun;
    if (k < 1 || k > p.d.matches.size()) return;
    MatchCheck& c = p.mc[k - 1];
    if (c.result) return;
    const Match& m = p.d.matches[k - 1];
    c.result = true;
    c.winner = !winner || !strcmp(winner, "null") ? -1 : atoi(winner);
    c.score[0] = (int)w1; c.score[1] = (int)w2;
    c.have_hash = have_hash; c.hash = hash;
    if (p.live && !m.have_result) {   /* the live game's result is on its way: compared when it comes */
        note("match %u over at playback frame %u after %u frames: winner %s, %u-%u, hash %016llx (the live result is not here yet)",
             k, pf, frames, c.winner < 0 ? "none" : c.winner == 0 ? "P1" : "P2", w1, w2, (unsigned long long)hash);
        return;
    }
    c.settled = true;
    c.same = m.have_result && m.complete && c.winner == m.winner && c.score[0] == m.score[0] && c.score[1] == m.score[1] &&
             (!m.have_hash || (have_hash && hash == m.hash));
    note("match %u over at playback frame %u after %u frames: winner %s, %u-%u, hash %016llx -- recorded: winner %s, %d-%d, hash %016llx: %s",
         k, pf, frames, c.winner < 0 ? "none" : c.winner == 0 ? "P1" : "P2", w1, w2, (unsigned long long)hash,
         m.winner < 0 ? "none" : m.winner == 0 ? "P1" : "P2", m.score[0], m.score[1], (unsigned long long)m.hash,
         c.same ? "THE SAME" : "DIFFERENT");
    if (k >= p.target && p.end_at == UINT32_MAX) p.end_at = pf + p.tail;
}

bool play_frame(uint32_t pf)
{
    Play& p = P();
    if (!p.on || p.finished) return !p.finished;
    p.last_p = pf;
    const int64_t r = (int64_t)pf - p.offset;
    if (pf >= p.end_at) { p.end_why = "the watched match is over"; return false; }
    if (r > (int64_t)p.end_frame()) { p.end_why = "end of the recording"; return false; }
    return true;
}

void play_finish(const char* why)
{
    Play& p = P();
    if (!p.on || p.finished) return;
    p.finished = true;
    if (why && *why) p.end_why = why;
    if (p.live) {
        live_poll(p);
        for (uint32_t k = 0; k < p.mc.size(); k++) settle_match(p, k);
        p.target = (uint32_t)std::min<size_t>(p.d.matches.size(), std::max<uint32_t>(p.begun, 1));
        write_status(p, p.last_p, true);
    }
    bool results_same = true, all_seen = true;
    std::string ms;
    char b[512];
    for (uint32_t k = 1; k <= p.target && k <= p.d.matches.size(); k++) {
        const MatchCheck& c = p.mc[k - 1];
        const Match& m = p.d.matches[k - 1];
        if (!c.seen) all_seen = false;
        if (m.complete && !c.same) results_same = false;
        snprintf(b, sizeof b, "%s{\"n\": %u, \"played\": %s, \"winner\": %s, \"score\": [%d, %d], \"hash\": %s, \"recorded_winner\": %s, "
                              "\"recorded_score\": [%d, %d], \"recorded_hash\": %s, \"recorded_complete\": %s, \"same\": %s}",
                 k > 1 ? ", " : "", k, c.result ? "true" : "false", !c.result || c.winner < 0 ? "null" : c.winner == 0 ? "0" : "1",
                 c.score[0], c.score[1], hexq(c.have_hash, c.hash).c_str(),
                 !m.have_result || m.winner < 0 ? "null" : m.winner == 0 ? "0" : "1", m.score[0], m.score[1],
                 hexq(m.have_hash, m.hash).c_str(), m.complete ? "true" : "false", c.same ? "true" : "false");
        ms += b;
    }
    const bool identical = p.compared > 0 && p.mismatched == 0 && p.bar_bad == 0 && p.model_bad == 0 && results_same && all_seen;
    std::string fb = p.first_bad < 0 ? "null" : std::to_string(p.first_bad);
    const char* slash = strrchr(p.path.c_str(), '\\');
    const char* slash2 = strrchr(p.path.c_str(), '/');
    const char* base = std::max(slash, slash2);
    snprintf(b, sizeof b, "{\"file\": %s, \"watched\": %u, \"matches_total\": %zu, \"end\": %s, \"frames\": %u, \"hashes_compared\": %u, "
                          "\"hash_mismatches\": %u, \"first_mismatch\": %s, \"sync_points\": %u, \"sync_points_recorded\": %zu, "
                          "\"sync_point_problems\": %u, \"setup_problems\": %u, \"identical\": %s, \"matches\": [",
             jstr(base ? base + 1 : p.path).c_str(), p.target, p.d.matches.size(), jstr(p.end_why).c_str(), p.last_p, p.compared,
             p.mismatched, fb.c_str(), p.bar_seen, p.d.bars.size(), p.bar_bad, p.model_bad, identical ? "true" : "false");
    std::string out = std::string(b) + ms + "]";
    if (p.live) {
        snprintf(b, sizeof b, ", \"live\": true, \"stream_end\": %s, \"stalls\": %u, \"stall_seconds\": %.2f, \"uncompared\": %zu, "
                              "\"delay_avg\": %.2f, \"delay_max\": %.2f, \"received_frames\": %zu, \"received_bytes\": %llu",
                 jstr(p.live_why).c_str(), p.stalls, p.stall_s, p.pend_hash.size(), p.delay_n ? p.delay_sum / p.delay_n : -1.0,
                 p.delay_n ? p.delay_max : -1.0, p.d.in[0].size(), (unsigned long long)p.lbytes);
        out += b;
    }
    out += "}";
    note("playback over (%s): %u hashes compared, %u different%s; results %s -- %s", p.end_why.c_str(), p.compared, p.mismatched,
         p.first_bad >= 0 ? (" (first at recorded frame " + fb + ")").c_str() : "", results_same ? "the same" : "DIFFERENT",
         identical ? "IDENTICAL to the live match" : "NOT identical");
    note("verdict: %s", out.c_str());
    if (!p.result_path.empty()) {
        const std::string tmp = p.result_path + ".tmp";
        if (FILE* fp = fopen(tmp.c_str(), "wb")) {
            fputs(out.c_str(), fp);
            fclose(fp);
            for (int i = 0; i < 50 && !MoveFileExA(tmp.c_str(), p.result_path.c_str(), MOVEFILE_REPLACE_EXISTING); i++) Sleep(2);
        }
    }
}

/* ---- the direct-fight driver's side (df_fight.cpp) ----------------------------- */
extern "C" void t5_replay_fight_start(unsigned match, const int chr[2], const int btn[2], const int model[2], int stage,
                                      int rounds, int pick, const char* name1, const char* name2)
{
    Fight ft;
    for (int i = 0; i < 2; i++) { ft.chr[i] = chr[i]; ft.btn[i] = btn[i]; ft.model[i] = model[i]; }
    ft.stage = stage; ft.rounds = rounds; ft.pick = pick;
    ft.names[0] = name1 ? name1 : ""; ft.names[1] = name2 ? name2 : "";
    if (playing()) play_fight(ft, match);
    else rec_fight(ft);
}

extern "C" int t5_replay_fight_line(unsigned match, char* buf, int size)
{
    std::string line;
    if (!play_fight_line(match, &line) || size <= 0) return 0;
    snprintf(buf, (size_t)size, "%s", line.c_str());
    return 1;
}

void play_fail(const char* path, const char* why)
{
    note("cannot play %s: %s", path ? path : "(no file)", why);
    const char* rf = env("T5_REPLAY_RESULT");
    if (!rf) return;
    const std::string out = "{\"file\": " + jstr(path ? path : "") + ", \"error\": " + jstr(why) + ", \"identical\": false}";
    const std::string tmp = std::string(rf) + ".tmp";
    if (FILE* fp = fopen(tmp.c_str(), "wb")) {
        fputs(out.c_str(), fp);
        fclose(fp);
        MoveFileExA(tmp.c_str(), rf, MOVEFILE_REPLACE_EXISTING);
    }
}

} // namespace rp
