/*
 * T5DR direct fight -- the match driver (NPUB30009 v01.00; docs/DIRECTFIGHT.md).
 *
 *   T5_FIGHT=p1,p2,stage[,rounds][,p1color,p2color][ match=<id>]
 *       p1/p2   character: id 0-35, 3-letter code (pau, law, ...) or name prefix
 *       stage   stage id, or "random" / -1: without netplay the game's own pick; with
 *               netplay a stage derived from the shared seed (the game's pick happens
 *               on each PC on its own and would differ)
 *       rounds  rounds to win (default T5_NET_ROUNDS, else 3)
 *       colors  1 or 2 (kept for old lines: the second confirm is the handicap bar,
 *               not a costume; the costume is the button that confirms the character)
 *       match=  the lobby's match id (any position, key=value): goes into the result
 *               file so the launcher can tell this match's result from an old one
 *       pick=N  in-game select (docs/DIRECTFIGHT.md "Character select in the game"):
 *               each player picks character and costume on the game's own select
 *               screen within N seconds (else p1/p2 of the line, the launcher's
 *               characters); the picks are exchanged over the netplay session
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
 *   4. match over: 0x1008EBD5 != 0, rounds won by each fighter (match_score.h) -> result file.
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
#include "../netplay/match_score.h"   /* a decided match's score: the fighters' round counts */
#include "../netplay/match_rules.h"   /* online training and the health handicap (train=, life=) */

extern "C" void t5_netplay_start(void);
extern "C" int  t5_netplay_lockstep_active(void);
extern "C" int  t5_netplay_match_end_final(void);   /* netplay: the match end seen is final (rollback: every input up to it confirmed) */
extern "C" int  t5_netplay_local_slot(void);
extern "C" void t5_netplay_set_match(const char* id);
extern "C" unsigned t5_netplay_match_seed(void);
extern "C" int  t5_netplay_session_begin(void);
extern "C" void t5_netplay_session_end(const char* why);
extern "C" const char* t5_netplay_take_session_lost(void);
extern "C" void t5_netplay_give_up(const char* reason, const char* text);   /* src/netplay/t5_hooks.cpp: this side ends the session */
extern "C" const char* t5_env(const char* key);
extern "C" void t5_netplay_pick_send(unsigned key, unsigned pick);
extern "C" int  t5_netplay_pick_peer(unsigned key, unsigned* pick);
extern "C" int  t5_netplay_connected(void);
extern "C" void t5_netplay_pause(void);
/* replays (src/netplay/replay.cpp, docs/REPLAYS.md): this match's setup goes into the recording at FIGHT
 * START; a playback takes every match's line from the file and checks the setup against it */
extern "C" void t5_replay_fight_start(unsigned match, const int chr[2], const int btn[2], const int model[2], int stage,
                                      int rounds, int pick, const char* name1, const char* name2,
                                      const unsigned char* costumes, unsigned rules);
extern "C" int  t5_replay_fight_line(unsigned match, char* buf, int size);
/* unlocks (df_unlock.cpp, docs/DIRECTFIGHT.md "Unlocks"): Jinpachi's and the random cell on the select grid
 * (online: the match kind T5_NET_UNLOCKS, a playback: its file); a persistent game's session sets its kind */
extern "C" int  t5_unlock_grid_open(void);
extern "C" int  t5_unlock_online_open(void);
extern "C" int  t5_unlock_set_open(int open);

