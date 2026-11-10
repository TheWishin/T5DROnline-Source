/*
 * T5DR input display -- the player's own names for the buttons (docs/TRAINING.md
 * "Your own button names") and who gets the display in offline Versus. Pure
 * logic: training.cpp hands in the text of the controls.ini the runtime reads;
 * tests/c/button_names_test.cpp checks the rules.
 *
 *   [names]            both players
 *   [names1] [names2]  player 1 / player 2 only (win over [names])
 *   1 = LP             targets as in a binding line: 1 2 3 4 (or LP RP LK RK, or
 *   CROSS = KICK       SQUARE TRIANGLE CROSS CIRCLE), L1 R1 L2 R2 L3 R3 START SELECT
 *   L1 = TAG
 *
 * The ini rules are the runtime's (pad_host_win32.c ini_load): lines starting
 * with ; or # are comments, so is whitespace followed by ; or # after a value;
 * names are case-insensitive; of a section given twice only the first counts;
 * of a key given twice the last. A name is at most kNameChars characters
 * (UTF-8), control characters are dropped, "quotes" around it are taken off;
 * an empty name is the default.
 *
 * Defaults: 1 2 3 4 for the attack buttons. The other eight buttons have no
 * place in the list by default: each is listed once it has a name.
 */
#pragma once
#include <stdint.h>
#include <stddef.h>
#include <string.h>

