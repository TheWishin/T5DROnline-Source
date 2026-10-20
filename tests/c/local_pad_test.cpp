/*
 * Which controller is this PC's player online (src/netplay/local_pad.h / local_pad.cpp,
 * docs/NETPLAY.md "Which controller plays online"), without the runtime: the ports are fakes here.
 * tests/test_local_pad.py builds and runs it; prints "PASS <n> checks".
 *
 * Checked:
 *   - the follower: port 1 until another port is pressed; a press there switches at once and that very
 *     press is the player's input; idle, resting and stuck controllers never take over; one pad seen
 *     twice (a virtual pad mirroring it) never makes the input jump; a controller that goes away;
 *     stick directions with hysteresis; a port's first sample is no press;
 *   - controls.ini: which [port1] device lines pin player 1 (the runtime's parsing rules);
 *   - the glue (local_pad.cpp): port 1 only when pinned, in local mode, with T5_NET_PADPORT=1 or with
 *     netplay off; otherwise what the follower says, the chosen port's data handed over unchanged.
 */
#include <windows.h>
#include <cstdarg>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <map>
#include <string>

#include "../../src/netplay/netplay.h"

/* ---- fakes for what local_pad.cpp calls ------------------------------------------------------------- */
static np::Mode g_mode = np::Mode::Host;
static bool g_replay = false;
static std::map<std::string, std::string> g_env;
static HostPadData g_port[7];
static bool g_conn[7];
static int g_reads[7];

namespace np {
Mode mode() { return g_mode; }
bool replaying() { return g_replay; }
void note(const char* fmt, ...)
{
    va_list ap; va_start(ap, fmt);
    printf("  [netplay] "); vprintf(fmt, ap); printf("\n");
    va_end(ap);
}
}
extern "C" const char* t5_env(const char* key)
{
    auto it = g_env.find(key);
    return it == g_env.end() ? nullptr : it->second.c_str();
}
extern "C" int32_t cellPad_sample_local(uint32_t port, HostPadData* out)
{
    memset(out, 0, sizeof *out);
    if (port >= 7) return -1;
    g_reads[port]++;
    if (port != 0 && !g_conn[port]) return 0;
    *out = g_port[port];
    return 0;
}
extern "C" int32_t cellPad_local_connected(uint32_t port) { return port == 0 || (port < 7 && g_conn[port]); }

#include "../../src/netplay/local_pad.cpp"

/* ---- checks ----------------------------------------------------------------------------------------- */
static int g_checks, g_fail;
#define CHECK(c, ...) do { g_checks++; if (!(c)) { g_fail++; printf("FAIL %s:%d: ", __FILE__, __LINE__); \
    printf(__VA_ARGS__); printf("\n"); } } while (0)

using np::lp::Follower;
using np::lp::PortSample;
using np::lp::kPorts;

constexpr uint16_t CROSS = 0x4000, CIRCLE = 0x2000, SQUARE = 0x8000, RIGHT = 0x0020, LEFT = 0x0080, START = 0x0008;

struct Rig {
    Follower f;
    PortSample s[kPorts];
    uint64_t t = 1000;
    Rig() { s[0].present = true; }
    int step(uint64_t ms = 16) { t += ms; return f.update(s, t); }
};

