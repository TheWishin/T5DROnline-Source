/* Declaration-only stand-in for <sys/types.h>: tests/test_posix_syntax.py
 * syntax-checks src/platform's POSIX code (macOS arm64/x86-64, Linux x86-64)
 * on a PC with no POSIX headers. Names, types and the macOS/glibc differences
 * that matter here (st_mtimespec vs st_mtim, MAP_ANON, RTLD_NOLOAD values,
 * dladdr behind _GNU_SOURCE on glibc) follow the real headers; nothing else
 * does. Not a libc: never link against it. */
#pragma once
#include <stddef.h>
#include <stdint.h>
typedef long          ssize_t;
typedef long long     off_t;
typedef int           pid_t;
typedef unsigned int  uid_t;
typedef unsigned int  gid_t;
#if defined(__APPLE__)
typedef unsigned short mode_t;
typedef int           suseconds_t;
#else
typedef unsigned int  mode_t;
typedef long          suseconds_t;
#endif
typedef long          time_t;
typedef int           clockid_t;
typedef unsigned int  useconds_t;
typedef unsigned char  u_char;
typedef unsigned short u_short;
typedef unsigned int   u_int;
typedef unsigned long  u_long;
