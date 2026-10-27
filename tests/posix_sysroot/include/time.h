/* Declaration-only stand-in (tests/test_macos_port.py): names, types and the
 * macOS/glibc differences that matter follow the real headers. Not a libc. */
#pragma once
#include <sys/types.h>
struct timespec { time_t tv_sec; long tv_nsec; };
#if defined(__APPLE__)
struct tm { int tm_sec, tm_min, tm_hour, tm_mday, tm_mon, tm_year, tm_wday, tm_yday, tm_isdst; long tm_gmtoff; char* tm_zone; };
#  define CLOCK_REALTIME           0
#  define CLOCK_MONOTONIC          6
#  define CLOCK_MONOTONIC_RAW      4
#  define CLOCK_UPTIME_RAW         8
#  define CLOCK_PROCESS_CPUTIME_ID 12
#  define CLOCK_THREAD_CPUTIME_ID  16
#  define CLOCKS_PER_SEC 1000000
#else
struct tm { int tm_sec, tm_min, tm_hour, tm_mday, tm_mon, tm_year, tm_wday, tm_yday, tm_isdst; long tm_gmtoff; const char* tm_zone; };
#  define CLOCK_REALTIME           0
#  define CLOCK_MONOTONIC          1
#  define CLOCK_PROCESS_CPUTIME_ID 2
#  define CLOCK_THREAD_CPUTIME_ID  3
#  define CLOCK_MONOTONIC_RAW      4
#  define CLOCKS_PER_SEC 1000000l
#endif
#define TIME_UTC 1
typedef unsigned long clock_t;
#ifdef __cplusplus
extern "C" {
#endif
int    clock_gettime(clockid_t clk, struct timespec* ts);
int    clock_getres(clockid_t clk, struct timespec* ts);
int    nanosleep(const struct timespec* req, struct timespec* rem);
int    timespec_get(struct timespec* ts, int base);
time_t time(time_t* t);
clock_t clock(void);
double difftime(time_t a, time_t b);
time_t mktime(struct tm* t);
struct tm* localtime(const time_t* t);
struct tm* gmtime(const time_t* t);
struct tm* localtime_r(const time_t* t, struct tm* out);
struct tm* gmtime_r(const time_t* t, struct tm* out);
size_t strftime(char* b, size_t n, const char* fmt, const struct tm* t);
char*  ctime(const time_t* t);
char*  asctime(const struct tm* t);
#if defined(__APPLE__)
__UINT64_TYPE__ clock_gettime_nsec_np(clockid_t clk);
#endif
#ifdef __cplusplus
}
#endif
