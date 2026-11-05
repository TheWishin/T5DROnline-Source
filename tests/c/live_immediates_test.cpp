#include "../../src/platform/t5_live_immediates.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define CHECK(x) do { if (!(x)) { printf("FAIL line %d: %s\n", __LINE__, #x); return 1; } } while (0)
static const char expected[] = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
int main(int argc, char** argv) {
    CHECK(!t5game::live_immediate_manifest_matches(0, expected, expected));
    CHECK(!t5game::live_immediate_manifest_matches(2, expected, expected));
    CHECK(!t5game::live_immediate_manifest_matches(1, nullptr, expected));
    CHECK(!t5game::live_immediate_manifest_matches(1, expected, nullptr));
    CHECK(!t5game::live_immediate_manifest_matches(1, "", expected));
    CHECK(!t5game::live_immediate_manifest_matches(1, expected, "wrong"));
    CHECK(t5game::live_immediate_manifest_matches(1, expected, expected));
#ifdef TEST_MONOLITHIC
    CHECK(t5game::has_live_immediates(expected) == (TEST_EXPECT_MONOLITHIC != 0));
#else
    CHECK(argc == 3);
    CHECK(!t5game::has_live_immediates(expected)); // no module: do not cache this negative result
    HMODULE module = LoadLibraryA(argv[1]);
    CHECK(module);
    CHECK(t5game::has_live_immediates(expected) == (atoi(argv[2]) != 0));
    CHECK(!t5game::has_live_immediates("wrong"));
    CHECK(FreeLibrary(module));
    CHECK(!t5game::has_live_immediates(expected)); // no stale positive after unload
#endif
    puts("PASS live-immediate ABI, exact manifest, missing/old modules and module lifetime");
    return 0;
}
