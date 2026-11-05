#include "../../src/rollback/rb_rand_sites.h"
#include <cstdio>

static int failures = 0, checks = 0;
#define CHECK(c) do { ++checks; if (!(c)) { ++failures; std::printf("FAIL line %d: %s\n", __LINE__, #c); } } while (0)

int main()
{
    // A real mixed-pair failure: its EU constructor has extra instructions,
    // while the 372-word suffix containing this call is the same.
    uint32_t regression = 0;
    CHECK(rb::rand_site_us(0x000B66FCu, &regression));
    CHECK(regression == 0x000B508Cu);
    const uint32_t seeds[] = { 0, 1, 0xFFFFFFFFu, 0xF82B9AE1u };
    uint32_t last = 0;
    for (const rb::RandSite& site : rb::kEuRandSites) {
        CHECK(site.eu > last);
        last = site.eu;
        uint32_t us = 0;
        CHECK(rb::rand_site_us(site.eu, &us));
        CHECK(us == site.us);
        for (uint32_t seed : seeds) {
            // The US stream preserves every bit of its previous seed.
            CHECK(rb::rand_site_seed(seed, site.us) == (seed ^ (site.us * 0x85EBCA6Bu)));
            // A paired relocated caller must produce the same stream seed.
            CHECK(rb::rand_site_seed(seed, us) == rb::rand_site_seed(seed, site.us));
            CHECK(rb::rand_site_seed(seed, site.eu) != rb::rand_site_seed(seed, site.us));
        }
        // Matching an adjacent instruction is unsafe: require an exact site.
        uint32_t unresolved = 0xDEADBEEFu;
        CHECK(!rb::rand_site_us(site.eu + 1, &unresolved));
        CHECK(unresolved == 0xDEADBEEFu);
    }
    uint32_t out = 0;
    CHECK(!rb::rand_site_us(0, &out));
    CHECK(!rb::rand_site_us(0xFFFFFFFFu, &out));
    std::printf("%s %d checks\n", failures ? "FAIL" : "PASS", checks);
    return failures ? 1 : 0;
}
