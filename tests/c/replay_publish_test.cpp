/* Game-free publication policy regression; no files or game data are created. */
#include <cassert>
#include "../../src/netplay/replay_publish.h"

int main()
{
    unsigned attempts = 0, pauses = 0;
    bool published = rp::detail::publish_retry(
        [&] { ++attempts; return false; }, [&] { ++pauses; });
    assert(!published && attempts == 50 && pauses == 49);
    attempts = pauses = 0;
    published = rp::detail::publish_retry(
        [&] { return ++attempts == 3; }, [&] { ++pauses; });
    assert(published && attempts == 3 && pauses == 2);
    attempts = pauses = 0;
    published = rp::detail::publish_retry(
        [&] { ++attempts; return true; }, [&] { ++pauses; });
    assert(published && attempts == 1 && pauses == 0);
    attempts = pauses = 0;
    published = rp::detail::publish_retry(
        [&] { ++attempts; return true; }, [&] { ++pauses; }, 0);
    assert(!published && attempts == 0 && pauses == 0);
    return 0;
}
