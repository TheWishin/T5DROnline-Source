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
extern "C" int  t5_netplay_session_begin(void);
extern "C" void t5_netplay_session_end(const char* why);
extern "C" const char* t5_netplay_take_session_lost(void);
extern "C" const char* t5_env(const char* key);

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
constexpr uint32_t kWinnerIdx    = 0x1008EBD6;   /* u8: 0 = P1, 1 = P2, set together with kMatchOver (seen in the dry run) */
constexpr uint32_t kSelectState  = 0x1008F070;   /* select mode: 1,2,3 (choosing), 4 (stage confirmed), 5 (leaving); fight phases after */
constexpr uint32_t kStageId      = 0x1008F088;   /* chosen stage, written at the stage confirm, read by the game-mode loader */
constexpr uint32_t kRecord       = 0x10093F58;   /* per-player select records, 0x78 apart */
constexpr uint32_t kRecordStride = 0x78;
constexpr uint32_t kRecCell      = 0x00;         /* cursor cell */
constexpr uint32_t kRecFace      = 0x08;         /* portrait id under the cursor */
constexpr uint32_t kRecState     = 0x20;         /* u8: 3 choosing, 9 costume, then done (0x15 on P1, 0x0D on P2) */
constexpr uint32_t kModeTitle = 1, kModeGame = 4, kModeSelect = 6;
constexpr uint32_t kModeNone = 14;               /* the request's "next" when no mode change is pending */

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
 * (build/df runs p9/p10) and checked against the screen. -1 = not reachable.
 * Cells 28 and 31 are Devil Jin and Feng: the first table had them the other
 * way round, so T5_FIGHT Devil Jin (29) gave Feng and Feng (31) Devil Jin
 * (completeness audit: the select screen's portraits of all 35 ids). */
const int kGrid[36] = {
    23, 18, 1, 6, 3, 33, 34, 14, 8, 0, 21, 27,       /* middle: Anna Marduk Law Hwoarang King Lili Dragunov Heihachi Christie Paul Jack-5 Bruce */
    22, 2, 5, 17, 15, 7, 9, 16, 10, 4, 13, 11,       /* bottom: Roger Lei Nina Steve Kazuya Xiaoyu Jin Lee Julia Yoshimitsu Bryan Kuma */
    -1, 20, 28, 19, 29, 30, 26, 31, 25, 24, 32,      /* top: (Jinpachi) Eddy Baek Mokujin DevilJin Raven Asuka Feng Ganryu Wang ArmorKing */
    -1 };
int cell_of(int chr)
{
    for (int c = 0; c < 35; c++) if (kGrid[c] == chr) return c;
    if (chr == 12) return cell_of(11);      /* Panda shares Kuma's cell (a kick button confirms Panda) */
    return -1;
}
int cell_row(int c) { return c >= 24 ? 0 : c >= 12 ? 2 : 1; }         /* 0 top, 1 middle, 2 bottom */
int cell_col(int c) { return c >= 24 ? c - 24 : c >= 12 ? c - 12 : c; }

/* ---- configuration ----------------------------------------------------- */
/* HUD identity (docs/DIRECTFIGHT.md "Names and ranks in the HUD"): names[p]
 * empty = the game's own "Unknown", rank[p] < 0 = left as the game has it. */
struct Fight { int chr[2] = { -1, -1 }; int stage = -1; int rounds = 3; int color[2] = { 1, 1 }; bool valid = false;
               std::string text, match; std::string names[2]; int rank[2] = { -1, -1 }; bool hud = false; };
std::string g_fight_file, g_status_file, g_result_file;
Fight g_cfg;            /* the fight being set up / fought */
bool g_configured = false;
uint16_t g_alt_button = B_CIRCLE;   /* T5_DF_ALT_BUTTON (hex): the confirm button that picks the shared-cell character (Panda) */

/* The session's environment: in a persistent game the control channel's
 * overlay (the runtime caches getenv() for good), else the process's. */
const char* sess_env(const char* k) { const char* v = t5_env(k); return (v && *v) ? v : nullptr; }

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
    const char* r = sess_env("T5_NET_ROUNDS");
    const int n = r ? atoi(r) : 0;
    return (n >= 1 && n <= 5) ? n : 3;
}

/* "%41b" -> "Ab" (names in a fight line: spaces and separators percent-encoded) */
std::string pct_decode(const std::string& s)
{
    std::string o;
    for (size_t i = 0; i < s.size(); i++) {
        if (s[i] == '%' && i + 2 < s.size() && isxdigit((unsigned char)s[i + 1]) && isxdigit((unsigned char)s[i + 2])) {
            o += (char)strtoul(s.substr(i + 1, 2).c_str(), nullptr, 16);
            i += 2;
        } else o += s[i];
    }
    return o;
}

/* names "A|B" (T5_HUD_NAMES, or a fight line's names=) and ranks "11,3" / "11|3" */
void parse_hud(Fight& f, const char* names, const char* ranks, bool encoded)
{
    if (names) {
        std::string n = names;
        const size_t bar = n.find('|');
        f.names[0] = n.substr(0, bar);
        f.names[1] = bar == std::string::npos ? std::string() : n.substr(bar + 1);
        for (auto& x : f.names) { if (encoded) x = pct_decode(x); if (x.size() > 16) x.resize(16); }
        f.hud = true;
    }
    if (ranks) {
        int r[2] = { -1, -1 };
        char* e;
        r[0] = (int)strtol(ranks, &e, 10);
        if (e != ranks && (*e == ',' || *e == '|')) r[1] = (int)strtol(e + 1, nullptr, 10);
        for (int p = 0; p < 2; p++) f.rank[p] = (r[p] >= 0 && r[p] <= 36) ? r[p] : -1;
        f.hud = true;
    }
}

