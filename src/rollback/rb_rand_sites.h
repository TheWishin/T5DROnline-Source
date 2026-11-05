#pragma once

#include <stdint.h>
#include <stddef.h>

namespace rb {

struct RandSite { uint32_t eu, us; };
#include "rb_rand_sites.inc"

/* A private random stream's identity must survive a relink of the guest.
 * Each listed EU return site is proven to call the same generator at the
 * same instruction in a matched function or instruction block. Unknown sites
 * stay unresolved. */
inline bool rand_site_us(uint32_t eu, uint32_t* us)
{
    size_t lo = 0, hi = sizeof(kEuRandSites) / sizeof(kEuRandSites[0]);
    while (lo < hi) {
        const size_t mid = (lo + hi) / 2;
        if (kEuRandSites[mid].eu < eu) lo = mid + 1; else hi = mid;
    }
    if (lo == sizeof(kEuRandSites) / sizeof(kEuRandSites[0]) || kEuRandSites[lo].eu != eu) return false;
    *us = kEuRandSites[lo].us;
    return true;
}

/* US and same-program sessions retain their original stream seed exactly. */
inline uint32_t rand_site_seed(uint32_t session_seed, uint32_t site)
{
    return session_seed ^ (site * 0x85EBCA6Bu);
}

} // namespace rb
