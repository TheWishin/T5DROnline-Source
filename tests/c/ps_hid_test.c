/*
 * Unit test of the runtime's own reading of DualShock 4 / DualSense pads (libs/input/pad_host_win32.c,
 * ps3recomp patch 0042, "PlayStation pads read directly"): every report mode is built here byte by byte
 * and parsed by the runtime's code, which must give the state DirectInput gives for the same pad, and
 * through the "ps" layout the right PS3 buttons and sticks. No controller is needed or touched.
 *
 *   ps_hid_test                    the checks; prints "PASS <n> checks" (exit 0) or the failures (exit 1)
 *   ps_hid_test vectors=<file>     for tests/test_ps_hid.py: each line "<model> <bt> <hex report>"
 *                                  (model ds4|dualsense|edge, bt 0|1) is parsed; one output line each:
 *                                  "R <mode> <bits0> <bits1> <bits2> <bits3> <bits4> <ax0> ... <ax7>"
 *   ps_hid_test scan [seconds]     list the PlayStation pads Windows has now and what they send
 *                                  (reads only; nothing is sent to a pad). Never needed by a test.
 *
 * The runtime file is included as it is (its functions are static), so this is the runtime's own code.
 * Built by tests/test_ps_hid.py with clang-cl or cl against the Windows SDK, like pad_table_dump.c.
 */
#include "pad_host_win32.c"

/* the latency log (patch 0034) is not part of this test */
volatile int g_lat_log_on = 0;
int  lat_log_init(void) { return 0; }
void lat_log_(char kind, const char* fmt, ...) { (void)kind; (void)fmt; }
#pragma comment(lib, "user32.lib")

static int g_checks, g_fails;
#define CHECK(cond, ...)                                                        \
    do {                                                                        \
        g_checks++;                                                             \
        if (!(cond)) {                                                          \
            g_fails++;                                                          \
            printf("FAIL line %d: ", __LINE__); printf(__VA_ARGS__); printf("\n"); \
        }                                                                       \
    } while (0)

/* ------------------------------------------------------------------ building reports (independently) */

enum { M_USB, M_SIMPLE, M_EXT, M_AUDIO };
static const char* const k_mode[] = { "USB", "BT simple", "BT extended", "BT extended + audio" };

/* buttons: bit n = B(n+1) in DirectInput's order (square cross circle triangle L1 R1 L2 R2 share options
 * L3 R3 PS touchpad mute Fn-L Fn-R paddle-L paddle-R); hat 0..7 or -1 */
typedef struct { u32 btn; int hat; u8 lx, ly, rx, ry, l2, r2; } St;

static u32 crc32_bitwise(u32 crc, const u8* p, size_t n)       /* the plain bit-at-a-time CRC-32 */
{
    crc = ~crc;
    for (size_t i = 0; i < n; i++) {
        crc ^= p[i];
        for (int k = 0; k < 8; k++) crc = (crc >> 1) ^ (0xEDB88320u & (0u - (crc & 1u)));
    }
    return ~crc;
}

static void put_crc(u8* rep, size_t len)
{
    u8 tmp[600];
    tmp[0] = 0xA1;
    memcpy(tmp + 1, rep, len - 4);
    const u32 c = crc32_bitwise(0, tmp, len - 3);
    rep[len - 4] = (u8)c; rep[len - 3] = (u8)(c >> 8); rep[len - 2] = (u8)(c >> 16); rep[len - 1] = (u8)(c >> 24);
}

/* Which B-numbers a report carries. */
static u32 carried(int model, int mode)
{
    u32 m = (1u << 14) - 1;                                     /* B1..B14 */
    const int full = mode == M_USB || mode == M_EXT;
    if (model != PSM_DS4 && full) m |= 1u << 14;                /* mute */
    if (model == PSM_EDGE && full) m |= 0xFu << 15;             /* Fn, paddles */
    return m;
}

static void put_buttons(u8* b, int model, int mode, const St* s, u8 counter)
{
    const u32 x = s->btn & carried(model, mode);
    b[0] = (u8)((s->hat < 0 ? 8 : s->hat) | (x & 0xF) << 4);
    b[1] = (u8)(x >> 4);
    b[2] = (u8)((x >> 12) & 3);
    if (model == PSM_DS4 || mode == M_SIMPLE) b[2] |= (u8)(counter << 2);
    else b[2] |= (u8)(((x >> 14) & 1) << 2 | ((x >> 15) & 0xF) << 4);
}

/* Builds the report into out (zero-padded to what Windows would hand over); returns that length.
 * Bytes the parser must not look at get noise. */
