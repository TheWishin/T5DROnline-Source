/* Declaration-only stand-in for <sys/socket.h>: tests/test_posix_syntax.py
 * syntax-checks src/platform's POSIX code (macOS arm64/x86-64, Linux x86-64)
 * on a PC with no POSIX headers. Names, types and the macOS/glibc differences
 * that matter here (st_mtimespec vs st_mtim, MAP_ANON, RTLD_NOLOAD values,
 * dladdr behind _GNU_SOURCE on glibc) follow the real headers; nothing else
 * does. Not a libc: never link against it. */
#pragma once
#include <sys/types.h>
typedef unsigned int  socklen_t;
typedef unsigned char sa_family_t_byte;
#if defined(__APPLE__)
typedef unsigned char sa_family_t;
struct sockaddr { unsigned char sa_len; sa_family_t sa_family; char sa_data[14]; };
#  define SOL_SOCKET  0xffff
#  define SO_RCVTIMEO 0x1006
#  define SO_REUSEADDR 0x0004
#else
typedef unsigned short sa_family_t;
struct sockaddr { sa_family_t sa_family; char sa_data[14]; };
#  define SOL_SOCKET  1
#  define SO_RCVTIMEO 20
#  define SO_REUSEADDR 2
#endif
#define AF_UNSPEC  0
#define AF_INET    2
#if defined(__APPLE__)
#  define AF_INET6 30
#  define SO_SNDTIMEO 0x1005
#  define SO_SNDBUF 0x1001
#  define SO_RCVBUF 0x1002
#  define SO_BROADCAST 0x0020
#  define SO_NOSIGPIPE 0x1022
#  define MSG_DONTWAIT 0x80
#else
#  define AF_INET6 10
#  define SO_SNDTIMEO 21
#  define SO_SNDBUF 7
#  define SO_RCVBUF 8
#  define SO_BROADCAST 6
#  define MSG_DONTWAIT 0x40
#endif
#define SHUT_RDWR 2
#define SOCK_STREAM 1
#define SOCK_DGRAM  2
#ifdef __cplusplus
extern "C" {
#endif
int     socket(int domain, int type, int protocol);
int     bind(int fd, const struct sockaddr* addr, socklen_t len);
int     setsockopt(int fd, int level, int name, const void* val, socklen_t len);
ssize_t sendto(int fd, const void* buf, size_t n, int flags, const struct sockaddr* to, socklen_t tolen);
ssize_t recvfrom(int fd, void* buf, size_t n, int flags, struct sockaddr* from, socklen_t* fromlen);
ssize_t send(int fd, const void* buf, size_t n, int flags);
ssize_t recv(int fd, void* buf, size_t n, int flags);
int     connect(int fd, const struct sockaddr* addr, socklen_t len);
int     listen(int fd, int backlog);
int     accept(int fd, struct sockaddr* addr, socklen_t* len);
int     shutdown(int fd, int how);
int     getsockname(int fd, struct sockaddr* addr, socklen_t* len);
int     getpeername(int fd, struct sockaddr* addr, socklen_t* len);
int     getsockopt(int fd, int level, int name, void* val, socklen_t* len);
#ifdef __cplusplus
}
#endif
