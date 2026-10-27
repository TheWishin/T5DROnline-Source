/* Declaration-only stand-in for <fcntl.h>: tests/test_posix_syntax.py
 * syntax-checks src/platform's POSIX code (macOS arm64/x86-64, Linux x86-64)
 * on a PC with no POSIX headers. Names, types and the macOS/glibc differences
 * that matter here (st_mtimespec vs st_mtim, MAP_ANON, RTLD_NOLOAD values,
 * dladdr behind _GNU_SOURCE on glibc) follow the real headers; nothing else
 * does. Not a libc: never link against it. */
#pragma once
#include <sys/types.h>
#if defined(__APPLE__)
#  define O_RDONLY  0x0000
#  define O_WRONLY  0x0001
#  define O_RDWR    0x0002
#  define O_CREAT   0x0200
#  define O_TRUNC   0x0400
#  define O_CLOEXEC 0x01000000
#  define O_APPEND  0x0008
#  define O_EXCL    0x0800
#  define O_NONBLOCK 0x0004
#else
#  define O_RDONLY  00
#  define O_WRONLY  01
#  define O_RDWR    02
#  define O_CREAT   0100
#  define O_TRUNC   01000
#  define O_CLOEXEC 02000000
#  define O_APPEND  02000
#  define O_EXCL    0200
#  define O_NONBLOCK 04000
#endif
#ifdef __cplusplus
extern "C" {
#endif
int open(const char* path, int flags, ...);
#ifdef __cplusplus
}
#endif