static void follower_checks()
{
    {   /* one controller: port 1, always */
        Rig r;
        for (int i = 0; i < 10; i++) {
            r.s[0].buttons = (i & 1) ? CROSS : 0;
            CHECK(r.step() == 0, "lone pad");
        }
    }
    {   /* an idle pad on port 1, the DualSense on port 2: its first press makes it the player, that press included */
        Rig r;
        r.s[1].present = true;
        CHECK(r.step() == 0, "starts at port 1");
        for (int i = 0; i < 20; i++) CHECK(r.step() == 0, "nothing pressed: stays");
        r.s[1].buttons = CROSS;
        CHECK(r.step() == 1, "the press on port 2 switches at once");
        r.s[1].buttons = 0;
        CHECK(r.step() == 1, "released: stays");
        for (int i = 0; i < 100; i++) CHECK(r.step() == 1, "idle port 1 never takes it back");
    }
    {   /* a controller that rests with something held (a pedal at one end, a stuck button): never a press */
        Rig r;
        r.s[0].buttons = LEFT; r.s[0].lx = 0;           /* port 1: held from its first sample on */
        r.s[1].present = true;
        r.step();
        r.s[1].buttons = CIRCLE;
        CHECK(r.step() == 1, "press on port 2");
        r.s[1].buttons = 0;
        for (int i = 0; i < 50; i++) CHECK(r.step() == 1, "the held port never takes over");
    }
    {   /* a port that appears holding a button: its first sample is where it rests */
        Rig r;
        r.step();
        r.s[2].present = true; r.s[2].buttons = START;
        CHECK(r.step() == 0, "a new port's held button is no press");
        CHECK(r.step() == 0, "still no press");
        r.s[2].buttons = 0; r.step();
        r.s[2].buttons = START;
        CHECK(r.step() == 2, "a real press on it");
    }
    {   /* one pad seen twice (DS4Windows' virtual pad on port 1, the real pad on port 2): presses on both, a frame
           apart in either order -- the player never jumps between them while it plays */
        Rig r;
        r.s[1].present = true;
        r.step();
        r.s[1].buttons = CROSS; CHECK(r.step() == 1, "the real pad first: port 2");
        r.s[0].buttons = CROSS; CHECK(r.step() == 1, "the mirror a frame later: still port 2");
        int switches = 0, last = 1;
        for (int i = 0; i < 200; i++) {
            const uint16_t b = (i % 7 < 3) ? (uint16_t)(SQUARE | RIGHT) : 0;
            r.s[1].buttons = b;
            r.s[0].buttons = (i % 7 < 4 && i % 7 > 0) ? (uint16_t)(SQUARE | RIGHT) : 0;   /* a frame behind */
            const int p = r.step();
            if (p != last) switches++;
            last = p;
        }
        CHECK(switches == 0, "mirror: %d switches", switches);
        switches = 0;
        for (int i = 0; i < 400; i++) {
            r.s[0].buttons = (i % 20 < 3) ? CROSS : 0;                                    /* now port 1 leads */
            r.s[1].buttons = (i % 20 < 4 && i % 20 > 0) ? CROSS : 0;
            const int p = r.step();
            if (p != last) switches++;
            last = p;
        }
        CHECK(switches <= 1 && last == 0, "mirror, the other one first: %d switches (at most one, to the one "
              "that is first), ends on port %d", switches, last + 1);
    }
    {   /* someone else's press on another pad while the player plays: ignored; after a pause it may take over */
        Rig r;
        r.s[1].present = true;
        r.step();
        r.s[1].buttons = CROSS; CHECK(r.step() == 1, "player on port 2");
        r.s[1].buttons = 0; r.s[0].buttons = CIRCLE;
        CHECK(r.step(16) == 1, "a press on port 1 16 ms after the player's: stays");
        r.s[0].buttons = 0; r.step(16);
        r.s[0].buttons = CIRCLE;
        CHECK(r.step(200) == 0, "after 200 ms without a press on port 2: port 1 takes it");
    }
    {   /* the player's controller goes away: back to the lowest port with something on it */
        Rig r;
        r.s[2].present = true; r.s[4].present = true;
        r.step();
        r.s[4].buttons = CROSS; CHECK(r.step() == 4, "port 5");
        r.s[4] = PortSample();
        CHECK(r.step() == 0, "port 5 unplugged: port 1");
        r.s[2].buttons = CROSS; CHECK(r.step() == 2, "then a press on port 3");
        r.s[4].present = true; r.s[4].buttons = CROSS;
        CHECK(r.step(500) == 2, "port 5 back, holding: no press");
    }
    {   /* sticks: half deflection counts, a stick resting near the line does not count again and again */
        Rig r;
        r.s[1].present = true;
        r.step();
        r.s[1].lx = 100; CHECK(r.step() == 0, "a quarter tilt is no press");
        r.s[1].lx = 20; CHECK(r.step() == 1, "past half: a press");
        Rig q;
        q.s[1].present = true; q.s[1].ly = 60;    /* a drifting stick resting past the line */
        q.step();
        q.s[0].buttons = CROSS; q.step(); q.s[0].buttons = 0; q.step(500);
        int jumps = 0;
        for (int i = 0; i < 100; i++) {          /* 55..90: wobbling across 64, never back inside 96 */
            q.s[1].ly = (uint8_t)(55 + (i * 7) % 36);
            if (q.step(500) != 0) jumps++;
        }
        CHECK(jumps == 0, "a stick wobbling at the line took over %d times", jumps);
        uint8_t d = np::lp::stick_dirs(PortSample(), 0);
        CHECK(d == 0, "centred sticks: no direction (%02X)", d);
        PortSample a; a.rx = 255; a.ry = 0;
        d = np::lp::stick_dirs(a, 0);
        CHECK(d == ((2u << 4) | (1u << 6)), "RX high, RY low: %02X", d);
    }
}

