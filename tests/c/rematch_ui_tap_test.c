/* Exercise the runtime's real sampler and per-reader delivery with a fake
 * clock and a pad file. No device enumeration, threads, game or network. */
#include "pad_host_win32.c"

volatile int g_lat_log_on = 0;
int lat_log_init(void) { return 0; }
void lat_log_(char kind, const char* fmt, ...) { (void)kind; (void)fmt; }
#pragma comment(lib, "user32.lib")

static unsigned checks;
#define CHECK(x) do { ++checks; if (!(x)) { fprintf(stderr, "line %d: %s\n", __LINE__, #x); exit(1); } } while (0)

static BOOL CALLBACK no_devices(PINIT_ONCE once, PVOID param, PVOID* context)
{ (void)once; (void)param; (void)context; return TRUE; }

static void sample(const char* buttons, unsigned ms)
{
    FILE* file = fopen(g_cfg.file[0], "wb");
    CHECK(file != NULL);
    CHECK(fwrite(buttons, 1, strlen(buttons), file) == strlen(buttons));
    CHECK(fclose(file) == 0);
    sample_locked(0, &g_port[0], (LONGLONG)ms * 1000);
}

static PadHostPort read_at(int reader, unsigned ms)
{
    PadHostPort out;
    deliver_locked(0, &g_port[0], reader, (LONGLONG)ms * 1000, &out);
    return out;
}

int main(int argc, char** argv)
{
    CHECK(argc == 2);
    /* Mark initialization complete without running the runtime's real device
     * and background-thread initialization. All samples below are explicit. */
    CHECK(InitOnceExecuteOnce(&g_init_once, no_devices, NULL, NULL));
    g_qpf = 1000000;
    g_cfg.kb_port = g_cfg.kb2_port = -1;
    g_cfg.tap_latch = 1;
    g_cfg.tap_max_age_ms = 250;
    snprintf(g_cfg.file[0], sizeof g_cfg.file[0], "%s", argv[1]);

    sample("", 1000);
    CHECK(read_at(PADH_READER_UI, 1000).buttons == 0);
    /* The observed failure: Cross is held for 120 ms entirely inside a
     * 193 ms gap between live UI frames. The current-only peek has lost it. */
    sample("CROSS", 1010);
    sample("", 1130);
    CHECK(g_port[0].last.buttons == 0);
    CHECK(read_at(PADH_READER_GAME, 1140).buttons == CELL_PAD_CTRL_CROSS);
    CHECK(read_at(PADH_READER_LOCAL, 1150).buttons == CELL_PAD_CTRL_CROSS);
    PadHostPort ui = read_at(PADH_READER_UI, 1193);
    CHECK(ui.buttons == CELL_PAD_CTRL_CROSS && ui.tapped == CELL_PAD_CTRL_CROSS);
    CHECK(g_port[0].latch[PADH_READER_UI] == 0);
    sample("", 1194);
    CHECK(read_at(PADH_READER_UI, 1194).buttons == 0); /* exactly one press */

    /* Reading UI first likewise cannot steal the game's or netplay's tap. */
    sample("CIRCLE", 1200);
    sample("", 1205);
    CHECK(read_at(PADH_READER_UI, 1210).buttons == CELL_PAD_CTRL_CIRCLE);
    CHECK(read_at(PADH_READER_LOCAL, 1211).buttons == CELL_PAD_CTRL_CIRCLE);
    CHECK(read_at(PADH_READER_GAME, 1212).buttons == CELL_PAD_CTRL_CIRCLE);

    /* Stale taps from before a loading/idle interval stay discarded. */
    sample("CROSS", 1300);
    sample("", 1310);
    CHECK(read_at(PADH_READER_UI, 1551).buttons == 0);
    CHECK(g_port[0].tap_stale[PADH_READER_UI] == 1);
    /* A button still held remains held even when its edge is old. */
    sample("CROSS", 1600);
    CHECK(read_at(PADH_READER_UI, 1900).buttons == CELL_PAD_CTRL_CROSS);
    CHECK(read_at(PADH_READER_UI, 1901).buttons == CELL_PAD_CTRL_CROSS);
    sample("", 1902);
    CHECK(read_at(PADH_READER_UI, 1902).buttons == 0);
    remove(argv[1]);
    printf("PASS %u checks\n", checks);
    return 0;
}
