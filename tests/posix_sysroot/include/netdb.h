/* Declaration-only stand-in for <netdb.h>: tests/test_posix_syntax.py
 * syntax-checks src/platform's POSIX code (macOS arm64/x86-64, Linux x86-64)
 * on a PC with no POSIX headers. Names, types and the macOS/glibc differences
 * that matter here (st_mtimespec vs st_mtim, MAP_ANON, RTLD_NOLOAD values,
 * dladdr behind _GNU_SOURCE on glibc) follow the real headers; nothing else
 * does. Not a libc: never link against it. */
#pragma once
#include <sys/socket.h>
struct addrinfo {
    int ai_flags, ai_family, ai_socktype, ai_protocol;
    socklen_t ai_addrlen;
#if defined(__APPLE__)
    char* ai_canonname;
    struct sockaddr* ai_addr;
#else
    struct sockaddr* ai_addr;
    char* ai_canonname;
#endif
    struct addrinfo* ai_next;
};
#ifdef __cplusplus
extern "C" {
#endif
int  getaddrinfo(const char* node, const char* service, const struct addrinfo* hints, struct addrinfo** res);
void freeaddrinfo(struct addrinfo* res);
#ifdef __cplusplus
}
#endif