bool parse_fight(const char* s, Fight& out)
{
    Fight f; f.text = s ? s : "";
    f.rounds = default_rounds();
    /* the HUD identity carries over from the last fight (a rematch: same players) unless the line has its own */
    for (int p = 0; p < 2; p++) { f.names[p] = out.names[p]; f.rank[p] = out.rank[p]; }
    f.hud = out.hud;
    std::vector<std::string> tok;
    std::string cur, names, ranks;
    auto push = [&]() {
        if (cur.empty()) return;
        const size_t eq = cur.find('=');
        const std::string k = eq == std::string::npos ? std::string() : cur.substr(0, eq);
        if (eq == std::string::npos) tok.push_back(cur);
        else if (_stricmp(k.c_str(), "match") == 0) f.match = cur.substr(eq + 1);   /* key=value options */
        else if (_stricmp(k.c_str(), "names") == 0) names = cur.substr(eq + 1);
        else if (_stricmp(k.c_str(), "ranks") == 0) ranks = cur.substr(eq + 1);
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
    parse_hud(f, names.empty() ? nullptr : names.c_str(), ranks.empty() ? nullptr : ranks.c_str(), true);
    f.valid = true;
    out = f;
    return true;
}

/* ---- HUD identity ------------------------------------------------------------
 * The fight HUD shows, under each health bar, a name and a rank badge from the
 * VS "custom data" of that side: blocks of 0x1F4 bytes at the address in the
 * TOC entry 0x46ECD0 (0x106C9934 on this path), one per player. Read by the
 * game's own getters 0x2A1740 (name: UTF-16BE at +0x134, 20 characters; blank
 * -> message 0x104FF "Unknown", 0x105BB4) and 0x2A180C (rank: u8 at +0x11C,
 * the 37 ranks in the game's order, the badge sprite table at 0x100692F0;
 * 34-36 all show the Dark Lord badge). Nothing in a fight reads them, and they
 * are outside the netplay state hash; both PCs write the same values anyway
 * (the lobby's P1/P2 names and tiers), at the same frame in lockstep. */
constexpr uint32_t kTocCustomData = 0x0046ECD0;
constexpr uint32_t kCustomStride  = 0x1F4;
constexpr uint32_t kCustomRank    = 0x11C;
constexpr uint32_t kCustomName    = 0x134;

void write_hud(const Fight& f, uint32_t frame)
{
    if (!f.hud) return;
    const uint32_t base = rd32(kTocCustomData);
    if (base < 0x10000000u || base >= 0x10760000u) { note("HUD identity: custom data pointer 0x%08X unexpected, left alone", base); return; }
    for (int p = 0; p < 2; p++) {
        const uint32_t b = base + (uint32_t)p * kCustomStride;
        if (!f.names[p].empty()) {
            for (uint32_t i = 0; i < 20; i++) wr16(b + kCustomName + 2 * i, 0);
            for (size_t i = 0; i < f.names[p].size() && i < 16; i++) {
                const unsigned char c = (unsigned char)f.names[p][i];
                wr16(b + kCustomName + 2 * (uint32_t)i, (uint16_t)(c >= 0x20 && c < 0x7F ? c : '?'));
            }
        }
        if (f.rank[p] >= 0) wr8(b + kCustomRank, (uint8_t)f.rank[p]);
    }
    note("frame %u: HUD identity: P1 '%s' rank %d, P2 '%s' rank %d", frame, f.names[0].c_str(), f.rank[0],
         f.names[1].c_str(), f.rank[1]);
}

/* ---- status / result files ------------------------------------------------ */
const char* g_state_name = "boot";
uint32_t g_match = 0;
int g_last_winner = -2; int g_last_score[2] = { 0, 0 };

/* Persistent game (T5_CTL_DIR): the control channel's state */
bool g_ctl = false;
bool g_session = false;          /* a netplay session is set up (persistent game) */
uint32_t g_sessions = 0;
std::string g_session_key;       /* T5_NET_MODE|PORT|PEER|KEY|SEED of that session: a "fight" with the same is a rematch in it */
std::string g_ctl_match;         /* the command's match id of the fight being set up / played */
std::string g_ctl_error;         /* why the last session ended by itself; cleared by the next command */
bool g_after_match = false;      /* the session has played a match (state "result" while it waits) */
bool g_pending_cmd = false;      /* a "fight" waiting to be set up (persistent game) */

/* The match is played over netplay: always with T5_NET_MODE; in a persistent
 * game only while a session is set up. */
bool session_netplay() { return netplay_on() && (!g_ctl || g_session); }

void write_text(const std::string& path, const std::string& text)
{
    if (path.empty()) return;
    const std::string tmp = path + ".tmp";
    if (FILE* fp = fopen(tmp.c_str(), "wb")) {
        fwrite(text.data(), 1, text.size(), fp);
        fclose(fp);
        /* the launcher may be reading the file this very moment (Windows refuses the replace then) */
        for (int i = 0; i < 20 && !MoveFileExA(tmp.c_str(), path.c_str(), MOVEFILE_REPLACE_EXISTING); i++) Sleep(1);
    }
}

void ctl_report(uint32_t f)
{
    if (!g_ctl) return;
    const std::string st = g_state_name;
    const char* c;
    if (st == "boot") c = "boot";
    else if (st == "title" || st == "reset" || st == "leave") c = g_pending_cmd ? "connecting" : (g_ctl_error.empty() ? "idle" : "error");
    else if (st == "select" || st == "stage") c = "connecting";
    else if (st == "loading") c = "loading";
    else if (st == "fight") c = "fight";
    else if (st == "over") c = "result";
    else c = !g_ctl_error.empty() ? "error" : (g_session && g_after_match) ? "result" : "idle";
    ctl_state(c, f, g_ctl_match, g_ctl_error.empty() ? nullptr : g_ctl_error.c_str(), g_sessions);
}

void status(const char* state, uint32_t f)
{
    g_state_name = state;
    note("frame %u: state %s", f, state);
    ctl_report(f);
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
    if (g_result_file.empty() || session_netplay()) return;   /* netplay writes it when it owns the match */
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
    if (g_fight_file.empty() || g_ctl) return false;   /* a persistent game takes its fights from the control channel */
    FILE* fp = fopen(g_fight_file.c_str(), "rb");
    if (!fp) return false;
    char line[512] = {};
    fgets(line, sizeof line, fp);
    fclose(fp);
    const std::string done = g_fight_file + ".done";
    remove(done.c_str());
    MoveFileExA(g_fight_file.c_str(), done.c_str(), MOVEFILE_REPLACE_EXISTING);
    note("next fight from %s: %s", g_fight_file.c_str(), line);
    return parse_fight(line, out);
}

/* ---- the driver ----------------------------------------------------------- */
/* Reset: towards a fresh select screen (persistent game, before a new
 * opponent) -- through the title once after a fight, else by restarting the
 * select screen. Leave: out of a fight whose session ended (persistent game). */
enum class Ph { Boot, Title, Select, Stage, WaitGame, Fight, Over, Neutral, Reset, Leave };
Ph g_ph = Ph::Boot;
uint32_t g_ph_frame = 0;        /* frame the phase began */
uint32_t g_title_seen = UINT32_MAX;
uint32_t g_fight_frame = 0;     /* frame the fight (game mode) started */
bool g_result_done = false;
bool g_over_clear = false;      /* kMatchOver was 0 in this fight: the previous match's flag has been reset */
bool g_held = false;            /* the pads are held neutral until the next select (the match is decided) */
bool g_intro_hold = false;      /* the pads are held through the fight's loading and intros (netplay) */
uint32_t g_decided = 0;         /* frame the match was decided (hold_pads) */
bool g_fresh = false;           /* the select screen was entered from the title and no fight was driven on it since */
bool g_mode_asked = false;      /* Reset / Leave: the mode request is out */
bool g_wait_setup = false;      /* WaitGame: the fight's setup is written (FIGHT START waits for the game mode's phase 7) */
bool g_game_seen = false;       /* the game mode ran since the last trip to the title (a fight, or part of one) */
bool g_restart_low = false;     /* Reset by a select restart: the select screen has gone through its set-up again */
uint32_t g_restart_frame = 0;   /* ... and the frame start VS was called at the select screen */
ULONGLONG g_ph_ms = 0;          /* wall time the phase began (the stuck check) */
uint32_t g_stuck_s = 60;        /* T5_DF_STUCK_SECONDS: a reset / leave that gets nowhere in this long ends the process */
CtlCmd g_cmd;                   /* the pending "fight" (g_pending_cmd) */
bool g_cmd_rematch = false;
bool g_reset_titles = true;     /* T5_DF_RESET=0: a new opponent starts from the select screen as it is */
uint32_t g_stage_wait = 30;     /* T5_DF_STAGE_WAIT: frames from both fighters confirmed to the first stage confirm (was 90) */
constexpr uint32_t kFnModeRequest = 0x0025DA54; /* (mode, param): the mode manager's request */

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

/* From the moment a match is decided until the driver's next select, the game
 * reads both pads as neutral: mashing through the KO and the win pose otherwise
 * reaches the select screen the game returns to, picks fighters there and
 * starts the game's own next VS battle ("VS BATTLE 2", the Champion/Challenger
 * round), and the next fight never starts (dry run; build/dp mash runs). Under
 * lockstep this is the local slot's exchanged input (each PC holds its own,
 * from the same game frame on both); offline it is the module's own pad
 * override. The driver's presses still get through (press()). */
bool g_hold = true;              /* T5_DF_HOLD=0: pads stay live after the match (the old behaviour, for comparisons) */
void hold_pads(uint32_t f, const char* why)
{
    if (!g_hold) { if (!g_held) g_decided = f; g_held = true; return; }
    for (int p = 0; p < 2; p++) { g_press[p].active = false; inject(p, true, 0); }
    if (!g_held) { note("frame %u: pads held neutral (%s)", f, why); g_decided = f; }
    g_held = true;
}

/* With the pads held the game would play the whole KO replay and win pose
 * (~850 frames, mash2). The driver skips them like a player would, from the
 * same game state on both PCs: one press of g_skip_button every 20 frames from
 * 40 frames after the decision, until the game asks for the select mode. Each
 * press is over before the game reacts to it with the mode change, so none
 * reaches the select screen. T5_DF_SKIP=0: no skipping. */
bool g_skip = true;
uint16_t g_skip_button = B_START;     /* T5_DF_SKIP_BUTTON (hex); CROSS does not skip the replay (mash3) */
void post_match_skip(uint32_t f)
{
    if (!g_skip || !g_held || mode_cur() != kModeGame || mode_next() == kModeSelect) return;
    if (f < g_decided + 40 || (f - g_decided) % 20 != 0 || !press_idle(0) || !press_idle(1)) return;
    for (int p = 0; p < 2; p++) if (drives(p)) press(p, g_skip_button, f);
}

void set_phase(Ph ph, const char* name, uint32_t f) { g_ph = ph; g_ph_frame = f; g_ph_ms = GetTickCount64(); g_mode_asked = false; status(name, f); }
/* The select screen takes input for the players this PC drives: the select
 * mode, its state 3, and every record this PC drives still "choosing". Under
 * lockstep (a rematch) that is this PC's own player only. The peer's game may
 * have taken its rematch command earlier and its player be on the way or
 * confirmed already -- its presses come through the exchange -- so P1's record
 * says nothing about this PC's readiness. Waiting for P1's record to read 3
 * (the old test) never ended on P2 when P1 had confirmed before P2's command
 * came: no FIGHT START, both games at the select screen for good (1.0.0, room
 * "JinFury vs Wishin", rematch in session 2; tools/fight_flow_test.py
 * --same-chars --skew 1.5: the rematch keeps the characters, P1's cursor sits on
 * its cell and confirms within ~10 frames). */
bool select_live()
{
    if (mode_cur() != kModeSelect || rd32(kSelectState) < 3) return false;
    for (int p = 0; p < 2; p++)
        if (drives(p) && rd8(rec(p) + kRecState) != 3) return false;
    return true;
}

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
    if (g_cfg.stage >= 0 || !session_netplay()) return;
    uint32_t seed = 0;
    if (const char* v = sess_env("T5_NET_SEED")) seed = (uint32_t)strtoul(v, nullptr, 0);
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
    g_held = false;
    g_fresh = false;
    for (int p = 0; p < 2; p++) g_press[p].active = false;
    resolve_stage(false);
    for (int p = 0; p < 2; p++) {
        const int c = cell_of(g_cfg.chr[p]);
        note("player %d: %s (id %d) -> cell %d, color %d", p + 1, kName[g_cfg.chr[p]], g_cfg.chr[p], c, g_cfg.color[p]);
    }
    note("stage %d, rounds %d", g_cfg.stage, g_cfg.rounds);
    set_phase(Ph::Select, "select", f);
}