namespace df {

/* In lockstep (every match after the first under netplay) this PC drives only
 * its own player; the peer's presses arrive through the input exchange. */
bool drives(int p) { return !(netplay_on() && t5_netplay_lockstep_active()) || p == t5_netplay_local_slot(); }

/* ---- guest addresses (NPUB30009 v01.00) ---------------------------------- */
constexpr uint32_t kFnStartGame  = 0x0004E9DC;   /* (game_type, player_mask) -> config + select mode */
constexpr uint32_t kConfig       = 0x1008EBAC;   /* battle config: +0 game type (4 = VS) */
constexpr uint32_t kRoundsToWin  = 0x1008EBD4;   /* u8 */
constexpr uint32_t kLifeP1       = 0x1008EBF4;   /* u32: P1's health handicap in percent (100 after the select's bar) */
constexpr uint32_t kLifeP2       = 0x1008EBF8;   /* u32: P2's; the game mode's set-up scales both fighters' health by them */
constexpr uint32_t kMatchOver    = 0x1008EBD5;   /* u8: non-zero once the match is decided */
constexpr uint32_t kWinsP1       = np::MatchScore::kRoundWinsP1;   /* u8: rounds P1 won (fighter block +0xA1) */
constexpr uint32_t kWinsP2       = np::MatchScore::kRoundWinsP2;   /* u8: rounds P2 won */
constexpr uint32_t kWinnerIdx    = 0x1008EBD6;   /* u8: 0 = P1, 1 = P2, set together with kMatchOver (seen in the dry run) */
constexpr uint32_t kSelectState  = 0x1008F070;   /* select mode: 1,2,3 (choosing), 4 (stage confirmed), 5 (leaving); fight phases after */
constexpr uint32_t kStageId      = 0x1008F088;   /* chosen stage, written at the stage confirm, read by the game-mode loader */
constexpr uint32_t kRecord       = 0x10093F58;   /* per-player select records, 0x78 apart */
constexpr uint32_t kRecordStride = 0x78;
constexpr uint32_t kRecCell      = 0x00;         /* cursor cell */
constexpr uint32_t kRecFace      = 0x08;         /* portrait id under the cursor */
constexpr uint32_t kRecModel     = 0x0C;         /* the picked model id (character + costume; 0xFFFFFFFF until confirmed) */
constexpr uint32_t kRecState     = 0x20;         /* u8: 3 choosing, 9 handicap bar, then done: 0x0C while the other side still
                                                  * chooses (P2; P1 too after a match), then 0x0D (P2) / 0x15 (P1) */
constexpr uint32_t kModeTitle = 1, kModeGame = 4, kModeSelect = 6;
constexpr uint32_t kModeNone = 14;               /* the request's "next" when no mode change is pending */
/* mode manager words (object found by df_hooks.cpp): +0x58 {cur, next, prev, param}, +0x6C the mode's task object */
constexpr uint32_t kMgrNext = 0x5C, kMgrParam = 0x64, kMgrModeObj = 0x6C;

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
 * (cell 24 is skipped) -- unless Jinpachi is offered (the save, or online a
 * match of the "open" kind, df_unlock.cpp): then the top row has 12 cells, the
 * random cell at 24 (column 0) and Jinpachi at 35 (column 11), and every column
 * reaches it. The random cell draws a fighter and costume at its confirm (the
 * record's model is the drawn one; runs off5, off6), Jinpachi's models are
 * 0x52 / 0x53 (runs off3, pair_rb). Measured by walking the cursor
 * (build/df runs p9/p10) and checked against the screen. -1 = not reachable.
 * Cells 28 and 31 are Devil Jin and Feng: the first table had them the other
 * way round, so T5_FIGHT Devil Jin (29) gave Feng and Feng (31) Devil Jin
 * (completeness audit: the select screen's portraits of all 35 ids). */
const int kGrid[36] = {
    23, 18, 1, 6, 3, 33, 34, 14, 8, 0, 21, 27,       /* middle: Anna Marduk Law Hwoarang King Lili Dragunov Heihachi Christie Paul Jack-5 Bruce */
    22, 2, 5, 17, 15, 7, 9, 16, 10, 4, 13, 11,       /* bottom: Roger Lei Nina Steve Kazuya Xiaoyu Jin Lee Julia Yoshimitsu Bryan Kuma */
    -1, 20, 28, 19, 29, 30, 26, 31, 25, 24, 32,      /* top: (Jinpachi) Eddy Baek Mokujin DevilJin Raven Asuka Feng Ganryu Wang ArmorKing */
    -1 };
constexpr int kRandomCell = 24, kJinpachiCell = 35;   /* the open grid's two extra top-row cells (probe runs off3, off5) */
bool grid_open() { return t5_unlock_grid_open() != 0; }
int cell_of(int chr)
{
    if (chr == 35) return grid_open() ? kJinpachiCell : -1;
    for (int c = 0; c < 35; c++) if (kGrid[c] == chr) return c;
    if (chr == 12) return cell_of(11);      /* Panda shares Kuma's cell (a kick button confirms Panda) */
    return -1;
}
/* the character of a cell: -1 none / not on this grid, -2 the random cell */
int char_at(int cell)
{
    if (cell == kJinpachiCell) return grid_open() ? 35 : -1;
    if (cell == kRandomCell) return grid_open() ? -2 : -1;
    return cell >= 0 && cell < 35 ? kGrid[cell] : -1;
}
int cell_row(int c) { return c >= 24 ? 0 : c >= 12 ? 2 : 1; }         /* 0 top, 1 middle, 2 bottom */
int cell_col(int c) { return c >= 24 ? c - 24 : c >= 12 ? c - 12 : c; }

/* ---- configuration ----------------------------------------------------- */
/* HUD identity (docs/DIRECTFIGHT.md "Names and ranks in the HUD"): names[p]
 * empty = the game's own "Unknown", rank[p] < 0 = left as the game has it. */
/* btn[p]: the button that confirms side p's character (1-4, btn_bits(); 0 = the
 * default: Cross, Square for Kuma, T5_DF_ALT_BUTTON for Panda) -- an in-game pick's
 * costume. pick: seconds for the in-game select (0 = the line's characters). */
struct Fight { int chr[2] = { -1, -1 }; int stage = -1; int rounds = 3; int color[2] = { 1, 1 }; bool valid = false;
               std::string text, match; std::string names[2]; int rank[2] = { -1, -1 }; bool hud = false;
               int btn[2] = { 0, 0 }; int pick = 0;
               np::MatchRules rules; };   /* train=1, life=P1|P2 (match_rules.h) */
std::string g_fight_file, g_status_file, g_result_file;
Fight g_cfg;            /* the fight being set up / fought */
bool g_configured = false;
bool g_replay = false;  /* T5_NET_MODE=replay: the fights come from the replay file, nobody picks on the select screen */
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

int g_pick_default = 0;   /* T5_DF_PICK=<seconds>: the in-game select for fight lines without pick= (tests) */
/* T5_DF_RULES="train=1 life=70|100": the rules for fight lines without train= / life= (tests; the launcher looks for
 * this name in the game binary to know the build can play training rooms and the health handicap) */
std::string g_rules_default;

bool parse_fight(const char* s0, Fight& out)
{
    std::string line = s0 ? s0 : "";
    if (!g_rules_default.empty() && line.find("train=") == std::string::npos && line.find("life=") == std::string::npos)
        line += " " + g_rules_default;
    const char* s = line.c_str();
    Fight f; f.text = s;
    f.rounds = default_rounds();
    f.pick = g_pick_default;
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
        else if (_stricmp(k.c_str(), "pick") == 0) { const int n = atoi(cur.substr(eq + 1).c_str()); f.pick = n < 0 ? 0 : n > 120 ? 120 : n; }
        else if (_stricmp(k.c_str(), "train") == 0) f.rules.training = atoi(cur.substr(eq + 1).c_str()) != 0;
        else if (_stricmp(k.c_str(), "life") == 0) {   /* life=P1|P2: each side's health in percent (the handicap) */
            const std::string v = cur.substr(eq + 1);
            const size_t bar = v.find('|');
            const int a = atoi(v.c_str()), b = bar == std::string::npos ? 100 : atoi(v.c_str() + bar + 1);
            f.rules.life[0] = a > 0 ? np::MatchRules::clamp_life(a) : 100;
            f.rules.life[1] = b > 0 ? np::MatchRules::clamp_life(b) : 100;
        }
        else if (_stricmp(k.c_str(), "buttons") == 0) {   /* buttons=b1|b2: the confirm buttons (costumes), 1-4, 0 = default */
            const std::string v = cur.substr(eq + 1);
            const size_t bar = v.find('|');
            const int b1 = atoi(v.c_str()), b2 = bar == std::string::npos ? 0 : atoi(v.c_str() + bar + 1);
            f.btn[0] = b1 >= 1 && b1 <= 4 ? b1 : 0;
            f.btn[1] = b2 >= 1 && b2 <= 4 ? b2 : 0;
        }
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
    if (f.rules.training) f.rounds = 1;   /* a training fight ends at its first KO (a give-up): back to the select screen */
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

/* custom costumes (df_costume.cpp): exchanged with the opponent in a netplay session, read from the file in a
 * replay (nothing to exchange), from T5_COSTUME_SAVE(2) offline */
CostumeMode costume_mode() { return g_replay ? CostumeMode::Replay : session_netplay() ? CostumeMode::Net : CostumeMode::Offline; }

void write_text(const std::string& path, const std::string& text)
{
    if (path.empty()) return;
    const std::string tmp = path + ".tmp";
    if (FILE* fp = fopen(tmp.c_str(), "wb")) {
        fwrite(text.data(), 1, text.size(), fp);
        fclose(fp);
        /* the launcher may be reading the file this very moment (Windows refuses the replace then) */
        for (int i = 0; i < 60 && !MoveFileExA(tmp.c_str(), path.c_str(), MOVEFILE_REPLACE_EXISTING); i++) Sleep(1);
    }
}

void ctl_report(uint32_t f)
{
    if (!g_ctl) return;
    const std::string st = g_state_name;
    const char* c;
    if (st == "boot") c = "boot";
    else if (st == "title" || st == "reset" || st == "leave") c = g_pending_cmd ? "connecting" : (g_ctl_error.empty() ? "idle" : "error");
    else if (st == "select" || st == "stage" || st == "pick" || st == "pick_wait") c = "connecting";
    else if (st == "loading") c = "loading";
    else if (st == "fight") c = "fight";
    else if (st == "over") c = "result";
    else c = !g_ctl_error.empty() ? "error" : (g_session && g_after_match) ? "result" : "idle";
    ctl_state(c, f, g_ctl_match, g_ctl_error.empty() ? nullptr : g_ctl_error.c_str(), g_sessions);
}

std::string status_extra();   /* the in-game select's part of the status (below) */
void status(const char* state, uint32_t f)
{
    g_state_name = state;
    note("frame %u: state %s", f, state);
    ctl_report(f);
    if (g_status_file.empty()) return;
    char buf[640];
    snprintf(buf, sizeof buf,
             "{\"state\": \"%s\", \"frame\": %u, \"match\": %u, \"p1\": %d, \"p2\": %d, \"stage\": %d, \"rounds\": %d, "
             "\"last_winner\": %s, \"last_score\": [%d, %d], \"pick\": %d, \"b1\": %d, \"b2\": %d, \"training\": %s, \"life\": [%d, %d]%s}\n",
             state, f, g_match, g_cfg.chr[0], g_cfg.chr[1], g_cfg.stage, g_cfg.rounds,
             g_last_winner == -2 ? "null" : g_last_winner == -1 ? "null" : (g_last_winner == 0 ? "0" : "1"),
             g_last_score[0], g_last_score[1], g_cfg.pick, g_cfg.btn[0], g_cfg.btn[1],
             g_cfg.rules.training ? "true" : "false", g_cfg.rules.life[0], g_cfg.rules.life[1], status_extra().c_str());
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
    if (g_replay) {   /* a replay: the next match of the recorded session (the same lines the live games had) */
        char line[512];
        if (!t5_replay_fight_line(g_match + 1, line, (int)sizeof line)) return false;
        note("next fight from the replay (match %u): %s", g_match + 1, line);
        return parse_fight(line, out);
    }
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
/* Pick / PickWait: the in-game select (this PC's player picks on the select
 * screen, then the peer's pick is awaited; Select drives the peer's side). */
enum class Ph { Boot, Title, Select, Stage, WaitGame, Fight, Over, Neutral, Reset, Leave, Pick, PickWait };
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
bool g_autosave_wait = false;   /* the title waits for its savedata autosave before start VS */
ULONGLONG g_autosave_noted = 0; /* ... last "still running" line */
bool g_over_wait = false;       /* a match end seen on predicted input, waiting for its confirmation */
ULONGLONG g_cmd_ms = 0;         /* when the pending "fight" came (stuck_check) */
uint32_t g_cmd_frame = 0;       /* ... and its frame */
bool g_mode_asked = false;      /* Reset / Leave: the mode request is out */
bool g_wait_setup = false;      /* WaitGame: the fight's setup is written (FIGHT START waits for the game mode's phase 7) */
bool g_game_seen = false;       /* the game mode ran since the last trip to the title (a fight, or part of one) */
bool g_restart_low = false;     /* Reset by a select restart: the select screen has gone through its set-up again */
uint32_t g_restart_frame = 0;   /* ... and the frame start VS was called at the select screen */
uint32_t g_restart_obj = 0;     /* ... and the select mode's task object it was called on (a new one comes) */
bool g_restart_inplace = false; /* T5_DF_SELECT_RESTART=inplace: the old way (start VS alone; breaks after 4-11, docs) */
uint32_t g_restarts = 0;        /* select restarts in this process (log) */
ULONGLONG g_ph_ms = 0;          /* wall time the phase began (the stuck check) */
uint32_t g_stuck_s = 60;        /* T5_DF_STUCK_SECONDS: a reset / leave that gets nowhere in this long ends the process */
uint32_t g_session_matches = 0; /* fights started in this netplay session (the in-game select's exchange key) */
int g_last_chr[2] = { -1, -1 }, g_last_btn[2] = { 0, 0 };   /* the session's last fight: who with which button (costume) */
bool g_pause_asked = false;     /* in-game select: the lockstep's pause is requested (after a match) */
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
/* the button that confirms a character when no pick names one */
uint16_t default_confirm(int chr) { return chr == 12 ? g_alt_button : chr == 11 ? (uint16_t)B_SQUARE : (uint16_t)B_CROSS; }

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

void set_phase(Ph ph, const char* name, uint32_t f)
{
    /* out of the in-game select by any other way (a reset, a session lost while
     * picking): its hints under the portraits go */
    if ((g_ph == Ph::Pick || g_ph == Ph::PickWait) && ph != Ph::Pick && ph != Ph::PickWait) plates_restore();
    g_ph = ph; g_ph_frame = f; g_ph_ms = GetTickCount64(); g_mode_asked = false; status(name, f);
}
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
         * without a cell in this column is skipped, so columns 0 and 11 cannot
         * reach the top row (its cells are columns 1..10): step sideways first.
         * Column 11 was missed: a cursor left on Bruce or Kuma/Panda went
         * DOWN, DOWN, ... between the middle and bottom rows for a top-row
         * fighter until the driver gave up ("cannot reach cell 30 from 23",
         * RTT 250 batch R250a; in-game select run final_rb match 12). */
        const bool open = grid_open();   /* the open grid's top row has columns 0 and 11 too */
        if (!open && tr == 0 && c == 0) b = B_RIGHT;
        else if (!open && tr == 0 && c == 11) b = B_LEFT;
        else b = ((tr - r + 3) % 3 == 1) ? B_DOWN : B_UP;
    } else {
        /* the top row cycles its 10 cells (columns 1..10; the open grid's 12), the others 12 */
        const bool top10 = r == 0 && !grid_open();
        const int n = top10 ? 10 : 12, cc = top10 ? c - 1 : c, tcc = top10 ? tc - 1 : tc;
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

bool pick_begin(uint32_t f);   /* in-game select (below) */
void pick_fight_start(uint32_t f);   /* in-game select: what was picked, both sides (below) */
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
    costume_session(f, costume_mode());
    /* (a replay: the recorded picks are driven like a lobby's; pick= stays for the pause between matches) */
    if (g_cfg.pick > 0 && !g_replay && pick_begin(f)) return;
    /* the same fighter as in the session's last fight keeps its costume (a
     * ranked set's later games: the lock names the characters only); the same
     * on both PCs, which played the same fights */
    for (int p = 0; p < 2; p++) {
        if (!g_cfg.btn[p] && g_cfg.chr[p] == g_last_chr[p] && g_last_btn[p]) g_cfg.btn[p] = g_last_btn[p];
        /* Kuma and Panda share a cell and the button decides which (punch Kuma,
         * kick Panda): a costume button of the other kind (a hand-made
         * buttons=) would fight the other bear under this one's name
         * (pick_flow_test --no-pick: "Panda with Square", model 0x1E) -- the
         * default button instead, the same on both PCs */
        const int b = g_cfg.btn[p];
        if ((g_cfg.chr[p] == 11 && (b == 3 || b == 4)) || (g_cfg.chr[p] == 12 && (b == 1 || b == 2))) {
            note("player %d: %s cannot be confirmed with %s -- the default button", p + 1, kName[g_cfg.chr[p]], btn_name(b));
            g_cfg.btn[p] = 0;
        }
    }
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
    g_session_matches = 0;
    g_last_chr[0] = g_last_chr[1] = -1;
    g_last_btn[0] = g_last_btn[1] = 0;
    g_pause_asked = false;
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
/* The game's async reader (ZsAread), which every scene load goes through: its
 * service object 0x1009FE28 -- +0 the request semaphore's id, +4 the
 * completion semaphore's id, +8 busy (0 idle, 1 a read in flight), +0x14 the
 * queue of requests (the one being read first), +0x20.. the read in flight;
 * the request pool (64 x 0x28 bytes) at 0x1009FF68..0x100A0968, +0 a
 * request's status (1 queued / being read, then its result), +4 the next; a
 * config copy at 0x100A0968 (0x20). The main thread's service (0x9A784, once
 * per frame) starts the head request (posts +0, busy = 1) and, while busy,
 * takes the reader thread's completion token with a trywait.
 *
 * Select stall (docs/DIRECTFIGHT.md "Select stall after a fight"): all of this
 * lies inside the fight-state block the boot state copies (0x1008E000..
 * 0x100A5000). Taken while a read was in flight -- 30 frames into the boot
 * title the title's own load (T55DATA1 entry 0x105, 1.2 MB) is usually done,
 * on a loaded PC not -- the copy said "busy, the title's request queued"; put
 * back at the first title visit after a fight with the reader idle, the
 * service waited for a completion token no read would ever post, every later
 * request queued behind it, and the select mode's set-up (phase 1 of 0x5AF04
 * waits for its portraits/models, 0x2739F4 -> state 7) never ended: the select
 * screen at phase 1 for good (offline pf_off2, main e3/p2; reproduced every
 * time with PS3_TEST_FS_DELAY=150: copy "busy 1, 1 request", restore -> phase 1
 * for 220 s, 5 requests queued, 0 tokens). The reverse (copy idle, put back
 * during a read) dropped the read in flight from the queue and left its token
 * to complete the next request before its data was read. So the reader's own
 * data (0x1009FE20..0x100A0988: thread id, service object, path buffer, quit
 * flag, pool, config) is never copied: it is live I/O state, not match state
 * (and at an idle reader its bytes equal the boot copy's: T5_DF_FRESH_SCAN over
 * it found no difference after fights). Also, the copy is taken and put back
 * only once the reader has nothing queued (reader_idle), so both games run
 * start VS from a title whose loads are done. */
constexpr uint32_t kReader = 0x1009FE28u, kReaderPool = 0x1009FF68u, kReaderPoolEnd = 0x100A0968u;
constexpr uint32_t kReaderData = 0x1009FE20u, kReaderDataEnd = 0x100A0988u;
constexpr uint32_t kDecoderSemPtr = 0x1054AD58u, kAsyncSemPtr = 0x106CD858u;   /* the other loader threads' semaphore ids */
extern "C" int32_t t5_sem_count(uint32_t id);   /* src/netplay/t5_hooks.cpp: a kernel semaphore's count, -1 none */
bool reader_idle() { return rd32(kReader + 8) == 0 && rd32(kReader + 0x14) == 0; }
bool g_reader_guard = true;      /* T5_DF_READER_GUARD=0: the reader's data copied like the rest, no wait for it (old) */
bool g_reader_wait = false;      /* the title waits for the reader before the copy / start VS (logged once) */
std::string reader_desc()
{
    char b[160];
    const uint32_t q = rd32(kReader + 0x14);
    int queued = 0;
    for (uint32_t r = q; r >= kReaderPool && r < kReaderPoolEnd && queued < 70; r = rd32(r + 4)) queued++;
    snprintf(b, sizeof b, "reader busy %u, queue 0x%08X (%d request(s)%s), completion tokens %d", rd32(kReader + 8), q, queued,
             q && (q < kReaderPool || q >= kReaderPoolEnd) ? ", not a pool slot" : "", t5_sem_count(rd32(kReader + 4)));
    return b;
}

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
    note("frame %u: boot state of %zu area(s), %zu bytes, kept for later opponents (%s)", f, g_fresh_areas.size(), n,
         reader_desc().c_str());
}
bool g_fresh_log = false;        /* T5_DF_FRESH_LOG=1: list the words the restore changes */
void fresh_restore(uint32_t f)
{
    if (!g_fresh_taken) return;
    note("frame %u: before the restore: %s", f, reader_desc().c_str());
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
    note("frame %u: the match state areas are back as at boot (%zu bytes differed; %s)", f, changed, reader_desc().c_str());
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
    g_cmd_ms = GetTickCount64();
    g_cmd_frame = f;
    g_ctl_error.clear();
    /* the same session (a rematch) when the launcher says so or the netplay variables are the session's */
    std::string key;
    for (const char* v : kSessionVars) {
        std::string x;
        for (const auto& kv : c.env) if (!_stricmp(kv.first.c_str(), v)) x = kv.second;
        key += x + '|';
    }
    g_cmd_rematch = g_session && (c.rematch || key == g_session_key) && (g_ph == Ph::Over || g_ph == Ph::Neutral);
    /* A new session's match kind (T5_NET_UNLOCKS=open: Jinpachi and the random cell
     * on the grid, df_unlock.cpp), set now -- before the select screen it is picked
     * on is built. A fresh select screen built with the other answer is built
     * again (a select restart), so both PCs pick on the same grid. */
    bool regrid = false;
    if (!g_cmd_rematch) {
        std::string u;
        for (const auto& kv : c.env) if (!_stricmp(kv.first.c_str(), "T5_NET_UNLOCKS")) u = kv.second;
        regrid = t5_unlock_set_open(!_stricmp(u.c_str(), "open")) != 0;
    }
    if (!g_cmd_rematch) {
        if (g_session) end_session(f, "a new opponent", false);
        else if (g_ph != Ph::Neutral || !g_fresh || regrid) go_reset(f);
    }
    ctl_report(f);
}

/* A used select screen made fresh again without the title (no fight since
 * the title; see Ph::Reset). The start-VS routine fills the VS battle config
 * again (game type, players, VS counters) and asks the mode manager for the
 * select mode -- a request the manager drops while the select mode is the
 * current one (0x25D978 returns when cur == the mode asked for). Called alone
 * at the select screen (the old restart "in place") it only made the running
 * select mode start its set-up again (phase word 0 -> 3): the set-up builds the
 * select scene a second time -- both fighters' preview models, the portraits,
 * their animation and resource managers, ~150 KB of the scene heap and more --
 * and nothing ever freed the first scene, whose tasks went on running every
 * frame. In the 4th to 11th restart an allocation of the model code
 * (0x2B1F40, through the select's own update 0x1159AC -> 0x109320 ->
 * 0x2B81E0) came back NULL: the model code wrote its node into the null page,
 * 0x2DBBEC took a count from there and memset 138 MB from NULL -- the OPD
 * page with the vblank handler's descriptor 0x4635A8 and the code below
 * 0x08481084 cleared (docs/DIRECTFIGHT.md "Select restarts").
 *
 * So the request is made to count: the driver writes it into the manager
 * itself, as 0x25D978 would for another mode (next = select, param 0). The
 * manager then does what it does for every mode change: it waits until no
 * task of the select scene is busy (loads in flight), ends the select mode
 * with its whole scene (the heap goes back) and builds a new select mode from
 * scratch, like the title's start VS -- one or two frames. */
void select_restart(uint32_t f)
{
    const uint32_t mgr = mode_manager();
    g_restart_obj = mgr ? rd32(mgr + kMgrModeObj) : 0;
    gcall(kFnStartGame, 4, 3);
    if (g_restart_inplace || !mgr || mode_cur() != kModeSelect || mode_next() != kModeNone) {
        note("frame %u: select screen restart in place (func_0004E9DC(4, 3) at the select screen; no fight since the title%s)",
             f, g_restart_inplace ? "; T5_DF_SELECT_RESTART=inplace" : "; the mode manager is busy");
        g_restart_obj = 0;
        return;
    }
    wr32(mgr + kMgrParam, 0);
    wr32(mgr + kMgrNext, kModeSelect);
    note("frame %u: select screen restart (start VS at the select screen, select mode 0x%08X ended and built again by the "
         "mode manager; no fight since the title)", f, g_restart_obj);
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
/* A wait counts as stuck only once it has also run this many frames per
 * second of it (a third of 60): the checks run at frame boundaries, so a game
 * that is really stuck in a mode change keeps its full frame rate, while one
 * that its PC slows to a crawl (other programs at normal priority: 0.8-2.7 fps
 * for a minute in select_stall_test O1) is still on its way -- before, the
 * reset's 60 s ended such a game 0.1 s after its select screen had loaded. */
constexpr uint32_t kStuckMinFps = 20;
bool pick_screen_wait();        /* the in-game select waits for its select screen (below) */

/* A select screen that never gets past its loading (Select, or the in-game
 * select's Pick, before the screen takes input). Its cause is gone (the
 * reader, kReaderData); this is the backstop, and it must never end a slow
 * load (PS3_TEST_FS_DELAY=150: one request of the select's took over 30 s, its
 * whole set-up 38 s). Two states get nowhere by themselves:
 *   - the reader wedged: busy, no completion token, and the reader thread
 *     parked on its request semaphore -- nobody will post the token the service
 *     waits for (what the bad copy did); a slow read has the thread waiting for
 *     its data instead, or a token pending: T5_DF_SELECT_STUCK_SECONDS (10);
 *   - nothing to load: the reader idle with an empty queue, and the other
 *     loader threads parked too -- the "decoder" (inflates what was read,
 *     semaphore id at 0x1054AD58) and TNUD::ASync (0x106CD858) -- while the
 *     select's phase word and the mode manager stay as they are: the stuck
 *     seconds of a reset (T5_DF_STUCK_SECONDS, 60). (Under a CPU hog the
 *     decoder alone took 30 s of one select's set-up, the reader idle:
 *     select_stall_test S1 cycle 30.)
 * Either one held without a break for that long: the game says what it waits
 * on and ends as a stuck reset does (exit code 6: the launcher starts a fresh
 * game for the match, which match_driver reports as game_stuck, no strike).
 * Before, such a screen sat at phase 1 until the next command (e3/p2: 46 s)
 * or for good (pf_off2). 0 = never. */
uint32_t g_select_stuck_s = 10;
int g_sl_kind = 0;              /* 1 wedged reader, 2 nothing to load; 0 the select loads (or is live) */
uint64_t g_sl_sig = 0;          /* phase word, modes, reader state when the kind began */
ULONGLONG g_sl_ms = 0;          /* when it began */
uint32_t g_sl_frame = 0;        /* ... and its frame */
bool g_sl_dumped = false;
void select_load_check(uint32_t f)
{
    const bool loading = g_ctl && ((g_ph == Ph::Select && !(mode_cur() == kModeSelect && rd32(kSelectState) >= 3)) ||
                                   pick_screen_wait());
    const uint32_t busy = rd32(kReader + 8), q = rd32(kReader + 0x14);
    const int32_t tokens = t5_sem_count(rd32(kReader + 4));
    int kind = 0;
    if (loading) {
        if (busy == 1 && tokens == 0 && sem_parked(rd32(kReader))) kind = 1;
        else if (busy == 0 && q == 0 && sem_parked(rd32(kReader)) && sem_parked(rd32(kDecoderSemPtr)) &&
                 sem_parked(rd32(kAsyncSemPtr))) kind = 2;
    }
    const uint32_t limit = kind == 1 ? g_select_stuck_s : kind == 2 ? g_stuck_s : 0;
    const uint64_t sig = (uint64_t)rd32(kSelectState) | ((uint64_t)mode_cur() << 8) | ((uint64_t)mode_next() << 16) |
                         ((uint64_t)q << 24);
    const ULONGLONG now = GetTickCount64();
    if (!limit) { g_sl_kind = 0; return; }
    if (kind != g_sl_kind || sig != g_sl_sig) {
        g_sl_kind = kind; g_sl_sig = sig; g_sl_ms = now; g_sl_frame = f; g_sl_dumped = false;
        return;
    }
    const ULONGLONG ms = now - g_sl_ms;
    const char* what = kind == 1 ? "the async reader waits for a read nobody does" : "nothing loads (every loader parked)";
    if (ms >= (ULONGLONG)limit * 500 && !g_sl_dumped) {
        g_sl_dumped = true;
        note("frame %u: the select screen's loading is stuck for %u s, %s (mode %u, next %u, phase word %u; %s):", f,
             (unsigned)(ms / 1000), what, mode_cur(), mode_next(), rd32(kSelectState), reader_desc().c_str());
        stuck_dump(f);
    }
    if (ms < (ULONGLONG)limit * 1000 || f - g_sl_frame < limit * kStuckMinFps) return;
    note("frame %u: STUCK: the select screen's loading for %u s, %s (mode %u, phase word %u; %s) -- the game ends, "
         "the launcher starts a fresh one", f, limit, what, mode_cur(), rd32(kSelectState), reader_desc().c_str());
    ctl_state("error", f, g_ctl_match, "stuck", g_sessions);
    fflush(stdout); fflush(stderr);
    TerminateProcess(GetCurrentProcess(), 6);
}

void stuck_check(uint32_t f)
{
    select_load_check(f);
    /* Neutral with a "fight" pending waits for the select screen to take input
     * (select_live); a select mode that never gets past its loading (phase word
     * 1, every loader parked: reset_cycle_test F10, F12 under heavy load) held
     * the game there for good -- counted from the command, as a reset. */
    const bool neutral_wait = g_ph == Ph::Neutral && g_pending_cmd;
    const bool waiting = g_ph == Ph::Leave || g_ph == Ph::Reset || (g_ph == Ph::Title && g_fresh_taken) || neutral_wait;
    if (!g_ctl || !g_stuck_s || !waiting) return;
    const ULONGLONG since = neutral_wait && g_cmd_ms > g_ph_ms ? g_cmd_ms : g_ph_ms;
    const uint32_t since_f = neutral_wait && g_cmd_ms > g_ph_ms ? g_cmd_frame : g_ph_frame;
    const ULONGLONG ms = GetTickCount64() - since;
    if (ms >= (ULONGLONG)g_stuck_s * 500 && g_stuck_dumped != since) {   /* half way: what it waits on */
        g_stuck_dumped = since;
        note("frame %u: %s for %u s (mode %u, next %u, phase word %u):", f, g_state_name, (unsigned)(ms / 1000),
             mode_cur(), mode_next(), rd32(kSelectState));
        stuck_dump(f);
    }
    if (ms < (ULONGLONG)g_stuck_s * 1000 || f - since_f < g_stuck_s * kStuckMinFps) return;
    note("frame %u: STUCK: %s for %u s (mode %u, next %u, phase word %u) -- the game ends, the launcher starts a fresh one",
         f, g_state_name, g_stuck_s, mode_cur(), mode_next(), rd32(kSelectState));
    ctl_state("error", f, g_ctl_match, "stuck", g_sessions);
    fflush(stdout); fflush(stderr);
    TerminateProcess(GetCurrentProcess(), 6);
}

/* ---- in-game select (docs/DIRECTFIGHT.md "Character select in the game") --------
 * pick=N on the fight line: each player picks character and costume on the
 * game's own select screen. The two select screens are not in lockstep (the
 * first match of a session: lockstep has not started; a rematch: the lockstep
 * pauses at the select screen, see Over). This PC's player moves its own
 * cursor -- the local pad goes to its side only, filtered (directions, one face
 * button at a time: the confirming button is the costume; L1, Start and the
 * rest blocked; Select = a random pick) -- and the driver confirms the handicap
 * bar at 100 %. The pick (character, button, model id) goes to the peer over
 * the netplay session; the peer's pick, once in, is driven onto the other side
 * by the driver (Select), then the stage and the fight as always. No pick
 * within N seconds: the driver picks the line's character for this player
 * (the launcher's). The select screen's name plates show the seconds left and
 * whether the opponent is still picking. */
struct Pick {
    bool on = false;             /* this match's fighters are picked on the select screen */
    bool net = false;            /* the peer's pick comes over the netplay session (else: offline, the line's character) */
    int me = 0;                  /* the side this PC's player picks */
    uint32_t key = 0;            /* exchange key: the session's match number */
    uint32_t secs = 30;
    bool live = false;           /* the select screen takes input for this player */
    ULONGLONG t0 = 0;            /* ... since then (the pick's clock) */
    bool armed = false;          /* every button was up once since then (a press left from the launcher counts not) */
    uint16_t raw_prev = 0;
    uint16_t face = 0;           /* the one face button held (never two at a time: the costume is unambiguous) */
    uint16_t confirm = 0;        /* the face button the game saw last */
    int auto_chr = -1, auto_btn = 0;   /* the driver picks for this player: the time ran out, or Select (random) */
    bool have = false;           /* this player's pick is known (character confirmed) */
    int chr = -1, cell = -1, btn = 0, model = -1;
    uint32_t t9 = 0;             /* frame the handicap bar came up */
    bool peer = false;           /* the opponent's pick is in */
    int peer_model = -1;
    ULONGLONG tw = 0;            /* PickWait since */
    int shown_s = -1;
    bool bad_noted = false;
    uint8_t last_st = 0;
    uint16_t hold = 0;           /* P2's confirm (its face button), held until P1 is confirmed on this PC (below) */
    bool held = false;           /* ... and pressed */
    bool peer_none = false;      /* no netplay: the other side keeps the line's character */
    bool gave_up = false;        /* no pick came from the opponent: the session was ended */
};
Pick g_pick;

/* Mirror matches: the select screen gives the SECOND of two confirms of the
 * same model the character's other costume (Steve Square 0x29 twice: the one
 * confirmed later becomes 0x2A). Which one is second must not depend on which
 * side is local -- each PC used to confirm its own player first (the host P1,
 * the joiner P2) and the two games fought Steve 0x29 vs 0x2A on one PC and
 * 0x2A vs 0x29 on the other: every frame apart from the fight's first (e2e
 * cs_mirror, 1.1.0 blocker). So on every PC and every path P1 is confirmed
 * first and P2 only after P1's pick is settled (record past the handicap bar):
 * the game's own rule then gives P2 the other costume on both PCs, whatever
 * that costume is for the fighter (2 or 4 costumes). */
bool p1_settled() { return rd8(rec(0) + kRecState) >= 0x0C; }
int g_models[2] = { -1, -1 };    /* the model ids both sides fight with (status file) */

std::string status_extra()
{
    char b[96];
    snprintf(b, sizeof b, ", \"m1\": %d, \"m2\": %d", g_models[0], g_models[1]);
    return b;
}

void pick_wait_frame(uint32_t f);
bool take_peer_pick(uint32_t f);
bool pick_begin(uint32_t f)
{
    const bool net = session_netplay();
    if (net && t5_netplay_lockstep_active()) {
        note("frame %u: in-game select: the lockstep runs (not paused) -- the line's characters instead", f);
        return false;
    }
    g_pick = Pick();
    g_pick.on = true;
    g_pick.net = net;
    g_pick.me = net ? t5_netplay_local_slot() : 0;
    if (g_pick.me < 0 || g_pick.me > 1) g_pick.me = 0;
    g_pick.secs = (uint32_t)g_cfg.pick;
    g_pick.key = 0x70000000u | (g_session_matches + 1);
    g_models[0] = g_models[1] = -1;
    note("frame %u: in-game select: player %d picks on the select screen (%u s, else %s), exchange key %08X%s", f, g_pick.me + 1,
         g_pick.secs, kName[g_cfg.chr[g_pick.me]], g_pick.key, net ? "" : " (no netplay: the other side keeps the line's character)");
    set_phase(Ph::Pick, "pick", f);
    return true;
}

bool pick_screen_wait() { return g_ph == Ph::Pick && !g_pick.live; }

void pick_frame(uint32_t f)
{
    Pick& k = g_pick;
    const int me = k.me;
    const uint8_t st = rd8(rec(me) + kRecState);
    if (!k.live) {
        if (mode_cur() != kModeSelect || rd32(kSelectState) < 3 || st != 3) {
            if ((f - g_ph_frame) % 120 == 0 && f > g_ph_frame)
                note("frame %u: in-game select: waiting for the select screen (mode %u, select state %u, record %02X; %s)", f,
                     mode_cur(), rd32(kSelectState), st, reader_desc().c_str());
            return;
        }
        k.live = true;
        k.t0 = GetTickCount64();
        for (int p = 0; p < 2; p++) inject(p, true, 0);
        write_hud(g_cfg, f);   /* the players' names under the portraits already (written again at FIGHT START) */
        plates_save();
        const uint32_t cell = rd32(rec(me) + kRecCell);
        note("frame %u: in-game select: the select screen is live, player %d's cursor at cell %u (%s)%s", f, me + 1, cell,
             char_at((int)cell) >= 0 ? kName[char_at((int)cell)] : "?", grid_open() ? " -- Jinpachi and the random cell offered" : "");
    }
    const ULONGLONG ms = GetTickCount64() - k.t0;
    if (st != k.last_st) {   /* every state of this player's record (3 choosing, 9 handicap, done) */
        note("frame %u: in-game select: player %d's record state %02X -> %02X (word %08X)", f, me + 1, k.last_st, st,
             rd32(rec(me) + kRecState));
        k.last_st = st;
    }
    if (st == 3 && k.hold) {
        /* P2 (this PC's player on the joiner) has chosen; its confirm waits until
         * P1 -- the opponent's pick, driven here -- is settled (p1_settled) */
        if (k.held) {   /* pressed: the record leaves 3 within a frame or two; pressed again if it did not */
            if (press_idle(me) && f >= k.t9 + 40) { k.t9 = f; press(me, k.hold, f); }
            return;
        }
        if (!press_idle(0) || !press_idle(me)) return;
        inject(me, true, 0);
        if (!take_peer_pick(f)) { plate_text(1 - me, "PICKING..."); return; }
        const uint8_t s1 = rd8(rec(0) + kRecState);
        if (s1 == 3) {
            const int target = cell_of(g_cfg.chr[0]);
            if (target >= 0 && navigate(0, target, f))
                press(0, g_cfg.btn[0] ? btn_bits(g_cfg.btn[0]) : default_confirm(g_cfg.chr[0]), f);
            return;
        }
        if (s1 == 9) { press(0, g_cfg.color[0] == 2 ? B_TRIANGLE : B_CROSS, f); return; }
        if (!p1_settled()) return;
        plate_text(1 - me, nullptr);
        k.held = true;
        k.t9 = f;
        k.confirm = k.hold;
        press(me, k.hold, f);
        note("frame %u: in-game select: P1 is settled (model 0x%X) -- player %d's confirm %s goes in now", f,
             rd32(rec(0) + kRecModel), me + 1, btn_name(btn_index(k.hold)));
        return;
    }
    if (st == 3) {
        if (k.auto_chr < 0 && ms >= (ULONGLONG)k.secs * 1000) {
            k.auto_chr = g_cfg.chr[me];
            k.auto_btn = 0;
            g_steps[me] = 0;
            inject(me, true, 0);
            plate_text(me, "TIME UP");
            note("frame %u: in-game select: no pick within %u s -- %s (the launcher's character) for player %d", f, k.secs,
                 kName[k.auto_chr], me + 1);
        }
        if (k.auto_chr >= 0) {   /* the driver picks: as in a direct fight */
            if (!press_idle(me)) return;
            const int target = cell_of(k.auto_chr);
            if (target >= 0 && navigate(me, target, f)) {
                k.confirm = k.auto_btn ? btn_bits(k.auto_btn) : default_confirm(k.auto_chr);
                if (me == 1 && !p1_settled()) {
                    k.hold = k.confirm;
                    k.tw = GetTickCount64();
                    note("frame %u: in-game select: player 2's pick %s with %s waits for P1's", f, kName[k.auto_chr],
                         btn_name(btn_index(k.hold)));
                } else {
                    press(me, k.confirm, f);
                }
            }
            return;
        }
        const int left = (int)(((ULONGLONG)k.secs * 1000 - ms + 999) / 1000);
        if (left != k.shown_s) {
            char t[24];
            snprintf(t, sizeof t, "CHOOSE  %d", left);
            plate_text(me, t);
            k.shown_s = left;
        }
        const uint16_t raw = pick_read_local_pad();
        if (!k.armed) {
            if (raw) { inject(me, true, 0); return; }
            k.armed = true;
        }
        if ((raw & B_SELECT) && !(k.raw_prev & B_SELECT)) {
            /* Select: a random character and costume, drawn on this PC; the pick
             * goes to the peer like any other, so both games fight the same */
            LARGE_INTEGER q; QueryPerformanceCounter(&q);
            uint32_t x = (uint32_t)q.QuadPart ^ (uint32_t)(q.QuadPart >> 32) ^ (GetCurrentProcessId() * 0x9E3779B9u) ^ f;
            x ^= x >> 16; x *= 0x7FEB352Du; x ^= x >> 15; x *= 0x846CA68Bu; x ^= x >> 16;
            const uint32_t n = grid_open() ? 36u : 35u;      /* 0..34: every selectable character; Jinpachi when offered */
            k.auto_chr = (int)(x % n);
            const uint32_t y = x / n;
            k.auto_btn = k.auto_chr == 11 ? 1 + (int)(y % 2)  /* Kuma: a punch button */
                       : k.auto_chr == 12 ? 3 + (int)(y % 2)  /* Panda: a kick button */
                       : 1 + (int)(y % 4);
            g_steps[me] = 0;
            inject(me, true, 0);
            plate_text(me, "RANDOM");
            note("frame %u: in-game select: Select -- random pick for player %d: %s with %s", f, me + 1, kName[k.auto_chr],
                 btn_name(k.auto_btn));
            k.raw_prev = raw;
            return;
        }
        k.raw_prev = raw;
        if (g_trace_presses) {   /* T5_DF_TRACE=1: every move of this player's cursor (tests drive it closed-loop) */
            const int cell = (int)rd32(rec(me) + kRecCell);
            if (cell != k.cell) { k.cell = cell; note("frame %u: in-game select: cursor at cell %d", f, cell); }
        }
        if (k.face && !(raw & k.face)) k.face = 0;
        bool newly = false;
        if (!k.face)
            for (int b = 1; b <= 4; b++)
                if (raw & btn_bits(b)) { k.face = btn_bits(b); newly = true; break; }
        if (k.face) k.confirm = k.face;
        if (newly && me == 1 && !p1_settled()) {
            /* this player's choice: cell and button; the game sees the confirm
             * once P1's pick is settled (the opponent's pick stays hidden until
             * then, as before) */
            k.hold = k.face;
            k.tw = GetTickCount64();
            inject(me, true, 0);
            plate_text(me, "READY");
            const int cell = (int)rd32(rec(me) + kRecCell);
            note("frame %u: in-game select: player 2 chose cell %d (%s) with %s -- confirmed once P1's pick is in", f, cell,
                 char_at(cell) >= 0 ? kName[char_at(cell)] : char_at(cell) == -2 ? "the random cell" : "?",
                 btn_name(btn_index(k.hold)));
            return;
        }
        inject(me, true, (uint16_t)((raw & (B_UP | B_DOWN | B_LEFT | B_RIGHT)) | k.face));
        return;
    }
    if (!k.have) {
        /* the character is confirmed (the handicap bar is up): what was picked */
        inject(me, true, 0);
        k.have = true;
        k.t9 = f;
        k.cell = (int)rd32(rec(me) + kRecCell);
        k.model = (int)rd32(rec(me) + kRecModel);
        k.btn = btn_index(k.confirm);
        if (!k.btn) k.btn = 3;
        int chr = char_at(k.cell);
        const bool random_cell = chr == -2;
        if (chr == 11 && (k.btn == 3 || k.btn == 4)) chr = 12;   /* Kuma's cell with a kick button: Panda */
        const int by_model = model_char(k.model);
        if (chr < 0) chr = by_model >= 0 ? by_model : g_cfg.chr[me];
        if (random_cell) {
            /* The random cell drew a fighter and costume at the confirm (it follows
             * the frame it is pressed on); the record has the drawn model. What goes
             * to the peer is that fighter on its own cell with the button that gives
             * the model there (pick_button_for), so the peer's driver confirms the
             * same model -- and so does a playback of the replay. */
            const int b = pick_button_for(chr, k.model);
            note("frame %u: in-game select: the random cell gave %s (model 0x%X): sent as cell %d with %s", f, kName[chr],
                 k.model, cell_of(chr), btn_name(b ? b : k.btn));
            if (b) k.btn = b;
            k.cell = cell_of(chr);
        }
        if (by_model != chr)
            note("frame %u: in-game select: cell %d gives %s, model 0x%X says %s (model table?) -- the cell counts", f, k.cell,
                 kName[chr], k.model, by_model >= 0 ? kName[by_model] : "?");
        k.chr = chr;
        g_cfg.chr[me] = chr;
        g_cfg.btn[me] = k.btn;
        note("frame %u: in-game select: player %d picked %s with %s (cell %d, model 0x%X) after %.1f s%s", f, me + 1, kName[chr],
             btn_name(k.btn), k.cell, k.model, ms / 1000.0, k.auto_chr >= 0 ? " (by the driver)" : "");
        if (k.net) t5_netplay_pick_send(k.key, pick_pack(chr, k.cell, k.btn, k.model));
    }
    if (st == 9) {   /* the handicap bar: kept at 100 %, confirmed by the driver */
        if (press_idle(me) && f >= k.t9 + 10 && (f - k.t9) % 20 == 10) press(me, B_CROSS, f);
        return;
    }
    /* done: 0x0C while the other side is still choosing (P2 always; P1 too on the
     * select screen a match returns to: run rep1), then 0x0D / 0x15 (probe e10) */
    if (st == 0x15 || st == 0x0D || st == 0x0C) {
        k.tw = GetTickCount64();
        plate_text(me, nullptr);
        set_phase(Ph::PickWait, "pick_wait", f);
        pick_wait_frame(f);
    }
}

/* The opponent's pick (or, after N + 45 s without one, the line's character):
 * true once known, into g_cfg for the opponent's side. */
bool take_peer_pick(uint32_t f)
{
    Pick& k = g_pick;
    const int other = 1 - k.me;
    if (k.peer || k.peer_none) return true;
    bool go = false;
    unsigned v = 0;
    if (k.net && t5_netplay_pick_peer(k.key, &v)) {
        int chr, cell, btn, model;
        if (pick_unpack(v, &chr, &cell, &btn, &model) && chr < (grid_open() ? 36 : 35) && cell_of(chr) == cell) {
            g_cfg.chr[other] = chr;
            g_cfg.btn[other] = btn;
            k.peer = true;
            k.peer_model = model;
            go = true;
            note("frame %u: in-game select: player %d (the opponent) picked %s with %s (model 0x%X); waited %.1f s", f, other + 1,
                 kName[chr], btn_name(btn), model, (GetTickCount64() - k.tw) / 1000.0);
        } else if (!k.bad_noted) {
            k.bad_noted = true;
            note("frame %u: in-game select: the opponent's pick %08X makes no sense -- waiting for another", f, v);
        }
    }
    /* The opponent's own clock runs out after the same N seconds (its select
     * screen may have come up later than this one) and then sends the launcher's
     * character; only a game that never gets to pick is waited out -- and then the
     * session ends. This PC never decides the opponent's fighter itself any more:
     * it took the line's character after N + 45 s, and an opponent whose select
     * screen came up later than that (a slow PC still loading it) could pick
     * another one on its own screen -- two different matches (docs/NETPLAY.md
     * "Slow loading"). A select screen comes up within the stuck check's 60 s of
     * the command, or that game ends itself (its pick never comes: silence). */
    if (!go && !k.net) {
        g_cfg.btn[other] = 0;
        k.peer_none = true;
        go = true;
        note("frame %u: in-game select: no netplay -- player %d plays %s (the line's character)", f, other + 1,
             kName[g_cfg.chr[other]]);
    } else if (!go && !k.gave_up && GetTickCount64() - k.t0 > (ULONGLONG)(k.secs + 90) * 1000) {
        k.gave_up = true;
        note("frame %u: in-game select: no pick came from the opponent within %u s -- the session ends", f, k.secs + 90);
        char why[96];
        snprintf(why, sizeof why, "no pick came from the opponent within %u s", k.secs + 90);
        t5_netplay_give_up("peer_stalled", why);
    }
    if (go) g_steps[other] = 0;
    return go;
}

void pick_wait_frame(uint32_t f)
{
    if (!take_peer_pick(f)) {
        plate_text(1 - g_pick.me, "PICKING...");
        return;
    }
    plates_restore();
    g_steps[0] = g_steps[1] = 0;
    set_phase(Ph::Select, "select", f);   /* the driver confirms the opponent's pick on its side, then the stage */
}

/* FIGHT START: what both sides fight with (the same on both PCs, or the pick
 * went wrong somewhere) */
/* What each fighter block plays (+0x4C of the blocks 0x10090030 and 0x10090900):
 * the fighter in the low byte (the select's character id for most, not all: Lili
 * 0x1E, Jinpachi 0x22; bit 16 is set on P2's block) -- for Mokujin the fighter he
 * copies, which the game mode's set-up drew
 * (0x121E0C <- 0x5A304 <- 0x53C88, phase 2) from the select screen's pinned
 * generator; logged at FIGHT START as "plays". */
/* The rules latched at FIGHT START (match_rules.h): what the training rule in t5_hooks.cpp acts on. */
np::MatchRules g_rules;

/* ", training (...), health P1 70 % / P2 100 % (...)" for the FIGHT START line */
std::string rules_text()
{
    if (!g_rules.any()) return std::string();
    std::string o;
    char b[160];
    if (g_rules.training) o += ", training (endless health, no timer, SELECT held 1 s gives up)";
    snprintf(b, sizeof b, ", health P1 %d %% / P2 %d %% (handicap words %u / %u)", g_rules.life[0], g_rules.life[1],
             rd32(kLifeP1), rd32(kLifeP2));
    o += b;
    return o;
}

std::string fighter_words()
{
    std::string o;
    for (int p = 0; p < 2; p++) {
        const uint32_t w = rd32(0x1009007Cu + (uint32_t)p * 0x8D0u);
        char b[64];
        snprintf(b, sizeof b, "%sP%d plays 0x%X%s", p ? ", " : "", p + 1, w, g_cfg.chr[p] == 19 ? " (Mokujin's copy)" : "");
        o += b;
    }
    return o;
}

void pick_fight_start(uint32_t f)
{
    for (int p = 0; p < 2; p++) g_models[p] = (int)rd32(rec(p) + kRecModel);
    note("frame %u: fighters: P1 %s with %s (model 0x%X), P2 %s with %s (model 0x%X)%s; %s", f, kName[g_cfg.chr[0]],
         btn_name(g_cfg.btn[0]), g_models[0], kName[g_cfg.chr[1]], btn_name(g_cfg.btn[1]), g_models[1],
         g_pick.on ? " (in-game select)" : "", fighter_words().c_str());
    if (!g_pick.on) return;
    g_pick.on = false;
    const int me = g_pick.me, other = 1 - me;
    /* A mirror match of one costume: P2, confirmed after P1 on every PC
     * (p1_settled), fights in the game's other costume -- the picks' models say
     * so already (P2's own pick reads its model after its confirm), so the
     * checks below hold for mirrors too. */
    if (g_cfg.chr[0] == g_cfg.chr[1])
        note("frame %u: in-game select: mirror match: P1 model 0x%X, P2 model 0x%X", f, g_models[0], g_models[1]);
    if (g_pick.have && g_models[me] != g_pick.model)
        note("frame %u: PICK MISMATCH: player %d's side has model 0x%X, picked 0x%X", f, me + 1, g_models[me], g_pick.model);
    if (g_pick.peer && g_models[other] != g_pick.peer_model)
        note("frame %u: PICK MISMATCH: player %d's side has model 0x%X here, 0x%X on the opponent's PC", f, other + 1,
             g_models[other], g_pick.peer_model);
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
        /* Not while the title's savedata autosave still runs: it takes a memory
         * container and 1 MB blocks from the same sys_memory window as the
         * select mode's 65 MB block (allocated right after start VS), so the
         * two orders put the fight's heap 1 MB apart -- and the heap pointers
         * in the fight state with it: a whole match desynced from the first
         * compared frame (reset_cycle_test F11 cycle 5: S's block at
         * 0x45C00000, O's at 0x45D00000, 38 differing words, all pointers
         * 0x100000 apart). Both games wait for it here, so both allocate in the
         * same order. As long as it takes (an autosave takes well under a second;
         * it used to be at most 10 s, and a PC whose disk took longer would have
         * started VS beside it -- the heap apart again, docs/NETPLAY.md "Slow
         * loading"); an autosave that never ends is the stuck check's (60 s: the
         * game ends, the launcher starts a fresh one).
         * The boot state goes back after the wait, right before start VS as
         * before. */
        if ((f >= g_title_seen + 30 || (g_restore_due && f >= g_title_seen + g_fresh_at)) && autosave_running()) {
            if (!g_autosave_wait) { g_autosave_wait = true; g_autosave_noted = GetTickCount64(); note("frame %u: waiting for the title's autosave before start VS", f); }
            else if (GetTickCount64() - g_autosave_noted >= 10000) {
                g_autosave_noted = GetTickCount64();
                note("frame %u: the title's autosave is still running (%.0f s) -- start VS waits for it", f,
                     (GetTickCount64() - g_ph_ms) / 1000.0);
            }
            break;
        }
        /* Nor while the async reader still has a request queued or in flight
         * (the title's own loads; on a loaded PC they outlast the 30 frames): the
         * boot state is taken and put back, and start VS called, only from a
         * title whose loads are done -- the same point in every game (see
         * kReaderData: a copy taken during a read once wedged the reader and
         * the next select screen with it). At most 10 s since the title began
         * (the reader's data is never copied, so going on is safe). */
        if (g_reader_guard && (f >= g_title_seen + 30 || (g_restore_due && f >= g_title_seen + g_fresh_at)) &&
            !reader_idle() && GetTickCount64() - g_ph_ms < 10000) {
            if (!g_reader_wait) { g_reader_wait = true; note("frame %u: waiting for the title's loads before start VS (%s)", f, reader_desc().c_str()); }
            break;
        }
        if (g_reader_wait) {
            g_reader_wait = false;
            note("frame %u: %s (%s)", f, reader_idle() ? "the title's loads are done" : "the title still loads after 10 s: going on",
                 reader_desc().c_str());
        }
        if (g_restore_due && f >= g_title_seen + g_fresh_at) { g_restore_due = false; fresh_restore(f); }
        if (f >= g_title_seen + 30) {
            if (g_autosave_wait) { g_autosave_wait = false; note("frame %u: the autosave is done", f); }
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
                note("frame %u: waiting for the select screen (mode %u, select state %u, records %02X/%02X; %s)", f, mode,
                     rd32(kSelectState), rd8(rec(0) + kRecState), rd8(rec(1) + kRecState), reader_desc().c_str());
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
                /* a mirror: P2's confirm after P1's is settled (p1_settled) -- the
                 * game's "second confirm gets the other costume" rule then falls
                 * on P2 on both PCs, in every game of a locked set too */
                if (p == 1 && g_cfg.chr[0] == g_cfg.chr[1] && !p1_settled()) {
                    navigate(p, target, f);
                    continue;
                }
                if (navigate(p, target, f)) {
                    /* Kuma and Panda share a cell: a punch button (SQUARE) picks
                     * Kuma, a kick button (CROSS/CIRCLE) Panda -- so Kuma cannot
                     * be confirmed with CROSS like everyone else (it gave Panda).
                     * An in-game pick names its button (the costume). */
                    const uint16_t confirm = g_cfg.btn[p] ? btn_bits(g_cfg.btn[p]) : default_confirm(g_cfg.chr[p]);
                    press(p, confirm, f);
                }
            } else if (st == 9) {
                press(p, g_cfg.color[p] == 2 ? B_TRIANGLE : B_CROSS, f);
            }
        }
        if (all_done) {
            note("frame %u: select done: P1 %s with %s (model 0x%X), P2 %s with %s (model 0x%X)", f, kName[g_cfg.chr[0]],
                 btn_name(g_cfg.btn[0]), rd32(rec(0) + kRecModel), kName[g_cfg.chr[1]], btn_name(g_cfg.btn[1]),
                 rd32(rec(1) + kRecModel));
            set_phase(Ph::Stage, "stage", f);
        }
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
        /* custom costumes: no fight before the opponent's table is here (both PCs
         * write both tables at the game mode's start; df_costume.cpp) */
        if (!costume_ready(costume_mode())) {
            costume_session(f, costume_mode());             /* (set already, or netplay was not up at the select) */
            if ((f - g_ph_frame) % 300 == 0 && f > g_ph_frame) note("frame %u: waiting for the opponent's costume table", f);
            break;
        }
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
            /* the health handicap: the game mode's set-up reads these when it builds the fighters (after this
             * frame), the same values on both PCs (100 % unless the line says otherwise) */
            wr32(kLifeP1, (uint32_t)g_cfg.rules.life[0]);
            wr32(kLifeP2, (uint32_t)g_cfg.rules.life[1]);
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
        pick_fight_start(f);
        for (int p = 0; p < 2; p++) { g_last_chr[p] = g_cfg.chr[p]; g_last_btn[p] = g_cfg.btn[p]; }
        g_session_matches++;
        g_match++;
        g_over_clear = false;
        g_over_wait = false;
        g_held = false;
        g_fight_frame = f;
        g_rules = g_cfg.rules;   /* the training rule (t5_hooks.cpp) reads them from the next frame on */
        note("frame %u: FIGHT START match %u%s%s: %s vs %s, stage %d (field 0x%X), rounds %u, game type %u%s",
             f, g_match, g_cfg.match.empty() ? "" : " id ", g_cfg.match.c_str(), kName[g_cfg.chr[0]], kName[g_cfg.chr[1]],
             g_cfg.stage, rd32(kStageId), rd8(kRoundsToWin), rd32(kConfig), rules_text().c_str());
        /* each player's custom costume, both sides, the same on both PCs (df_costume.cpp); a replay's from its file */
        costume_apply(f, costume_mode(), g_match);
        /* the replay: what this match is (recording), or the check that it is the recorded one (playback) */
        t5_replay_fight_start(g_match, g_cfg.chr, g_cfg.btn, g_models, g_cfg.stage, g_cfg.rounds, g_cfg.pick,
                              g_cfg.names[0].c_str(), g_cfg.names[1].c_str(), costume_written(), g_rules.pack());
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
            if (rd32(kSelectState) >= 11) costume_check(f);   /* once: the loading is over, the costumes the same */
            if (!g_held && session_netplay() && t5_netplay_lockstep_active() && intro != g_intro_hold) {
                g_intro_hold = intro;
                for (int p = 0; p < 2; p++) inject(p, intro, 0);
            }
        }
        const uint8_t over0 = rd8(kMatchOver);
        if (!over0) g_over_clear = true;
        uint8_t over = g_over_clear ? over0 : 0;   /* a rematch starts with the last match's flag still set */
        /* Under rollback a KO on the live frame may rest on predicted input;
         * the next rollback can take it back (e2e g2, RTT 250: the pads held
         * and START pressed in a fight that went on, no result ever). Acted
         * on once every input under it is confirmed -- a few frames later. */
        if (over && session_netplay() && !t5_netplay_match_end_final()) {
            if (!g_over_wait) { g_over_wait = true; note("frame %u: the match end rests on predicted input -- acted on once confirmed", f); }
            over = 0;
        }
        if (over && g_over_wait) { g_over_wait = false; note("frame %u: the match end is confirmed", f); }
        if (over && !g_held) hold_pads(f, "the match is decided");
        post_match_skip(f);
        const np::MatchScore sc = np::MatchScore::of(rd8(kWinsP1), rd8(kWinsP2), rd8(kMatchOver), rd8(kWinnerIdx), rd8(kRoundsToWin));
        const uint8_t w1 = (uint8_t)sc.p1, w2 = (uint8_t)sc.p2;
        if (over && (w1 || w2) && !g_result_done) {
            g_result_done = true;
            const int winner = sc.winner();
            g_last_winner = winner; g_last_score[0] = w1; g_last_score[1] = w2;
            g_after_match = true;
            note("frame %u: MATCH OVER match %u after %u frames: P1 %u - P2 %u, winner %s", f, g_match, f - g_fight_frame, w1, w2,
                 winner < 0 ? "none" : winner == 0 ? "P1" : "P2");
            write_result(winner, w1, w2);
            set_phase(Ph::Over, "over", f);
        }
        break; }
    case Ph::Over:
        /* Under rollback the deciding KO may have been seen on a predicted
         * frame that the correction then undid: the fight goes on (decided byte
         * back at 0 in the fight phase) -- netplay drops its pending result for
         * it ("the match end ... was rolled back"). The driver must too: it held
         * this PC's player neutral and pressed START every 20 frames to skip a
         * win pose that never came -- the player lost control and START paused
         * the fight, and the pause menu's presses ended in the game's end mode
         * (8), where the next reset hung for good (desync hunt, run
         * mx_cpus4_rb match 3: KO at 2022 rolled back, the match ran on to 4689). */
        if (mode == kModeGame && g_over_clear && !rd8(kMatchOver) && rd32(kSelectState) == 17) {
            note("frame %u: the match end of frame %u was taken back by a rollback -- the fight goes on", f, g_ph_frame);
            for (int p = 0; p < 2; p++) { g_press[p].active = false; inject(p, false, 0); }
            g_held = false; g_result_done = false; g_after_match = false; g_intro_hold = false;
            set_phase(Ph::Fight, "fight", f);
            break;
        }
        /* the game shows the win pose and returns to character select by itself */
        post_match_skip(f);
        if (select_live() && g_cfg.pick > 0 && session_netplay() && t5_netplay_lockstep_active() &&
            !(g_ctl && g_pending_cmd && !g_cmd_rematch)) {
            /* in-game select: the next pick is made on each PC's own select
             * screen, so the lockstep pauses here (a sync point: both games ask
             * at the same game frame) and resumes at the next FIGHT START */
            if (!g_pause_asked) { g_pause_asked = true; t5_netplay_pause(); note("frame %u: lockstep pause requested (in-game select next)", f); }
            break;
        }
        if (select_live()) {
            g_pause_asked = false;
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
         * state) as before; without one the select screen is restarted
         * (select_restart() below), or left as it is when it is fresh
         * already. */
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
                /* a new select mode (the manager built it) going through its set-up */
                if (sel < 3 && (g_restart_inplace || rd32(mode_manager() + kMgrModeObj) != g_restart_obj)) g_restart_low = true;
                if (g_restart_low && select_live()) {
                    note("frame %u: select screen restarted (%u in this game)", f, ++g_restarts);
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
                    select_restart(f);
                }
            }
        }
        if ((f - g_ph_frame) % 300 == 0 && f > g_ph_frame) note("frame %u: reset: waiting in mode %u", f, mode);
        break;
    case Ph::Pick:
        pick_frame(f);
        break;
    case Ph::PickWait:
        pick_wait_frame(f);
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
/* the fight's rules (match_rules.h MatchRules::pack), latched at FIGHT START: the training rule in t5_hooks.cpp */
extern "C" uint32_t t5_df_rules(void) { return df::g_rules.pack(); }
/* Fights started in this netplay session (FIGHT START counts; a new session starts at 0): the same on
 * both PCs at their select screens and in a playback -- t5_hooks.cpp mixes it into the select screen's
 * random seed (Mokujin's copy). */
extern "C" uint32_t t5_df_session_matches(void) { return df::g_session_matches; }

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
/* ... and the mode it has asked for (14 = none): game state as well (rb_net.cpp post-match rule) */
extern "C" uint32_t t5_df_mode_next(void) { return df::mode_manager() ? df::mode_next() : 14u; }
extern "C" uint32_t t5_df_mode_cur(void) { return df::mode_manager() ? df::mode_cur() : 0u; }

namespace df {

void fight_init()
{
    const char* fight = getenv("T5_FIGHT");
    const char* file = getenv("T5_FIGHT_FILE");
    g_ctl = ctl_enabled();
    { const char* nm = getenv("T5_NET_MODE"); g_replay = nm && !_stricmp(nm, "replay") && !g_ctl; }
    if (!(fight && *fight) && !(file && *file) && !g_ctl && !g_replay) return;
    g_configured = true;
    { const char* r = getenv("T5_DF_RESET"); g_reset_titles = !(r && *r == '0'); }
    { const char* r = getenv("T5_DF_SELECT_RESTART"); g_restart_inplace = r && !strcmp(r, "inplace"); }
    { const char* k = getenv("T5_DF_SKIP"); g_skip = !(k && *k == '0'); }
    if (const char* w = getenv("T5_DF_STAGE_WAIT")) g_stage_wait = (uint32_t)atoi(w);
    { const char* r = getenv("T5_DF_FRESH"); g_fresh_on = !(r && *r == '0'); }
    { const char* r = getenv("T5_DF_FRESH_LOG"); g_fresh_log = r && *r == '1'; }
    if (const char* r = getenv("T5_DF_FRESH_AT")) g_fresh_at = (uint32_t)atoi(r);
    if (const char* r = getenv("T5_DF_STUCK_SECONDS")) g_stuck_s = (uint32_t)atoi(r);
    if (const char* r = getenv("T5_DF_SELECT_STUCK_SECONDS")) g_select_stuck_s = (uint32_t)atoi(r);
    if (const char* r = getenv("T5_DF_LEAVE_PHASE")) g_leave_phase = (uint32_t)atoi(r);
    {
        if (const char* r = getenv("T5_DF_READER_GUARD")) g_reader_guard = *r != '0';
        const char* spec = getenv("T5_DF_FRESH_RANGES");
        if (!spec || !*spec) spec = "1008E000:17000";   /* the fight-state block 0x1008E000..0x100A5000 (reset-fix: leftovers beyond the four hashed areas) */
        for (const char* p = spec; *p;) {
            char* e;
            const uint32_t a = (uint32_t)strtoul(p, &e, 16); if (e == p || *e != ':') break; p = e + 1;
            const uint32_t l = (uint32_t)strtoul(p, &e, 16); if (e == p) break; p = e;
            /* never the async reader's own data (live I/O state, see kReaderData): an area over it is split
             * (T5_DF_READER_GUARD=0: the old way, for comparisons) */
            const uint32_t end = a + l;
            if (g_reader_guard && a < kReaderDataEnd && end > kReaderData) {
                if (a < kReaderData) g_fresh_areas.push_back({ a, kReaderData - a, {} });
                if (end > kReaderDataEnd) g_fresh_areas.push_back({ kReaderDataEnd, end - kReaderDataEnd, {} });
            } else if (l) {
                g_fresh_areas.push_back({ a, l, {} });
            }
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
    if (const char* pk = getenv("T5_DF_PICK")) { const int n = atoi(pk); g_pick_default = n < 0 ? 0 : n > 120 ? 120 : n; }
    if (const char* ru = getenv("T5_DF_RULES")) g_rules_default = ru;
    { const char* t = getenv("T5_DF_TRACE"); g_trace_presses = t && *t == '1'; }
    if (fight && *fight && !g_ctl && !g_replay) parse_fight(fight, g_cfg);   /* (a replay reads its lines at the title) */
    note("direct fight: %s%s%s", g_cfg.valid ? g_cfg.text.c_str() : g_ctl ? "(persistent game: fights from the control channel)"
                                                                 : g_replay ? "(a replay: the fights come from the file)"
                                                                 : "(waiting for T5_FIGHT_FILE)",
         g_fight_file.empty() || g_ctl ? "" : ", next fights from ", g_fight_file.c_str());
    ctl_report(0);
}

} // namespace df