static void ini_checks()
{
    using np::lp::port1_pinned_in;
    struct { const char* text; bool pinned; } cases[] = {
        { "", false },
        { "[port1]\ndevice = auto\n", false },
        { "[port1]\ndevice =\n", false },
        { "[port1]\ndevice = dinput:054C:0CE6\n", true },
        { "[port1]\r\ndevice = xinput\r\n", true },
        { "[PORT1]\nDevice = XInput:0   ; my pad\n", true },
        { "[port1]\ndevice = none\n", true },
        { "[port1]\ndevice = gamepad\n", false },                              /* unknown: the runtime says auto */
        { "[port1]\ndevice = dinput:0F0D:00EE\ndevice = auto\n", false },     /* the last one wins */
        { "[port1]\ndevice = auto\ndevice = dinput:Hori\n", true },
        { "[port2]\ndevice = dinput:054C:0CE6\n", false },
        { "[port1]\n; device = dinput:054C:0CE6\n", false },
        { "[port1]\n# device = xinput\n", false },
        { "[port1]\nmacros = tekken\n[port1]\ndevice = xinput\n", false },     /* the first [port1] counts */
        { "[port1]\ndevice = xinput\n[port2]\ndevice = auto\n", true },
        { "[general]\ndevice = xinput\n", false },
        { "device = xinput\n[port1]\n", false },
        { "[port1\ndevice = xinput\n", false },                                /* a broken header: no section */
        { "[ port1 ]\n  device   =   dinput   \n", true },
        { "[port1]\ndevice = auto#x\n", false },                               /* no space before #: part of it */
        { "[port1]\ndevice = auto #x\n", false },
    };
    for (auto& c : cases)
        CHECK(port1_pinned_in(c.text) == c.pinned, "ini %s -> %d", c.text, (int)c.pinned);
}

static void set_port(int p, uint16_t buttons, uint8_t lx = 128)
{
    HostPadData& d = g_port[p];
    memset(&d, 0, sizeof d);
    d.len = 8;
    d.button[2] = (uint16_t)(buttons & 0xFF);
    d.button[3] = (uint16_t)(buttons >> 8);
    d.button[4] = d.button[5] = d.button[7] = 128;
    d.button[6] = lx;
    d.button[8] = (uint16_t)(0x100 + p);             /* a marker: which port's data came back */
}

static int sample(HostPadData* out) { return np::local_player_sample(out); }