/* ---- persistent game: sessions from the control channel ------------------------ */
const char* const kSessionVars[] = { "T5_NET_MODE", "T5_NET_PORT", "T5_NET_PEER", "T5_NET_KEY", "T5_NET_SEED" };

std::string session_key()
{
    std::string k;
    for (const char* v : kSessionVars) {
        const char* x = sess_env(v);
        k += x ? x : "";
        k += '|';
    }
    return k;
}

/* The command's fight line and the files of this match (process mode has them
 * from boot; here every command brings its own). */
bool take_fight_env(const CtlCmd& c, bool new_opponent)
{
    if (const char* r = sess_env("T5_NET_RESULT_FILE")) g_result_file = r;
    if (const char* st = sess_env("T5_DF_STATUS_FILE")) g_status_file = st;
    Fight nf = g_cfg;
    if (new_opponent) { nf.names[0].clear(); nf.names[1].clear(); nf.rank[0] = nf.rank[1] = -1; nf.hud = false; }
    parse_hud(nf, sess_env("T5_HUD_NAMES"), sess_env("T5_HUD_RANKS"), false);
    const char* line = sess_env("T5_FIGHT");
    if (!line || !parse_fight(line, nf)) {
        note("control command %u: no usable T5_FIGHT ('%s')", c.seq, line ? line : "");
        return false;
    }
    if (!c.match.empty()) nf.match = c.match;
    else if (const char* m = sess_env("T5_NET_MATCH")) nf.match = m;
    g_cfg = nf;
    return true;
}

