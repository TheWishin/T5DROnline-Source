/*
 * T5DR direct fight -- the game control channel of a persistent game
 * (T5_CTL_DIR; docs/DIRECTFIGHT.md "Persistent game", docs/RANKED.md "Game
 * control channel").
 *
 * The launcher starts the game once with T5_CTL_DIR=<dir> and hands it every
 * match as a command; the game stays open between opponents:
 *
 *   <dir>/cmd.json    launcher -> game, replaced atomically, seq increasing
 *     {"seq": 3, "cmd": "fight", "match": "m1a2...", "rematch": false,
 *      "env": {"T5_NET_MODE": "host", "T5_NET_PORT": "52685", ..., "T5_FIGHT": "9,33,20,3",
 *              "T5_NET_RESULT_FILE": "...", "T5_HUD_NAMES": "A|B", "T5_HUD_RANKS": "11,3"}}
 *     {"seq": 4, "cmd": "idle"}     end the session (frees the UDP port), back to the select screen
 *     {"seq": 5, "cmd": "quit"}     exit
 *   <dir>/state.json  game -> launcher, replaced atomically on every change
 *     {"ctl": 1, "seq": <last command taken>, "state": "boot|idle|connecting|loading|fight|result|error",
 *      "match": ..., "error": ..., "session": n, "frame": f}
 *
 * A "fight" sets up netplay from its env exactly as if those variables had been
 * there at boot (a new session: new socket, handshake), then plays the fight.
 * A "fight" with "rematch": true while that session still runs is the next
 * match in it (like T5_FIGHT_FILE in process mode). The env goes to the
 * session environment overlay (t5_env_overlay_*), not to the process
 * environment: the runtime caches getenv().
 */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdio.h>
#include <string>
#include <vector>
#include "df.h"

extern "C" void t5_env_overlay_begin(void);
extern "C" void t5_env_overlay_set(const char* key, const char* value);

