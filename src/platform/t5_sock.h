/* UDP sockets for the netplay transport: Winsock on Windows, BSD sockets on
 * macOS and Linux (docs/MACOS.md). Header only; the Windows half is the exact
 * calls netplay_core.cpp made before.
 *
 * Include it before t5_win.h (Winsock must come before <windows.h>). */
#pragma once

#if defined(_WIN32)
#  include <winsock2.h>
#  include <ws2tcpip.h>
#else
#  include <sys/types.h>
#  include <sys/socket.h>
#  include <sys/time.h>
#  include <netinet/in.h>
#  include <arpa/inet.h>
#  include <netdb.h>
#  include <unistd.h>
#  include <errno.h>
#endif

#ifdef __cplusplus
extern "C" {
#endif

#if defined(_WIN32)
typedef SOCKET t5s_socket;
typedef int    t5s_socklen;
#  define T5S_INVALID INVALID_SOCKET
#  define T5S_ERROR   SOCKET_ERROR

/* Once per process before the first socket; 1 = ready. */
static inline int t5s_startup(void) { WSADATA wsa; return WSAStartup(MAKEWORD(2, 2), &wsa) == 0; }
static inline int t5s_last_error(void) { return WSAGetLastError(); }
static inline void t5s_close(t5s_socket s) { closesocket(s); }
/* A blocking recvfrom returns after `ms` with a timeout error. */
static inline void t5s_set_recv_timeout(t5s_socket s, unsigned ms)
{
    DWORD tmo = ms;
    setsockopt(s, SOL_SOCKET, SO_RCVTIMEO, (const char*)&tmo, sizeof tmo);
}
/* An ICMP "port unreachable" from an earlier send must not make the next
 * recvfrom fail with WSAECONNRESET (Windows only: SIO_UDP_CONNRESET). */
static inline void t5s_no_connreset(t5s_socket s)
{
    BOOL off = FALSE; DWORD ret = 0;
    WSAIoctl(s, _WSAIOW(IOC_VENDOR, 12) /* SIO_UDP_CONNRESET */, &off, sizeof off, NULL, 0, &ret, NULL, NULL);
}
/* recvfrom errors that only mean "nothing this time": the receive timeout, an
 * ICMP reset, a datagram larger than the buffer. */
static inline int t5s_error_is_transient(int e) { return e == WSAETIMEDOUT || e == WSAECONNRESET || e == WSAEMSGSIZE; }

#else
typedef int       t5s_socket;
typedef socklen_t t5s_socklen;
#  define T5S_INVALID (-1)
#  define T5S_ERROR   (-1)

static inline int t5s_startup(void) { return 1; }
static inline int t5s_last_error(void) { return errno; }
static inline void t5s_close(t5s_socket s) { close(s); }
static inline void t5s_set_recv_timeout(t5s_socket s, unsigned ms)
{
    struct timeval tv;
    tv.tv_sec = (time_t)(ms / 1000u);
    tv.tv_usec = (suseconds_t)((ms % 1000u) * 1000u);
    setsockopt(s, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof tv);
}
/* BSD sockets never report an ICMP error on an unconnected UDP socket. */
static inline void t5s_no_connreset(t5s_socket s) { (void)s; }
/* A receive timeout is EAGAIN/EWOULDBLOCK here, EINTR a signal that
 * interrupted the wait. */
static inline int t5s_error_is_transient(int e)
{
    return e == EAGAIN || e == EWOULDBLOCK || e == EINTR || e == ECONNREFUSED || e == EMSGSIZE;
}
#endif

#ifdef __cplusplus
}
#endif