/* A new opponent: a new netplay session from the command's env, then the fight
 * from a fresh select screen. */
void start_session_fight(uint32_t f)
{
    g_pending_cmd = false;
    ctl_apply_env(g_cmd);
    g_session = t5_netplay_session_begin() != 0;
    g_sessions++;
    g_session_key = session_key();
    g_after_match = false;
    g_ctl_error.clear();
    g_ctl_match = g_cmd.match;
    if (!take_fight_env(g_cmd, true)) {
        g_ctl_error = "bad_fight";
        set_phase(Ph::Neutral, "neutral", f);
        return;
    }
    note("frame %u: session %u: %s, match %s", f, g_sessions, g_session ? "netplay set up, handshake running" : "no netplay (offline fight)",
         g_cfg.match.c_str());
    begin_select(f);
}

/* The next match against the same opponent, in the running session (like a
 * T5_FIGHT_FILE line in process mode). */
void start_rematch(uint32_t f)
{
    g_pending_cmd = false;
    ctl_apply_env(g_cmd);
    g_ctl_error.clear();
    g_ctl_match = g_cmd.match;
    if (!take_fight_env(g_cmd, false)) { set_phase(Ph::Neutral, "neutral", f); return; }
    note("frame %u: rematch in session %u, match %s", f, g_sessions, g_cfg.match.c_str());
    begin_select(f);
}

/* A played game must meet a fresh one in step. What a match leaves behind in
 * the hashed match state (the fight block, unused third/fourth fighter blocks,
 * effect records) is zero in a game that has never fought, and the next fight
 * does not overwrite all of it: a persistent game that had played met a just
 * started one with 1,662 of 1,662 frames mismatching (run dm2; 0x100902F8..,
 * 0x10090A3C, 0x10090C08, 0x100A3B90.. leftover vs zero), the fight itself the
 * same. So the areas are copied when the game first reaches the title at boot
 * and put back when a persistent game returns to the title for a new opponent
 * (Reset): from there both games run the same title -> start VS -> select ->
 * fight path from the same bytes. T5_DF_FRESH=0: off; T5_DF_FRESH_RANGES:
 * "addr:len,..." (hex), default the netplay hash's game areas. */
struct Area { uint32_t addr, len; std::vector<uint8_t> boot; };
std::vector<Area> g_fresh_areas;
std::vector<Area> g_scan_areas;  /* T5_DF_FRESH_SCAN=addr:len,...: compared with boot at every restore, not restored (diagnostics) */
bool g_fresh_on = true;
bool g_fresh_taken = false;
bool g_restore_due = false;      /* a reset reached the title: the boot state goes back once it has settled */
uint32_t g_fresh_at = 30;        /* T5_DF_FRESH_AT (tests): frames into the settled title the boot state goes back
                                  * (30 = right before start VS, where the boot state was taken; 0 = at once) */
void fresh_take(uint32_t f)
{
    if (!g_ctl || !g_fresh_on || g_fresh_taken) return;
    g_fresh_taken = true;
    size_t n = 0;
    for (Area& a : g_fresh_areas) { a.boot.assign(vm_base + a.addr, vm_base + a.addr + a.len); n += a.len; }
    for (Area& a : g_scan_areas) a.boot.assign(vm_base + a.addr, vm_base + a.addr + a.len);
    note("frame %u: boot state of %zu area(s), %zu bytes, kept for later opponents", f, g_fresh_areas.size(), n);
}
bool g_fresh_log = false;        /* T5_DF_FRESH_LOG=1: list the words the restore changes */
void fresh_restore(uint32_t f)
{
    if (!g_fresh_taken) return;
    size_t changed = 0, listed = 0;
    for (const Area& a : g_fresh_areas) {
        for (uint32_t i = 0; i < a.len; i++) if (vm_base[a.addr + i] != a.boot[i]) changed++;
        if (g_fresh_log)
            for (uint32_t i = 0; i + 4 <= a.len && listed < 400; i += 4)
                if (memcmp(vm_base + a.addr + i, a.boot.data() + i, 4)) {
                    listed++;
                    note("frame %u: restore 0x%08X: %02X%02X%02X%02X -> %02X%02X%02X%02X", f, a.addr + i,
                         vm_base[a.addr + i], vm_base[a.addr + i + 1], vm_base[a.addr + i + 2], vm_base[a.addr + i + 3],
                         a.boot[i], a.boot[i + 1], a.boot[i + 2], a.boot[i + 3]);
                }
        memcpy(vm_base + a.addr, a.boot.data(), a.len);
    }
    for (const Area& a : g_scan_areas) {   /* runs of differing words (gap <= 2 words) */
        int runs = 0;
        for (uint32_t i = 0; i + 4 <= a.len && runs < 400;) {
            if (!memcmp(vm_base + a.addr + i, a.boot.data() + i, 4)) { i += 4; continue; }
            uint32_t e = i + 4, k = 1;
            for (uint32_t j = e; j + 4 <= a.len && j <= e + 8; j += 4)
                if (memcmp(vm_base + a.addr + j, a.boot.data() + j, 4)) { e = j + 4; k++; }
            note("frame %u: scan 0x%08X..0x%08X (%u words) now %08X boot %08X", f, a.addr + i, a.addr + e, k,
                 rd32(a.addr + i), _byteswap_ulong(*(const uint32_t*)(a.boot.data() + i)));
            runs++;
            i = e;
        }
    }
    note("frame %u: the match state areas are back as at boot (%zu bytes differed)", f, changed);
}