namespace training {

enum : int { kBtn1 = 0, kBtn2, kBtn3, kBtn4, kBtnL1, kBtnR1, kBtnL2, kBtnR2, kBtnL3, kBtnR3, kBtnStart, kBtnSelect, kBtnCount };
constexpr int kNameChars = 8;                     /* characters shown per name */
constexpr int kNameBytes = kNameChars * 4 + 1;

/* the game's pad mask (a DUALSHOCK 3's digital word) for the eight other buttons */
constexpr uint16_t kPadL2 = 0x0001, kPadR2 = 0x0002, kPadL1 = 0x0004, kPadR1 = 0x0008,
                   kPadSelect = 0x0100, kPadL3 = 0x0200, kPadR3 = 0x0400, kPadStart = 0x0800;

inline const char* button_default_name(int b)
{
    static const char* const def[kBtnCount] = { "1", "2", "3", "4", "L1", "R1", "L2", "R2", "L3", "R3", "START", "SELECT" };
    return b >= 0 && b < kBtnCount ? def[b] : "";
}

struct ButtonNames {
    char name[2][kBtnCount][kNameBytes];
    bool custom[2][kBtnCount];                    /* named in controls.ini */
    ButtonNames() { reset(); }
    void reset()
    {
        for (int p = 0; p < 2; p++)
            for (int b = 0; b < kBtnCount; b++) {
                strncpy(name[p][b], button_default_name(b), kNameBytes - 1);
                name[p][b][kNameBytes - 1] = 0;
                custom[p][b] = false;
            }
    }
    bool any_custom(int p) const
    {
        for (int b = 0; b < kBtnCount; b++) if (custom[p][b]) return true;
        return false;
    }
    /* the named ones among the eight other buttons, as display bits kBtnL1..kBtnSelect */
    uint16_t extras(int p) const
    {
        uint16_t m = 0;
        for (int b = kBtnL1; b < kBtnCount; b++) if (custom[p][b]) m |= (uint16_t)(1u << b);
        return m;
    }
};

namespace names_detail {

inline char up(char c) { return c >= 'a' && c <= 'z' ? (char)(c - 32) : c; }
inline bool space(char c) { return c == ' ' || c == '\t' || c == '\r' || c == '\n' || c == '\v' || c == '\f'; }
inline bool eq(const char* a, size_t n, const char* b)
{
    size_t i = 0;
    for (; i < n && b[i]; i++) if (up(a[i]) != b[i]) return false;
    return i == n && !b[i];
}
inline void trim(const char*& s, size_t& n)
{
    while (n && space(*s)) { s++; n--; }
    while (n && space(s[n - 1])) n--;
}
inline int target(const char* k, size_t n)
{
    static const struct { const char* key; int b; } t[] = {
        { "1", kBtn1 }, { "LP", kBtn1 }, { "SQUARE", kBtn1 }, { "2", kBtn2 }, { "RP", kBtn2 }, { "TRIANGLE", kBtn2 },
        { "3", kBtn3 }, { "LK", kBtn3 }, { "CROSS", kBtn3 }, { "4", kBtn4 }, { "RK", kBtn4 }, { "CIRCLE", kBtn4 },
        { "L1", kBtnL1 }, { "R1", kBtnR1 }, { "L2", kBtnL2 }, { "R2", kBtnR2 }, { "L3", kBtnL3 }, { "R3", kBtnR3 },
        { "START", kBtnStart }, { "SELECT", kBtnSelect },
    };
    for (const auto& e : t) if (eq(k, n, e.key)) return e.b;
    return -1;
}
/* at most kNameChars characters of well-formed UTF-8, no control characters; false = nothing left */
inline bool clean(const char* v, size_t n, char out[kNameBytes])
{
    if (n >= 2 && v[0] == '"' && v[n - 1] == '"') { v++; n -= 2; }
    trim(v, n);
    size_t k = 0;
    int chars = 0;
    for (size_t i = 0; i < n && chars < kNameChars;) {
        const unsigned char c = (unsigned char)v[i];
        const size_t len = c < 0x80 ? 1 : (c & 0xE0) == 0xC0 ? 2 : (c & 0xF0) == 0xE0 ? 3 : (c & 0xF8) == 0xF0 ? 4 : 0;
        bool ok = len && i + len <= n && !(c < 0x20 || c == 0x7F);
        for (size_t j = 1; ok && j < len; j++) ok = ((unsigned char)v[i + j] & 0xC0) == 0x80;
        if (!ok) { i++; continue; }                 /* a control character or a broken sequence: dropped */
        memcpy(out + k, v + i, len);
        k += len; i += len; chars++;
    }
    while (k && out[k - 1] == ' ') k--;             /* (a name cut at a space) */
    out[k] = 0;
    return k != 0;
}

} // namespace names_detail

/* The names in a controls.ini's text ("" or no [names] section: the defaults). */
inline void parse_button_names(const char* text, size_t len, ButtonNames& out)
{
    using namespace names_detail;
    out.reset();
    bool seen[3] = { false, false, false };          /* [names] [names1] [names2] already given */
    bool own[2][kBtnCount] = {};                     /* set by the player's own section: [names] does not replace it */
    int sec = -1;                                    /* 0 [names], 1 [names1], 2 [names2], -1 another or a repeat */
    for (size_t pos = 0; pos < len;) {
        size_t end = pos;
        while (end < len && text[end] != '\n') end++;
        const char* s = text + pos;
        size_t n = end - pos;
        pos = end + 1;
        trim(s, n);
        if (!n || *s == ';' || *s == '#') continue;
        if (*s == '[') {
            const char* e = (const char*)memchr(s, ']', n);
            sec = -1;
            if (!e) continue;
            const char* name = s + 1;
            size_t nn = (size_t)(e - name);
            trim(name, nn);
            const int k = eq(name, nn, "NAMES") ? 0 : eq(name, nn, "NAMES1") ? 1 : eq(name, nn, "NAMES2") ? 2 : -1;
            if (k >= 0 && !seen[k]) { seen[k] = true; sec = k; }
            continue;
        }
        if (sec < 0) continue;
        const char* eqs = (const char*)memchr(s, '=', n);
        if (!eqs) continue;
        const char* key = s;
        size_t kn = (size_t)(eqs - s);
        const char* val = eqs + 1;
        size_t vn = n - kn - 1;
        for (size_t i = 1; i < vn; i++)
            if ((val[i] == ';' || val[i] == '#') && space(val[i - 1])) { vn = i; break; }
        trim(key, kn);
        trim(val, vn);
        const int b = target(key, kn);
        if (b < 0) continue;
        char nm[kNameBytes];
        const bool has = clean(val, vn, nm);
        for (int p = 0; p < 2; p++) {
            if (sec != 0 && sec - 1 != p) continue;
            if (sec == 0 && own[p][b]) continue;
            if (sec != 0) own[p][b] = true;
            strncpy(out.name[p][b], has ? nm : button_default_name(b), kNameBytes - 1);
            out.name[p][b][kNameBytes - 1] = 0;
            out.custom[p][b] = has;
        }
    }
}

/* The other buttons of a pad mask as display bits kBtnL1..kBtnSelect. */
inline uint16_t pad_extras(uint16_t pad)
{
    return (uint16_t)(((pad & kPadL1) ? 1u << kBtnL1 : 0) | ((pad & kPadR1) ? 1u << kBtnR1 : 0) |
                      ((pad & kPadL2) ? 1u << kBtnL2 : 0) | ((pad & kPadR2) ? 1u << kBtnR2 : 0) |
                      ((pad & kPadL3) ? 1u << kBtnL3 : 0) | ((pad & kPadR3) ? 1u << kBtnR3 : 0) |
                      ((pad & kPadStart) ? 1u << kBtnStart : 0) | ((pad & kPadSelect) ? 1u << kBtnSelect : 0));
}

/* "LP+RK", "1+2", "TAG": the pressed buttons (display bits) under player p's names, joined with +.
 * Whole names only: what does not fit in n bytes is left out. */
inline void buttons_named(uint16_t bits, const ButtonNames& names, int p, char* out, size_t n)
{
    size_t k = 0;
    if (n) out[0] = 0;
    for (int b = 0; b < kBtnCount; b++) {
        if (!(bits & (1u << b))) continue;
        const size_t l = strlen(names.name[p][b]);
        if (k + l + (k ? 1 : 0) + 1 > n) break;
        if (k) out[k++] = '+';
        memcpy(out + k, names.name[p][b], l);
        k += l;
        out[k] = 0;
    }
}

/* The input list's panel: as wide as its widest row needs (the buttons' text), within limits. */
constexpr float kHistW = 156.0f, kHistMaxW = 372.0f;
inline float history_width(float widest_buttons_text)
{
    const float w = 78.0f + widest_buttons_text + 12.0f;     /* frames, direction, text, margin */
    return w < kHistW ? kHistW : w > kHistMaxW ? kHistMaxW : w;
}

/* ---- who gets the input display in an offline fight -------------------------------
 * (not online, not a replay: the caller's rule). Practice, or every offline mode with
 * "also in the other offline modes": the training setting, switched by F2. Otherwise
 * only Versus with its own setting (off by default): the inputs, never frame data,
 * switched off and on by F2. */
enum : int { kShowOff = 0, kShowInputs = 1, kShowFrames = 2 };

/* Versus runs on its own setting (and F2 switches that one) */
inline bool versus_own_display(bool versus, bool vs_setting, bool all, int training_setting)
{
    return versus && vs_setting && !(all && training_setting != kShowOff);
}

/* training_mode: the training setting or F2's choice; vs_f2: F2's choice in Versus (-1 none, 0 off, 1 on) */
inline int offline_show(bool practice, bool all, int training_setting, int training_mode,
                        bool versus, bool vs_setting, int vs_f2)
{
    if (versus_own_display(versus, vs_setting, all, training_setting)) return vs_f2 == 0 ? kShowOff : kShowInputs;
    if (practice || all) return training_mode;
    return kShowOff;
}

} // namespace training
