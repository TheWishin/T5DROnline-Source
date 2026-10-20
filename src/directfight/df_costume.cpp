/*
 * Custom costumes online (docs/DIRECTFIGHT.md "Custom costumes online").
 *
 * An online game plays on a save of its own (patch 0044) and starts VS with no
 * profile, so both fighters wear their default costumes. Here each player's
 * own customization reaches the match:
 *
 *   1. At the start of a netplay session this PC reads its player's own save
 *      (T5_COSTUME_SAVE = the SYS-DATA of the offline save, the launcher names
 *      it; unset or "0" = nothing is shown) and keeps the blocks with something
 *      worn as a wire table (costume_logic.h), which netplay sends to the
 *      opponent (PKT_COSTUME, at most 9,283 bytes, chunked, acknowledged, the
 *      whole table checked against its hash) -- the opponent's arrives the same
 *      way. Both PCs then hold the same two tables, byte for byte: this PC
 *      uses for its own player exactly the bytes it sent.
 *   2. The stage panel is not confirmed before the opponent's table is here
 *      (the select may go on meanwhile), so neither game starts a fight
 *      without both tables.
 *   3. At FIGHT START (the game mode's phase 7: the fighter objects know
 *      their item character now, the models are not loaded yet; before
 *      t5_netplay_start()) each side's VS custom data gets the 0x108-byte
 *      block of the character it fights with -- the item character index the
 *      game itself uses (fighter object +0x40, as 0x2A77B0 reads it) -- when
 *      that player's table has one and it passes the check both PCs make
 *      (costume::block_valid); otherwise the zero block the game has there
 *      online today (the default costumes). Both PCs write the same bytes for
 *      both sides; the bytes' hash is logged, read back once the loading is
 *      over, and the blocks go into the replay (a replay writes them again).
 *
 * Offline (direct fight without netplay; tests): T5_COSTUME_SAVE for P1 and
 * T5_COSTUME_SAVE2 for P2.
 */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
#include <string>
#include <vector>
#include "df.h"
#include "costume_logic.h"

extern "C" const char* t5_env(const char* key);
extern "C" int  t5_netplay_local_slot(void);
extern "C" void t5_netplay_costume_set(const unsigned char* p, unsigned n);
extern "C" int  t5_netplay_costume_local_set(void);
extern "C" int  t5_netplay_costume_peer(unsigned char* out, unsigned cap, unsigned* n);
extern "C" int  t5_replay_costumes(unsigned match, unsigned char* out);   /* src/netplay/replay.cpp */