/* Out of whatever runs now, towards a fresh select screen: a fight is left
 * (mode request 6), a select screen is left for the title (request 1). */
void go_reset(uint32_t f)
{
    hold_pads(f, "the session ended");
    if (g_ph == Ph::Fight || g_ph == Ph::WaitGame || (g_ph == Ph::Stage && mode_cur() == kModeGame)) {
        set_phase(Ph::Leave, "leave", f);
        return;
    }
    if (g_ph == Ph::Boot || g_ph == Ph::Title || g_ph == Ph::Reset || g_ph == Ph::Leave) return;   /* on its way already */
    if (!g_reset_titles && (g_ph == Ph::Neutral || g_ph == Ph::Over)) return;
    set_phase(Ph::Reset, "reset", f);
}

void end_session(uint32_t f, const char* why, bool lost)
{
    if (!lost) t5_netplay_session_end(why);    /* (a lost session was ended by the netplay hooks) */
    g_session = false;
    g_after_match = false;
    if (lost) g_ctl_error = why;
    note("frame %u: session %u ended (%s)%s", f, g_sessions, why, lost ? " by itself" : "");
    go_reset(f);
    ctl_report(f);
}

/* Commands and session ends, every frame (cmd.json is looked at every 6 frames
 * while the game waits, every 30 otherwise). */
void persistent_frame(uint32_t f)
{
    if (const char* lost = t5_netplay_take_session_lost()) end_session(f, lost, true);
    CtlCmd c;
    const bool waiting = g_ph == Ph::Neutral || g_ph == Ph::Over || g_ph == Ph::Reset || g_ph == Ph::Title;
    if (!ctl_poll(c, f, waiting ? 6 : 30)) return;
    if (c.cmd == "quit") {
        note("frame %u: quit", f);
        t5_netplay_session_end("quit");
        ctl_state("quit", f, g_ctl_match, nullptr, g_sessions);
        fflush(stdout); fflush(stderr);
        TerminateProcess(GetCurrentProcess(), 0);
        return;
    }
    if (c.cmd == "idle") {
        g_pending_cmd = false;
        g_ctl_error.clear();
        if (g_session) end_session(f, "idle", false);
        else { go_reset(f); ctl_report(f); }
        return;
    }
    if (c.cmd != "fight") { note("control command %u: '%s' unknown, ignored", c.seq, c.cmd.c_str()); return; }
    g_cmd = c;
    g_pending_cmd = true;
    g_ctl_error.clear();
    /* the same session (a rematch) when the launcher says so or the netplay variables are the session's */
    std::string key;
    for (const char* v : kSessionVars) {
        std::string x;
        for (const auto& kv : c.env) if (!_stricmp(kv.first.c_str(), v)) x = kv.second;
        key += x + '|';
    }
    g_cmd_rematch = g_session && (c.rematch || key == g_session_key) && (g_ph == Ph::Over || g_ph == Ph::Neutral);
    if (!g_cmd_rematch) {
        if (g_session) end_session(f, "a new opponent", false);
        else if (g_ph != Ph::Neutral || !g_fresh) go_reset(f);
    }
    ctl_report(f);
}

/* A reset has a fresh select screen: the pending "fight" (a new session)
 * starts on it, else the game waits there. */
void reset_done(uint32_t f)
{
    if (g_pending_cmd && !g_cmd_rematch) start_session_fight(f);
    else set_phase(Ph::Neutral, "neutral", f);
}

/* A reset / leave that gets nowhere (the game mode ignoring the request to
 * leave a fight whose loading hung: release dry run 0.1.6, "leave: waiting in
 * mode 4" for 3.5 minutes) cannot become a clean neutral state any more: the
 * process ends (exit code 6) and the launcher starts a new game for the next
 * match (match_driver: a persistent game that is not running is started again). */
uint32_t g_leave_phase = 10;    /* T5_DF_LEAVE_PHASE (diagnostics): a fight is left once its phase word is past this */
ULONGLONG g_stuck_dumped = 0;   /* g_ph_ms of the phase whose wait was dumped */
void stuck_check(uint32_t f)
{
    const bool waiting = g_ph == Ph::Leave || g_ph == Ph::Reset || (g_ph == Ph::Title && g_fresh_taken);
    if (!g_ctl || !g_stuck_s || !waiting) return;
    const ULONGLONG ms = GetTickCount64() - g_ph_ms;
    if (ms >= (ULONGLONG)g_stuck_s * 500 && g_stuck_dumped != g_ph_ms) {   /* half way: what it waits on */
        g_stuck_dumped = g_ph_ms;
        note("frame %u: %s for %u s (mode %u, next %u, phase word %u):", f, g_state_name, (unsigned)(ms / 1000),
             mode_cur(), mode_next(), rd32(kSelectState));
        stuck_dump(f);
    }
    if (ms < (ULONGLONG)g_stuck_s * 1000) return;
    note("frame %u: STUCK: %s for %u s (mode %u, next %u, phase word %u) -- the game ends, the launcher starts a fresh one",
         f, g_state_name, g_stuck_s, mode_cur(), mode_next(), rd32(kSelectState));
    ctl_state("error", f, g_ctl_match, "stuck", g_sessions);
    fflush(stdout); fflush(stderr);
    TerminateProcess(GetCurrentProcess(), 6);
}