static size_t build(int model, int mode, const St* s, u8 counter, u8* out)
{
    const size_t padto = mode == M_USB ? 64 : model == PSM_DS4 ? 547 : 78;
    memset(out, 0, padto);
    u8 noise = (u8)(0x5A + counter * 7);
    if (mode == M_SIMPLE) {
        out[0] = 0x01; out[1] = s->lx; out[2] = s->ly; out[3] = s->rx; out[4] = s->ry;
        put_buttons(out + 5, model, mode, s, counter);
        out[8] = s->l2; out[9] = s->r2;
        return padto;
    }
    if (model == PSM_DS4) {
        const size_t o = mode == M_USB ? 1 : 3, len = mode == M_USB ? 64 : mode == M_EXT ? 78 : 270;
        for (size_t i = 0; i < len; i++) out[i] = noise = (u8)(noise * 13 + 1);
        out[0] = mode == M_USB ? 0x01 : mode == M_EXT ? 0x11 : 0x14;
        if (mode != M_USB) { out[1] = 0xC0; out[2] = 0x00; }
        out[o] = s->lx; out[o + 1] = s->ly; out[o + 2] = s->rx; out[o + 3] = s->ry;
        put_buttons(out + o + 4, model, mode, s, counter);
        out[o + 7] = s->l2; out[o + 8] = s->r2;
        if (mode != M_USB) put_crc(out, len);
        return padto;
    }
    const size_t o = mode == M_USB ? 1 : 2, len = mode == M_USB ? 64 : 78;
    for (size_t i = 0; i < len; i++) out[i] = noise = (u8)(noise * 13 + 1);
    out[0] = mode == M_USB ? 0x01 : 0x31;
    if (mode != M_USB) out[1] = (u8)(counter << 4);
    out[o] = s->lx; out[o + 1] = s->ly; out[o + 2] = s->rx; out[o + 3] = s->ry;
    out[o + 4] = s->l2; out[o + 5] = s->r2; out[o + 6] = counter;
    put_buttons(out + o + 7, model, mode, s, counter);
    if (mode != M_USB) put_crc(out, len);
    return padto;
}

/* ------------------------------------------------------------------ what DirectInput would report */

static void expect_raw(int model, int mode, const St* s, RawState* e)
{
    memset(e, 0, sizeof *e);
    e->bits[0] = s->btn & carried(model, mode);
    /* hat: 0 up, 1 up-right, ... clockwise; ids CID_HAT + {0 up, 1 right, 2 down, 3 left} */
    switch (s->hat) {
    case 0: raw_set(e, CID_HAT + 0); break;
    case 1: raw_set(e, CID_HAT + 0); raw_set(e, CID_HAT + 1); break;
    case 2: raw_set(e, CID_HAT + 1); break;
    case 3: raw_set(e, CID_HAT + 1); raw_set(e, CID_HAT + 2); break;
    case 4: raw_set(e, CID_HAT + 2); break;
    case 5: raw_set(e, CID_HAT + 2); raw_set(e, CID_HAT + 3); break;
    case 6: raw_set(e, CID_HAT + 3); break;
    case 7: raw_set(e, CID_HAT + 3); raw_set(e, CID_HAT + 0); break;
    default: break;
    }
    /* DirectInput axes X Y Z RX RY RZ: LX LY RX-stick L2 R2 RY-stick, logical 0..255 -> -32768..32767 */
    const u8 v[6] = { s->lx, s->ly, s->rx, s->l2, s->r2, s->ry };
    for (int a = 0; a < 6; a++) {
        e->axis[a] = (s32)((v[a] * 65535L) / 255 - 32768);
        if (e->axis[a] > 16384) raw_set(e, CID_AXIS + a * 2);
        if (e->axis[a] < -16384) raw_set(e, CID_AXIS + a * 2 + 1);
    }
}

static int same_raw(const RawState* a, const RawState* b)
{
    return !memcmp(a->bits, b->bits, sizeof a->bits) && !memcmp(a->axis, b->axis, sizeof a->axis);
}

static const int k_models[] = { PSM_DS4, PSM_DS, PSM_EDGE };
static const u16 k_pids[] = { 0, 0x09CC, 0x0CE6, 0x0DF2 };

static int modes_of(int model, int* out)
{
    int n = 0;
    out[n++] = M_USB; out[n++] = M_SIMPLE; out[n++] = M_EXT;
    if (model == PSM_DS4) out[n++] = M_AUDIO;
    return n;
}

static int expected_psr(int model, int mode)
{
    const int base = model == PSM_DS4 ? 0 : 3;
    return base + (mode == M_USB ? 1 : mode == M_SIMPLE ? 2 : 3);
}

/* ------------------------------------------------------------------ the checks */

static void test_crc(void)
{
    static const u8 nine[] = "123456789";
    CHECK(ps_crc32(0, nine, 9) == 0xCBF43926u, "CRC-32 check value: %08X", ps_crc32(0, nine, 9));
    CHECK(ps_crc32(ps_crc32(0, nine, 4), nine + 4, 5) == 0xCBF43926u, "CRC-32 chained");
    u8 buf[300];
    for (int i = 0; i < 300; i++) buf[i] = (u8)(i * 31 + 7);
    for (size_t n = 0; n < 300; n += 37)
        CHECK(ps_crc32(0, buf, n) == crc32_bitwise(0, buf, n), "CRC-32 table vs bitwise, %u bytes", (unsigned)n);
    CHECK(ps_crc_len(PSM_DS4, 0x11) == 78 && ps_crc_len(PSM_DS4, 0x14) == 270 && ps_crc_len(PSM_DS4, 0x19) == 547 &&
          ps_crc_len(PSM_DS, 0x31) == 78 && ps_crc_len(PSM_EDGE, 0x31) == 78 && ps_crc_len(PSM_DS4, 0x01) == 0 &&
          ps_crc_len(PSM_DS, 0x11) == 0 && ps_crc_len(PSM_DS4, 0x31) == 0, "CRC report lengths");
}

