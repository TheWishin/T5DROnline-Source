/*
 * A DirectInput device that is lost again right after it was found (patch 0087, libs/input/pad_host_win32.c).
 * A Razer Panthera PS4 in PS4 mode (1532:0401) showed two DirectInput devices of that name: the stick, and a
 * phantom that failed its reads at once and was found again every ~0.5 s -- port 2 flipped disconnected /
 * connected ~200 times and the game's menus got presses nobody made.
 *
 * Here DirectInput itself is a fake (an IDirectInput8W / IDirectInputDevice8W in C) with two devices of the
 * same name and VID:PID: "the stick", which reads a state the test sets, and "the phantom", whose first reads
 * after an Acquire return a zeroed HID state (axes at their minimum, hat 0 = up) and whose later reads fail.
 * The runtime's own code runs on it -- its hot-plug thread, its 1 ms sampler thread and padh_read as the game
 * reads -- for:
 *   1. 4 s with both plugged in: port 2 must never connect, no read of port 1 or 2 may hold a press or a
 *      stick off centre, and the phantom must be created at most 3 times (then quarantined);
 *   2. the stick's B2 -> CROSS on port 1 (it still works);
 *   3. the stick unplugged and plugged in again with B3 held: no CIRCLE until B3 is released and pressed again.
 *
 *   pad_flap_test               the scenario; prints the counts and "PASS <n> checks" (exit 0) or the failures
 *   pad_flap_test ini=<file>    load <file> as controls.ini and print [general] tap_latch as the runtime reads it
 *
 * The runtime file is included as it is (its functions are static). Built by tests/test_pad_flap.py with
 * clang-cl or cl against the Windows SDK, like ps_hid_test.c; it also builds against the runtime before
 * patch 0087, where the scenario fails (the test's proof that it sees the bug).
 */
#include <windows.h>
/* The hot-plug thread rescans DirectInput when Windows' input device count changes: the test's count. */
static volatile LONG g_fake_raw_count = 10;
static UINT WINAPI fake_GetRawInputDeviceList(PRAWINPUTDEVICELIST l, PUINT n, UINT cb)
{
    (void)l; (void)cb;
    if (n) *n = (UINT)g_fake_raw_count;
    return 0;
}
#define GetRawInputDeviceList fake_GetRawInputDeviceList
#include "pad_host_win32.c"

volatile int g_lat_log_on = 0;
int  lat_log_init(void) { return 0; }
void lat_log_(char kind, const char* fmt, ...) { (void)kind; (void)fmt; }
#pragma comment(lib, "user32.lib")
#pragma comment(lib, "winmm.lib")
#pragma comment(lib, "dinput8.lib")
#pragma comment(lib, "dxguid.lib")
#pragma comment(lib, "xinput.lib")
#pragma comment(lib, "hid.lib")
#pragma comment(lib, "setupapi.lib")

static int g_checks, g_fails;
#define CHECK(cond, ...)                                                        \
    do {                                                                        \
        g_checks++;                                                             \
        if (!(cond)) {                                                          \
            g_fails++;                                                          \
            printf("FAIL line %d: ", __LINE__); printf(__VA_ARGS__); printf("\n"); \
        }                                                                       \
    } while (0)

/* ------------------------------------------------------------------ the fake DirectInput */

enum { STICK = 0, PHANTOM = 1, NSPEC = 2 };
typedef struct {
    GUID inst;
    const WCHAR* path;
    volatile LONG present;     /* in EnumDevices; reads fail while 0 */
    volatile LONG buttons;     /* STICK: bit n = B(n+1) held */
    volatile LONG creates;     /* CreateDevice calls */
} FakeSpec;
static FakeSpec g_spec[NSPEC] = {
    { { 0x11111111, 1, 1, { 1, 1, 1, 1, 1, 1, 1, 1 } }, L"\\\\?\\hid#vid_1532&pid_0401&mi_00#7&aa&0&0000#{4d1e55b2-f16f-11cf-88cb-001111000030}", 1, 0, 0 },
    { { 0x22222222, 2, 2, { 2, 2, 2, 2, 2, 2, 2, 2 } }, L"\\\\?\\hid#vid_1532&pid_0401&mi_03#7&bb&0&0000#{4d1e55b2-f16f-11cf-88cb-001111000030}", 1, 0, 0 },
};

typedef struct {
    IDirectInputDevice8W iface;
    int which;
    volatile LONG reads;       /* GetDeviceState calls since it was created */
} FakeDev;

