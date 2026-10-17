/* The runtime is built for x86-64 with SSE4.1 (ps3recomp compiles its C with
 * -msse4.1: the SPU shuffle/blend ops of the sound core). A processor without
 * it -- before Intel Core 2 "Penryn" (2008), AMD before Bulldozer/Jaguar
 * (Phenom II, Athlon II) -- would die on the first such instruction with no
 * word. This check runs before main() and every static constructor
 * (.CRT$XCB) and says so instead (exit code 14). Everything above SSE4.1 in
 * t5dr.exe sits in the Microsoft C library behind its own CPUID dispatch; the
 * game DLL is checked against its build target when it is loaded (patch 0031).
 * T5DR_TEST_CPU=nosse41 takes the failure path on any PC (tests). */
#include <windows.h>
#include <intrin.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static void t5dr_cpu_check(void)
{
    int r[4] = {0, 0, 0, 0};
    __cpuid(r, 0);
    int ok = 0;
    if (r[0] >= 1) {
        __cpuid(r, 1);
        ok = (r[2] & (1 << 19)) != 0;                 /* CPUID.1:ECX.SSE4_1 */
    }
    const char* t = getenv("T5DR_TEST_CPU");
    if (t && strstr(t, "nosse41")) ok = 0;
    if (ok) return;
    fprintf(stderr, "[cpu] FATAL (exit code 14): this processor lacks SSE4.1, which T5DR Online needs\n");
    fflush(stderr);
    if (!getenv("PS3_WINDOW_BACKGROUND") && !getenv("PS3_NO_DIALOGS"))
        MessageBoxW(NULL,
                    L"This processor is too old for T5DR Online: it lacks the SSE4.1 instructions.\n\n"
                    L"Processors from about 2008 on have them (Intel Core 2 Duo E8000/Q9000 and newer, "
                    L"AMD FX, A-series, Ryzen and newer).",
                    L"T5DR Online - processor not supported", MB_OK | MB_ICONERROR | MB_SETFOREGROUND);
    ExitProcess(14);
}

typedef void (*t5dr_initfn)(void);
#pragma section(".CRT$XCB", read)
extern "C" __declspec(allocate(".CRT$XCB")) __attribute__((used)) const t5dr_initfn t5dr_cpu_check_init = t5dr_cpu_check;
