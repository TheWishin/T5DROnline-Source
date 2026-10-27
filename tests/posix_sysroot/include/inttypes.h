/* Declaration-only stand-in (tests/test_macos_port.py): names, types and the
 * macOS/glibc differences that matter follow the real headers. Not a libc. */
#pragma once
#include <stdint.h>
#define PRId32 "d"
#define PRIu32 "u"
#define PRIx32 "x"
#define PRIX32 "X"
#define PRId64 "lld"
#define PRIu64 "llu"
#define PRIx64 "llx"
#define PRIX64 "llX"
#define PRIuPTR "lu"
#define PRIxPTR "lx"
#ifdef __cplusplus
extern "C" {
#endif
intmax_t strtoimax(const char* s, char** end, int base);
uintmax_t strtoumax(const char* s, char** end, int base);
#ifdef __cplusplus
}
#endif
