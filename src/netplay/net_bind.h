/*
 * Which local address the netplay UDP socket binds (docs/NETPLAY.md "Bind address").
 *
 * Windows Firewall asks "allow public and private networks to access this app?" once per exe
 * path when a program binds a non-loopback address; loopback is never filtered. Test runs
 * start t5dr.exe from many build folders with both games on 127.0.0.1, so they bind
 * 127.0.0.1; a player's game keeps binding every interface.
 *
 *   T5_NET_BIND=<IPv4>   bind exactly this address (tests: 127.0.0.1; 0.0.0.0 = every interface).
 *                        Anything that is not a dotted IPv4 address is noted in the log and
 *                        ignored: every interface.
 *   unset                127.0.0.1 when T5_NET_PEER's host is a loopback address (127.x.x.x or
 *                        "localhost") and this is not a lobby match (T5_NET_MATCH unset);
 *                        otherwise every interface, as before. A lobby match keeps every
 *                        interface even with a loopback peer: the launcher's relay bridge hands
 *                        real players T5_NET_PEER=127.0.0.1:<port> (lobby/t5lobby/nat.py
 *                        RelayBridge), and a player's game must not change; local lobby tests
 *                        set T5_NET_BIND themselves.
 *
 * Pure functions, no Winsock: tests/c/net_bind_test.cpp checks them (tests/test_net_bind.py).
 */
#pragma once

#include <cstdint>
#include <cstdio>
#include <cstring>

namespace np {

struct BindChoice {
    uint32_t addr;        /* host byte order: 0 = every interface (INADDR_ANY), 0x7F000001 = 127.0.0.1 */
    const char* why;      /* for the log line */
    bool bad_value;       /* T5_NET_BIND was given but is not an IPv4 address (logged, every interface used) */
};

/* Strict dotted quad: four decimal parts 0..255, nothing else (no spaces, no port, no hex, no leading
 * zeros -- the launcher's Python check, ipaddress.IPv4Address, refuses those too). */
inline bool parse_ipv4(const char* s, uint32_t* out)
{
    if (!s) return false;
    uint32_t v = 0;
    for (int part = 0; part < 4; part++) {
        if (part && *s++ != '.') return false;
        if (*s < '0' || *s > '9') return false;
        if (s[0] == '0' && s[1] >= '0' && s[1] <= '9') return false;
        unsigned n = 0;
        int digits = 0;
        while (*s >= '0' && *s <= '9') {
            n = n * 10 + (unsigned)(*s++ - '0');
            if (++digits > 3 || n > 255) return false;
        }
        v = (v << 8) | n;
    }
    if (*s) return false;
    *out = v;
    return true;
}

/* T5_NET_PEER ("host:port") names this PC's loopback: 127.x.x.x or localhost. */
inline bool peer_is_loopback(const char* peer)
{
    if (!peer || !*peer) return false;
    const char* colon = strrchr(peer, ':');
    size_t n = colon ? (size_t)(colon - peer) : strlen(peer);
    char host[64];
    if (n == 0 || n >= sizeof host) return false;
    memcpy(host, peer, n);
    host[n] = 0;
    uint32_t a;
    if (parse_ipv4(host, &a)) return (a >> 24) == 127;
    static const char kLocal[] = "localhost";
    if (n != sizeof kLocal - 1) return false;
    for (size_t i = 0; i < n; i++) {
        char c = host[i];
        if (c >= 'A' && c <= 'Z') c = (char)(c - 'A' + 'a');
        if (c != kLocal[i]) return false;
    }
    return true;
}

/* bind_env = T5_NET_BIND, peer_env = T5_NET_PEER, match_env = T5_NET_MATCH (nullptr or "" = unset). */
inline BindChoice choose_bind(const char* bind_env, const char* peer_env, const char* match_env)
{
    if (bind_env && *bind_env) {
        uint32_t a;
        if (parse_ipv4(bind_env, &a)) return {a, "T5_NET_BIND", false};
        return {0, "T5_NET_BIND is not an IPv4 address", true};
    }
    const bool lobby = match_env && *match_env;
    if (!lobby && peer_is_loopback(peer_env)) return {0x7F000001u, "loopback peer", false};
    return {0, "default", false};
}

inline void format_ipv4(uint32_t a, char* buf, size_t n)
{
    snprintf(buf, n, "%u.%u.%u.%u", (unsigned)(a >> 24), (unsigned)(a >> 16) & 255, (unsigned)(a >> 8) & 255,
             (unsigned)a & 255);
}

}  // namespace np