static HRESULT STDMETHODCALLTYPE fd_qi(IDirectInputDevice8W* t, REFIID r, void** o) { (void)t; (void)r; *o = NULL; return E_NOINTERFACE; }
static ULONG STDMETHODCALLTYPE fd_addref(IDirectInputDevice8W* t) { (void)t; return 1; }
static ULONG STDMETHODCALLTYPE fd_release(IDirectInputDevice8W* t) { free(t); return 0; }
static HRESULT STDMETHODCALLTYPE fd_enum_objects(IDirectInputDevice8W* t, LPDIENUMDEVICEOBJECTSCALLBACKW cb, LPVOID ref, DWORD fl)
{ (void)t; (void)cb; (void)ref; (void)fl; return DI_OK; }
static HRESULT STDMETHODCALLTYPE fd_get_property(IDirectInputDevice8W* t, REFGUID prop, LPDIPROPHEADER h)
{
    FakeDev* d = (FakeDev*)t;
    if (prop != DIPROP_GUIDANDPATH) return DIERR_UNSUPPORTED;
    DIPROPGUIDANDPATH* gp = (DIPROPGUIDANDPATH*)h;
    gp->guidClass = GUID_NULL;
    wcscpy_s(gp->wszPath, MAX_PATH, g_spec[d->which].path);
    return DI_OK;
}
static HRESULT STDMETHODCALLTYPE fd_set_property(IDirectInputDevice8W* t, REFGUID prop, LPCDIPROPHEADER h)
{ (void)t; (void)prop; (void)h; return DI_OK; }
static HRESULT STDMETHODCALLTYPE fd_acquire(IDirectInputDevice8W* t)
{
    FakeDev* d = (FakeDev*)t;
    if (!g_spec[d->which].present) return DIERR_UNPLUGGED;
    return d->which == PHANTOM && d->reads >= 3 ? DIERR_UNPLUGGED : DI_OK;
}
static HRESULT STDMETHODCALLTYPE fd_unacquire(IDirectInputDevice8W* t) { (void)t; return DI_OK; }
static HRESULT STDMETHODCALLTYPE fd_poll(IDirectInputDevice8W* t) { (void)t; return DI_NOEFFECT; }
static HRESULT STDMETHODCALLTYPE fd_get_state(IDirectInputDevice8W* t, DWORD cb, LPVOID out)
{
    FakeDev* d = (FakeDev*)t;
    const LONG n = InterlockedIncrement(&d->reads);
    if (cb != sizeof(DIJOYSTATE2)) return DIERR_INVALIDPARAM;
    DIJOYSTATE2* js = (DIJOYSTATE2*)out;
    memset(js, 0, sizeof *js);
    if (!g_spec[d->which].present) return DIERR_INPUTLOST;
    if (d->which == PHANTOM) {
        /* a HID state nothing was ever written to: every axis at its minimum, hat 0 (= up) */
        if (n > 3) return DIERR_INPUTLOST;
        js->lX = js->lY = js->lZ = js->lRx = js->lRy = js->lRz = -32768;
        return DI_OK;
    }
    for (int i = 0; i < 4; i++) js->rgdwPOV[i] = 0xFFFFFFFF;           /* centred, axes at 0 = centre */
    for (int b = 0; b < 32; b++) if ((g_spec[STICK].buttons >> b) & 1) js->rgbButtons[b] = 0x80;
    return DI_OK;
}
static HRESULT STDMETHODCALLTYPE fd_get_data(IDirectInputDevice8W* t, DWORD cb, LPDIDEVICEOBJECTDATA ev, LPDWORD n, DWORD fl)
{
    FakeDev* d = (FakeDev*)t;
    (void)cb; (void)ev; (void)fl;
    *n = 0;                                    /* no events: the immediate state carries everything here */
    return g_spec[d->which].present ? DI_OK : DIERR_INPUTLOST;
}
static HRESULT STDMETHODCALLTYPE fd_set_format(IDirectInputDevice8W* t, LPCDIDATAFORMAT f) { (void)t; (void)f; return DI_OK; }

static IDirectInputDevice8WVtbl g_fd_vtbl;

static HRESULT STDMETHODCALLTYPE fi_create(IDirectInput8W* t, REFGUID g, LPDIRECTINPUTDEVICE8W* out, LPUNKNOWN outer)
{
    (void)t; (void)outer;
    for (int i = 0; i < NSPEC; i++) {
        if (!IsEqualGUID(g, &g_spec[i].inst) || !g_spec[i].present) continue;
        FakeDev* d = (FakeDev*)calloc(1, sizeof *d);
        d->iface.lpVtbl = &g_fd_vtbl;
        d->which = i;
        InterlockedIncrement(&g_spec[i].creates);
        *out = &d->iface;
        return DI_OK;
    }
    return DIERR_DEVICENOTREG;
}
static HRESULT STDMETHODCALLTYPE fi_enum(IDirectInput8W* t, DWORD type, LPDIENUMDEVICESCALLBACKW cb, LPVOID ref, DWORD fl)
{
    (void)t; (void)type; (void)fl;
    for (int i = 0; i < NSPEC; i++) {
        if (!g_spec[i].present) continue;
        DIDEVICEINSTANCEW in; memset(&in, 0, sizeof in);
        in.dwSize = sizeof in;
        in.guidInstance = g_spec[i].inst;
        in.guidProduct.Data1 = 0x04011532;     /* PID 0401, VID 1532 */
        wcscpy_s(in.tszProductName, MAX_PATH, L"Razer Panthera PS4");
        wcscpy_s(in.tszInstanceName, MAX_PATH, L"Razer Panthera PS4");
        if (cb(&in, ref) == DIENUM_STOP) break;
    }
    return DI_OK;
}
static IDirectInput8WVtbl g_fi_vtbl;
static IDirectInput8W g_fake_di;

