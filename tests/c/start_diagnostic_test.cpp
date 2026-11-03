/* The Python test extracts the actual pad_into implementation from the core.
 * These are fake mapped pad samples, not game/controller data. */
#include <atomic>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstdarg>
#include <string>
#include <vector>

static constexpr uint16_t B_START = 0x0008;
struct HostPadData { int len = 0; uint16_t button[8] = {}; };
struct PadInput { uint16_t buttons = 0; uint8_t lx = 128, ly = 128, rx = 128, ry = 128; };
static std::vector<std::string> messages;
static void note_(const char* fmt, ...)
{
    char buf[1024];
    va_list ap; va_start(ap, fmt); vsnprintf(buf, sizeof buf, fmt, ap); va_end(ap);
    messages.emplace_back(buf);
}

#include "pad_into_under_test.h"

#define CHECK(test) do { if (!(test)) { fprintf(stderr, "FAIL line %d: %s\n", __LINE__, #test); return 1; } } while (0)
int main()
{
    HostPadData d;
    PadInput out;
    d.button[2] = B_START;
    g_no_start = true;
    pad_into(d, &out);
    CHECK(messages.empty() && out.buttons == 0);  // no valid packet

    d.len = 8;
    d.button[2] = B_START | 0x0040;
    d.button[3] = 0x0080;
    d.button[4] = 17; d.button[5] = 23; d.button[6] = 31; d.button[7] = 47;
    out.buttons = 0x0100;
    pad_into(d, &out);
    CHECK(out.buttons == (0x0040 | 0x8000 | 0x0100));
    CHECK(out.rx == 17 && out.ry == 23 && out.lx == 31 && out.ly == 47);
    CHECK(d.button[2] == (B_START | 0x0040));       // never alter the device sample
    CHECK(messages.size() == 1);
    CHECK(messages[0].find("START received from mapped local input") != std::string::npos);
    CHECK(messages[0].find("blocked by no-pause online before sending") != std::string::npos);

    for (int i = 0; i < 10000; ++i) { out = {}; pad_into(d, &out); CHECK(!(out.buttons & B_START)); }
    CHECK(messages.size() == 1);                 // a held button does not flood logs

    g_no_start = false;
    out = {};
    pad_into(d, &out);
    CHECK(out.buttons == (B_START | 0x0040 | 0x8000));
    CHECK(messages.size() == 2);
    CHECK(messages[1].find("passed by the local START gate") != std::string::npos);
    CHECK(messages[1].find("online skips still require both players") != std::string::npos);
    for (int i = 0; i < 10000; ++i) { out = {}; pad_into(d, &out); CHECK(out.buttons & B_START); }
    g_no_start = true;
    out = {}; pad_into(d, &out);
    CHECK(!(out.buttons & B_START) && messages.size() == 2);
    d.button[2] = 0x0040;
    out = {}; pad_into(d, &out);
    CHECK(out.buttons == (0x0040 | 0x8000) && messages.size() == 2);
    puts("PASS mapped START diagnostics and unchanged inputs");
    return 0;
}
