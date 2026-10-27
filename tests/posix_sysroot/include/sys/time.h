/* Declaration-only stand-in (tests/test_macos_port.py): names, types and the
 * macOS/glibc differences that matter follow the real headers. Not a libc. */
#pragma once
#include <sys/types.h>
#include <time.h>
struct timeval { time_t tv_sec; suseconds_t tv_usec; };
#ifdef __cplusplus
extern "C" {
#endif
int gettimeofday(struct timeval* tv, void* tz);
#ifdef __cplusplus
}
#endif