static void fake_di_init(void)
{
    g_fd_vtbl.QueryInterface = fd_qi; g_fd_vtbl.AddRef = fd_addref; g_fd_vtbl.Release = fd_release;
    g_fd_vtbl.EnumObjects = fd_enum_objects; g_fd_vtbl.GetProperty = fd_get_property;
    g_fd_vtbl.SetProperty = fd_set_property; g_fd_vtbl.Acquire = fd_acquire; g_fd_vtbl.Unacquire = fd_unacquire;
    g_fd_vtbl.GetDeviceState = fd_get_state; g_fd_vtbl.GetDeviceData = fd_get_data;
    g_fd_vtbl.SetDataFormat = fd_set_format; g_fd_vtbl.Poll = fd_poll;
    g_fi_vtbl.CreateDevice = fi_create; g_fi_vtbl.EnumDevices = fi_enum;
    g_fake_di.lpVtbl = &g_fi_vtbl;
}

/* ------------------------------------------------------------------ the scenario */

static BOOL CALLBACK no_init(PINIT_ONCE o, PVOID p, PVOID* c) { (void)o; (void)p; (void)c; return TRUE; }

typedef struct {
    int flips[PADH_MAX_PORTS];        /* connected changes seen by the reads */
    int presses[PADH_MAX_PORTS];      /* reads with a button that was up in the previous read */
    int stick[PADH_MAX_PORTS];        /* reads with a stick off centre */
    u16 seen[PADH_MAX_PORTS];         /* every button any read had */
    int was_conn[PADH_MAX_PORTS];
    u16 prev[PADH_MAX_PORTS];
    int have;
} Reads;

/* The game reading ports 1 and 2 at ~60 Hz for `ms`. */
static void game_reads(Reads* g, int ms)
{
    const DWORD t0 = GetTickCount();
    while ((int)(GetTickCount() - t0) < ms) {
        for (u32 p = 0; p < 2; p++) {
            PadHostPort o;
            padh_read(p, PADH_READER_GAME, &o, 500);
            const int c = padh_port_connected(p);
            if (g->have && c != g->was_conn[p]) g->flips[p]++;
            g->was_conn[p] = c;
            if (o.buttons & ~g->prev[p]) g->presses[p]++;
            g->seen[p] |= o.buttons;
            g->prev[p] = o.buttons;
            if (o.lx < 64 || o.lx > 192 || o.ly < 64 || o.ly > 192) g->stick[p]++;
        }
        g->have = 1;
        Sleep(16);
    }
}

