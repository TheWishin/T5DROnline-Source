/* Declaration-only stand-in (tests/test_macos_port.py): names, types and the
 * macOS/glibc differences that matter follow the real headers. Not a libc. */
#pragma once
#ifdef __cplusplus
extern "C" {
#endif
int    backtrace(void** buf, int n);
char** backtrace_symbols(void* const* buf, int n);
void   backtrace_symbols_fd(void* const* buf, int n, int fd);
#ifdef __cplusplus
}
#endif
