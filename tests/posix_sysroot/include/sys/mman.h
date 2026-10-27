/* Declaration-only stand-in for <sys/mman.h>: tests/test_posix_syntax.py
 * syntax-checks src/platform's POSIX code (macOS arm64/x86-64, Linux x86-64)
 * on a PC with no POSIX headers. Names, types and the macOS/glibc differences
 * that matter here (st_mtimespec vs st_mtim, MAP_ANON, RTLD_NOLOAD values,
 * dladdr behind _GNU_SOURCE on glibc) follow the real headers; nothing else
 * does. Not a libc: never link against it. */
#pragma once
#include <sys/types.h>
#define PROT_NONE  0x0
#define PROT_READ  0x1
#define PROT_WRITE 0x2
#define PROT_EXEC  0x4
#define MAP_SHARED  0x0001
#define MAP_PRIVATE 0x0002
#define MAP_FIXED   0x0010
#if defined(__APPLE__)
#  define MAP_ANON      0x1000
#  define MAP_ANONYMOUS MAP_ANON
#  define MAP_NORESERVE 0x0040
#  define MAP_JIT       0x0800
#else
#  define MAP_ANONYMOUS 0x20
#  if defined(_GNU_SOURCE) || defined(_DEFAULT_SOURCE)
#    define MAP_ANON MAP_ANONYMOUS
#  endif
#  define MAP_NORESERVE 0x4000
#endif
#define MAP_FAILED ((void*)-1)
#ifdef __cplusplus
extern "C" {
#endif
void* mmap(void* addr, size_t len, int prot, int flags, int fd, off_t off);
int   munmap(void* addr, size_t len);
int   mprotect(void* addr, size_t len, int prot);
#ifdef __cplusplus
}
#endif