namespace df {

namespace {

constexpr uint32_t kTocCustomData = 0x0046ECD0;   /* -> the VS custom data, 0x1F4 per side */
constexpr uint32_t kCustomStride  = 0x1F4;
constexpr uint32_t kTocFighters   = 0x0046EE20;   /* -> the two fighter objects (0x2A77B0: +0x40 the item character index) */
constexpr uint32_t kFighterItemChar = 0x40;
constexpr uint32_t kItemTables    = 0x10076724;   /* price tables per item character: {s32 id, s32 price} ..., id < 0 ends */

bool in_data(uint32_t a, uint32_t len) { return a >= 0x10000000u && a + len <= 0x10760000u && a + len > a; }

costume::Items items_of(int c)
{
    costume::Items it;
    if (c < 0 || c >= costume::kChars) return it;
    const uint32_t p = rd32(kItemTables + 4 * (uint32_t)c);
    if (!p || !in_data(p, 8)) return it;
    for (uint32_t a = p; it.n < costume::kMaxItems && in_data(a, 8); a += 8) {
        const uint32_t id = rd32(a);
        if (id & 0x80000000u) break;
        if (id <= 0xFFFF) it.id[it.n++] = (uint16_t)id;
    }
    return it;
}

std::vector<uint8_t> g_local_wire;   /* this PC's table as sent (the bytes its own player's blocks come from) */
bool g_local_loaded = false;
std::string g_local_note;
uint64_t g_written_hash = 0;         /* both sides' blocks as written at FIGHT START */
bool g_written = false, g_checked = false;
uint8_t g_written_blocks[2 * costume::kBlock];   /* ... the bytes (for the replay) */

/* a block with any byte set (a replay's zero block: nothing was written for that side) */
bool block_any(const uint8_t* b) { for (uint32_t i = 0; i < costume::kBlock; i++) if (b[i]) return true; return false; }

/* The player's own table from T5_COSTUME_SAVE (or `var`). */
std::vector<uint8_t> load_wire(const char* var, std::string& why)
{
    costume::Table t;
    const char* path = t5_env(var);
    if (!path || !*path || !strcmp(path, "0")) { why = "no save given"; return costume::to_wire(t); }
    std::vector<uint8_t> d;
    if (FILE* fp = fopen(path, "rb")) {
        uint8_t buf[65536];
        size_t n;
        while ((n = fread(buf, 1, sizeof buf, fp)) > 0 && d.size() <= costume::kSaveSize) d.insert(d.end(), buf, buf + n);
        fclose(fp);
    }
    if (d.size() != costume::kSaveSize || !costume::from_save(d.data(), d.size(), t)) {
        why = d.empty() ? "the save cannot be read" : "not a SYS-DATA of this game";
        return costume::to_wire(costume::Table());
    }
    char b[160];
    std::string list;
    for (int c = 0; c < costume::kChars; c++) if (t.have[c]) { snprintf(b, sizeof b, "%s%02X", list.empty() ? "" : " ", c); list += b; }
    snprintf(b, sizeof b, "%d character(s) customized%s%s", t.count(), list.empty() ? "" : ": ", list.c_str());
    why = b;
    return costume::to_wire(t);
}

int item_char_of(int side, uint32_t* objp)
{
    *objp = 0;
    const uint32_t arr = rd32(kTocFighters);
    if (!in_data(arr, 8)) return -1;
    const uint32_t obj = rd32(arr + 4 * (uint32_t)side);
    *objp = obj;
    if (obj < 0x10000000u || obj >= 0xD0000000u) return -1;
    const int c = (int16_t)rd16(obj + kFighterItemChar);
    return c >= 0 && c < costume::kChars ? c : -1;
}

} // namespace

/* Start of a session (or an offline fight): this PC's table, handed to netplay once per session. A replay
 * has no table of its own: its blocks come from the file. */
void costume_session(uint32_t f, CostumeMode m)
{
    if (m == CostumeMode::Replay) return;
    if (m == CostumeMode::Net) {
        if (t5_netplay_costume_local_set()) return;
        g_local_wire = load_wire("T5_COSTUME_SAVE", g_local_note);
        t5_netplay_costume_set(g_local_wire.data(), (unsigned)g_local_wire.size());
        note("frame %u: costumes: this player's table %zu bytes (%s), sent to the opponent", f, g_local_wire.size(),
             g_local_note.c_str());
        return;
    }
    if (g_local_loaded) return;
    g_local_loaded = true;
    g_local_wire = load_wire("T5_COSTUME_SAVE", g_local_note);
    note("frame %u: costumes (offline): P1's table %zu bytes (%s)", f, g_local_wire.size(), g_local_note.c_str());
}

/* The opponent's table is here (offline and in a replay: nothing to wait for). */
bool costume_ready(CostumeMode m)
{
    if (m != CostumeMode::Net) return true;
    unsigned n = 0;
    return t5_netplay_costume_peer(nullptr, 0, &n) != 0;
}

/* FIGHT START: both sides' blocks into the VS custom data. */
void costume_apply(uint32_t f, CostumeMode m, uint32_t match)
{
    g_written = false;
    g_checked = false;
    const uint32_t base = rd32(kTocCustomData);
    if (!in_data(base, 2 * kCustomStride)) { note("frame %u: costumes: VS custom data pointer 0x%08X unexpected, left alone", f, base); return; }
    std::vector<uint8_t> wires[2];
    uint8_t recorded[2 * costume::kBlock];
    const bool replay = m == CostumeMode::Replay && t5_replay_costumes(match, recorded);
    if (m == CostumeMode::Net) {
        const int me = t5_netplay_local_slot() == 1 ? 1 : 0;
        std::vector<uint8_t> peer(costume::kWireMax);
        unsigned n = 0;
        wires[me] = g_local_wire;
        if (!t5_netplay_costume_peer(peer.data(), (unsigned)peer.size(), &n)) {
            /* never: the stage confirm waits for it (costume_ready); both sides then default, logged */
            note("frame %u: costumes: the opponent's table is missing -- default costumes for both", f);
            n = 0;
            wires[me].clear();
        }
        peer.resize(n);
        wires[1 - me] = peer;
    } else if (m == CostumeMode::Offline) {
        std::string why2;
        wires[0] = g_local_wire;
        wires[1] = load_wire("T5_COSTUME_SAVE2", why2);
    }
    static const uint8_t kZero[costume::kBlock] = {};
    uint64_t h = costume::fnv64(nullptr, 0);
    std::string line;
    for (int s = 0; s < 2; s++) {
        uint32_t obj = 0;
        const int c = item_char_of(s, &obj);
        const uint8_t* src = kZero;
        const char* why = "nothing customized";
        costume::Table t;
        if (m == CostumeMode::Replay) {
            /* the blocks the live match fought in, checked again (a file can be edited) */
            if (!replay) why = "not in the replay";
            else if (block_any(recorded + s * costume::kBlock) && c >= 0) {
                if (costume::block_valid(recorded + s * costume::kBlock, items_of(c), &why)) { src = recorded + s * costume::kBlock; why = "custom (replay)"; }
            }
        } else if (!costume::from_wire(wires[s].data(), wires[s].size(), t)) why = "no table (not a valid one)";
        else if (c < 0) why = "item character unknown";
        else if (t.have[c]) {
            if (costume::block_valid(t.blk[c], items_of(c), &why)) { src = t.blk[c]; why = "custom"; }
        }
        const uint32_t dst = base + (uint32_t)s * kCustomStride;
        memcpy(vm_base + dst, src, costume::kBlock);     /* big-endian bytes, as in the save */
        memcpy(g_written_blocks + s * costume::kBlock, src, costume::kBlock);
        h = costume::fnv64(src, costume::kBlock, h);
        char b[160];
        snprintf(b, sizeof b, "%sP%d item char %d (fighter 0x%08X): %s", s ? ", " : "", s + 1, c, obj, why);
        line += b;
    }
    g_written_hash = h;
    g_written = true;
    note("frame %u: costumes written: %s; blocks hash %016llX", f, line.c_str(), (unsigned long long)h);
}

const unsigned char* costume_written() { return g_written ? g_written_blocks : nullptr; }

/* The loading is over (the intros' first frame): the blocks are still what was written. */
void costume_check(uint32_t f)
{
    if (!g_written || g_checked) return;
    g_checked = true;
    const uint32_t base = rd32(kTocCustomData);
    if (!in_data(base, 2 * kCustomStride)) return;
    uint64_t h = costume::fnv64(nullptr, 0);
    for (int s = 0; s < 2; s++) h = costume::fnv64(vm_base + base + (uint32_t)s * kCustomStride, costume::kBlock, h);
    if (h != g_written_hash)
        note("frame %u: costumes: the VS custom data changed during the loading (hash %016llX, written %016llX)", f,
             (unsigned long long)h, (unsigned long long)g_written_hash);
    else
        note("frame %u: costumes: blocks hash %016llX after the loading", f, (unsigned long long)h);
}

} // namespace df