void fight_on_frame(uint32_t f)
{
    if (!g_configured) return;
    service_presses(f);
    const uint32_t mgr = mode_manager();
    if (!mgr) return;
    const uint32_t mode = mode_cur();
    if (mode == kModeGame) g_game_seen = true;
    if (g_ctl) persistent_frame(f);
    stuck_check(f);

    switch (g_ph) {
    case Ph::Boot:
        if (mode == kModeTitle) { g_title_seen = f; set_phase(Ph::Title, "title", f); }
        break;
    case Ph::Title:
        /* the title mode needs a few frames of its own init; 30 was verified.
         * Counted from the first frame the title runs with no mode change
         * pending (a request made a frame ago may still be on its way). */
        if (mode != kModeTitle || mode_next() != kModeNone) { g_title_seen = f; break; }
        if (g_restore_due && f >= g_title_seen + g_fresh_at) { g_restore_due = false; fresh_restore(f); }
        if (f >= g_title_seen + 30) {
            /* the boot state is taken (at boot) and put back (after a reset) at
             * the same point: the title settled, right before start VS */
            fresh_take(f);
            note("frame %u: start VS battle (func_0004E9DC(4, 3)) from the title mode", f);
            gcall(kFnStartGame, 4, 3);
            g_fresh = true;
            g_game_seen = false;
            if (g_ctl) {
                if (g_pending_cmd && !g_cmd_rematch) start_session_fight(f);
                else set_phase(Ph::Neutral, "neutral", f);
            } else if (!g_cfg.valid && !read_fight_file(g_cfg)) {
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
                    /* Kuma and Panda share a cell: a punch button (SQUARE) picks
                     * Kuma, a kick button (CROSS/CIRCLE) Panda -- so Kuma cannot
                     * be confirmed with CROSS like everyone else (it gave Panda). */
                    const uint16_t confirm = g_cfg.chr[p] == 12 ? g_alt_button
                                           : g_cfg.chr[p] == 11 ? (uint16_t)B_SQUARE : (uint16_t)B_CROSS;
                    press(p, confirm, f);
                }
            } else if (st == 9) {
                press(p, g_cfg.color[p] == 2 ? B_TRIANGLE : B_CROSS, f);
            }
        }
        if (all_done) set_phase(Ph::Stage, "stage", f);
        break; }
    case Ph::Stage:
        if (mode == kModeGame) { g_wait_setup = false; set_phase(Ph::WaitGame, "loading", f); break; }
        /* The stage confirm writes the panel's own pick (random, different on
         * the two PCs: fd_rematch showed 0x1d vs 0x11 for 50 frames in
         * lockstep) to 0x1008F088, two frames before the select state turns 4.
         * Ours replaces it at the top of every frame of this phase, before the
         * frame's state hash; the phase begins at the same frame on both PCs
         * (both players' records done), and the panel only writes the word. */
        if (g_cfg.stage >= 0 && rd32(kStageId) != (uint32_t)g_cfg.stage) wr32(kStageId, (uint32_t)g_cfg.stage);
        if (rd32(kSelectState) >= 4) break;                 /* stage confirmed, the mode switch follows */
        if (f >= g_ph_frame + g_stage_wait && press_idle(0) && press_idle(1) && ((f - g_ph_frame - g_stage_wait) % 30) == 0) {
            for (int p = 0; p < 2; p++) if (drives(p)) press(p, B_CROSS, f);   /* confirm whatever stage the panel shows */
        }
        break;
    case Ph::WaitGame:
        /* first frame in the game mode: apply the setup the loader reads */
        if (!g_wait_setup) {
            g_wait_setup = true;
            resolve_stage(true);
            wr8(kRoundsToWin, (uint8_t)g_cfg.rounds);
            if (session_netplay() && !g_cfg.match.empty()) t5_netplay_set_match(g_cfg.match.c_str());
            write_hud(g_cfg, f);
        }
        if (g_cfg.stage >= 0) wr32(kStageId, (uint32_t)g_cfg.stage);
        /* FIGHT START (lockstep frame 0 is the next frame) at the first frame the
         * game mode's own phase word has reached 7 -- not at the first frame the
         * mode manager says "game": a game that has played and a fresh one
         * switch modes at a different point of the game mode's set-up (phase 0,
         * 2, 7, 8 one frame each). Started at "mode 4", netplay frame 1 found
         * the played game at phase 7 and the fresh one at 8 (reset-fix run
         * dump1); started at phase 7 both are at the same set-up frame (run
         * bss_stall: the four hashed areas equal at frame 1). The end of the
         * loading stays a sync point as before. The pads stay held meanwhile
         * (the driver's injection is still on). */
        if (mode == kModeGame && rd32(kSelectState) < 7 && f < g_ph_frame + 60) break;
        g_wait_setup = false;
        for (int p = 0; p < 2; p++) inject(p, false, 0);   /* (before lockstep: the hooks' own injection, cleared) */
        g_intro_hold = false;
        g_match++;
        g_over_clear = false;
        g_held = false;
        g_fight_frame = f;
        note("frame %u: FIGHT START match %u%s%s: %s vs %s, stage %d (field 0x%X), rounds %u, game type %u",
             f, g_match, g_cfg.match.empty() ? "" : " id ", g_cfg.match.c_str(), kName[g_cfg.chr[0]], kName[g_cfg.chr[1]],
             g_cfg.stage, rd32(kStageId), rd8(kRoundsToWin), rd32(kConfig));
        if (session_netplay()) { t5_netplay_start(); note("frame %u: t5_netplay_start() called (lockstep frame 0 is the next frame)", f); }
        set_phase(Ph::Fight, "fight", f);
        break;
    case Ph::Fight: {
        if (mode != kModeGame) {
            note("frame %u: left the game mode (mode %u) without a result", f, mode);
            hold_pads(f, "left the fight");
            set_phase(Ph::Over, "over", f);
            break;
        }
        {   /* the game mode's start, loading and intros (phase 0..12) take no input under netplay: held, released
             * for the fight (17). The rollback loop does the same for its intro frames; in lockstep a faster PC
             * otherwise runs the last loading frames before the scene barrier with input the other never sees */
            /* only once lockstep runs: then inject() is this PC's exchanged input (before, it would be the
             * hooks' own override of the game's pad read, which the release below could not clear) */
            const bool intro = rd32(kSelectState) <= 12;
            if (!g_held && session_netplay() && t5_netplay_lockstep_active() && intro != g_intro_hold) {
                g_intro_hold = intro;
                for (int p = 0; p < 2; p++) inject(p, intro, 0);
            }
        }
        const uint8_t over0 = rd8(kMatchOver);
        if (!over0) g_over_clear = true;
        const uint8_t over = g_over_clear ? over0 : 0;   /* a rematch starts with the last match's flag still set */
        if (over && !g_held) hold_pads(f, "the match is decided");
        post_match_skip(f);
        uint8_t w1 = rd8(kWinsP1), w2 = rd8(kWinsP2);
        if (over && w1 == 0 && w2 == 0 && rd8(kWinnerIdx) <= 1) {   /* the tallies stay 0 here: use the winner byte */
            const uint8_t r = rd8(kRoundsToWin) ? rd8(kRoundsToWin) : 1;
            if (rd8(kWinnerIdx) == 0) w1 = r; else w2 = r;
        }
        if (over && (w1 || w2) && !g_result_done) {
            g_result_done = true;
            const int winner = w1 > w2 ? 0 : w2 > w1 ? 1 : -1;
            g_last_winner = winner; g_last_score[0] = w1; g_last_score[1] = w2;
            g_after_match = true;
            note("frame %u: MATCH OVER match %u after %u frames: P1 %u - P2 %u, winner %s", f, g_match, f - g_fight_frame, w1, w2,
                 winner < 0 ? "none" : winner == 0 ? "P1" : "P2");
            write_result(winner, w1, w2);
            set_phase(Ph::Over, "over", f);
        }
        break; }
    case Ph::Over:
        /* the game shows the win pose and returns to character select by itself */
        post_match_skip(f);
        if (select_live()) {
            if (g_ctl) {
                if (g_pending_cmd && g_cmd_rematch) start_rematch(f);
                else if (g_pending_cmd) { set_phase(Ph::Neutral, "neutral", f); go_reset(f); }
                else set_phase(Ph::Neutral, "neutral", f);
                break;
            }
            g_cfg.valid = false;
            if (read_fight_file(g_cfg)) begin_select(f);
            else set_phase(Ph::Neutral, "neutral", f);
        } else if (mode != kModeGame && mode != kModeSelect && (f - g_ph_frame) % 300 == 0) {
            note("frame %u: waiting in mode %u for character select", f, mode);
        }
        break;
    case Ph::Neutral:
        if (g_ctl) {
            if (!g_pending_cmd) break;
            if (g_cmd_rematch) { if (select_live()) start_rematch(f); }
            else if (g_fresh || !g_reset_titles) { if (select_live()) start_session_fight(f); }
            else go_reset(f);
            break;
        }
        if ((f - g_ph_frame) % 15 == 0 && read_fight_file(g_cfg)) {
            if (mode == kModeSelect) begin_select(f);
            else note("frame %u: fight requested but the game is in mode %u", f, mode);
        }
        break;
    case Ph::Reset:
        /* Towards a fresh select screen, whatever the last opponent left
         * (battle config, VS counters, cursors). Nothing is done while a mode
         * change is still under way (an "idle" a few frames after start VS
         * found the title with the select mode requested: the boot state went
         * back under the select mode's set-up, NULL accesses from then on).
         *
         * The title is visited at most once per fight: the second visit to
         * the title mode after a game mode, with no game mode in between,
         * corrupts the game -- its set-up initialises a model from a stale
         * pointer into the game heap (a count of 0x02120420), asks for 138 MB,
         * gets NULL and clears guest memory from there on, the vblank
         * handler's descriptor (0x4635A8) and the code below 0x08481084 with
         * it (release dry run 0.1.6: a session lost in the fight's loading,
         * the reset to the title, then the launcher's "idle" -> a second
         * visit; reproduced offline every time, also after a match played to
         * its end, also without the boot-state restore and with the title's
         * autosave suppressed). So after a fight: the title (and the boot
         * state) as before; without one the select screen is restarted in
         * place by the same start-VS routine (the select mode sets itself up
         * again: phase 0 -> 3, the VS config filled again), or left as it is
         * when it is fresh already. */
        if (mode == kModeTitle && mode_next() == kModeNone) {
            g_title_seen = f; g_restore_due = g_fresh_taken; set_phase(Ph::Title, "title", f); break;
        }
        /* a fight the driver did not see decided (the stage confirm raced the
         * reset): out of it like out of a fight whose session ended */
        if (mode == kModeGame && mode_next() == kModeNone && !g_result_done) { set_phase(Ph::Leave, "leave", f); break; }
        post_match_skip(f);                                 /* still in the win pose: skip it as in Over */
        if (mode == kModeSelect && mode_next() == kModeNone) {
            const uint32_t sel = rd32(kSelectState);
            if (g_mode_asked && !g_game_seen) {             /* the select restart is under way */
                if (sel < 3) g_restart_low = true;
                if (g_restart_low && select_live()) {
                    note("frame %u: select screen restarted", f);
                    g_fresh = true;
                    reset_done(f);
                } else if (!g_restart_low && f > g_restart_frame + 120) {
                    /* never seen in the tests; the title is no way out here (no fight since it) */
                    note("frame %u: the select screen did not restart -- taken as it is", f);
                    reset_done(f);
                }
            } else if (!g_mode_asked && sel == 3) {
                if (g_game_seen) {
                    g_mode_asked = true;
                    gcall(kFnModeRequest, kModeTitle, 0);
                    note("frame %u: to the title for a fresh select screen (mode request 1)", f);
                } else if (g_fresh) {                       /* entered from the title, untouched: wait for its records */
                    if (select_live()) {
                        note("frame %u: the select screen is fresh already (no fight since the title)", f);
                        reset_done(f);
                    }
                } else {
                    g_mode_asked = true; g_restart_low = false; g_restart_frame = f;
                    gcall(kFnStartGame, 4, 3);
                    note("frame %u: select screen restart (func_0004E9DC(4, 3) at the select screen; no fight since the title)", f);
                }
            }
        }
        if ((f - g_ph_frame) % 300 == 0 && f > g_ph_frame) note("frame %u: reset: waiting in mode %u", f, mode);
        break;
    case Ph::Leave:
        /* out of a fight whose session ended: the game's own way back to select --
         * once the fight's loading is over (phase word 11, the intros' first
         * frame; at once when the session ended later). Not in the middle of the
         * loading (loads in flight), and not after the intros either: a fight
         * left at "Fight!" -- intros and the Fight! frame run by this game alone
         * -- left something outside the boot-state copy that made the next match
         * against a fresh game fight apart for its first 200-260 frames (reset-
         * fix cycle test, cycles 9 and 10: Kazuya vs Heihachi and Asuka vs Law
         * after a session lost in the loading; also with the whole data section
         * copied back; 0 mismatching frames when left here or at once). A
         * loading that hangs never takes the request (the dry run's host:
         * stuck_check() ends such a game). */
        if (mode == kModeSelect) { set_phase(Ph::Reset, "reset", f); break; }
        if (!g_mode_asked && mode == kModeGame && rd32(kSelectState) <= g_leave_phase) {
            if (f == g_ph_frame) note("frame %u: leave: the fight's loading first (phase %u)", f, rd32(kSelectState));
            break;
        }
        if (!g_mode_asked && mode == kModeGame) {
            g_mode_asked = true;
            gcall(kFnModeRequest, kModeSelect, 0);
            note("frame %u: leaving the fight (mode request 6)", f);
        }
        if ((f - g_ph_frame) % 300 == 0 && f > g_ph_frame) note("frame %u: leave: waiting in mode %u", f, mode);
        break;
    }
}

