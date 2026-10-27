/* Declaration-only stand-in for <dlfcn.h>: tests/test_posix_syntax.py
 * syntax-checks src/platform's POSIX code (macOS arm64/x86-64, Linux x86-64)
 * on a PC with no POSIX headers. Names, types and the macOS/glibc differences
 * that matter here (st_mtimespec vs st_mtim, MAP_ANON, RTLD_NOLOAD values,
 * dladdr behind _GNU_SOURCE on glibc) follow the real headers; nothing else
 * does. Not a libc: never link against it. */
#pragma once
#if defined(__APPLE__)
#  define RTLD_LAZY    0x1
#  define RTLD_NOW     0x2
#  define RTLD_LOCAL   0x4
#  define RTLD_GLOBAL  0x8
#  define RTLD_NOLOAD  0x10
#  define RTLD_DEFAULT ((void*)-2)
#  define T5_SYSROOT_HAVE_DLADDR 1
#else
#  define RTLD_LAZY    0x00001
#  define RTLD_NOW     0x00002
#  define RTLD_NOLOAD  0x00004
#  define RTLD_GLOBAL  0x00100
#  define RTLD_LOCAL   0
#  if defined(_GNU_SOURCE)
#    define RTLD_DEFAULT ((void*)0)
#    define T5_SYSROOT_HAVE_DLADDR 1
#  endif
#endif
#ifdef __cplusplus
extern "C" {
#endif
void* dlopen(const char* path, int mode);
void* dlsym(void* handle, const char* name);
int   dlclose(void* handle);
char* dlerror(void);
#ifdef T5_SYSROOT_HAVE_DLADDR
typedef struct {
    const char* dli_fname;
    void*       dli_fbase;
    const char* dli_sname;
    void*       dli_saddr;
} Dl_info;
int dladdr(const void* addr, Dl_info* info);
#endif
#ifdef __cplusplus
}
#endif