/* Every mode of every model: each button alone, each hat value, stick and trigger extremes, mixes. */
static void test_parse_all_modes(void)
{
    for (int mi = 0; mi < 3; mi++) {
        const int model = k_models[mi];
        int modes[4]; const int nm = modes_of(model, modes);
        for (int k = 0; k < nm; k++) {
            const int mode = modes[k];
            for (int bt = 0; bt < 2; bt++) {
                if (mode == M_USB && bt) continue;            /* USB reports come over USB */
                if (mode != M_USB && !bt) continue;
                int bad = 0, n = 0;
                St cases[64]; int nc = 0;
                for (int b = 0; b < 19; b++) cases[nc++] = (St){ 1u << b, -1, 128, 128, 128, 128, 0, 0 };
                for (int h = -1; h < 8; h++) cases[nc++] = (St){ 0, h, 128, 128, 128, 128, 0, 0 };
                cases[nc++] = (St){ 0, -1, 0, 0, 0, 0, 0, 0 };
                cases[nc++] = (St){ 0, -1, 255, 255, 255, 255, 255, 255 };
                cases[nc++] = (St){ 0x7FFFF, 1, 1, 254, 64, 192, 128, 17 };
                cases[nc++] = (St){ 0x0AAAA, 5, 200, 30, 129, 127, 254, 1 };
                cases[nc++] = (St){ 0x55555, 7, 77, 99, 11, 222, 3, 250 };
                for (int c = 0; c < nc; c++) {
                    u8 rep[600];
                    const size_t len = build(model, mode, &cases[c], (u8)(c * 5 + 3), rep);
                    RawState r, e;
                    const int psr = ps_parse(model, bt, rep, len, &r);
                    expect_raw(model, mode, &cases[c], &e);
                    n++;
                    if (psr != expected_psr(model, mode) || !same_raw(&r, &e)) {
                        if (bad++ < 3)
                            printf("  %s %s case %d: mode %d (want %d) bits %08X/%08X want %08X/%08X axes %d %d %d %d %d %d\n",
                                   k_psm_name[model], k_mode[mode], c, psr, expected_psr(model, mode), r.bits[0], r.bits[4],
                                   e.bits[0], e.bits[4], r.axis[0], r.axis[1], r.axis[2], r.axis[3], r.axis[4], r.axis[5]);
                    }
                    /* the CRC of every Bluetooth extended report is right */
                    if (mode == M_EXT || mode == M_AUDIO) {
                        if (ps_crc_check(model, rep, len) != 1 && bad++ < 3) printf("  CRC not accepted\n");
                    } else if (ps_crc_check(model, rep, len) != -1 && bad++ < 3) printf("  CRC checked where there is none\n");
                }
                CHECK(!bad, "%s %s: %d of %d reports parsed wrong", k_psm_name[model], k_mode[mode], bad, n);
            }
        }
    }
}

/* A DualSense's 0x01: the 64-byte USB report, or over Bluetooth the 10-byte simple one (padded to 78). */
static void test_dualsense_01(void)
{
    const St s = { 1u << 1, 2, 10, 20, 30, 40, 50, 60 };          /* cross, right */
    u8 rep[600]; RawState r, e;
    size_t len = build(PSM_DS, M_SIMPLE, &s, 1, rep);
    CHECK(len == 78 && ps_parse(PSM_DS, 1, rep, len, &r) == PSR_DS_SIMPLE, "DualSense BT simple");
    CHECK(ps_parse(PSM_DS, 0, rep, len, &r) == PSR_DS_SIMPLE, "a 78-byte 0x01 is the simple report even if the path did not say Bluetooth");
    CHECK(ps_parse(PSM_DS, 1, rep, 10, &r) == PSR_DS_SIMPLE, "an unpadded 10-byte simple report");
    expect_raw(PSM_DS, M_SIMPLE, &s, &e);
    CHECK(same_raw(&r, &e), "simple report content");
    len = build(PSM_DS, M_USB, &s, 1, rep);
    CHECK(len == 64 && ps_parse(PSM_DS, 0, rep, len, &r) == PSR_DS_USB, "DualSense USB");
    expect_raw(PSM_DS, M_USB, &s, &e);
    CHECK(same_raw(&r, &e), "USB report content");
    RawState keep; ps_neutral(&keep); r = keep;
    CHECK(ps_parse(PSM_DS, 0, rep, 9, &r) == PSR_NONE && same_raw(&r, &keep), "a cut report is not parsed");
}

