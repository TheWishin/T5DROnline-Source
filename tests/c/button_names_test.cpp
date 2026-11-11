/*
 * The players' own button names and the offline Versus rule, without the game
 * (tests/test_vs_overlay.py builds and runs it): src/training/button_names.h --
 * controls.ini text -> names, the defaults when nothing is named, the ini rules
 * of the runtime, the pad mask's other buttons, the text of a row, the panel's
 * width, and who gets the input display in which offline mode.
 * Prints "PASS <n> checks" and exits 0, or the failed checks and exits 1.
 */
#include <stdio.h>
#include <string.h>
#include <string>

#include "training_logic.h"
#include "button_names.h"

using namespace training;

static int g_checks = 0, g_fail = 0;
#define CHECK(c) do { g_checks++; if (!(c)) { g_fail++; printf("FAIL %s:%d: %s\n", __FILE__, __LINE__, #c); } } while (0)
#define CHECK_STR(a, b) do { g_checks++; if (strcmp((a), (b)) != 0) { g_fail++; \
    printf("FAIL %s:%d: %s == %s (\"%s\" vs \"%s\")\n", __FILE__, __LINE__, #a, #b, (a), (b)); } } while (0)

static ButtonNames parse(const std::string& s)
{
    ButtonNames n;
    parse_button_names(s.data(), s.size(), n);
    return n;
}

static std::string row(const ButtonNames& n, int p, uint16_t bits)
{
    char b[kBtnCount * (kNameBytes + 1)];
    buttons_named(bits, n, p, b, sizeof b);
    return b;
}

static void test_defaults()
{
    /* no file, an empty file, a file without a names section: 1 2 3 4, nothing else listed */
    for (const char* text : { "", "[general]\nxinput = 1\n[keys1]\n1 = U\nL1 = Q\n", "; [names]\n# 1 = LP\n" }) {
        const ButtonNames n = parse(text);
        for (int p = 0; p < 2; p++) {
            CHECK(!n.any_custom(p));
            CHECK(n.extras(p) == 0);
            CHECK_STR(n.name[p][kBtn1], "1");
            CHECK_STR(n.name[p][kBtn2], "2");
            CHECK_STR(n.name[p][kBtn3], "3");
            CHECK_STR(n.name[p][kBtn4], "4");
            CHECK_STR(n.name[p][kBtnL1], "L1");
            CHECK_STR(n.name[p][kBtnSelect], "SELECT");
            CHECK(row(n, p, 0x3) == "1+2");
            CHECK(row(n, p, 0xF) == "1+2+3+4");
            CHECK(row(n, p, 0) == "");
        }
    }
    /* the plain text of the default names is what buttons_text writes */
    char a[16];
    const ButtonNames d;
    for (unsigned b = 0; b < 16; b++) {
        buttons_text((uint16_t)b, a, sizeof a);
        CHECK(row(d, 0, (uint16_t)b) == a);
    }
}

static void test_targets()
{
    /* every way to write a target, case-insensitive */
    ButtonNames n = parse("[names]\n1 = LP\nrp = RP\nCross = LK\n4=RK\n");
    for (int p = 0; p < 2; p++) {
        CHECK_STR(n.name[p][kBtn1], "LP");
        CHECK_STR(n.name[p][kBtn2], "RP");
        CHECK_STR(n.name[p][kBtn3], "LK");
        CHECK_STR(n.name[p][kBtn4], "RK");
        CHECK(n.any_custom(p) && n.extras(p) == 0);
        CHECK(row(n, p, 0x9) == "LP+RK");
    }
    n = parse("[NAMES]\nSQUARE=A\nTRIANGLE=B\nlk=C\ncircle=D\nL1=E\nr1=F\nL2=G\nR2=H\nl3=I\nR3=J\nstart=K\nSelect=L\n");
    static const char* want[kBtnCount] = { "A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L" };
    for (int b = 0; b < kBtnCount; b++) { CHECK_STR(n.name[0][b], want[b]); CHECK(n.custom[1][b]); }
    CHECK(n.extras(0) == 0xFF0);
    CHECK(row(n, 0, 0xFFF) == "A+B+C+D+E+F+G+H+I+J+K+L");
    /* unknown targets, binding-style combos and lines without = are not names */
    n = parse("[names]\n1+2 = BOTH\nUP = U\nfoo = bar\njust a line\n2 = OK\n");
    CHECK_STR(n.name[0][kBtn1], "1");
    CHECK_STR(n.name[0][kBtn2], "OK");
    CHECK(!n.custom[0][kBtn1] && n.custom[0][kBtn2]);
}

static void test_players()
{
    /* [names] both, [names1] / [names2] one player and stronger than [names], whatever the order */
    ButtonNames n = parse("[names1]\n1 = P1LP\nL1 = TAG\n[names]\n1 = LP\n2 = RP\n[names2]\n2 = P2RP\n");
    CHECK_STR(n.name[0][kBtn1], "P1LP");
    CHECK_STR(n.name[1][kBtn1], "LP");
    CHECK_STR(n.name[0][kBtn2], "RP");
    CHECK_STR(n.name[1][kBtn2], "P2RP");
    CHECK(n.extras(0) == (1u << kBtnL1) && n.extras(1) == 0);       /* only P1 named L1 */
    CHECK_STR(n.name[1][kBtnL1], "L1");
    CHECK(row(n, 0, 0x3 | (1u << kBtnL1)) == "P1LP+RP+TAG");
    CHECK(row(n, 1, 0x3) == "LP+P2RP");
    /* names in other sections are bindings, not names */
    n = parse("[keys1]\n1 = U\n[port1]\ndevice = auto\n[names3]\n1 = X\n[names 1]\n1 = Y\n");
    CHECK(!n.any_custom(0) && !n.any_custom(1));
}

static void test_ini_rules()
{
    /* comments, inline comments (whitespace before ; or #), blanks, CRLF, quotes */
    ButtonNames n = parse("  [ names ]  \r\n ; a comment\r\n# another\r\n  1   =   LP   ; left punch\r\n2 = R#P\r\n"
                          "3 = \"L K\"\r\n4 = RK\t# kick\r\n");
    CHECK_STR(n.name[0][kBtn1], "LP");
    CHECK_STR(n.name[0][kBtn2], "R#P");            /* no whitespace before #: part of the name */
    CHECK_STR(n.name[0][kBtn3], "L K");
    CHECK_STR(n.name[0][kBtn4], "RK");
    /* a key given twice: the last; a section given twice: the first */
    n = parse("[names]\n1 = A\n1 = B\n[keys1]\n[names]\n1 = C\n2 = D\n");
    CHECK_STR(n.name[0][kBtn1], "B");
    CHECK_STR(n.name[0][kBtn2], "2");
    /* an empty name is the default again, also over [names] in a player's section */
    n = parse("[names]\n1 = LP\nL1 = TAG\n[names2]\n1 =\nL1 =   ; none\n");
    CHECK_STR(n.name[0][kBtn1], "LP");
    CHECK_STR(n.name[1][kBtn1], "1");
    CHECK(!n.custom[1][kBtn1] && !n.custom[1][kBtnL1] && n.custom[0][kBtnL1]);
    CHECK(n.extras(1) == 0);
    /* no newline at the end, a key before any section, a broken section line */
    n = parse("1 = X\n[names\n1 = Y\n[names]\n4 = RK");
    CHECK_STR(n.name[0][kBtn1], "1");
    CHECK_STR(n.name[0][kBtn4], "RK");
}

static void test_name_limits()
{
    /* at most kNameChars characters; UTF-8 kept whole; control characters and broken bytes dropped */
    ButtonNames n = parse("[names]\n1 = ABCDEFGHIJKLMNOP\n2 = \xC3\x9C" "ber\n3 = A\x01" "B\x7F" "C\n4 = \xE3\x83\x91\xE3\x83\xB3\xE3\x83\x81\n"
                          "L1 = \xFFOK\xC3\nR1 = \x01\x02\nL2 = ABCDEFG HIJ\n");
    CHECK_STR(n.name[0][kBtn1], "ABCDEFGH");
    CHECK_STR(n.name[0][kBtn2], "\xC3\x9C" "ber");
    CHECK_STR(n.name[0][kBtn3], "ABC");
    CHECK_STR(n.name[0][kBtn4], "\xE3\x83\x91\xE3\x83\xB3\xE3\x83\x81");
    CHECK_STR(n.name[0][kBtnL1], "OK");
    CHECK(!n.custom[0][kBtnR1]);                   /* nothing left: the default, not listed */
    CHECK_STR(n.name[0][kBtnL2], "ABCDEFG");       /* cut at the space: no trailing blank */
    /* eight four-byte characters fit, the buffer is terminated */
    std::string s = "[names]\n1 = ";
    for (int i = 0; i < 12; i++) s += "\xF0\x9F\x98\x80";
    n = parse(s);
    CHECK(strlen(n.name[0][kBtn1]) == 32);
    /* a row never overruns its buffer and never ends in half a name */
    n = parse("[names]\n1 = AAAAAAAA\n2 = BBBBBBBB\n3 = CCCCCCCC\n");
    char small[20];
    buttons_named(0x7, n, 0, small, sizeof small);
    CHECK_STR(small, "AAAAAAAA+BBBBBBBB");
    buttons_named(0x7, n, 0, small, 9);
    CHECK_STR(small, "AAAAAAAA");
    buttons_named(0x7, n, 0, small, 4);
    CHECK_STR(small, "");
}

static void test_pad_extras()
{
    CHECK(pad_extras(0) == 0);
    CHECK(pad_extras(kPadL1) == 1u << kBtnL1);
    CHECK(pad_extras(kPadR1) == 1u << kBtnR1);
    CHECK(pad_extras(kPadL2) == 1u << kBtnL2);
    CHECK(pad_extras(kPadR2) == 1u << kBtnR2);
    CHECK(pad_extras(kPadL3) == 1u << kBtnL3);
    CHECK(pad_extras(kPadR3) == 1u << kBtnR3);
    CHECK(pad_extras(kPadStart) == 1u << kBtnStart);
    CHECK(pad_extras(kPadSelect) == 1u << kBtnSelect);
    CHECK(kPadStart == kStart && kPadSelect == kSelect);          /* the practice tools' two */
    /* directions and attack buttons are not among them, and never collide with notation()'s bits */
    CHECK(pad_extras((uint16_t)(kUp | kDown | kLeft | kRight | kSquare | kTriangle | kCross | kCircle)) == 0);
    CHECK((pad_extras(0xFFFF) & 0xF) == 0 && pad_extras(0xFFFF) == 0xFF0);
    /* a history row changes when a named other button comes or goes, and not otherwise */
    History<8> h;
    Notation a = notation(kSquare, false);
    h.push(a);
    Notation b = a;
    b.buttons = (uint16_t)(b.buttons | pad_extras(kPadL1));
    h.push(b);
    h.push(b);
    CHECK(h.count == 2 && h.rows[0].frames == 2 && h.rows[0].n.buttons == (1u | (1u << kBtnL1)));
}

static void test_width()
{
    CHECK(history_width(0) == kHistW);                 /* 1 2 3 4: the panel as it always was */
    CHECK(history_width(48) == kHistW);                /* "1+2+3+4" under the default names still fits */
    CHECK(history_width(66) == kHistW);
    CHECK(history_width(120) == 78.0f + 120.0f + 12.0f);
    CHECK(history_width(5000) == kHistMaxW);
    CHECK(history_width(-18) == kHistW);
}

static void test_who_sees_it()
{
    const bool P = true, V = true;
    /* offline_show(practice, all, training setting, training mode, versus, vs setting, vs F2) */
    /* defaults (training "frames", Versus off): Practice as before, Versus nothing */
    CHECK(offline_show(P, false, kShowFrames, kShowFrames, false, false, -1) == kShowFrames);
    CHECK(offline_show(false, false, kShowFrames, kShowFrames, V, false, -1) == kShowOff);
    /* ... until F2 (or the pad's overlay button) is pressed there: the inputs, with the setting off and with
     * the training overlay Off (report 2026-11-11: F2 did nothing in offline Versus) */
    CHECK(versus_own_display(V, false, false, kShowFrames));
    CHECK(versus_own_display(V, false, false, kShowOff));
    CHECK(versus_switch_pressed(false, -1) == 1);
    CHECK(offline_show(false, false, kShowFrames, kShowFrames, V, false, 1) == kShowInputs);
    CHECK(offline_show(false, false, kShowOff, kShowOff, V, false, 1) == kShowInputs);
    CHECK(versus_switch_pressed(false, 1) == 0);
    CHECK(offline_show(false, false, kShowFrames, kShowFrames, V, false, 0) == kShowOff);
    CHECK(versus_switch_pressed(false, 0) == 1);
    /* with the setting on the first press switches it off, the next on again */
    CHECK(versus_switch_pressed(true, -1) == 0);
    CHECK(versus_switch_pressed(true, 0) == 1);
    CHECK(versus_switch_pressed(true, 1) == 0);
    /* F2's choice in Versus never reaches Practice or the other modes */
    CHECK(offline_show(P, false, kShowOff, kShowOff, false, false, 1) == kShowOff);
    CHECK(offline_show(false, false, kShowFrames, kShowFrames, false, false, 1) == kShowOff);
    /* the Versus setting: inputs, never frame data -- also with the training overlay Off */
    CHECK(offline_show(false, false, kShowFrames, kShowFrames, V, true, -1) == kShowInputs);
    CHECK(offline_show(false, false, kShowOff, kShowOff, V, true, -1) == kShowInputs);
    CHECK(offline_show(false, false, kShowInputs, kShowInputs, V, true, 1) == kShowInputs);
    /* F2 in Versus: off, on again */
    CHECK(offline_show(false, false, kShowOff, kShowOff, V, true, 0) == kShowOff);
    CHECK(offline_show(false, false, kShowOff, kShowOff, V, true, 1) == kShowInputs);
    /* it is Versus only: Arcade, Survival, ... stay off; Practice keeps the training setting */
    CHECK(offline_show(false, false, kShowOff, kShowOff, false, true, -1) == kShowOff);
    CHECK(offline_show(false, false, kShowFrames, kShowFrames, false, true, -1) == kShowOff);
    CHECK(offline_show(P, false, kShowOff, kShowOff, false, true, -1) == kShowOff);
    CHECK(offline_show(P, false, kShowInputs, kShowInputs, false, true, -1) == kShowInputs);
    /* "also in the other offline modes" already covers Versus: the training setting and its F2 rule there */
    CHECK(offline_show(false, true, kShowFrames, kShowFrames, V, true, -1) == kShowFrames);
    CHECK(offline_show(false, true, kShowFrames, kShowOff, V, true, -1) == kShowOff);
    CHECK(offline_show(false, true, kShowFrames, kShowFrames, V, false, -1) == kShowFrames);
    CHECK(!versus_own_display(V, true, true, kShowFrames));
    /* ... unless the training overlay is Off: then Versus has its own */
    CHECK(versus_own_display(V, true, true, kShowOff));
    CHECK(offline_show(false, true, kShowOff, kShowOff, V, true, -1) == kShowInputs);
    CHECK(versus_own_display(V, true, false, kShowFrames));
    CHECK(!versus_own_display(false, true, false, kShowFrames));
    CHECK(!versus_own_display(false, false, false, kShowFrames));
    CHECK(!versus_own_display(V, false, true, kShowFrames));
}

static uint16_t toggle(const std::string& s, bool* ok = nullptr) { return parse_overlay_toggle(s.data(), s.size(), ok); }

static void test_overlay_button()
{
    bool ok = false;
    /* default: R3, with no file text, no section, no line, an empty value */
    CHECK(kOverlayToggleDefault == kPadR3);
    CHECK(toggle("", &ok) == kPadR3 && ok);
    CHECK(toggle("[port1]\nR3 = B10\n[names]\nR3 = X\n") == kPadR3);
    CHECK(toggle("[overlay]\n") == kPadR3);
    CHECK(toggle("[overlay]\ntoggle =\n") == kPadR3);
    CHECK(toggle("[overlay]\ntoggle = ; nothing\n") == kPadR3);
    /* one button, any case, blanks, comments, CRLF */
    CHECK(toggle("[overlay]\ntoggle = L3\n") == kPadL3);
    CHECK(toggle("[Overlay]\r\n  Toggle = select   ; the Back button\r\n") == kPadSelect);
    CHECK(toggle("[overlay]\ntoggle=START # x\n") == kPadStart);
    CHECK(toggle("[overlay]\ntoggle = L1\n") == kPadL1 && toggle("[overlay]\ntoggle = R1\n") == kPadR1);
    CHECK(toggle("[overlay]\ntoggle = L2\n") == kPadL2 && toggle("[overlay]\ntoggle = R2\n") == kPadR2);
    /* held together */
    CHECK(toggle("[overlay]\ntoggle = SELECT+R3\n") == (kPadSelect | kPadR3));
    CHECK(toggle("[overlay]\ntoggle = l1 + r1 + start\n") == (kPadL1 | kPadR1 | kPadStart));
    /* off */
    for (const char* v : { "off", "OFF", "none", "no", "0" })
        CHECK(toggle(std::string("[overlay]\ntoggle = ") + v + "\n", &ok) == 0 && ok);
    /* an unknown name, an attack button, a direction: no button at all, and said so */
    for (const char* v : { "R4", "1", "CROSS", "LEFT", "R3+", "+R3", "R3+X", "R3 L3" }) {
        ok = true;
        CHECK(toggle(std::string("[overlay]\ntoggle = ") + v + "\n", &ok) == 0);
        CHECK(!ok);
    }
    /* the runtime's ini rules: the last line of a key counts, the first section of a name; other keys and
     * other sections' toggle lines are not ours */
    CHECK(toggle("[overlay]\ntoggle = L3\ntoggle = SELECT\n") == kPadSelect);
    CHECK(toggle("[overlay]\ntoggle = L3\n[overlay]\ntoggle = SELECT\n") == kPadL3);
    CHECK(toggle("[general]\ntoggle = L3\n[overlay]\nother = L1\n;toggle = L2\n") == kPadR3);
    CHECK(toggle("[overlay]\ntoggle = L3\n[port1]\ntoggle = SELECT\n") == kPadL3);
    /* held: every button of the combination, on either player's pad; never with no button */
    CHECK(overlay_toggle_held(kPadR3, kPadR3, 0) && overlay_toggle_held(kPadR3, 0, kPadR3 | 0x0040));
    CHECK(!overlay_toggle_held(kPadR3, kPadL3, 0x00F0));
    CHECK(!overlay_toggle_held(kPadSelect | kPadR3, kPadSelect, kPadR3));
    CHECK(overlay_toggle_held(kPadSelect | kPadR3, 0, kPadSelect | kPadR3 | kPadL1));
    CHECK(!overlay_toggle_held(0, 0xFFFF, 0xFFFF));
}

int main()
{
    test_defaults();
    test_targets();
    test_players();
    test_ini_rules();
    test_name_limits();
    test_pad_extras();
    test_width();
    test_who_sees_it();
    test_overlay_button();
    if (g_fail) { printf("%d of %d checks FAILED\n", g_fail, g_checks); return 1; }
    printf("PASS %d checks\n", g_checks);
    return 0;
}
