/* Declaration-only stand-in (tests/test_macos_port.py): names, types and the
 * macOS/glibc differences that matter follow the real headers. Not a libc. */
#pragma once
#if defined(__APPLE__)
#  define SYS_exit    1
#  define SYS_getpid  20
#else
#  define SYS_gettid  186
#  define SYS_futex   202
#endif
