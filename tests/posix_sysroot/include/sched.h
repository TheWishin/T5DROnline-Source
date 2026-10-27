/* Declaration-only stand-in (tests/test_macos_port.py): names, types and the
 * macOS/glibc differences that matter follow the real headers. Not a libc. */
#pragma once
#include <sys/types.h>
#if defined(__APPLE__)
struct sched_param { int sched_priority; char __opaque[4]; };
#  define SCHED_OTHER 1
#  define SCHED_FIFO  4
#  define SCHED_RR    2
#else
struct sched_param { int sched_priority; };
#  define SCHED_OTHER 0
#  define SCHED_FIFO  1
#  define SCHED_RR    2
#endif
#ifdef __cplusplus
extern "C" {
#endif
int sched_yield(void);
int sched_get_priority_min(int policy);
int sched_get_priority_max(int policy);
#ifdef __cplusplus
}
#endif
