/*
 * Unit test of the picture format rectangles (ps3recomp patch 0107, libs/video/rsx_picture_rect.h;
 * docs/PICTURE_FORMAT.md): where the present puts the game's 1280 x 720 picture in windows of every
 * shape, for PS3_PICTURE = fit / fill / stretch / 4:3, and where the training overlay goes.
 *
 *   fit      = the present before 0107, to the pixel (the old formula is repeated here)
 *   fill     = no bars, shape kept, the cut shared by both sides
 *   stretch  = the whole window
 *   4:3      = the middle 960 x 720 of the picture, as large as the window allows
 *   overlay  = always a 16:9 rectangle inside the visible part
 *
 *   picture_rect_test    prints "PASS <n> checks" (exit 0) or the failures (exit 1)
 *
 * Built by tests/test_picture_format.py with clang-cl or cl.
 */
#include "rsx_picture_rect.h"

#include <math.h>
#include <stdio.h>
#include <stdlib.h>

static int g_checks, g_fails;
#define CHECK(cond, ...)                                                        \
    do {                                                                        \
        g_checks++;                                                             \
        if (!(cond)) {                                                          \
            g_fails++;                                                          \
            printf("FAIL line %d: ", __LINE__); printf(__VA_ARGS__); printf("\n"); \
        }                                                                       \
    } while (0)

/* ld_present_copy before patch 0107, verbatim */
static void old_present(unsigned bwu, unsigned bhu, unsigned aw, unsigned ah,
                        float* vx, float* vy, float* vw_, float* vh_, long sc[4])
{
    const float bw = (float)bwu, bh = (float)bhu;
    const float k = bw / (float)aw < bh / (float)ah ? bw / (float)aw : bh / (float)ah;
    const float vw = (float)aw * k, vh = (float)ah * k;
    *vx = (float)(long)((bw - vw) * 0.5f);
    *vy = (float)(long)((bh - vh) * 0.5f);
    *vw_ = vw; *vh_ = vh;
    sc[0] = (long)*vx; sc[1] = (long)*vy;
    sc[2] = (long)(*vx + vw + 0.5f); sc[3] = (long)(*vy + vh + 0.5f);
}

/* within the present's rounding: origins are truncated to whole pixels */
static int near(float a, float b) { return fabsf(a - b) <= 1.5f; }