namespace df {

namespace {

std::string g_dir;
uint32_t g_seen = 0;                  /* seq of the last command taken */
FILETIME g_mtime = {};
uint32_t g_last_check = 0;
std::string g_state_text;

/* ---- a small JSON reader: objects, strings, numbers, true/false/null ---------- */
struct Json {
    const char* p;
    const char* end;
    bool ok = true;
    void ws() { while (p < end && (*p == ' ' || *p == '\t' || *p == '\r' || *p == '\n')) p++; }
    bool lit(const char* s) { size_t n = strlen(s); if ((size_t)(end - p) >= n && !memcmp(p, s, n)) { p += n; return true; } return false; }
    std::string str()
    {
        std::string out;
        if (p >= end || *p != '"') { ok = false; return out; }
        p++;
        while (p < end && *p != '"') {
            char c = *p++;
            if (c != '\\') { out += c; continue; }
            if (p >= end) { ok = false; return out; }
            c = *p++;
            switch (c) {
            case 'n': out += '\n'; break;
            case 't': out += '\t'; break;
            case 'r': out += '\r'; break;
            case 'b': out += '\b'; break;
            case 'f': out += '\f'; break;
            case 'u': {
                if (end - p < 4) { ok = false; return out; }
                unsigned cp = (unsigned)strtoul(std::string(p, 4).c_str(), nullptr, 16);
                p += 4;
                if (cp < 0x80) out += (char)cp;
                else if (cp < 0x800) { out += (char)(0xC0 | (cp >> 6)); out += (char)(0x80 | (cp & 0x3F)); }
                else { out += (char)(0xE0 | (cp >> 12)); out += (char)(0x80 | ((cp >> 6) & 0x3F)); out += (char)(0x80 | (cp & 0x3F)); }
                break; }
            default: out += c; break;   /* \" \\ \/ */
            }
        }
        if (p >= end) { ok = false; return out; }
        p++;
        return out;
    }
    /* any value as text (strings unquoted; objects/arrays skipped -> "") */
    std::string value()
    {
        ws();
        if (p >= end) { ok = false; return ""; }
        if (*p == '"') return str();
        if (*p == '{' || *p == '[') { skip(); return ""; }
        const char* b = p;
        while (p < end && *p != ',' && *p != '}' && *p != ']' && *p != ' ' && *p != '\r' && *p != '\n') p++;
        return std::string(b, p);
    }
    void skip()
    {
        int depth = 0;
        do {
            if (p >= end) { ok = false; return; }
            if (*p == '"') { str(); continue; }
            if (*p == '{' || *p == '[') depth++;
            else if (*p == '}' || *p == ']') depth--;
            p++;
        } while (depth > 0);
    }
    /* object: calls fn(key) with p at the value; fn must consume it */
    template <class F> void object(F fn)
    {
        ws();
        if (p >= end || *p != '{') { ok = false; return; }
        p++;
        for (;;) {
            ws();
            if (p < end && *p == '}') { p++; return; }
            std::string k = str();
            if (!ok) return;
            ws();
            if (p >= end || *p != ':') { ok = false; return; }
            p++;
            ws();
            fn(k);
            if (!ok) return;
            ws();
            if (p < end && *p == ',') { p++; continue; }
            if (p < end && *p == '}') { p++; return; }
            ok = false;
            return;
        }
    }
};

bool parse_cmd(const std::string& text, CtlCmd& c)
{
    Json j{ text.data(), text.data() + text.size() };
    c = CtlCmd();
    j.object([&](const std::string& k) {
        if (k == "seq") c.seq = (uint32_t)strtoul(j.value().c_str(), nullptr, 10);
        else if (k == "cmd") c.cmd = j.value();
        else if (k == "match") c.match = j.value();
        else if (k == "rematch") c.rematch = j.value() == "true";
        else if (k == "env") {
            j.ws();
            if (j.p < j.end && *j.p == '{') j.object([&](const std::string& ek) { c.env.push_back({ ek, j.value() }); });
            else j.value();
        } else j.value();
    });
    if (c.match == "null") c.match.clear();
    return j.ok && c.seq && !c.cmd.empty();
}

std::string json_str(const std::string& s)
{
    std::string o = "\"";
    for (char c : s) {
        if (c == '"' || c == '\\') { o += '\\'; o += c; }
        else if ((unsigned char)c < 0x20) { char b[8]; snprintf(b, sizeof b, "\\u%04x", c); o += b; }
        else o += c;
    }
    return o + "\"";
}

} // namespace

bool ctl_enabled() { return !g_dir.empty(); }

void ctl_init()
{
    const char* d = getenv("T5_CTL_DIR");
    if (!d || !*d) return;
    g_dir = d;
    CreateDirectoryA(g_dir.c_str(), nullptr);
    note("control channel %s: the game stays open between matches (persistent game)", g_dir.c_str());
}

bool ctl_poll(CtlCmd& out, uint32_t f, uint32_t every)
{
    if (g_dir.empty()) return false;
    if (every > 1 && f - g_last_check < every) return false;
    g_last_check = f;
    const std::string path = g_dir + "\\cmd.json";
    WIN32_FILE_ATTRIBUTE_DATA a;
    if (!GetFileAttributesExA(path.c_str(), GetFileExInfoStandard, &a)) return false;
    if (!CompareFileTime(&a.ftLastWriteTime, &g_mtime) && g_seen) return false;
    /* Opened with FILE_SHARE_DELETE: the launcher replaces cmd.json atomically
     * (os.replace = MoveFileEx), and Windows refuses that while another process
     * has the file open without delete sharing -- a command written while this
     * poll read the old one failed on the launcher's side (rematch-fix: one of
     * ~20 commands in a run, PermissionError in the test harness). */
    std::string text;
    HANDLE h = CreateFileA(path.c_str(), GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
                           nullptr, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, nullptr);
    if (h == INVALID_HANDLE_VALUE) return false;
    {
        char buf[4096];
        DWORD n = 0;
        while (ReadFile(h, buf, sizeof buf, &n, nullptr) && n > 0) text.append(buf, n);
        CloseHandle(h);
    }
    CtlCmd c;
    if (!parse_cmd(text, c)) return false;   /* half written? the next poll reads it again */
    g_mtime = a.ftLastWriteTime;
    if (c.seq <= g_seen) return false;
    g_seen = c.seq;
    note("frame %u: control command %u: %s%s%s (%zu variable(s))", f, c.seq, c.cmd.c_str(),
         c.match.empty() ? "" : " match ", c.match.c_str(), c.env.size());
    out = c;
    return true;
}

void ctl_apply_env(const CtlCmd& c)
{
    t5_env_overlay_begin();
    for (const auto& kv : c.env) t5_env_overlay_set(kv.first.c_str(), kv.second.c_str());
}

void ctl_state(const char* state, uint32_t f, const std::string& match, const char* error, uint32_t session)
{
    if (g_dir.empty()) return;
    const std::string key = std::string(state) + "|" + match + "|" + (error ? error : "") + "|" +
                            std::to_string(g_seen) + "|" + std::to_string(session);
    if (key == g_state_text) return;
    g_state_text = key;
    char head[160];
    snprintf(head, sizeof head, "{\"ctl\": 1, \"seq\": %u, \"state\": \"%s\", \"frame\": %u, \"session\": %u, \"match\": ",
             g_seen, state, f, session);
    std::string text = head;
    text += match.empty() ? "null" : json_str(match);
    text += ", \"error\": ";
    text += error ? json_str(error) : "null";
    text += "}\n";
    const std::string path = g_dir + "\\state.json", tmp = path + ".tmp";
    if (FILE* fp = fopen(tmp.c_str(), "wb")) {
        fwrite(text.data(), 1, text.size(), fp);
        fclose(fp);
        for (int i = 0; i < 60 && !MoveFileExA(tmp.c_str(), path.c_str(), MOVEFILE_REPLACE_EXISTING); i++) Sleep(1);
    }
}

} // namespace df