/* Reports that carry no input state leave the state alone. */
static void test_not_input(void)
{
    u8 rep[600]; RawState r, keep;
    ps_neutral(&keep);
    const St s = { 0x3FF, 0, 0, 0, 0, 0, 255, 255 };
    size_t len = build(PSM_DS4, M_EXT, &s, 0, rep);
    rep[1] = 0x40;                                   /* "input data present" flag off */
    put_crc(rep, 78);
    r = keep;
    CHECK(ps_parse(PSM_DS4, 1, rep, len, &r) == PSR_NONE && same_raw(&r, &keep), "DS4 0x11 without input data");
    static const u8 ids[] = { 0x02, 0x05, 0x10, 0x1A, 0x31, 0x32, 0xA3, 0xE2, 0x00 };
    for (unsigned i = 0; i < sizeof ids; i++) {
        memset(rep, 0x77, 100); rep[0] = ids[i];
        r = keep;
        CHECK(ps_parse(PSM_DS4, 1, rep, 100, &r) == PSR_NONE && same_raw(&r, &keep), "DS4 report 0x%02X", ids[i]);
    }
    static const u8 ids2[] = { 0x02, 0x05, 0x11, 0x14, 0x30, 0x32, 0x09, 0x20 };
    for (unsigned i = 0; i < sizeof ids2; i++) {
        memset(rep, 0x77, 100); rep[0] = ids2[i];
        r = keep;
        CHECK(ps_parse(PSM_DS, 1, rep, 78, &r) == PSR_NONE && same_raw(&r, &keep), "DualSense report 0x%02X", ids2[i]);
    }
    CHECK(ps_parse(PSM_NONE, 0, rep, 64, &r) == PSR_NONE, "not a PlayStation pad");
    CHECK(ps_model(0x054C, 0x05C4) == PSM_DS4 && ps_model(0x054C, 0x09CC) == PSM_DS4 && ps_model(0x054C, 0x0CE6) == PSM_DS &&
          ps_model(0x054C, 0x0DF2) == PSM_EDGE && ps_model(0x054C, 0x0BA0) == PSM_NONE && ps_model(0x054D, 0x0CE6) == PSM_NONE &&
          ps_model(0x045E, 0x09CC) == PSM_NONE, "models by VID:PID");
}

/* Through the "ps" layout (DirectInput class, as the runtime binds these pads): PS3 buttons and sticks. */
static void test_layout(void)
{
    static const struct { int b; u16 want; } k[] = {
        { 0, CELL_PAD_CTRL_SQUARE }, { 1, CELL_PAD_CTRL_CROSS }, { 2, CELL_PAD_CTRL_CIRCLE }, { 3, CELL_PAD_CTRL_TRIANGLE },
        { 4, CELL_PAD_CTRL_L1 }, { 5, CELL_PAD_CTRL_R1 }, { 6, CELL_PAD_CTRL_L2 }, { 7, CELL_PAD_CTRL_R2 },
        { 8, CELL_PAD_CTRL_SELECT }, { 9, CELL_PAD_CTRL_START }, { 10, CELL_PAD_CTRL_L3 }, { 11, CELL_PAD_CTRL_R3 },
        { 12, 0 }, { 13, 0 }, { 14, 0 }, { 15, 0 }, { 16, 0 }, { 17, 0 }, { 18, 0 },   /* PS, touchpad, mute, Edge: unbound */
    };
    static const u16 hat_want[8] = {
        CELL_PAD_CTRL_UP, CELL_PAD_CTRL_UP | CELL_PAD_CTRL_RIGHT, CELL_PAD_CTRL_RIGHT, CELL_PAD_CTRL_RIGHT | CELL_PAD_CTRL_DOWN,
        CELL_PAD_CTRL_DOWN, CELL_PAD_CTRL_DOWN | CELL_PAD_CTRL_LEFT, CELL_PAD_CTRL_LEFT, CELL_PAD_CTRL_LEFT | CELL_PAD_CTRL_UP };
    for (int mi = 0; mi < 3; mi++) {
        const int model = k_models[mi];
        BindTable t;
        build_table(&t, CLS_DINPUT, 0, PS_VID, k_pids[model], NULL);
        CHECK(!strcmp(t.desc, "ps"), "%s gets the ps layout (got '%s')", k_psm_name[model], t.desc);
        int modes[4]; const int nm = modes_of(model, modes);
        for (int mk = 0; mk < nm; mk++) {
            const int mode = modes[mk], bt = mode != M_USB;
            int bad = 0;
            for (unsigned i = 0; i < sizeof k / sizeof k[0]; i++) {
                const St s = { 1u << k[i].b, -1, 128, 128, 128, 128, 0, 0 };
                u8 rep[600]; RawState r; Merge m; memset(&m, 0, sizeof m);
                const size_t len = build(model, mode, &s, 9, rep);
                ps_parse(model, bt, rep, len, &r);
                apply_table(&m, &t, &r, CLS_DINPUT);
                if (m.btn != k[i].want && bad++ < 3)
                    printf("  %s %s: B%d -> %04X, want %04X\n", k_psm_name[model], k_mode[mode], k[i].b + 1, m.btn, k[i].want);
            }
            for (int h = 0; h < 8; h++) {
                const St s = { 0, h, 128, 128, 128, 128, 0, 0 };
                u8 rep[600]; RawState r; Merge m; memset(&m, 0, sizeof m);
                ps_parse(model, bt, rep, build(model, mode, &s, 2, rep), &r);
                apply_table(&m, &t, &r, CLS_DINPUT);
                if (m.btn != hat_want[h] && bad++ < 3) printf("  %s %s: hat %d -> %04X\n", k_psm_name[model], k_mode[mode], h, m.btn);
            }
            /* sticks: the PS3 values (0..255, 128 centre) are the pad's own bytes; nothing pressed by the triggers' rest */
            static const u8 sv[][4] = { { 0, 255, 128, 64 }, { 255, 0, 1, 254 }, { 128, 128, 128, 128 }, { 37, 199, 250, 3 } };
            for (int i = 0; i < 4; i++) {
                const St s = { 0, -1, sv[i][0], sv[i][1], sv[i][2], sv[i][3], 0, 0 };
                u8 rep[600]; RawState r; Merge m; memset(&m, 0, sizeof m);
                ps_parse(model, bt, rep, build(model, mode, &s, 4, rep), &r);
                apply_table(&m, &t, &r, CLS_DINPUT);
                const u8 got[4] = { axis_u8(m.ax[TGT_LX]), axis_u8(m.ax[TGT_LY]), axis_u8(m.ax[TGT_RX]), axis_u8(m.ax[TGT_RY]) };
                if ((memcmp(got, sv[i], 4) || m.btn) && bad++ < 3)
                    printf("  %s %s: sticks %d %d %d %d -> %d %d %d %d btn %04X\n", k_psm_name[model], k_mode[mode],
                           sv[i][0], sv[i][1], sv[i][2], sv[i][3], got[0], got[1], got[2], got[3], m.btn);
            }
            /* L2/R2 pulled all the way with the digital bit: L2/R2 */
            const St s = { (1u << 6) | (1u << 7), -1, 128, 128, 128, 128, 255, 255 };
            u8 rep[600]; RawState r; Merge m; memset(&m, 0, sizeof m);
            ps_parse(model, bt, rep, build(model, mode, &s, 4, rep), &r);
            apply_table(&m, &t, &r, CLS_DINPUT);
            if (m.btn != (CELL_PAD_CTRL_L2 | CELL_PAD_CTRL_R2) && bad++ < 3) printf("  triggers -> %04X\n", m.btn);
            CHECK(!bad, "%s %s through the ps layout", k_psm_name[model], k_mode[mode]);
        }
    }
    /* a model section and macros apply to a pad read through HID exactly as to a DirectInput one */
    static const char ini[] = "[dinput.054C:0CE6]\n1 = B2\nmacros = tekken\n";
    char path[MAX_PATH]; GetTempPathA(sizeof path, path);
    strcat_s(path, sizeof path, "ps_hid_test_controls.ini");
    FILE* f = NULL; fopen_s(&f, path, "wb");
    if (f) { fwrite(ini, 1, sizeof ini - 1, f); fclose(f); }
    g_nkv = g_nsec = 0;
    CHECK(ini_load(path), "test controls.ini");
    BindTable t;
    build_table(&t, CLS_DINPUT, 0, PS_VID, 0x0CE6, NULL);
    const St s = { (1u << 1) | (1u << 5), -1, 128, 128, 128, 128, 0, 0 };   /* cross (B2) + R1 (B6) */
    u8 rep[600]; RawState r; Merge m; memset(&m, 0, sizeof m);
    ps_parse(PSM_DS, 1, rep, build(PSM_DS, M_EXT, &s, 1, rep), &r);
    apply_table(&m, &t, &r, CLS_DINPUT);
    CHECK(m.btn == (CELL_PAD_CTRL_SQUARE | CELL_PAD_CTRL_TRIANGLE),
          "[dinput.054C:0CE6] 1 = B2 and tekken macros (R1 = 1+2): %04X (%s)", m.btn, t.desc);
    remove(path);
    g_nkv = g_nsec = 0;
}

