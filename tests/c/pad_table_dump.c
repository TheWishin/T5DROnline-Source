/*
 * Dumps what the runtime's controls.ini parser (libs/input/pad_host_win32.c, patch 0009 and later) makes of a
 * file, for tests/test_controls_ui.py: the launcher's padmap.py and controls editor must agree with it.
 *
 *   pad_table_dump ini=<controls.ini> <device> ...
 *   device = xinput:<port>                    port 0-based
 *          = dinput:<port>:<VVVV>:<PPPP>      port -1 = not assigned
 *
 * Output, one line each (names as the runtime logs them):
 *   TABLE <device>
 *   BIND <source> <mask hex>        one per binding, in binding order
 *   PORT <n> stick=<0|1> socd=<n> spec=<n> slot=<n> vid=<hex> pid=<hex> match=<text>
 *
 * The runtime file is included as it is (the functions are static), so this is the runtime's own code.
 * Built by the test with clang-cl or cl against the Windows SDK; no libraries of ps3recomp are needed.
 */
#include "pad_host_win32.c"

/* the latency log (patch 0034) is not part of this test */
volatile int g_lat_log_on = 0;
int  lat_log_init(void) { return 0; }
void lat_log_(char kind, const char* fmt, ...) { (void)kind; (void)fmt; }
#pragma comment(lib, "user32.lib")

static void dump_table(const char* label, int cls, int port, u16 vid, u16 pid)
{
    BindTable t;
    build_table(&t, cls, port, vid, pid, NULL);
    printf("TABLE %s\n", label);
    for (int i = 0; i < t.n; i++) {
        char name[32];
        source_name(cls, t.b[i].src, name, sizeof name);
        printf("BIND %s %04X\n", name, t.b[i].mask);
    }
    printf("DESC %s\n", t.desc);
}

int main(int argc, char** argv)
{
    /* arguments are recognised by their prefix (a launcher that adds its own leading arguments does no harm) */
    const char* ini = NULL;
    for (int i = 1; i < argc; i++)
        if (!strncmp(argv[i], "ini=", 4)) ini = argv[i] + 4;
    if (!ini) { fprintf(stderr, "usage: pad_table_dump ini=<controls.ini> [xinput:P | dinput:P:VVVV:PPPP]...\n"); return 2; }
    _putenv_s("PS3_CONTROLS", ini);
    _putenv_s("PS3_PAD_FILE", "");
    load_config();
    for (int p = 0; p < PADH_MAX_PORTS; p++) {
        const PortCfg* pc = &g_cfg.port[p];
        printf("PORT %d stick=%d socd=%d spec=%d slot=%d vid=%04X pid=%04X match=%s\n", p + 1, pc->stick_dpad, pc->socd,
               pc->spec, pc->xi_slot, pc->vid, pc->pid, pc->match);
    }
    for (int i = 1; i < argc; i++) {
        int port = 0; unsigned vid = 0, pid = 0;
        if (sscanf(argv[i], "xinput:%d", &port) == 1)
            dump_table(argv[i], CLS_XINPUT, port, 0, 0);
        else if (sscanf(argv[i], "dinput:%d:%x:%x", &port, &vid, &pid) >= 1)
            dump_table(argv[i], CLS_DINPUT, port, (u16)vid, (u16)pid);
    }
    return 0;
}
