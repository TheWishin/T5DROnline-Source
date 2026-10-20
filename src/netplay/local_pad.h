/*
 * Which of this PC's controllers is the online player (docs/NETPLAY.md "Which controller plays online").
 *
 * Offline the game reads every PS3 port, so a pad the runtime put on port 2 (player 2) still plays. Online
 * there is one local player, and up to 1.1.1 netplay took it from port 1 only: a DualSense that landed on
 * port 2 -- because something else was on port 1 first (a virtual Xbox pad from DS4Windows / DSX / ViGEm, a
 * handheld's built-in pad, a pad lying on the desk, a wheel; the runtime gives XInput devices their ports
 * before PlayStation pads) -- worked offline and did nothing online.
 *
 * Now the online player is the controller pressed last: every local port with something on it is read at
 * every sample, and the port whose buttons (or a stick pushed past half way) were pressed most recently is
 * the player. A port that never changes -- an idle pad, a virtual pad nobody uses, a pedal resting at one
 * end -- never takes over. Two ports that are one pad seen twice (a virtual pad mirroring the real one)
 * press together; the one in use keeps the player while it was pressed in the last kQuietMs, so the input
 * never jumps between them. Pinned in controls.ini (`[port1] device = ...`): port 1 only, as before.
 *
 * Only the local sample changes: it is exchanged with the peer like any input, so the choice needs no
 * agreement between the PCs, and rollback re-simulation never reads devices (it replays exchanged inputs).
 *
 * This header is the pure part (no runtime calls), tests/c/local_pad_test.cpp checks it.
 */
#pragma once
#include <ctype.h>
#include <stdint.h>
#include <string.h>
#include <string>

namespace np {
namespace lp {

constexpr int kPorts = 7;               /* the runtime's ports (PADH_MAX_PORTS, CELL_PAD_MAX_PORT_NUM) */
constexpr uint64_t kQuietMs = 100;      /* the controller in use keeps the player while pressed this recently */

/* One port as cellPad_sample_local gives it. */
struct PortSample {
    bool     present = false;           /* something is on the port and it was read */
    uint16_t buttons = 0;               /* CELL_PAD_CTRL_* (DIGITAL1 low byte, DIGITAL2 high byte) */
    uint8_t  lx = 128, ly = 128, rx = 128, ry = 128;
};

/* Stick directions past half deflection, 2 bits per axis (LX low/high, LY, RX, RY). A direction comes on
 * beyond 64 / 191 and goes off only back inside 96..160, so a stick that rests near the line never counts
 * as pushed again and again. */
inline uint8_t stick_dirs(const PortSample& s, uint8_t prev)
{
    const uint8_t v[4] = { s.lx, s.ly, s.rx, s.ry };
    uint8_t out = 0;
    for (int a = 0; a < 4; a++) {
        const uint8_t lo = (uint8_t)(1u << (2 * a)), hi = (uint8_t)(2u << (2 * a));
        if (v[a] < 64 || ((prev & lo) && v[a] < 96)) out |= lo;
        if (v[a] > 191 || ((prev & hi) && v[a] > 160)) out |= hi;
    }
    return out;
}

/* Follows the controller pressed last. update() once per sample of every port. */
class Follower {
public:
    /* -> the port whose input is the player's now. *switched: it changed in this call. */
    int update(const PortSample (&s)[kPorts], uint64_t now_ms, bool* switched = nullptr)
    {
        bool rise[kPorts] = {};
        for (int p = 0; p < kPorts; p++) {
            Seen& w = seen_[p];
            if (!s[p].present) { w = Seen(); continue; }
            const uint8_t d = stick_dirs(s[p], w.have ? w.dirs : 0);
            /* the first sample of a port is where it rests, not a press */
            if (w.have) rise[p] = (s[p].buttons & (uint16_t)~w.buttons) != 0 || (d & (uint8_t)~w.dirs) != 0;
            w.have = true; w.buttons = s[p].buttons; w.dirs = d;
        }
        const int was = active_;
        if (!s[active_].present) {               /* its controller is gone: the lowest port with something */
            active_ = 0;
            for (int p = 0; p < kPorts; p++) if (s[p].present) { active_ = p; break; }
            pressed_ = false;
        }
        if (rise[active_]) {
            pressed_ = true; pressed_t_ = now_ms;
        } else {
            int cand = -1;
            for (int p = 0; p < kPorts && cand < 0; p++) if (rise[p]) cand = p;
            if (cand >= 0 && (!pressed_ || now_ms - pressed_t_ >= kQuietMs)) {
                active_ = cand; pressed_ = true; pressed_t_ = now_ms;
            }
        }
        if (switched) *switched = active_ != was;
        return active_;
    }
    int active() const { return active_; }
    void reset() { *this = Follower(); }

private:
    struct Seen { bool have = false; uint16_t buttons = 0; uint8_t dirs = 0; };
    Seen seen_[kPorts];
    int active_ = 0;
    bool pressed_ = false;                   /* the active port was pressed since it became the player */
    uint64_t pressed_t_ = 0;
};

/* Is player 1's device pinned in this controls.ini text? The runtime's rules (ps3recomp patch 0009,
 * pad_host_win32.c ini_load / ini_get / parse_device_spec): the first [port1] section counts, the last
 * `device` key in it wins, `none`, `xinput...` and `dinput...` pin, anything else (auto, empty, unknown)
 * does not. Comment lines start with ; or #, an inline comment is whitespace then ; or #. */
inline bool port1_pinned_in(const std::string& text)
{
    auto trim = [](std::string s) {
        size_t a = 0, b = s.size();
        while (a < b && isspace((unsigned char)s[a])) a++;
        while (b > a && isspace((unsigned char)s[b - 1])) b--;
        return s.substr(a, b - a);
    };
    auto ieq = [](const std::string& a, const char* b) { return _stricmp(a.c_str(), b) == 0; };
    int sec = 0;                             /* 0 none yet, 1 in the first [port1], 2 after it */
    bool in_cur = false, have = false;
    std::string dev;
    size_t pos = 0;
    while (pos <= text.size()) {
        size_t e = text.find('\n', pos);
        if (e == std::string::npos) e = text.size();
        std::string s = trim(text.substr(pos, e - pos));
        pos = e + 1;
        if (s.empty() || s[0] == ';' || s[0] == '#') continue;
        if (s[0] == '[') {
            const size_t r = s.find(']');
            const bool p1 = r != std::string::npos && ieq(trim(s.substr(1, r - 1)), "port1");
            if (in_cur) sec = 2;
            in_cur = p1 && sec == 0;
            if (in_cur) sec = 1;
            continue;
        }
        if (!in_cur) continue;
        const size_t eq = s.find('=');
        if (eq == std::string::npos) continue;
        if (!ieq(trim(s.substr(0, eq)), "device")) continue;
        std::string v = s.substr(eq + 1);
        for (size_t i = 1; i < v.size(); i++)
            if ((v[i] == ';' || v[i] == '#') && isspace((unsigned char)v[i - 1])) { v.resize(i); break; }
        dev = trim(v); have = true;
    }
    if (!have || dev.empty()) return false;
    return ieq(dev, "none") || _strnicmp(dev.c_str(), "xinput", 6) == 0 || _strnicmp(dev.c_str(), "dinput", 6) == 0;
}

} // namespace lp
} // namespace np
