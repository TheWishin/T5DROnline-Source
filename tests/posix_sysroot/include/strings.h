/* Declaration-only stand-in (tests/test_macos_port.py): names, types and the
 * macOS/glibc differences that matter follow the real headers. Not a libc. */
#pragma once
#include <stddef.h>
#ifdef __cplusplus
extern "C" {
#endif
int  strcasecmp(const char* a, const char* b);
int  strncasecmp(const char* a, const char* b, size_t n);
void bzero(void* p, size_t n);
int  ffs(int v);
#ifdef __cplusplus
}
#endif