/* The reader's store / take: the newest state, and a press that came and went between two samples. */
static void test_taps(void)
{
    HidDev* h = hid_new(PSM_DS, PS_VID, 0x0CE6, 1, 78, "test");
    CHECK(h != NULL, "hid_new");
    if (!h) return;
    BindTable t; build_table(&t, CLS_DINPUT, 0, PS_VID, 0x0CE6, NULL);
    RawState r; Merge m;
    hid_take(h, &r, 1);
    memset(&m, 0, sizeof m); apply_table(&m, &t, &r, CLS_DINPUT);
    CHECK(m.btn == 0 && !m.tap_btn && axis_u8(m.ax[TGT_LX]) == 128 && axis_u8(m.ax[TGT_RY]) == 128,
          "before the first report: at rest (%04X, sticks %d %d)", m.btn, axis_u8(m.ax[TGT_LX]), axis_u8(m.ax[TGT_RY]));
    u8 rep[600];
    const St press = { 1u << 1, 0, 128, 128, 128, 128, 0, 0 }, rel = { 0, -1, 128, 128, 128, 128, 0, 0 };
    hid_feed(h, rep, build(PSM_DS, M_EXT, &press, 1, rep));     /* cross + up ... */
    hid_feed(h, rep, build(PSM_DS, M_EXT, &rel, 2, rep));       /* ... and released before the sample */
    hid_take(h, &r, 1);
    memset(&m, 0, sizeof m); apply_table(&m, &t, &r, CLS_DINPUT);
    CHECK(m.btn == 0 && m.tap_btn == (CELL_PAD_CTRL_CROSS | CELL_PAD_CTRL_UP), "tap: held %04X tap %04X", m.btn, m.tap_btn);
    hid_take(h, &r, 1);
    memset(&m, 0, sizeof m); apply_table(&m, &t, &r, CLS_DINPUT);
    CHECK(m.btn == 0 && m.tap_btn == 0, "the tap is reported once: held %04X tap %04X", m.btn, m.tap_btn);
    hid_feed(h, rep, build(PSM_DS, M_EXT, &press, 3, rep));
    hid_take(h, &r, 0);                                         /* tap latch off / first read: no taps */
    memset(&m, 0, sizeof m); apply_table(&m, &t, &r, CLS_DINPUT);
    CHECK(m.btn == (CELL_PAD_CTRL_CROSS | CELL_PAD_CTRL_UP) && m.tap_btn == 0, "held without taps: %04X %04X", m.btn, m.tap_btn);
    hid_take(h, &r, 1);
    memset(&m, 0, sizeof m); apply_table(&m, &t, &r, CLS_DINPUT);
    CHECK(m.btn == (CELL_PAD_CTRL_CROSS | CELL_PAD_CTRL_UP), "still held");
    hid_free(h);

    /* dev_read on a PadDev with a HID reader: the first read drops older presses (di_primed) */
    g_cfg.tap_latch = 1;
    PadDev d; memset(&d, 0, sizeof d);
    d.kind = DEV_HID; d.hid = hid_new(PSM_DS4, PS_VID, 0x09CC, 0, 64, "test DS4");
    d.vid = PS_VID; d.pid = 0x09CC; d.port = 0;
    hid_feed(d.hid, rep, build(PSM_DS4, M_USB, &press, 1, rep));
    hid_feed(d.hid, rep, build(PSM_DS4, M_USB, &rel, 2, rep));
    CHECK(dev_read(&d, &r) == 1 && !r.tap[0] && !r.bits[0], "first read: no press from before it");
    hid_feed(d.hid, rep, build(PSM_DS4, M_USB, &press, 3, rep));
    hid_feed(d.hid, rep, build(PSM_DS4, M_USB, &rel, 4, rep));
    CHECK(dev_read(&d, &r) == 1 && ((r.tap[0] >> 1) & 1) && !r.bits[0], "second read: the tap");
    InterlockedExchange(&d.hid->dead, 1);
    CHECK(dev_read(&d, &r) == 0 && d.lost, "a dead reader = device lost");
    hid_free(d.hid);
}