static void glue_checks(const char* tmpdir)
{
    char ini[MAX_PATH];
    snprintf(ini, sizeof ini, "%s\\controls_auto.ini", tmpdir);
    FILE* f = fopen(ini, "w");
    fputs("[port1]\ndevice = auto\n", f);
    fclose(f);
    SetEnvironmentVariableA("PS3_CONTROLS", ini);
    _putenv_s("PS3_CONTROLS", ini);

    HostPadData out;
    memset(g_conn, 0, sizeof g_conn);
    set_port(0, 0);
    g_conn[1] = true; set_port(1, 0);
    g_mode = np::Mode::Host;
    int p = sample(&out);
    CHECK(p == 0 && out.button[8] == 0x100, "host: port 1 at first (%d)", p);
    CHECK(g_reads[1] == 1 && g_reads[2] == 0, "every port with something is read, the others not (%d %d)",
          g_reads[1], g_reads[2]);
    set_port(1, CROSS);
    p = sample(&out);
    CHECK(p == 1 && out.button[8] == 0x101 && out.button[3] == (CROSS >> 8), "a press on port 2 is the player's (%d)", p);
    set_port(1, 0);
    p = sample(&out);
    CHECK(p == 1 && out.button[3] == 0, "released, still port 2");

    g_env["T5_NET_PADPORT"] = "1";
    const int reads1 = g_reads[1];
    set_port(1, CIRCLE);
    p = sample(&out);
    CHECK(p == 0 && out.button[8] == 0x100 && g_reads[1] == reads1, "T5_NET_PADPORT=1: port 1 only, port 2 not read");
    g_env.erase("T5_NET_PADPORT");
    set_port(1, 0); sample(&out);

    g_mode = np::Mode::Local;
    set_port(1, SQUARE);
    p = sample(&out);
    CHECK(p == 0, "local mode (two players here): port 1 for P1 (%d)", p);
    g_replay = true;
    set_port(1, 0); sample(&out);
    set_port(1, START);
    p = sample(&out);
    CHECK(p == 1, "replay playback: any controller steers it (%d)", p);
    g_replay = false;
    g_mode = np::Mode::Off;
    p = sample(&out);
    CHECK(p == 0, "netplay off: port 1 (%d)", p);
    g_mode = np::Mode::Join;
    set_port(1, 0);
    p = sample(&out);
    CHECK(p == 1, "join: back to the followed port (%d)", p);
}

static void glue_pinned_checks(const char* tmpdir)
{
    /* a fresh process state would be needed for the read-once pin; this runs as its own process (pinned=...) */
    char ini[MAX_PATH];
    snprintf(ini, sizeof ini, "%s\\controls_pinned.ini", tmpdir);
    FILE* f = fopen(ini, "w");
    fputs("[general]\nhid = 1\n[port1]\ndevice = dinput:054C:0CE6   ; my DualSense\n", f);
    fclose(f);
    _putenv_s("PS3_CONTROLS", ini);
    HostPadData out;
    memset(g_conn, 0, sizeof g_conn);
    set_port(0, 0);
    g_conn[1] = true; set_port(1, 0);
    g_mode = np::Mode::Host;
    sample(&out);
    set_port(1, CROSS);
    const int p = sample(&out);
    CHECK(p == 0 && out.button[8] == 0x100, "[port1] pinned: port 1 only (%d)", p);
    CHECK(g_reads[1] == 0, "pinned: port 2 is never read (%d)", g_reads[1]);
}

int main(int argc, char** argv)
{
    char tmp[MAX_PATH];
    GetTempPathA(sizeof tmp, tmp);
    const char* dir = argc > 2 ? argv[2] : tmp;
    if (argc > 1 && !strcmp(argv[1], "pinned")) {
        glue_pinned_checks(dir);
    } else {
        follower_checks();
        ini_checks();
        glue_checks(dir);
    }
    if (g_fail) { printf("FAILED %d of %d checks\n", g_fail, g_checks); return 1; }
    printf("PASS %d checks\n", g_checks);
    return 0;
}
