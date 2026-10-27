/* Declaration-only stand-in for <netinet/in.h>: tests/test_posix_syntax.py
 * syntax-checks src/platform's POSIX code (macOS arm64/x86-64, Linux x86-64)
 * on a PC with no POSIX headers. Names, types and the macOS/glibc differences
 * that matter here (st_mtimespec vs st_mtim, MAP_ANON, RTLD_NOLOAD values,
 * dladdr behind _GNU_SOURCE on glibc) follow the real headers; nothing else
 * does. Not a libc: never link against it. */
#pragma once
#include <sys/socket.h>
#include <stdint.h>
typedef uint32_t in_addr_t;
typedef uint16_t in_port_t;
struct in_addr { in_addr_t s_addr; };
#if defined(__APPLE__)
struct sockaddr_in { unsigned char sin_len; sa_family_t sin_family; in_port_t sin_port; struct in_addr sin_addr; char sin_zero[8]; };
#else
struct sockaddr_in { sa_family_t sin_family; in_port_t sin_port; struct in_addr sin_addr; unsigned char sin_zero[8]; };
#endif
#define IPPROTO_UDP 17
#define INADDR_ANY  ((in_addr_t)0x00000000)
#define INADDR_LOOPBACK ((in_addr_t)0x7f000001)
#define INADDR_BROADCAST ((in_addr_t)0xffffffff)
#define INADDR_NONE ((in_addr_t)0xffffffff)
#define IPPROTO_IP  0
#define IPPROTO_TCP 6
#ifdef __cplusplus
extern "C" {
#endif
uint16_t htons(uint16_t v);
uint32_t htonl(uint32_t v);
uint16_t ntohs(uint16_t v);
uint32_t ntohl(uint32_t v);
#ifdef __cplusplus
}
#endif