static int scenario(void)
{
    timeBeginPeriod(1);
    LARGE_INTEGER fq; QueryPerformanceFrequency(&fq); g_qpf = fq.QuadPart;
    InitOnceExecuteOnce(&g_init_once, no_init, NULL, NULL);    /* padh_init: done by hand below */
    for (int p = 0; p < PADH_MAX_PORTS; p++) InitializeSRWLock(&g_port[p].lock);
    _putenv_s("PS3_PAD_FILE", ""); _putenv_s("PS3_PAD_FILE2", ""); _putenv_s("PS3_PAD_HID_FAKE", "");
    _putenv_s("PS3_CONTROLS", "pad_flap_test_no_such_controls.ini");
    load_config();
    g_cfg.devices = 1; g_cfg.dinput = 1; g_cfg.hid = 0; g_cfg.xinput = 0; g_cfg.tap_latch = 1;
    g_cfg.kb_port = g_cfg.kb2_port = -1;                    /* the test machine's keyboard stays out of it */
    fake_di_init();
    g_di = (IDirectInput8W*)&g_fake_di;
    /* as init_cb: scan, ports, the hot-plug thread, the sampler */
    di_scan();
    AcquireSRWLockExclusive(&g_dev_lock); assign_ports(); ReleaseSRWLockExclusive(&g_dev_lock);
    g_hotplug_stop = CreateEventW(NULL, TRUE, FALSE, NULL);
    g_hotplug_thread = CreateThread(NULL, 0, hotplug_main, NULL, 0, NULL);
    sampler_start();

    /* 1. both plugged in */
    Reads g; memset(&g, 0, sizeof g);
    game_reads(&g, 4000);
    printf("phase 1 (4 s, stick + phantom): port 2 connected changes %d, presses port 1 %d / port 2 %d,"
           " stick off centre port 1 %d / port 2 %d, buttons seen 0x%04X / 0x%04X, phantom created %ld times\n",
           g.flips[1], g.presses[0], g.presses[1], g.stick[0], g.stick[1], g.seen[0], g.seen[1], g_spec[PHANTOM].creates);
    CHECK(g.flips[1] == 0, "port 2 flipped %d times", g.flips[1]);
    CHECK(!padh_port_connected(1), "port 2 connected (the phantom has a port)");
    CHECK(g.presses[0] == 0 && g.presses[1] == 0, "ghost presses: port 1 %d, port 2 %d", g.presses[0], g.presses[1]);
    CHECK(g.stick[0] == 0 && g.stick[1] == 0, "ghost stick: port 1 %d, port 2 %d", g.stick[0], g.stick[1]);
    CHECK(g_spec[PHANTOM].creates <= 3, "the phantom was created %ld times (quarantine after 3)", g_spec[PHANTOM].creates);
    int stick_port = -9;
    AcquireSRWLockShared(&g_dev_lock);
    for (int i = 0; i < MAX_DEVS; i++)
        if (g_dev[i].kind == DEV_DINPUT && !g_dev[i].lost && !_wcsicmp(g_dev[i].path, g_spec[STICK].path)) stick_port = g_dev[i].port;
    ReleaseSRWLockShared(&g_dev_lock);
    CHECK(stick_port == 0, "the stick is on port %d, not 1", stick_port + 1);

    /* 2. the stick works: B2 = CROSS on port 1 */
    InterlockedExchange(&g_spec[STICK].buttons, 1 << 1);
    memset(&g, 0, sizeof g);
    game_reads(&g, 150);
    InterlockedExchange(&g_spec[STICK].buttons, 0);
    game_reads(&g, 100);
    printf("phase 2 (B2 held 150 ms): port 1 presses %d, buttons seen 0x%04X\n", g.presses[0], g.seen[0]);
    CHECK(g.seen[0] & CELL_PAD_CTRL_CROSS, "B2 did not reach port 1 as CROSS (seen 0x%04X)", g.seen[0]);

    /* 3. unplugged, and plugged in again with B3 (CIRCLE) held */
    InterlockedExchange(&g_spec[STICK].present, 0);
    InterlockedIncrement(&g_fake_raw_count);
    Sleep(1500);                                             /* dropped (port 1 itself always reads connected) */
    InterlockedExchange(&g_spec[STICK].buttons, 1 << 2);
    InterlockedExchange(&g_spec[STICK].present, 1);
    InterlockedIncrement(&g_fake_raw_count);
    memset(&g, 0, sizeof g);
    game_reads(&g, 2500);
    const int held_presses = g.presses[0];
    const u16 held_seen = g.seen[0];
    InterlockedExchange(&g_spec[STICK].buttons, 0);
    game_reads(&g, 100);
    InterlockedExchange(&g_spec[STICK].buttons, 1 << 2);
    memset(&g, 0, sizeof g);
    game_reads(&g, 150);
    InterlockedExchange(&g_spec[STICK].buttons, 0);
    printf("phase 3 (replugged with B3 held): CIRCLE while held from the start %s; after release + press: %s\n",
           (held_seen & CELL_PAD_CTRL_CIRCLE) ? "PRESSED" : "not pressed", (g.seen[0] & CELL_PAD_CTRL_CIRCLE) ? "pressed" : "NOT PRESSED");
    CHECK(!(held_seen & CELL_PAD_CTRL_CIRCLE) && held_presses == 0, "B3 held while plugged in reached port 1 as a press");
    CHECK(g.seen[0] & CELL_PAD_CTRL_CIRCLE, "B3 pressed again after its release did not reach port 1");

    SetEvent(g_hotplug_stop);
    WaitForSingleObject(g_hotplug_thread, 3000);
    if (g_fails) { printf("FAILED %d of %d checks\n", g_fails, g_checks); return 1; }
    printf("PASS %d checks\n", g_checks);
    return 0;
}

int main(int argc, char** argv)
{
    setvbuf(stdout, NULL, _IONBF, 0);
    for (int i = 1; i < argc; i++)
        if (!strncmp(argv[i], "ini=", 4)) {
            _putenv_s("PS3_CONTROLS", argv[i] + 4);
            _putenv_s("PAD_TAP_LATCH", "");
            load_config();
            printf("tap_latch = %d\n", g_cfg.tap_latch);
            return 0;
        }
    return scenario();
}
