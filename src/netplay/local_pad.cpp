/*
 * This PC's player online: the controller pressed last (local_pad.h has the rule and why).
 *
 *   T5_NET_PADPORT=N   (1..7) the online player is port N only -- N=1 is 1.1.1's way; unset or "auto": the rule
 *
 * Port 1 only, as before: [port1] device = ... in controls.ini (the player chose), local mode (two players at
 * one PC: P1 = port 1, P2 = port 2), netplay off. Callers: netplay's local sample (sample_local), the in-game
 * select (df_pick.cpp) and the replay controls (t5_hooks.cpp) -- one player, one choice for all of them.
 */
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include "../platform/t5_win.h"

#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <mutex>
#include <atomic>
#include <string>

#include "netplay.h"
#include "local_pad.h"

extern "C" int32_t cellPad_sample_local(uint32_t port_no, HostPadData* out);
extern "C" int32_t cellPad_local_connected(uint32_t port_no);
extern "C" int32_t cellPad_peek_local(uint32_t port_no, HostPadData* out);

namespace np {
namespace {

std::mutex g_mu;
lp::Follower g_follow;
int g_policy_logged = -2;               /* the policy last written to the log (-1 = follow) */
uint32_t g_switch_logs = 0;
/* UI only peeks the last selected device. It does not update the gameplay
 * follower, read controls.ini, or consume the simulation reader's tap latch. */
std::atomic<int> g_ui_port{0};
std::atomic<int> g_ui_fixed{0};

/* The controls.ini the runtime reads (pad_host_win32.c load_config): PS3_CONTROLS, else controls.ini next to
 * the exe, else in the working directory. "" = none (the runtime's built-in defaults). */
std::string read_controls_ini()
{
    auto slurp = [](const char* path, std::string* out) {
        FILE* f = fopen(path, "rb");
        if (!f) return false;
        char buf[4096];
        size_t n;
        while ((n = fread(buf, 1, sizeof buf, f)) > 0) out->append(buf, n);
        fclose(f);
        return true;
    };
    std::string text;
    const char* env = getenv("PS3_CONTROLS");          /* (the process's: the runtime read it at boot) */
    if (env && *env) {
        slurp(env, &text);
        return text;
    }
    char exe[MAX_PATH * 2];
    const DWORD n = GetModuleFileNameA(nullptr, exe, (DWORD)sizeof exe);
    if (n && n < sizeof exe) {
        if (char* slash = strrchr(exe, T5P_SEP[0])) {
            slash[1] = 0;
            std::string p = std::string(exe) + "controls.ini";
            if (slurp(p.c_str(), &text)) return text;
        }
    }
    slurp("controls.ini", &text);
    return text;
}

bool port1_pinned()
{
    static int pinned = -1;                            /* read once, like the runtime */
    if (pinned < 0) pinned = lp::port1_pinned_in(read_controls_ini()) ? 1 : 0;
    return pinned == 1;
}

/* -1 = follow the controller pressed last, else the one port to read (0-based); why says which rule. */
int policy(const char** why)
{
    if (const char* v = t5_env("T5_NET_PADPORT")) {
        const int n = atoi(v);
        if (n >= 1 && n <= lp::kPorts) { *why = "T5_NET_PADPORT"; return n - 1; }
    }
    const Mode m = mode();
    if (m == Mode::Off) { *why = "netplay off"; return 0; }
    if (m == Mode::Local && !replaying()) { *why = "two players at this PC"; return 0; }
    if (port1_pinned()) { *why = "[port1] device in controls.ini"; return 0; }
    *why = "";
    return -1;
}

uint64_t now_ms() { return GetTickCount64(); }

} // namespace

int local_player_sample(HostPadData* out)
{
    std::lock_guard<std::mutex> lk(g_mu);
    memset(out, 0, sizeof *out);
    const char* why = "";
    const int fixed = policy(&why);
    g_ui_fixed.store(fixed, std::memory_order_relaxed);
    if (fixed != g_policy_logged) {
        g_policy_logged = fixed;
        if (fixed >= 0) note("local player: port %d only (%s)", fixed + 1, why);
        else note("local player: the controller pressed last, on any port (T5_NET_PADPORT=1: port 1 only)");
    }
    if (fixed >= 0) {
        g_ui_port.store(fixed, std::memory_order_relaxed);
        cellPad_sample_local((uint32_t)fixed, out);
        return fixed;
    }
    static HostPadData d[lp::kPorts];
    lp::PortSample s[lp::kPorts];
    for (int p = 0; p < lp::kPorts; p++) {
        memset(&d[p], 0, sizeof d[p]);
        if (p > 0 && !cellPad_local_connected((uint32_t)p)) continue;
        if (cellPad_sample_local((uint32_t)p, &d[p]) != 0 || d[p].len == 0) continue;
        s[p].present = true;
        s[p].buttons = (uint16_t)((d[p].button[2] & 0xFF) | ((d[p].button[3] & 0xFF) << 8));
        s[p].rx = (uint8_t)d[p].button[4]; s[p].ry = (uint8_t)d[p].button[5];
        s[p].lx = (uint8_t)d[p].button[6]; s[p].ly = (uint8_t)d[p].button[7];
    }
    bool switched = false;
    const int was = g_follow.active();
    const int p = g_follow.update(s, now_ms(), &switched);
    if (switched && g_switch_logs++ < 16) {
        note("local player: port %d now (pressed there%s)%s", p + 1,
             s[was].present ? "; the one before was not pressed lately" : "; the one before is gone",
             g_switch_logs == 16 ? " -- further switches not logged" : "");
    }
    *out = d[p];
    g_ui_port.store(p, std::memory_order_relaxed);
    return p;
}

int local_player_peek_ui(HostPadData* out)
{
    memset(out, 0, sizeof *out);
    const int fixed = g_ui_fixed.load(std::memory_order_relaxed);
    if (fixed >= 0) return cellPad_peek_local((uint32_t)fixed, out) == 0 && out->len > 0 ? 0 : -1;
    /* This follower belongs to the live UI thread alone. Reconnects and a new
     * pad can navigate the idle menu even while gameplay is not sampling. */
    static lp::Follower follow;
    static int from_game = -1;
    const int selected = g_ui_port.load(std::memory_order_relaxed);
    if (from_game != selected) { follow.reset_to(selected); from_game = selected; }
    HostPadData data[lp::kPorts]{};
    lp::PortSample samples[lp::kPorts];
    for (int p = 0; p < lp::kPorts; ++p) {
        if (cellPad_peek_local((uint32_t)p, &data[p]) != 0 || data[p].len <= 0) continue;
        auto& sample = samples[p]; sample.present = true;
        sample.buttons = (uint16_t)((data[p].button[2] & 255) | ((data[p].button[3] & 255) << 8));
        sample.rx = (uint8_t)data[p].button[4]; sample.ry = (uint8_t)data[p].button[5];
        sample.lx = (uint8_t)data[p].button[6]; sample.ly = (uint8_t)data[p].button[7];
    }
    bool changed = false;
    const int p = follow.update(samples, now_ms(), &changed);
    *out = data[p];
    /* Signal a device change as a focus break so the menu requires release. */
    return changed ? 1 : out->len > 0 ? 0 : -1;
}

} // namespace np

/* The in-game select (src/directfight/df_pick.cpp) and the replay controls (t5_hooks.cpp): this PC's player, by
 * the same rule. `out` is cellPad_sample_local's layout ({ int32 len; uint16 button[64]; }). */
extern "C" int32_t t5_local_player_pad(void* out)
{
    np::local_player_sample(static_cast<HostPadData*>(out));
    return 0;
}

extern "C" int32_t t5_local_player_pad_ui(void* out)
{
    return np::local_player_peek_ui(static_cast<HostPadData*>(out));
}
