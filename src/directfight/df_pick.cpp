/*
 * T5DR direct fight -- helpers of the in-game character select (NPUB30009
 * v01.00; docs/DIRECTFIGHT.md "Character select in the game").
 *
 * The players pick on the game's own select screen; df_fight.cpp runs the
 * phases (Pick, PickWait). Here: the local pad as the select screen gets it,
 * the name plates of the select screen as a hint line, the pick's wire format,
 * and the game's model ids (what the select record says was picked).
 *
 * What the select screen does (probes build/cs/exp e1-e9, offline, scripted
 * pads):
 *   - per player, the record at 0x10093F58 + p*0x78: +0 cursor cell, +8 the
 *     portrait id under it, +0x0C the picked model id (0xFFFFFFFF until the
 *     character is confirmed), +0x10 the model shown, +0x20 the state byte
 *     (3 choosing, 9 handicap, then 0x15 / 0x0D done), +0x48 the model again.
 *   - every face button confirms the character; the button is the costume.
 *     Square (LP) and Triangle (RP), Cross (LK) and Circle (RK) give the same
 *     model for most characters (two costumes), Xiaoyu has four (0x10, 0x11,
 *     0x13, 0x14 for LP, LK, RP, RK); Kuma's cell gives Kuma with a punch
 *     button (0x1E) and Panda with a kick button (0x1F).
 *   - state 9 is the handicap bar (100 %); the next confirm finishes the pick.
 *   - L1 loads customize data (blocked here); Start, Select, R1, L2, R2, L3, R3
 *     do nothing on this screen; there is no random cell.
 *   - the name and rank of each side (the VS custom data, as in the fight HUD)
 *     are read every frame: writing them shows at once.
 */
#define WIN32_LEAN_AND_MEAN
#include "../platform/t5_win.h"
#include <stdio.h>
#include <string.h>
#include "df.h"

/* src/netplay/local_pad.cpp: this PC's player's controller -- online the one pressed last, on any port
 * (docs/NETPLAY.md "Which controller plays online") -- in cellPad_sample_local's layout, host-endian
 * (len, then button[] as cellPadGetData lays it out). */
struct DfHostPad { int32_t len; uint16_t button[64]; };
extern "C" int32_t t5_local_player_pad(void* out);

