/* Declaration-only stand-in (tests/test_macos_port.py): names, types and the
 * macOS/glibc differences that matter follow the real headers. Not a libc. */
#pragma once
#ifdef __cplusplus
extern "C" {
#endif
#if defined(__APPLE__)
extern int* __error(void);
#  define errno (*__error())
#  define EDEADLK 11
#  define EAGAIN 35
#  define EINPROGRESS 36
#  define EALREADY 37
#  define ENOTSOCK 38
#  define EMSGSIZE 40
#  define ENOTSUP 45
#  define EADDRINUSE 48
#  define EADDRNOTAVAIL 49
#  define ENETDOWN 50
#  define ENETUNREACH 51
#  define ECONNABORTED 53
#  define ECONNRESET 54
#  define ENOBUFS 55
#  define EISCONN 56
#  define ENOTCONN 57
#  define ETIMEDOUT 60
#  define ECONNREFUSED 61
#  define ENAMETOOLONG 63
#  define EHOSTUNREACH 65
#  define ENOTEMPTY 66
#  define ENOSYS 78
#  define EOVERFLOW 84
#  define ECANCELED 89
#  define EOPNOTSUPP 102
#else
extern int* __errno_location(void);
#  define errno (*__errno_location())
#  define EDEADLK 35
#  define EAGAIN 11
#  define EINPROGRESS 115
#  define EALREADY 114
#  define ENOTSOCK 88
#  define EMSGSIZE 90
#  define ENOTSUP 95
#  define EADDRINUSE 98
#  define EADDRNOTAVAIL 99
#  define ENETDOWN 100
#  define ENETUNREACH 101
#  define ECONNABORTED 103
#  define ECONNRESET 104
#  define ENOBUFS 105
#  define EISCONN 106
#  define ENOTCONN 107
#  define ETIMEDOUT 110
#  define ECONNREFUSED 111
#  define ENAMETOOLONG 36
#  define EHOSTUNREACH 113
#  define ENOTEMPTY 39
#  define ENOSYS 38
#  define EOVERFLOW 75
#  define ECANCELED 125
#  define EOPNOTSUPP 95
#endif
#define EWOULDBLOCK EAGAIN
#define EPERM 1
#define ENOENT 2
#define ESRCH 3
#define EINTR 4
#define EIO 5
#define ENXIO 6
#define E2BIG 7
#define ENOEXEC 8
#define EBADF 9
#define ECHILD 10
#define ENOMEM 12
#define EACCES 13
#define EFAULT 14
#define EBUSY 16
#define EEXIST 17
#define EXDEV 18
#define ENODEV 19
#define ENOTDIR 20
#define EISDIR 21
#define EINVAL 22
#define ENFILE 23
#define EMFILE 24
#define ENOTTY 25
#define EFBIG 27
#define ENOSPC 28
#define ESPIPE 29
#define EROFS 30
#define EMLINK 31
#define EPIPE 32
#define EDOM 33
#define ERANGE 34
#ifdef __cplusplus
}
#endif