static void check_one(unsigned bw, unsigned bh)
{
    const unsigned aw = 1280, ah = 720;
    rsx_pic_rect r;

    /* fit: identical to the old present (viewport, scissor) and the old overlay */
    float vx, vy, vw, vh; long sc[4];
    old_present(bw, bh, aw, ah, &vx, &vy, &vw, &vh, sc);
    rsx_picture_rect(RSX_PIC_FIT, bw, bh, aw, ah, &r);
    CHECK(r.vx == vx && r.vy == vy && r.vw == vw && r.vh == vh, "fit %ux%u viewport", bw, bh);
    CHECK(r.cl == sc[0] && r.ct == sc[1] && r.cr == sc[2] && r.cb == sc[3], "fit %ux%u scissor", bw, bh);
    CHECK(r.ox == vx && r.oy == vy && r.ow == vw && r.oh == vh, "fit %ux%u overlay", bw, bh);

    /* fill: covers the window, 16:9 kept, centred, cut <= what the shape needs */
    rsx_picture_rect(RSX_PIC_FILL, bw, bh, aw, ah, &r);
    CHECK(r.cl == 0 && r.ct == 0 && r.cr == (long)bw && r.cb == (long)bh, "fill %ux%u scissor", bw, bh);
    CHECK(r.vx <= 0.0f && r.vy <= 0.0f && r.vx + r.vw >= (float)bw - 0.5f && r.vy + r.vh >= (float)bh - 0.5f,
          "fill %ux%u covers", bw, bh);
    CHECK(fabsf(r.vw / r.vh - 16.0f / 9.0f) < 1e-3f, "fill %ux%u shape", bw, bh);
    CHECK(near(-r.vx, (r.vx + r.vw) - (float)bw) && near(-r.vy, (r.vy + r.vh) - (float)bh),
          "fill %ux%u centred (%.1f %.1f %.1f %.1f)", bw, bh, r.vx, r.vy, r.vw, r.vh);
    CHECK(near(r.vw, (float)bw) || near(r.vh, (float)bh), "fill %ux%u no more than needed", bw, bh);

    /* stretch */
    rsx_picture_rect(RSX_PIC_STRETCH, bw, bh, aw, ah, &r);
    CHECK(r.vx == 0 && r.vy == 0 && r.vw == (float)bw && r.vh == (float)bh, "stretch %ux%u", bw, bh);
    CHECK(r.cl == 0 && r.ct == 0 && r.cr == (long)bw && r.cb == (long)bh, "stretch %ux%u scissor", bw, bh);

    /* 4:3: visible part 4:3, the picture's middle (windows too small to have a shape: only no crash) */
    rsx_picture_rect(RSX_PIC_43, bw, bh, aw, ah, &r);
    if (bw < 16 || bh < 16) goto overlay;
    const float cw = (float)(r.cr - r.cl), ch = (float)(r.cb - r.ct);
    CHECK(fabsf(cw / ch - 4.0f / 3.0f) < 0.01f, "4:3 %ux%u visible %.0fx%.0f", bw, bh, cw, ch);
    CHECK(r.cl >= 0 && r.ct >= 0 && r.cr <= (long)bw && r.cb <= (long)bh, "4:3 %ux%u inside", bw, bh);
    CHECK(near(cw, (float)bw) || near(ch, (float)bh), "4:3 %ux%u as large as possible", bw, bh);
    CHECK(near(r.vh, ch) && near(r.vw, ch * 16.0f / 9.0f), "4:3 %ux%u picture height = visible", bw, bh);
    CHECK(near((float)r.cl - r.vx, (r.vx + r.vw) - (float)r.cr), "4:3 %ux%u middle", bw, bh);
    /* in guest pixels the visible part is x 160..1120 */
    CHECK(fabsf(((float)r.cl - r.vx) / r.vw * 1280.0f - 160.0f) < 2.5f, "4:3 %ux%u cut %.2f", bw, bh,
          ((float)r.cl - r.vx) / r.vw * 1280.0f);

overlay:
    /* the overlay: 16:9, inside the visible part */
    for (int m = 0; m < 4; m++) {
        rsx_picture_rect(m, bw, bh, aw, ah, &r);
        CHECK(fabsf(r.ow / r.oh - 16.0f / 9.0f) < 1e-3f, "overlay mode %d %ux%u shape", m, bw, bh);
        CHECK(r.ox >= (float)r.cl - 0.01f && r.oy >= (float)r.ct - 0.01f &&
              r.ox + r.ow <= (float)r.cr + 1.0f && r.oy + r.oh <= (float)r.cb + 1.0f,
              "overlay mode %d %ux%u inside", m, bw, bh);
    }
}