/* CRC gate: wrong CRCs dropped once the pad has shown it fills them in; a pad that never does is used. */
static void test_crc_gate(void)
{
    u8 rep[600];
    const St a = { 1u << 2, -1, 128, 128, 128, 128, 0, 0 }, b = { 1u << 3, -1, 128, 128, 128, 128, 0, 0 };
    HidDev* h = hid_new(PSM_DS, PS_VID, 0x0CE6, 1, 78, "crc");
    RawState r;
    hid_feed(h, rep, build(PSM_DS, M_EXT, &a, 1, rep));
    hid_take(h, &r, 0);
    CHECK(r.bits[0] == (1u << 2), "good CRC: used");
    size_t len = build(PSM_DS, M_EXT, &b, 2, rep);
    rep[20] ^= 0x10;                                       /* damaged on the way */
    hid_feed(h, rep, len);
    hid_take(h, &r, 1);
    CHECK(r.bits[0] == (1u << 2) && !r.tap[0], "bad CRC after good ones: dropped (%08X %08X)", r.bits[0], r.tap[0]);
    for (int i = 1; i < PS_CRC_RUN_WAS_GOOD - 1; i++) hid_feed(h, rep, len);
    hid_take(h, &r, 0);
    CHECK(r.bits[0] == (1u << 2), "%d bad in a row: still dropped", PS_CRC_RUN_WAS_GOOD - 1);
    hid_feed(h, rep, len);
    hid_take(h, &r, 0);
    CHECK(h->crc.lenient && (r.bits[0] & (1u << 3)), "%d bad in a row: used", PS_CRC_RUN_WAS_GOOD);
    hid_feed(h, rep, build(PSM_DS, M_EXT, &a, 3, rep));
    CHECK(!h->crc.lenient, "a good CRC: checking again");
    hid_free(h);

    h = hid_new(PSM_DS4, PS_VID, 0x09CC, 1, 547, "no crc");
    len = build(PSM_DS4, M_EXT, &b, 2, rep);
    rep[74] ^= 0xFF;                                       /* a pad that does not fill the CRC in */
    for (int i = 0; i < PS_CRC_RUN_NEVER_GOOD - 1; i++) hid_feed(h, rep, len);
    hid_take(h, &r, 0);
    CHECK(r.bits[0] == 0, "pad without CRC: the first %d dropped", PS_CRC_RUN_NEVER_GOOD - 1);
    hid_feed(h, rep, len);
    hid_take(h, &r, 0);
    CHECK(r.bits[0] == (1u << 3), "pad without CRC: used after %d", PS_CRC_RUN_NEVER_GOOD);
    hid_free(h);

    PsCrcGate g; memset(&g, 0, sizeof g);
    CHECK(ps_crc_gate(&g, -1) == 1 && g.good == 0 && g.bad == 0, "no CRC to check: used, not counted");
}

