/* Pure policy checks: no sockets, game, or guest memory. */
#include "../../src/netplay/rollback_delay.h"
#include <cassert>
#include <cstdio>
#include <limits>

int main()
{
    using np::detail::jitter_delay;
    float stable[] = {110, 110, 110, 110};
    float jitter[] = {100, 110, 130, 170};
    float huge[] = {900, 900, 900, 900};
    float bad[] = {120, 140, std::numeric_limits<float>::quiet_NaN(), -1};
    assert(jitter_delay(stable, 4, 2, 3) == 2);
    assert(jitter_delay(jitter, 4, 2, 3) == 3);
    assert(jitter_delay(jitter, 3, 2, 3) == 2);
    assert(jitter_delay(jitter, 4, 2, 2) == 2);
    assert(jitter_delay(huge, 4, 2, 3) == 3);
    assert(jitter_delay(huge, 4, 2, 6) == 6);
    assert(jitter_delay(bad, 4, 2, 3) == 2);
    assert(jitter_delay(jitter, 4, 4, 3) == 4);  /* never reduce an existing choice */
    puts("PASS 8 checks");
}
