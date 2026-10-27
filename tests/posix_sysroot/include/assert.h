/* Declaration-only stand-in (tests/test_macos_port.py): names, types and the
 * macOS/glibc differences that matter follow the real headers. Not a libc. */
#ifdef NDEBUG
#  define assert(e) ((void)0)
#else
#  define assert(e) ((e) ? (void)0 : __builtin_trap())
#endif
#ifndef __cplusplus
#  define static_assert _Static_assert
#endif