/* Steam's lists (SDL_GAMECONTROLLER_IGNORE_DEVICES[_EXCEPT]). */
static void test_steam_lists(void)
{
    VidPidList l;
    parse_vidpid_list(&l, "0x28DE/0x11FF,0x054c/0x0ce6, 0x054C/0x09CC");
    CHECK(l.set && l.n == 3 && vidpid_listed(&l, 0x054C, 0x0CE6) && vidpid_listed(&l, 0x054C, 0x09CC) &&
          vidpid_listed(&l, 0x28DE, 0x11FF) && !vidpid_listed(&l, 0x054C, 0x0DF2), "VID/PID list (%d)", l.n);
    parse_vidpid_list(&l, "garbage,0x054C,/0x0CE6,0x1/0x2/0x3");
    CHECK(l.n == 1 && vidpid_listed(&l, 1, 2), "VID/PID list with junk (%d)", l.n);
    parse_vidpid_list(&l, "");
    CHECK(!l.set && !l.n, "empty list");
    char path[MAX_PATH]; GetTempPathA(sizeof path, path);
    strcat_s(path, sizeof path, "ps_hid_test_ignore.txt");
    FILE* f = NULL; fopen_s(&f, path, "wb");
    if (f) { fputs("0x054C/0x0DF2\n", f); fclose(f); }
    char at[MAX_PATH + 2]; snprintf(at, sizeof at, "@%s", path);
    parse_vidpid_list(&l, at);
    CHECK(l.n == 1 && vidpid_listed(&l, 0x054C, 0x0DF2), "@file list");
    remove(path);

    memset(&g_cfg.steam_ignore, 0, sizeof g_cfg.steam_ignore);
    memset(&g_cfg.steam_except, 0, sizeof g_cfg.steam_except);
    CHECK(!steam_lists(0x054C, 0x0CE6), "no Steam: nothing skipped");
    parse_vidpid_list(&g_cfg.steam_ignore, "0x054C/0x0CE6");
    CHECK(steam_lists(0x054C, 0x0CE6) && !steam_lists(0x054C, 0x09CC), "ignore list");
    memset(&g_cfg.steam_ignore, 0, sizeof g_cfg.steam_ignore);
    parse_vidpid_list(&g_cfg.steam_except, "0x28DE/0x11FF");
    CHECK(steam_lists(0x054C, 0x0CE6) && !steam_lists(0x28DE, 0x11FF), "except list");
    /* skipped only while an XInput pad (Steam's virtual one) is there, and only with steam_input on */
    g_cfg.steam_input = 1;
    memset(g_dev, 0, sizeof g_dev);
    CHECK(!steam_skips(0x054C, 0x0CE6), "no XInput pad: read directly");
    g_dev[0].kind = DEV_XINPUT; g_dev[0].port = 0;
    CHECK(steam_skips(0x054C, 0x0CE6), "with Steam's virtual pad: left to Steam Input");
    CHECK(!steam_skips(0x0F0D, 0x00EE), "only PlayStation pads");
    g_cfg.steam_input = 0;
    CHECK(!steam_skips(0x054C, 0x0CE6), "steam_input = 0: read directly");
    memset(g_dev, 0, sizeof g_dev);
    memset(&g_cfg.steam_except, 0, sizeof g_cfg.steam_except);
    g_cfg.steam_input = 1;
}

/* Never twice: a DirectInput device is skipped when a live HID reader holds its path. */
static void test_claims(void)
{
    memset(g_dev, 0, sizeof g_dev);
    g_dev[0].kind = DEV_HID; g_dev[0].hid = hid_new(PSM_DS, PS_VID, 0x0CE6, 1, 78, "claim");
    g_dev[0].vid = PS_VID; g_dev[0].pid = 0x0CE6;
    wcscpy_s(g_dev[0].path, MAX_PATH, L"\\\\?\\hid#{00001124-0000-1000-8000-00805f9b34fb}_vid&0002054c_pid&0ce6#a&1&0&0000#{4d1e55b2-f16f-11cf-88cb-001111000030}");
    CHECK(hid_claims(L"\\\\?\\HID#{00001124-0000-1000-8000-00805F9B34FB}_VID&0002054C_PID&0CE6#A&1&0&0000#{4D1E55B2-F16F-11CF-88CB-001111000030}",
                     PS_VID, 0x0CE6), "same path, other case: claimed");
    CHECK(!hid_claims(L"\\\\?\\hid#vid_054c&pid_0ce6#b&2&0&0000#{4d1e55b2-f16f-11cf-88cb-001111000030}", PS_VID, 0x0CE6),
          "a second DualSense: not claimed");
    CHECK(hid_claims(L"", PS_VID, 0x0CE6) && !hid_claims(L"", PS_VID, 0x09CC), "no path: by model");
    g_dev[0].lost = 1;
    CHECK(!hid_claims(g_dev[0].path, PS_VID, 0x0CE6), "a lost reader claims nothing");
    hid_free(g_dev[0].hid);
    memset(g_dev, 0, sizeof g_dev);
    /* port pins: dinput:054C:0CE6 and dinput:<name> match a pad read through HID */
    PortCfg pc; memset(&pc, 0, sizeof pc);
    PadDev d; memset(&d, 0, sizeof d);
    d.kind = DEV_HID; d.vid = PS_VID; d.pid = 0x0CE6; snprintf(d.name, sizeof d.name, "DualSense Wireless Controller");
    parse_device_spec(&pc, "dinput:054C:0CE6");
    CHECK(spec_matches(&pc, &d), "dinput:054C:0CE6 pins the HID pad");
    parse_device_spec(&pc, "dinput:dualsense");
    CHECK(spec_matches(&pc, &d), "dinput:dualsense pins the HID pad");
    parse_device_spec(&pc, "dinput");
    CHECK(spec_matches(&pc, &d), "dinput pins the HID pad");
    parse_device_spec(&pc, "xinput");
    CHECK(!spec_matches(&pc, &d), "xinput does not");
}

