/* Declaration-only stand-in (tests/test_macos_port.py): names, types and the
 * macOS/glibc differences that matter follow the real headers. Not a libc. */
#pragma once
#include <stddef.h>
#ifdef __cplusplus
extern "C" {
#endif
int sysctlbyname(const char* name, void* old, size_t* oldlen, void* newp, size_t newlen);
#ifdef __cplusplus
}
#endif
