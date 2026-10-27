/* Declaration-only stand-in (tests/test_macos_port.py): names, types and the
 * macOS/glibc differences that matter follow the real headers. Not a libc. */
#pragma once
#include <stdint.h>
typedef struct mach_timebase_info { uint32_t numer; uint32_t denom; } mach_timebase_info_data_t, *mach_timebase_info_t;
#ifdef __cplusplus
extern "C" {
#endif
uint64_t mach_absolute_time(void);
uint64_t mach_continuous_time(void);
int      mach_timebase_info(mach_timebase_info_t info);
int      mach_wait_until(uint64_t deadline);
#ifdef __cplusplus
}
#endif
