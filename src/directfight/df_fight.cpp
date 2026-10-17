/*
 * T5DR direct fight -- the match driver (NPUB30009 v01.00; docs/DIRECTFIGHT.md).
 *
 *   T5_FIGHT=p1,p2,stage[,rounds][,p1color,p2color][ match=<id>]
 *       p1/p2   character: id 0-35, 3-letter code (pau, law, ...) or name prefix
 *       stage   stage id, or "random" / -1: without netplay the game's own pick; with
 *               netplay a stage derived from the shared seed (the game's pick happens
 *               on each PC on its own and would differ)
 *       rounds  rounds to win (default T5_NET_ROUNDS, else 3)
 *       colors  1 or 2 (costume; the second confirm's button)
 *       match=  the lobby's match id (any position, key=value): goes into the result
 *               file so the launcher can tell this match's result from an old one
 *   T5_FIGHT_FILE=<path>   the next fight: the file holds one T5_FIGHT line; it is
 *                          read when the game idles at character select (after a
 *                          match, or from boot when T5_FIGHT is not set) and renamed
 *                          to <path>.done once consumed
 *   T5_NET_RESULT_FILE     {"winner":0|1|null,"score":[p1,p2]} when a match ends
 *                          (written here when netplay is off; netplay writes it itself)
 *   T5_DF_STATUS_FILE      JSON status for the launcher, rewritten on every change:
 *                          {"state":..., "frame":N, "match":k, "p1":..,"p2":..,"stage":..}
 *
 * How it drives the game (all from the main thread at the frame boundary):
 *   1. title mode (1) reached -> call the game's own "start game type" routine
 *      func_0004E9DC(4 = VS BATTLE, 3 = both players): it fills the battle config
 *      (0x1008EBAC..) and requests the select mode (6). No intro, no menus.
 *   2. select mode: per player, the select record (0x10093F58 + p*0x78) holds the
 *      cursor cell (+0), the portrait id under it (+8) and the state byte (+0x20:
 *      3 choosing, 9 costume, 0x15 done). The cursor is moved by injected pad
 *      presses (closed loop: read the cell, step, re-read) to the character's cell
 *      (kGrid), CROSS confirms, the costume button confirms again. Then the stage
 *      panel: CROSS confirms whatever it shows; the stage id is overwritten at
 *      0x1008F088 at game-mode entry (the loader copies it from there).
 *   3. game mode (4): rounds to win -> 0x1008EBD4, stage -> 0x1008F088, then
 *      t5_netplay_start() (lockstep frame 0 on both PCs; no-op without netplay).
 *      "fight start" = the first frame in mode 4.
 *   4. match over: 0x1008EBD5 != 0 with wins at 0x1008EBDA/DB -> result file.
 *      The game returns to character select on its own: that is the neutral
 *      point; the next fight comes from T5_FIGHT_FILE.
 */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdio.h>
#include <ctype.h>
#include <string>
#include <vector>
#include "df.h"

extern "C" void t5_netplay_start(void);
extern "C" int  t5_netplay_lockstep_active(void);
extern "C" int  t5_netplay_local_slot(void);
extern "C" void t5_netplay_set_match(const char* id);
extern "C" unsigned t5_netplay_match_seed(void);