namespace df {

/* The local player's pad for the select screen: d-pad and left stick as
 * directions (opposite directions cancel), the four face buttons, Select. Read
 * through the runtime's pad layer (controls.ini, sticks, keyboard, PS3_PAD_FILE),
 * one read per frame with its own tap latch; the same controller netplay takes
 * the player's input from. */
uint16_t pick_read_local_pad()
{
    DfHostPad d;
    memset(&d, 0, sizeof d);
    if (t5_local_player_pad(&d) != 0 || d.len == 0) return 0;
    uint16_t b = (uint16_t)((d.button[2] & 0xFF) | ((d.button[3] & 0xFF) << 8));
    const unsigned lx = d.button[6] & 0xFF, ly = d.button[7] & 0xFF;
    if (lx < 64) b |= B_LEFT; else if (lx > 191) b |= B_RIGHT;
    if (ly < 64) b |= B_UP; else if (ly > 191) b |= B_DOWN;
    if ((b & B_LEFT) && (b & B_RIGHT)) b &= (uint16_t)~(B_LEFT | B_RIGHT);
    if ((b & B_UP) && (b & B_DOWN)) b &= (uint16_t)~(B_UP | B_DOWN);
    return (uint16_t)(b & (B_UP | B_DOWN | B_LEFT | B_RIGHT | B_SQUARE | B_TRIANGLE | B_CROSS | B_CIRCLE | B_SELECT));
}

/* ---- the name plates (VS custom data, docs/DIRECTFIGHT.md "Names and ranks") -- */
constexpr uint32_t kTocCustomData = 0x0046ECD0;
constexpr uint32_t kCustomStride  = 0x1F4;
constexpr uint32_t kCustomRank    = 0x11C;
constexpr uint32_t kCustomName    = 0x134;

namespace {
bool g_saved = false;
uint16_t g_name[2][20];
uint8_t g_rank[2];
char g_shown[2][24];

uint32_t custom_base()
{
    const uint32_t base = rd32(kTocCustomData);
    return (base >= 0x10000000u && base < 0x10760000u) ? base : 0;
}
} // namespace

void plates_save()
{
    const uint32_t base = custom_base();
    if (!base) return;
    for (int p = 0; p < 2; p++) {
        for (uint32_t i = 0; i < 20; i++) g_name[p][i] = rd16(base + p * kCustomStride + kCustomName + 2 * i);
        g_rank[p] = rd8(base + p * kCustomStride + kCustomRank);
        g_shown[p][0] = 0;
    }
    g_saved = true;
}

void plates_restore()
{
    const uint32_t base = custom_base();
    if (!base || !g_saved) return;
    for (int p = 0; p < 2; p++) {
        for (uint32_t i = 0; i < 20; i++) wr16(base + p * kCustomStride + kCustomName + 2 * i, g_name[p][i]);
        wr8(base + p * kCustomStride + kCustomRank, g_rank[p]);
    }
    g_saved = false;
}

/* `text` under side p's portrait (16 characters, printable ASCII); nullptr =
 * that side's own name again */
void plate_text(int p, const char* text)
{
    const uint32_t base = custom_base();
    if (!base || !g_saved || p < 0 || p > 1) return;
    const char* t = text ? text : "";
    if (text && !strcmp(g_shown[p], t)) return;
    const uint32_t b = base + (uint32_t)p * kCustomStride + kCustomName;
    if (!text) {
        for (uint32_t i = 0; i < 20; i++) wr16(b + 2 * i, g_name[p][i]);
        g_shown[p][0] = 0;
        return;
    }
    for (uint32_t i = 0; i < 20; i++) wr16(b + 2 * i, 0);
    for (size_t i = 0; t[i] && i < 16; i++) {
        const unsigned char c = (unsigned char)t[i];
        wr16(b + 2 * (uint32_t)i, (uint16_t)(c >= 0x20 && c < 0x7F ? c : '?'));
    }
    snprintf(g_shown[p], sizeof g_shown[p], "%s", t);
}

/* ---- the pick on the wire (PICK packets, src/netplay) ----------------------
 * u32: character id + 1 (bits 24-31, never 0), model id (16-23), confirm
 * button 1-4 (8-15), cursor cell (0-7). */
uint32_t pick_pack(int chr, int cell, int btn, int model)
{
    return ((uint32_t)(chr + 1) << 24) | ((uint32_t)(model & 0xFF) << 16) | ((uint32_t)(btn & 0xFF) << 8) | (uint32_t)(cell & 0xFF);
}

bool pick_unpack(uint32_t v, int* chr, int* cell, int* btn, int* model)
{
    const int c = (int)(v >> 24) - 1, b = (int)((v >> 8) & 0xFF);
    if (c < 0 || c > 35 || b < 1 || b > 4) return false;
    *chr = c; *btn = b; *model = (int)((v >> 16) & 0xFF); *cell = (int)(v & 0xFF);
    return true;
}

/* confirm buttons: 1 = Square (LP), 2 = Triangle (RP), 3 = Cross (LK), 4 = Circle (RK) */
uint16_t btn_bits(int btn)
{
    static const uint16_t k[5] = { 0, B_SQUARE, B_TRIANGLE, B_CROSS, B_CIRCLE };
    return btn >= 1 && btn <= 4 ? k[btn] : 0;
}

int btn_index(uint16_t bits)
{
    for (int i = 1; i <= 4; i++) if (bits & btn_bits(i)) return i;
    return 0;
}

const char* btn_name(int btn)
{
    static const char* const k[5] = { "default", "Square (LP)", "Triangle (RP)", "Cross (LK)", "Circle (RK)" };
    return btn >= 0 && btn <= 4 ? k[btn] : "?";
}

/* The character of a model id: the first model of each character (the model
 * shown under the cursor, walked over every cell), in character-id order. A
 * character's costumes follow its first model. */
int model_char(int model)
{
    static const int kFirst[35] = {
        0, 2, 5, 7, 9, 12, 14, 16, 21, 25, 28, 30, 31, 32, 34, 36, 38, 41, 43, 45,   /* Paul .. Mokujin */
        23, 47, 49, 51, 54, 56, 59, 63, 66, 68, 70, 73, 75, 77, 79 };                /* Eddy .. Dragunov */
    if (model == 0x52 || model == 0x53) return 35;   /* Jinpachi (the open grid's cell 35; runs off3, pair_rb) */
    int best = -1, best_first = -1;
    for (int c = 0; c < 35; c++)
        if (kFirst[c] <= model && kFirst[c] > best_first) { best = c; best_first = kFirst[c]; }
    return model >= 0 && model <= 80 ? best : -1;
}

/* The confirm button (1 LP, 2 RP, 3 LK, 4 RK) that gives `model` when chr's cell
 * is confirmed with it alone (docs/DIRECTFIGHT.md "Mirror matches": the model
 * table) -- for a pick made on the random cell, which the peer's driver confirms
 * on the fighter's own cell. 0 = not known (the pressed button is sent). */
int pick_button_for(int chr, int model)
{
    if (chr == 11) return 1;                 /* Kuma: a punch button */
    if (chr == 12) return 3;                 /* Panda: a kick button */
    if (chr == 35) return model == 0x52 ? 3 : model == 0x53 ? 2 : 0;   /* Jinpachi: Cross 0x52, Triangle 0x53 (pair_rb) */
    if (chr < 0 || chr > 34 || model_char(model) != chr) return 0;
    static const int kFirst[35] = {
        0, 2, 5, 7, 9, 12, 14, 16, 21, 25, 28, 30, 31, 32, 34, 36, 38, 41, 43, 45,
        23, 47, 49, 51, 54, 56, 59, 63, 66, 68, 70, 73, 75, 77, 79 };
    const int o = model - kFirst[chr];
    if (chr == 7) return o == 0 ? 1 : o == 1 ? 3 : o == 3 ? 2 : o == 4 ? 4 : 0;    /* Xiaoyu: 0x10 0x11 0x13 0x14 */
    if (chr == 26) return o == 0 ? 1 : o == 1 ? 3 : o == 2 ? 2 : o == 3 ? 4 : 0;   /* Asuka: 0x3B..0x3E */
    switch (chr) {
    case 1: case 4: case 9: case 16: case 23: case 25: case 27: case 30:     /* a third costume on Triangle */
        return o == 0 ? 1 : o == 1 ? 3 : o == 2 ? 2 : 0;
    default:
        return o == 0 ? 1 : o == 1 ? 3 : 0;
    }
}

} // namespace df
