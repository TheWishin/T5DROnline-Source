/* Declaration-only stand-in (tests/test_macos_port.py): names, types and the
 * macOS/glibc differences that matter follow the real headers. Not a libc. */
#pragma once
#include <stddef.h>
#include <stdarg.h>
#include <stdio.h>
#ifndef __cplusplus
typedef __WCHAR_TYPE__ wchar_t;
#endif
typedef int wint_t;
typedef struct { char __mbstate8[128]; long long _mbstateL; } mbstate_t;
#ifdef __cplusplus
extern "C" {
#endif
size_t   wcslen(const wchar_t* s);
wchar_t* wcscpy(wchar_t* d, const wchar_t* s);
wchar_t* wcsncpy(wchar_t* d, const wchar_t* s, size_t n);
int      wcscmp(const wchar_t* a, const wchar_t* b);
int      wcsncmp(const wchar_t* a, const wchar_t* b, size_t n);
wchar_t* wcschr(const wchar_t* s, wchar_t c);
int      swprintf(wchar_t* b, size_t n, const wchar_t* fmt, ...);
int      vswprintf(wchar_t* b, size_t n, const wchar_t* fmt, va_list ap);
size_t   mbrtowc(wchar_t* d, const char* s, size_t n, mbstate_t* st);
size_t   wcrtomb(char* d, wchar_t c, mbstate_t* st);
#ifdef __cplusplus
}
#endif