int main(void)
{
    /* names */
    CHECK(rsx_picture_mode_parse(NULL) == RSX_PIC_FIT, "null");
    CHECK(rsx_picture_mode_parse("") == RSX_PIC_FIT, "empty");
    CHECK(rsx_picture_mode_parse("fit") == RSX_PIC_FIT, "fit");
    CHECK(rsx_picture_mode_parse("FILL") == RSX_PIC_FILL, "FILL");
    CHECK(rsx_picture_mode_parse("zoom") == RSX_PIC_FILL, "zoom");
    CHECK(rsx_picture_mode_parse("Stretch") == RSX_PIC_STRETCH, "stretch");
    CHECK(rsx_picture_mode_parse("4:3") == RSX_PIC_43, "4:3");
    CHECK(rsx_picture_mode_parse("43") == RSX_PIC_43, "43");
    CHECK(rsx_picture_mode_parse("nonsense-long-value-here") == RSX_PIC_FIT, "unknown");
    for (int m = 0; m < 4; m++) CHECK(rsx_picture_mode_parse(rsx_picture_mode_name(m)) == m, "name %d", m);

    /* the shapes players have: 16:9, 16:10, 3:2, 4:3, 21:9, 32:9, portrait, odd sizes */
    static const unsigned sizes[][2] = {
        {1280, 720}, {1920, 1080}, {2560, 1440}, {3840, 2160}, {1920, 1200}, {2560, 1600}, {1680, 1050},
        {1440, 900}, {2160, 1440}, {3000, 2000}, {1920, 1280}, {2256, 1504}, {2880, 1920}, {1024, 768},
        {1600, 1200}, {640, 480}, {3440, 1440}, {2560, 1080}, {5120, 1440}, {1080, 1920}, {801, 601},
        {1366, 768}, {1, 1}, {7, 3}, {1281, 721}, {1279, 719},
    };
    for (size_t i = 0; i < sizeof sizes / sizeof sizes[0]; i++) check_one(sizes[i][0], sizes[i][1]);

    /* the numbers docs/PICTURE_FORMAT.md gives */
    rsx_pic_rect r;
    rsx_picture_rect(RSX_PIC_FIT, 1920, 1200, 1280, 720, &r);
    CHECK(r.cl == 0 && r.ct == 60 && r.cr == 1920 && r.cb == 1140, "16:10 fit bars 60");
    rsx_picture_rect(RSX_PIC_FIT, 1920, 1280, 1280, 720, &r);
    CHECK(r.ct == 100 && r.cb == 1180, "3:2 fit bars 100");
    rsx_picture_rect(RSX_PIC_FILL, 1920, 1200, 1280, 720, &r);
    CHECK(r.vx == -107.0f && near(r.vw, 2133.3f) && r.vh == 1200.0f, "16:10 fill (%.1f %.1f)", r.vx, r.vw);
    rsx_picture_rect(RSX_PIC_FILL, 2160, 1440, 1280, 720, &r);
    CHECK(r.vx == -200.0f && r.vw == 2560.0f, "3:2 fill (%.1f %.1f)", r.vx, r.vw);
    rsx_picture_rect(RSX_PIC_43, 1920, 1080, 1280, 720, &r);
    CHECK(r.cl == 240 && r.cr == 1680 && r.ct == 0 && r.cb == 1080 && r.vx == 0.0f && r.vw == 1920.0f,
          "4:3 on 1080p (%ld %ld %.1f %.1f)", r.cl, r.cr, r.vx, r.vw);
    rsx_picture_rect(RSX_PIC_43, 1024, 768, 1280, 720, &r);
    CHECK(r.cl == 0 && r.cr == 1024 && r.ct == 0 && r.cb == 768, "4:3 on 4:3 fills (%ld %ld %ld %ld)",
          r.cl, r.ct, r.cr, r.cb);

    /* a 4:3 guest picture in 4:3 mode is just fitted */
    rsx_picture_rect(RSX_PIC_43, 1920, 1080, 960, 720, &r);
    CHECK(r.cl == 240 && r.cr == 1680 && r.vw == 1440.0f, "4:3 guest");

    /* patch 0109 (review picture-120 P2): the present's plain copy is allowed only when nothing is cut or
     * barred. 4:3 at Native in the default 1280x720 window has a full-window viewport but the scissor keeps
     * 160..1120 -- the copy showed the whole 16:9 picture. */
    rsx_picture_rect(RSX_PIC_43, 1280, 720, 1280, 720, &r);
    CHECK(r.vx == 0.0f && r.vw == 1280.0f && r.cl == 160 && r.cr == 1120, "4:3 1280x720 (%.1f %.1f %ld %ld)",
          r.vx, r.vw, r.cl, r.cr);
    CHECK(!rsx_picture_rect_whole(&r, 1280, 720), "4:3 1280x720 is no plain copy");
    rsx_picture_rect(RSX_PIC_43, 1920, 1080, 1920, 1080, &r);
    CHECK(!rsx_picture_rect_whole(&r, 1920, 1080), "4:3 1920x1080 same size is no plain copy");
    for (int m = 0; m < 3; m++) {   /* fit, fill, stretch of a same-size, same-shape source: the copy */
        rsx_picture_rect(m, 1280, 720, 1280, 720, &r);
        CHECK(rsx_picture_rect_whole(&r, 1280, 720), "mode %d same size is the plain copy", m);
    }
    rsx_picture_rect(RSX_PIC_FIT, 1280, 720, 960, 720, &r);
    CHECK(!rsx_picture_rect_whole(&r, 1280, 720), "fit of a 4:3 guest has bars");
    rsx_picture_rect(RSX_PIC_FILL, 1920, 1200, 1280, 720, &r);
    CHECK(!rsx_picture_rect_whole(&r, 1920, 1200), "fill on 16:10 is cut");

    if (g_fails) {
        printf("FAILED %d of %d checks\n", g_fails, g_checks);
        return 1;
    }
    printf("PASS %d checks\n", g_checks);
    return 0;
}
