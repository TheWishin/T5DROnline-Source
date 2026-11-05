#include "../../src/netplay/first_block_hash.h"
#include <cstdio>
#include <vector>
using namespace np::cross_hash;
using namespace np::cross_hash::first_block;
#define CHECK(x) do { if (!(x)) { std::printf("FAIL line %d: %s\n", __LINE__, #x); return 1; } } while (0)
int main() {
    uint32_t count = 0;
    std::vector<uint8_t> ref(kUSLength, 0), current(ref);
    CHECK(validate(current.data(), ref.data(), kUSLength, false, &count) == 0 && count == 0);
    write_be(current.data() + 0x1B0, 79);
    CHECK(validate(current.data(), ref.data(), kUSLength, false, &count) == 0 && count == 79);
    current[0x818] ^= 1; // engine-used FLT_MAX must not disappear
    CHECK(validate(current.data(), ref.data(), kUSLength, false, &count) == 1);
    current[0x818] ^= 1;
    current[0x690] ^= 1; // stdio mutation is not silently discarded either
    CHECK(validate(current.data(), ref.data(), kUSLength, false, &count) == 1);
    CHECK(validate(current.data(), ref.data(), kUSLength - 1, false, &count) == 1);
    CHECK(validate(nullptr, ref.data(), kUSLength, false, &count) == 1);
    ref.assign(kEULength, 0); current = ref;
    write_be(current.data() + 0xB40, 1); write_be(current.data() + 0xB44, 0x10770000);
    write_be(current.data() + 0x1A8, 79);
    CHECK(validate(current.data(), ref.data(), kEULength, true, &count) == 0 && count == 79);
    write_be(current.data() + 0xB40, 2);
    CHECK(validate(current.data(), ref.data(), kEULength, true, &count) == 1);
    write_be(current.data() + 0xB40, 1); write_be(current.data() + 0xB44, 0x10770004);
    CHECK(validate(current.data(), ref.data(), kEULength, true, &count) == 1);
    CHECK(kBytes == 344);
    std::puts("PASS immutable prefix, raw callback count, numeric/stdio mutations, exact CRT launch invariant");
    return 0;
}