/* The fake pad (PS3_PAD_HID_FAKE): reports from a file, through the real reader thread code. */
static void test_fake(void)
{
    char path[MAX_PATH]; GetTempPathA(sizeof path, path);
    char name[64]; snprintf(name, sizeof name, "ps_hid_test_fake_%lu.txt", (unsigned long)GetCurrentProcessId());
    strcat_s(path, sizeof path, name);
    HidDev* h = hid_new(PSM_DS, PS_VID, 0x0CE6, 1, 78, "fake");
    snprintf(h->fake, sizeof h->fake, "%s", path);
    u8 rep[600];
    const St s = { (1u << 0) | (1u << 9), 6, 0, 255, 128, 128, 0, 0 };    /* square + options, left */
    const size_t len = build(PSM_DS, M_EXT, &s, 5, rep);
    FILE* f = NULL; fopen_s(&f, path, "wb");
    if (f) {
        fputs("# a comment line\n", f);
        for (size_t i = 0; i < 78; i++) fprintf(f, "%02x%s", rep[i], i + 1 < 78 ? " " : "   # the report\n");
        fclose(f);
    }
    (void)len;
    CHECK(hid_start(h), "fake reader thread");
    RawState r; int got = 0;
    for (int i = 0; i < 200 && !got; i++) {      /* up to 2 s */
        Sleep(10);
        hid_take(h, &r, 0);
        got = r.bits[0] == ((1u << 0) | (1u << 9));
    }
    CHECK(got && raw_get(&r, CID_HAT + 3) && r.axis[0] == -32768 && r.axis[1] == 32767, "fake pad: report from the file");
    CHECK(h->mode == PSR_DS_EXT, "fake pad: extended mode seen");
    remove(path);
    int dead = 0;
    for (int i = 0; i < 200 && !dead; i++) { Sleep(10); dead = h->dead != 0; }
    CHECK(dead, "fake pad: file gone = unplugged");
    hid_free(h);
}

/* ------------------------------------------------------------------ modes for other callers */

static int run_vectors(const char* file)
{
    FILE* f = NULL;
    if (fopen_s(&f, file, "rb") || !f) { fprintf(stderr, "cannot open %s\n", file); return 2; }
    static char line[8192];
    while (fgets(line, sizeof line, f)) {
        char model[16]; int bt = 0, off = 0;
        if (sscanf_s(line, "%15s %d %n", model, (unsigned)sizeof model, &bt, &off) < 2) continue;
        const int m = !strcmp(model, "ds4") ? PSM_DS4 : !strcmp(model, "dualsense") ? PSM_DS : !strcmp(model, "edge") ? PSM_EDGE : 0;
        u8 rep[2048];
        const size_t n = hex_bytes(line + off, line + strlen(line), rep, sizeof rep);
        RawState r; memset(&r, 0, sizeof r);
        const int crc = ps_crc_check(m, rep, n);
        const int psr = ps_parse(m, bt, rep, n, &r);
        printf("R %d %d %08X %08X %08X %08X %08X %d %d %d %d %d %d %d %d\n", psr, crc, r.bits[0], r.bits[1], r.bits[2], r.bits[3],
               r.bits[4], r.axis[0], r.axis[1], r.axis[2], r.axis[3], r.axis[4], r.axis[5], r.axis[6], r.axis[7]);
    }
    fclose(f);
    return 0;
}

static int run_scan(int seconds)
{
    _putenv_s("PS3_PAD_FILE", "");
    load_config();
    g_cfg.hid = 1; g_cfg.dinput = 0; g_cfg.devices = 1; g_cfg.tap_latch = 1;
    printf("PlayStation pads Windows has now (read only, nothing is sent):\n");
    hid_scan();
    int n = 0;
    for (int i = 0; i < MAX_DEVS; i++) if (g_dev[i].kind == DEV_HID) n++;
    if (!n) printf("none\n");
    for (int t = 0; t < seconds * 10 && n; t++) Sleep(100);
    for (int i = 0; i < MAX_DEVS; i++) {
        if (g_dev[i].kind != DEV_HID) continue;
        HidDev* h = g_dev[i].hid;
        printf("%s %04X:%04X %s: %u reports, %s, %u with a wrong CRC dropped%s\n", h->name, h->vid, h->pid,
               h->bt ? "Bluetooth" : "USB", h->n_reports, h->mode ? k_psr_name[h->mode] : "no report yet", h->n_dropped,
               h->dead ? ", reading stopped" : "");
        dev_release(&g_dev[i]);
    }
    return 0;
}

int main(int argc, char** argv)
{
    setvbuf(stdout, NULL, _IONBF, 0);
    for (int i = 1; i < argc; i++) {
        if (!strncmp(argv[i], "vectors=", 8)) return run_vectors(argv[i] + 8);
        if (!strcmp(argv[i], "scan")) return run_scan(i + 1 < argc ? atoi(argv[i + 1]) : 2);
    }
    LARGE_INTEGER fq; QueryPerformanceFrequency(&fq); g_qpf = fq.QuadPart;
    test_crc();
    test_parse_all_modes();
    test_dualsense_01();
    test_not_input();
    test_layout();
    test_taps();
    test_crc_gate();
    test_steam_lists();
    test_claims();
    test_fake();
    if (g_fails) { printf("FAILED %d of %d checks\n", g_fails, g_checks); return 1; }
    printf("PASS %d checks\n", g_checks);
    return 0;
}
