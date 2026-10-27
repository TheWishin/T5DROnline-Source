/* The Win32 surface src/ is written against, on every host (docs/MACOS.md).
 *
 * Windows: exactly <windows.h>, as every file here included it before. The
 * file's own WIN32_LEAN_AND_MEAN / NOMINMAX defines stay where they were, in
 * front of this include, so the Windows build preprocesses the same.
 *
 * Elsewhere (macOS, Linux): ps3recomp's POSIX shim for the part of Win32 the
 * runtime itself uses -- QueryPerformanceCounter, Sleep, GetTickCount64,
 * CRITICAL_SECTION, SRWLOCK, events, CreateThread, VirtualAlloc/Protect/Query,
 * vectored exception handlers (runtime/platform/win32_compat.h) -- plus the
 * MSVC CRT names (_stricmp, _byteswap_*, _putenv_s: msvc_compat.h) and
 * RtlCaptureStackBackTrace / GetModuleHandleA over backtrace(3) and dladdr
 * (win32_backtrace.h). CMake adds runtime/platform to the include path, and
 * _GNU_SOURCE, on those hosts only.
 *
 * What neither covers -- the write watch, code patching, file replace, the
 * process exit -- goes through t5_plat.h, which comes with this header.
 * Sockets: t5_sock.h (netplay_core.cpp only). */
#pragma once

#if defined(_WIN32)
#  include <windows.h>
#else
#  include "win32_compat.h"
#  include "msvc_compat.h"
#  include "win32_backtrace.h"
#endif

#include "t5_plat.h"
