/* Declaration-only stand-in for <libkern/OSCacheControl.h>: tests/test_posix_syntax.py
 * syntax-checks src/platform's POSIX code (macOS arm64/x86-64, Linux x86-64)
 * on a PC with no POSIX headers. Names, types and the macOS/glibc differences
 * that matter here (st_mtimespec vs st_mtim, MAP_ANON, RTLD_NOLOAD values,
 * dladdr behind _GNU_SOURCE on glibc) follow the real headers; nothing else
 * does. Not a libc: never link against it. */
#pragma once
#if !defined(__APPLE__)
#  error "<libkern/OSCacheControl.h> exists on Apple platforms only"
#endif
#include <stddef.h>
#ifdef __cplusplus
extern "C" {
#endif
void sys_icache_invalidate(void* start, size_t len);
void sys_dcache_flush(void* start, size_t len);
#ifdef __cplusplus
}
#endif
