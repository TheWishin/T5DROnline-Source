/* The netplay socket's bind address rule (src/netplay/net_bind.h); run by tests/test_net_bind.py.
 * Prints "PASS" and exits 0 when every case holds. */
#include <cstdio>
#include <cstring>

#include "net_bind.h"

static int g_fail = 0;

static void expect(const char* bind, const char* peer, const char* match, unsigned want, bool want_bad)
{
    const np::BindChoice c = np::choose_bind(bind, peer, match);
    char got[16], exp[16];
    np::format_ipv4(c.addr, got, sizeof got);
    np::format_ipv4(want, exp, sizeof exp);
    if (c.addr != want || c.bad_value != want_bad) {
        printf("FAIL bind=%s peer=%s match=%s: got %s (%s, bad=%d), want %s (bad=%d)\n", bind ? bind : "(unset)",
               peer ? peer : "(unset)", match ? match : "(unset)", got, c.why, c.bad_value, exp, want_bad);
        g_fail++;
    } else {
        printf("CASE bind=%s peer=%s match=%s -> %s (%s)\n", bind ? bind : "(unset)", peer ? peer : "(unset)",
               match ? match : "(unset)", got, c.why);
    }
}

int main(int argc, char** argv)
{
    /* net_bind_test <T5_NET_BIND> <T5_NET_PEER> <T5_NET_MATCH> ("-" = unset): prints "BIND <ip> <why>". */
    if (argc == 4) {
        auto arg = [](const char* a) -> const char* { return strcmp(a, "-") ? a : nullptr; };
        const np::BindChoice c = np::choose_bind(arg(argv[1]), arg(argv[2]), arg(argv[3]));
        char ip[16];
        np::format_ipv4(c.addr, ip, sizeof ip);
        printf("BIND %s %s\n", ip, c.why);
        return 0;
    }
    const unsigned ANY = 0, LO = 0x7F000001u;

    /* Explicit T5_NET_BIND wins over everything. */
    expect("127.0.0.1", nullptr, nullptr, LO, false);                      /* test host, no peer */
    expect("127.0.0.1", "127.0.0.1:7000", nullptr, LO, false);             /* test joiner */
    expect("127.0.0.1", "127.0.0.1:52100", "m123", LO, false);             /* local lobby test (e2e) */
    expect("0.0.0.0", "127.0.0.1:7000", nullptr, ANY, false);              /* explicit any beats the default */
    expect("192.168.1.20", "192.168.1.30:7000", nullptr, 0xC0A80114u, false);
    expect("127.0.0.2", nullptr, nullptr, 0x7F000002u, false);

    /* Invalid T5_NET_BIND: noted, every interface. */
    expect("localhost", "127.0.0.1:7000", nullptr, ANY, true);
    expect("127.0.0.1:7000", nullptr, nullptr, ANY, true);
    expect("256.0.0.1", nullptr, nullptr, ANY, true);
    expect("1.2.3", nullptr, nullptr, ANY, true);
    expect("1.2.3.4.5", nullptr, nullptr, ANY, true);
    expect(" 127.0.0.1", nullptr, nullptr, ANY, true);
    expect("127.0.0.1 ", nullptr, nullptr, ANY, true);
    expect("0x7f.0.0.1", nullptr, nullptr, ANY, true);
    expect("1..2.3", nullptr, nullptr, ANY, true);
    expect("1234.0.0.1", nullptr, nullptr, ANY, true);
    expect("yes", nullptr, nullptr, ANY, true);

    /* Unset (or empty): loopback peer outside a lobby match -> 127.0.0.1. */
    expect(nullptr, "127.0.0.1:7000", nullptr, LO, false);
    expect("", "127.0.0.1:7000", "", LO, false);
    expect(nullptr, "127.10.3.1:7000", nullptr, LO, false);
    expect(nullptr, "localhost:7000", nullptr, LO, false);
    expect(nullptr, "LocalHost:7000", nullptr, LO, false);

    /* Unset: everything else binds every interface, as before. */
    expect(nullptr, nullptr, nullptr, ANY, false);                         /* host without a peer */
    expect(nullptr, "", nullptr, ANY, false);
    expect(nullptr, "203.0.113.7:7000", nullptr, ANY, false);              /* direct-IP join to a friend */
    expect(nullptr, "192.168.1.30:7000", nullptr, ANY, false);             /* LAN */
    expect(nullptr, "128.0.0.1:7000", nullptr, ANY, false);
    expect(nullptr, "126.255.255.255:7000", nullptr, ANY, false);
    expect(nullptr, "example.org:7000", nullptr, ANY, false);
    expect(nullptr, "localhost.example.org:7000", nullptr, ANY, false);
    expect(nullptr, "127.0.0.1", nullptr, LO, false);                      /* no port: still the loopback host */

    /* A real online match through the lobby: every interface, whatever the peer. */
    expect(nullptr, "198.51.100.23:51234", "m6208516c8782", ANY, false);  /* direct path */
    expect(nullptr, "46.224.146.6:7781", "m6208516c8782", ANY, false);    /* lobby relay */
    expect(nullptr, "192.168.1.30:51234", "m6208516c8782", ANY, false);   /* lan path */
    expect(nullptr, "127.0.0.1:61000", "m6208516c8782", ANY, false);      /* launcher's relay bridge */

    /* parse_ipv4 edge values. */
    unsigned v = 1;
    if (!np::parse_ipv4("0.0.0.0", &v) || v != 0) { printf("FAIL parse 0.0.0.0\n"); g_fail++; }
    if (!np::parse_ipv4("255.255.255.255", &v) || v != 0xFFFFFFFFu) { printf("FAIL parse 255.255.255.255\n"); g_fail++; }
    if (!np::parse_ipv4("10.0.100.1", &v) || v != 0x0A006401u) { printf("FAIL parse 10.0.100.1\n"); g_fail++; }
    if (np::parse_ipv4("001.002.003.004", &v) || np::parse_ipv4("127.0.0.01", &v)) { printf("FAIL leading zeros\n"); g_fail++; }
    if (np::parse_ipv4(nullptr, &v) || np::parse_ipv4("", &v)) { printf("FAIL parse empty\n"); g_fail++; }

    if (g_fail) { printf("FAILED %d\n", g_fail); return 1; }
    printf("PASS\n");
    return 0;
}