bool fight_configured() { return g_configured; }

} // namespace df

/* tests (T5_NET_SCRIPT_FIGHT): the scripted fight input applies only in a fight */
extern "C" int t5_df_in_fight(void) { return df::g_ph == df::Ph::Fight ? 1 : 0; }

/* The game window was closed (netplay's handler, on the runtime's ticker
 * thread, right before the process ends): a persistent game tells its launcher
 * in state.json (the exit code says the same). */
extern "C" void t5_df_window_closed(void)
{
    if (!df::g_ctl) return;
    df::ctl_state("quit", 0, df::g_ctl_match, "window_closed", df::g_sessions);
}

/* netplay / rollback: the game's mode manager is in the game mode (the fight,
 * its loading and intros, its win pose) -- with the phase word up to 12 that
 * is the intro, which takes no input (rb_net.cpp intro rule, t5_hooks.cpp).
 * Read from guest memory (the tcb pool), so it is game state: the same on
 * both PCs at the same frame, and right inside a re-simulation too. */
extern "C" int t5_df_game_mode(void) { return df::mode_manager() && df::mode_cur() == df::kModeGame ? 1 : 0; }

namespace df {

void fight_init()
{
    const char* fight = getenv("T5_FIGHT");
    const char* file = getenv("T5_FIGHT_FILE");
    g_ctl = ctl_enabled();
    if (!(fight && *fight) && !(file && *file) && !g_ctl) return;
    g_configured = true;
    { const char* r = getenv("T5_DF_RESET"); g_reset_titles = !(r && *r == '0'); }
    { const char* k = getenv("T5_DF_SKIP"); g_skip = !(k && *k == '0'); }
    if (const char* w = getenv("T5_DF_STAGE_WAIT")) g_stage_wait = (uint32_t)atoi(w);
    { const char* r = getenv("T5_DF_FRESH"); g_fresh_on = !(r && *r == '0'); }
    { const char* r = getenv("T5_DF_FRESH_LOG"); g_fresh_log = r && *r == '1'; }
    if (const char* r = getenv("T5_DF_FRESH_AT")) g_fresh_at = (uint32_t)atoi(r);
    if (const char* r = getenv("T5_DF_STUCK_SECONDS")) g_stuck_s = (uint32_t)atoi(r);
    if (const char* r = getenv("T5_DF_LEAVE_PHASE")) g_leave_phase = (uint32_t)atoi(r);
    {
        const char* spec = getenv("T5_DF_FRESH_RANGES");
        if (!spec || !*spec) spec = "1008E000:17000";   /* the fight-state block 0x1008E000..0x100A5000 (reset-fix: leftovers beyond the four hashed areas) */
        for (const char* p = spec; *p;) {
            char* e;
            const uint32_t a = (uint32_t)strtoul(p, &e, 16); if (e == p || *e != ':') break; p = e + 1;
            const uint32_t l = (uint32_t)strtoul(p, &e, 16); if (e == p) break; p = e;
            g_fresh_areas.push_back({ a, l, {} });
            while (*p == ',' || *p == ' ') p++;
        }
    }
    if (const char* spec = getenv("T5_DF_FRESH_SCAN")) {
        for (const char* p = spec; *p;) {
            char* e;
            const uint32_t a = (uint32_t)strtoul(p, &e, 16); if (e == p || *e != ':') break; p = e + 1;
            const uint32_t l = (uint32_t)strtoul(p, &e, 16); if (e == p) break; p = e;
            g_scan_areas.push_back({ a, l, {} });
            while (*p == ',' || *p == ' ') p++;
        }
    }
    { const char* h = getenv("T5_DF_HOLD"); g_hold = !(h && *h == '0'); if (!g_hold) g_skip = false; }
    if (const char* b = getenv("T5_DF_SKIP_BUTTON")) g_skip_button = (uint16_t)strtoul(b, nullptr, 16);
    parse_hud(g_cfg, getenv("T5_HUD_NAMES"), getenv("T5_HUD_RANKS"), false);
    if (file) g_fight_file = file;
    if (const char* r = getenv("T5_NET_RESULT_FILE")) g_result_file = r;
    if (const char* s = getenv("T5_DF_STATUS_FILE")) g_status_file = s;
    if (const char* a = getenv("T5_DF_ALT_BUTTON")) g_alt_button = (uint16_t)strtoul(a, nullptr, 16);
    { const char* t = getenv("T5_DF_TRACE"); g_trace_presses = t && *t == '1'; }
    if (fight && *fight && !g_ctl) parse_fight(fight, g_cfg);
    note("direct fight: %s%s%s", g_cfg.valid ? g_cfg.text.c_str() : g_ctl ? "(persistent game: fights from the control channel)"
                                                                 : "(waiting for T5_FIGHT_FILE)",
         g_fight_file.empty() || g_ctl ? "" : ", next fights from ", g_fight_file.c_str());
    ctl_report(0);
}

} // namespace df