namespace df {

/* In lockstep (every match after the first under netplay) this PC drives only
 * its own player; the peer's presses arrive through the input exchange. */
bool drives(int p) { return !(netplay_on() && t5_netplay_lockstep_active()) || p == t5_netplay_local_slot(); }

/* ---- guest addresses (NPUB30009 v01.00) ---------------------------------- */
constexpr uint32_t kFnStartGame  = 0x0004E9DC;   /* (game_type, player_mask) -> config + select mode */
constexpr uint32_t kConfig       = 0x1008EBAC;   /* battle config: +0 game type (4 = VS) */
constexpr uint32_t kRoundsToWin  = 0x1008EBD4;   /* u8 */
constexpr uint32_t kMatchOver    = 0x1008EBD5;   /* u8: non-zero once the match is decided */
constexpr uint32_t kWinsP1       = 0x1008EBDA;   /* u8 */
constexpr uint32_t kWinsP2       = 0x1008EBDB;   /* u8 */
constexpr uint32_t kSelectState  = 0x1008F070;   /* select mode: 1,2,3 (choosing), 4 (stage confirmed), 5 (leaving); fight phases after */
constexpr uint32_t kStageId      = 0x1008F088;   /* chosen stage, written at the stage confirm, read by the game-mode loader */
constexpr uint32_t kRecord       = 0x10093F58;   /* per-player select records, 0x78 apart */
constexpr uint32_t kRecordStride = 0x78;
constexpr uint32_t kRecCell      = 0x00;         /* cursor cell */
constexpr uint32_t kRecFace      = 0x08;         /* portrait id under the cursor */
constexpr uint32_t kRecState     = 0x20;         /* u8: 3 choosing, 9 costume, then done (0x15 on P1, 0x0D on P2) */
constexpr uint32_t kModeTitle = 1, kModeGame = 4, kModeSelect = 6;

/* Character ids (the game's own order: 3-letter codes at 0x1001CE58, names at 0x10003F18). */
const char* const kCode[36] = {
    "pau", "law", "lei", "kin", "yos", "nin", "hwo", "xia", "cha", "jin", "jul", "kum",
    "pan", "bry", "hei", "kaz", "lee", "ste", "mar", "mok", "edd", "jac", "rog", "ann",
    "wan", "gan", "ask", "bru", "bae", "dvj", "rav", "fen", "amk", "lil", "dra", "jnp" };
const char* const kName[36] = {
    "Paul", "Law", "Lei", "King", "Yoshimitsu", "Nina", "Hwoarang", "Xiaoyu", "Christie", "Jin", "Julia", "Kuma",
    "Panda", "Bryan", "Heihachi", "Kazuya", "Lee", "Steve", "Marduk", "Mokujin", "Eddy", "Jack-5", "Roger Jr.", "Anna",
    "Wang", "Ganryu", "Asuka", "Bruce", "Baek", "Devil Jin", "Raven", "Feng", "Armor King", "Lili", "Dragunov", "Jinpachi" };

/* Select grid: cell -> character id. Cells 0-11 are the middle row, 12-23 the
 * bottom row, 24-34 the top row (column = cell - 24). The cursor cycles the
 * rows top -> middle -> bottom with DOWN (UP the other way) and skips a row
 * that has no cell in that column; in the top row it cycles cells 25..34 only
 * (cell 24, Jinpachi's slot, is skipped). Measured by walking the cursor
 * (build/df runs p9/p10) and checked against the screen. -1 = not reachable. */
const int kGrid[36] = {
    23, 18, 1, 6, 3, 33, 34, 14, 8, 0, 21, 27,       /* middle: Anna Marduk Law Hwoarang King Lili Dragunov Heihachi Christie Paul Jack-5 Bruce */
    22, 2, 5, 17, 15, 7, 9, 16, 10, 4, 13, 11,       /* bottom: Roger Lei Nina Steve Kazuya Xiaoyu Jin Lee Julia Yoshimitsu Bryan Kuma */
    -1, 20, 28, 19, 31, 30, 26, 29, 25, 24, 32,      /* top: (Jinpachi) Eddy Baek Mokujin Feng Raven Asuka DevilJin Ganryu Wang ArmorKing */
    -1 };
int cell_of(int chr)
{
    for (int c = 0; c < 35; c++) if (kGrid[c] == chr) return c;
    if (chr == 12) return cell_of(11);      /* Panda shares Kuma's cell (alternate confirm button) */
    return -1;
}
int cell_row(int c) { return c >= 24 ? 0 : c >= 12 ? 2 : 1; }         /* 0 top, 1 middle, 2 bottom */
int cell_col(int c) { return c >= 24 ? c - 24 : c >= 12 ? c - 12 : c; }

/* ---- configuration ----------------------------------------------------- */
struct Fight { int chr[2] = { -1, -1 }; int stage = -1; int rounds = 3; int color[2] = { 1, 1 }; bool valid = false;
               std::string text, match; };
std::string g_fight_file, g_status_file, g_result_file;
Fight g_cfg;            /* the fight being set up / fought */
bool g_configured = false;
uint16_t g_alt_button = B_CIRCLE;   /* T5_DF_ALT_BUTTON (hex): the confirm button that picks the shared-cell character (Panda) */

int parse_char(const std::string& t)
{
    if (t.empty()) return -1;
    char* e; long v = strtol(t.c_str(), &e, 10);
    if (*e == 0) return (v >= 0 && v < 36) ? (int)v : -1;
    for (int i = 0; i < 36; i++) if (_stricmp(t.c_str(), kCode[i]) == 0) return i;
    for (int i = 0; i < 36; i++) if (_strnicmp(t.c_str(), kName[i], t.size()) == 0) return i;
    return -1;
}

int default_rounds()
{
    const char* r = getenv("T5_NET_ROUNDS");
    const int n = r ? atoi(r) : 0;
    return (n >= 1 && n <= 5) ? n : 3;
}

bool parse_fight(const char* s, Fight& out)
{
    Fight f; f.text = s ? s : "";
    f.rounds = default_rounds();
    std::vector<std::string> tok;
    std::string cur;
    auto push = [&]() {
        if (cur.empty()) return;
        const size_t eq = cur.find('=');
        if (eq == std::string::npos) tok.push_back(cur);
        else if (_stricmp(cur.substr(0, eq).c_str(), "match") == 0) f.match = cur.substr(eq + 1);   /* key=value options */
        cur.clear();
    };
    for (const char* p = s; p && *p; p++) {
        if (*p == ',' || *p == ' ' || *p == ';') push();
        else if (*p != '\r' && *p != '\n') cur += *p;
    }
    push();
    if (tok.size() < 3) { note("T5_FIGHT needs p1,p2,stage[,rounds][,c1,c2]: '%s'", s ? s : ""); return false; }
    f.chr[0] = parse_char(tok[0]); f.chr[1] = parse_char(tok[1]);
    if (f.chr[0] < 0 || f.chr[1] < 0) { note("T5_FIGHT: unknown character in '%s'", s); return false; }
    if (_stricmp(tok[2].c_str(), "random") == 0 || tok[2] == "-1") f.stage = -1;
    else f.stage = atoi(tok[2].c_str());
    if (tok.size() > 3) f.rounds = atoi(tok[3].c_str());
    if (f.rounds < 1 || f.rounds > 5) f.rounds = default_rounds();
    if (tok.size() > 5) { f.color[0] = atoi(tok[4].c_str()) == 2 ? 2 : 1; f.color[1] = atoi(tok[5].c_str()) == 2 ? 2 : 1; }
    f.valid = true;
    out = f;
    return true;
}

/* ---- status / result files ------------------------------------------------ */
const char* g_state_name = "boot";
uint32_t g_match = 0;
int g_last_winner = -2; int g_last_score[2] = { 0, 0 };

void write_text(const std::string& path, const std::string& text)
{
    if (path.empty()) return;
    const std::string tmp = path + ".tmp";
    if (FILE* fp = fopen(tmp.c_str(), "wb")) {
        fwrite(text.data(), 1, text.size(), fp);
        fclose(fp);
        MoveFileExA(tmp.c_str(), path.c_str(), MOVEFILE_REPLACE_EXISTING);
    }
}

void status(const char* state, uint32_t f)
{
    g_state_name = state;
    note("frame %u: state %s", f, state);
    if (g_status_file.empty()) return;
    char buf[512];
    snprintf(buf, sizeof buf,
             "{\"state\": \"%s\", \"frame\": %u, \"match\": %u, \"p1\": %d, \"p2\": %d, \"stage\": %d, \"rounds\": %d, "
             "\"last_winner\": %s, \"last_score\": [%d, %d]}\n",
             state, f, g_match, g_cfg.chr[0], g_cfg.chr[1], g_cfg.stage, g_cfg.rounds,
             g_last_winner == -2 ? "null" : g_last_winner == -1 ? "null" : (g_last_winner == 0 ? "0" : "1"),
             g_last_score[0], g_last_score[1]);
    write_text(g_status_file, buf);
}

void write_result(int winner, int w1, int w2)
{
    if (g_result_file.empty() || netplay_on()) return;   /* netplay writes it when it owns the match */
    std::string id = "null";
    if (!g_cfg.match.empty()) {
        id = "\"";
        for (char c : g_cfg.match) id += (isalnum((unsigned char)c) || c == '-' || c == '_' || c == '.') ? c : '_';
        id += "\"";
    }
    char buf[256];
    snprintf(buf, sizeof buf, "{\"match\": %s, \"winner\": %s, \"score\": [%d, %d]}", id.c_str(),
             winner < 0 ? "null" : (winner == 0 ? "0" : "1"), w1, w2);
    write_text(g_result_file, buf);
    note("result written to %s: %s", g_result_file.c_str(), buf);
}

bool read_fight_file(Fight& out)
{
    if (g_fight_file.empty()) return false;
    FILE* fp = fopen(g_fight_file.c_str(), "rb");
    if (!fp) return false;
    char line[256] = {};
    fgets(line, sizeof line, fp);
    fclose(fp);
    const std::string done = g_fight_file + ".done";
    remove(done.c_str());
    MoveFileExA(g_fight_file.c_str(), done.c_str(), MOVEFILE_REPLACE_EXISTING);
    note("next fight from %s: %s", g_fight_file.c_str(), line);
    return parse_fight(line, out);
}

/* ---- the driver ----------------------------------------------------------- */
enum class Ph { Boot, Title, Select, Stage, WaitGame, Fight, Over, Neutral };
Ph g_ph = Ph::Boot;
uint32_t g_ph_frame = 0;        /* frame the phase began */
uint32_t g_title_seen = UINT32_MAX;
uint32_t g_fight_frame = 0;     /* frame the fight (game mode) started */
bool g_result_done = false;

/* per-player press scheduling: a press is `buttons` held for kHold frames then
 * released for kGap frames before the next one */
constexpr uint32_t kHold = 3, kGap = 5;
struct Press { uint16_t buttons = 0; uint32_t until = 0, next = 0; bool active = false; };
Press g_press[2];
int g_steps[2] = { 0, 0 };

uint32_t rec(int p) { return kRecord + p * kRecordStride; }
bool g_trace_presses = false;   /* T5_DF_TRACE=1 */
void press(int p, uint16_t buttons, uint32_t f)
{
    g_press[p].buttons = buttons; g_press[p].until = f + kHold; g_press[p].next = f + kHold + kGap; g_press[p].active = true;
    inject(p, true, buttons);
    if (g_trace_presses)
        note("frame %u: P%d press 0x%04X (cell %u face %u state %02X, select state %u)", f, p + 1, buttons,
             rd32(rec(p) + kRecCell), rd32(rec(p) + kRecFace), rd8(rec(p) + kRecState), rd32(kSelectState));
}
void service_presses(uint32_t f)
{
    for (int p = 0; p < 2; p++) {
        if (!g_press[p].active) continue;
        if (f >= g_press[p].until) inject(p, true, 0);
        if (f >= g_press[p].next) g_press[p].active = false;
    }
}
bool press_idle(int p) { return !g_press[p].active; }

void set_phase(Ph ph, const char* name, uint32_t f) { g_ph = ph; g_ph_frame = f; status(name, f); }

/* one navigation step for player p towards cell `target`; returns true when there */
bool navigate(int p, int target, uint32_t f)
{
    const int cell = (int)rd32(rec(p) + kRecCell);
    if (cell == target) return true;
    if (!press_idle(p)) return false;
    if (g_steps[p]++ > 80) { if (g_steps[p] == 82) note("player %d: cannot reach cell %d from %d, giving up", p + 1, target, cell); return false; }
    const int r = cell_row(cell), tr = cell_row(target), c = cell_col(cell), tc = cell_col(target);
    uint16_t b;
    if (r != tr) {
        /* rows cycle top(0) -> middle(1) -> bottom(2) -> top with DOWN; a row
         * without a cell in this column is skipped, so column 0 cannot reach
         * the top row: step sideways first */
        if (tr == 0 && c == 0) b = B_RIGHT;
        else b = ((tr - r + 3) % 3 == 1) ? B_DOWN : B_UP;
    } else {
        /* the top row cycles its 10 cells (columns 1..10), the others 12 */
        const int n = r == 0 ? 10 : 12, cc = r == 0 ? c - 1 : c, tcc = r == 0 ? tc - 1 : tc;
        const int fwd = (tcc - cc + n) % n, back = (cc - tcc + n) % n;
        b = fwd <= back ? B_RIGHT : B_LEFT;
    }
    press(p, b, f);
    return false;
}

/* With netplay a stage is never left to the game: its random pick at the stage
 * panel runs on each PC on its own (fd_random: different stages, desync from
 * frame 0). "random" becomes a stage from the seed both PCs share, mixed with
 * the match number (the same on both). The seed comes from T5_NET_SEED; without
 * it from the handshake, which may block -- so only once lockstep runs or at the
 * fight start (where the handshake is the barrier anyway). */
void resolve_stage(bool may_block)
{
    if (g_cfg.stage >= 0 || !netplay_on()) return;
    uint32_t seed = 0;
    if (const char* v = getenv("T5_NET_SEED")) seed = (uint32_t)strtoul(v, nullptr, 0);
    if (!seed && (may_block || t5_netplay_lockstep_active())) seed = t5_netplay_match_seed();
    if (!seed) return;
    uint32_t x = seed ^ ((g_match + 1) * 0x9E3779B9u);
    x ^= x >> 16; x *= 0x7FEB352Du; x ^= x >> 15; x *= 0x846CA68Bu; x ^= x >> 16;
    g_cfg.stage = 17 + (int)(x % 18);
    note("stage: random -> %d (from the shared seed, match %u)", g_cfg.stage, g_match + 1);
}

void begin_select(uint32_t f)
{
    g_steps[0] = g_steps[1] = 0;
    g_result_done = false;
    resolve_stage(false);
    for (int p = 0; p < 2; p++) {
        const int c = cell_of(g_cfg.chr[p]);
        note("player %d: %s (id %d) -> cell %d, color %d", p + 1, kName[g_cfg.chr[p]], g_cfg.chr[p], c, g_cfg.color[p]);
    }
    note("stage %d, rounds %d", g_cfg.stage, g_cfg.rounds);
    set_phase(Ph::Select, "select", f);
}

void fight_on_frame(uint32_t f)
{
    if (!g_configured) return;
    service_presses(f);
    const uint32_t mgr = mode_manager();
    if (!mgr) return;
    const uint32_t mode = mode_cur();

    switch (g_ph) {
    case Ph::Boot:
        if (mode == kModeTitle) { g_title_seen = f; set_phase(Ph::Title, "title", f); }
        break;
    case Ph::Title:
        /* the title mode needs a few frames of its own init; 30 was verified */
        if (f >= g_title_seen + 30) {
            note("frame %u: start VS battle (func_0004E9DC(4, 3)) from the title mode", f);
            gcall(kFnStartGame, 4, 3);
            if (!g_cfg.valid && !read_fight_file(g_cfg)) {
                set_phase(Ph::Neutral, "neutral", f);
            } else {
                begin_select(f);
            }
        }
        break;
    case Ph::Select: {
        if (mode != kModeSelect || rd32(kSelectState) < 3) {          /* loading / fading in */
            if ((f - g_ph_frame) % 120 == 0 && f > g_ph_frame)
                note("frame %u: waiting for the select screen (mode %u, select state %u, records %02X/%02X)", f, mode,
                     rd32(kSelectState), rd8(rec(0) + kRecState), rd8(rec(1) + kRecState));
            break;
        }
        if ((f - g_ph_frame) % 120 == 0 && g_trace_presses)
            note("frame %u: select: P1 cell %u state %02X, P2 cell %u state %02X", f, rd32(rec(0) + kRecCell), rd8(rec(0) + kRecState),
                 rd32(rec(1) + kRecCell), rd8(rec(1) + kRecState));
        bool all_done = true;
        for (int p = 0; p < 2; p++) {
            const uint8_t st = rd8(rec(p) + kRecState);
            if (st == 0x15 || st == 0x0D) continue;      /* done (0x15 on P1, 0x0D on P2 right after the costume) */
            all_done = false;
            if (st != 3 && st != 9) continue;            /* 0: the screen is not live yet */
            if (!press_idle(p) || !drives(p)) continue;
            if (st == 3) {
                const int target = cell_of(g_cfg.chr[p]);
                if (target < 0) { if (g_steps[p]++ == 0) note("player %d: no cell for character %d", p + 1, g_cfg.chr[p]); continue; }
                if (navigate(p, target, f)) {
                    const bool shared = (g_cfg.chr[p] == 12);   /* Panda on Kuma's cell */
                    press(p, shared ? g_alt_button : B_CROSS, f);
                }
            } else if (st == 9) {
                press(p, g_cfg.color[p] == 2 ? B_TRIANGLE : B_CROSS, f);
            }
        }
        if (all_done) set_phase(Ph::Stage, "stage", f);
        break; }
    case Ph::Stage:
        if (mode == kModeGame) { set_phase(Ph::WaitGame, "loading", f); break; }
        /* The stage confirm writes the panel's own pick (random, different on
         * the two PCs: fd_rematch showed 0x1d vs 0x11 for 50 frames in
         * lockstep) to 0x1008F088, two frames before the select state turns 4.
         * Ours replaces it at the top of every frame of this phase, before the
         * frame's state hash; the phase begins at the same frame on both PCs
         * (both players' records done), and the panel only writes the word. */
        if (g_cfg.stage >= 0 && rd32(kStageId) != (uint32_t)g_cfg.stage) wr32(kStageId, (uint32_t)g_cfg.stage);
        if (rd32(kSelectState) >= 4) break;                 /* stage confirmed, the mode switch follows */
        if (f >= g_ph_frame + 90 && press_idle(0) && press_idle(1) && ((f - g_ph_frame) % 30) == 0) {
            for (int p = 0; p < 2; p++) if (drives(p)) press(p, B_CROSS, f);   /* confirm whatever stage the panel shows */
        }
        break;
    case Ph::WaitGame:
        /* first frame in the game mode: apply the setup the loader reads, start lockstep */
        resolve_stage(true);
        wr8(kRoundsToWin, (uint8_t)g_cfg.rounds);
        if (netplay_on() && !g_cfg.match.empty()) t5_netplay_set_match(g_cfg.match.c_str());
        if (g_cfg.stage >= 0) wr32(kStageId, (uint32_t)g_cfg.stage);
        for (int p = 0; p < 2; p++) inject(p, false, 0);
        g_match++;
        g_fight_frame = f;
        note("frame %u: FIGHT START match %u%s%s: %s vs %s, stage %d (field 0x%X), rounds %u, game type %u",
             f, g_match, g_cfg.match.empty() ? "" : " id ", g_cfg.match.c_str(), kName[g_cfg.chr[0]], kName[g_cfg.chr[1]],
             g_cfg.stage, rd32(kStageId), rd8(kRoundsToWin), rd32(kConfig));
        if (netplay_on()) { t5_netplay_start(); note("frame %u: t5_netplay_start() called (lockstep frame 0 is the next frame)", f); }
        set_phase(Ph::Fight, "fight", f);
        break;
    case Ph::Fight: {
        if (mode != kModeGame) { note("frame %u: left the game mode (mode %u) without a result", f, mode); set_phase(Ph::Over, "over", f); break; }
        const uint8_t over = rd8(kMatchOver), w1 = rd8(kWinsP1), w2 = rd8(kWinsP2);
        if (over && (w1 || w2) && !g_result_done) {
            g_result_done = true;
            const int winner = w1 > w2 ? 0 : w2 > w1 ? 1 : -1;
            g_last_winner = winner; g_last_score[0] = w1; g_last_score[1] = w2;
            note("frame %u: MATCH OVER match %u after %u frames: P1 %u - P2 %u, winner %s", f, g_match, f - g_fight_frame, w1, w2,
                 winner < 0 ? "none" : winner == 0 ? "P1" : "P2");
            write_result(winner, w1, w2);
            set_phase(Ph::Over, "over", f);
        }
        break; }
    case Ph::Over:
        /* the game shows the win pose and returns to character select by itself */
        if (mode == kModeSelect && rd32(kSelectState) >= 3 && rd8(rec(0) + kRecState) == 3) {
            g_cfg.valid = false;
            if (read_fight_file(g_cfg)) begin_select(f);
            else set_phase(Ph::Neutral, "neutral", f);
        } else if (mode != kModeGame && mode != kModeSelect && (f - g_ph_frame) % 300 == 0) {
            note("frame %u: waiting in mode %u for character select", f, mode);
        }
        break;
    case Ph::Neutral:
        if ((f - g_ph_frame) % 15 == 0 && read_fight_file(g_cfg)) {
            if (mode == kModeSelect) begin_select(f);
            else note("frame %u: fight requested but the game is in mode %u", f, mode);
        }
        break;
    }
}

bool fight_configured() { return g_configured; }

void fight_init()
{
    const char* fight = getenv("T5_FIGHT");
    const char* file = getenv("T5_FIGHT_FILE");
    if (!(fight && *fight) && !(file && *file)) return;
    g_configured = true;
    if (file) g_fight_file = file;
    if (const char* r = getenv("T5_NET_RESULT_FILE")) g_result_file = r;
    if (const char* s = getenv("T5_DF_STATUS_FILE")) g_status_file = s;
    if (const char* a = getenv("T5_DF_ALT_BUTTON")) g_alt_button = (uint16_t)strtoul(a, nullptr, 16);
    { const char* t = getenv("T5_DF_TRACE"); g_trace_presses = t && *t == '1'; }
    if (fight && *fight) parse_fight(fight, g_cfg);
    note("direct fight: %s%s%s", g_cfg.valid ? g_cfg.text.c_str() : "(waiting for T5_FIGHT_FILE)",
         g_fight_file.empty() ? "" : ", next fights from ", g_fight_file.c_str());
}

} // namespace df
