#include "../../src/netplay/mixed_timing.h"
#include <vector>
#include <cstdio>
#include <memory>
#include <cstring>
using namespace np::mixed_timing;
#define CHECK(x) do { if (!(x)) { std::printf("FAIL line %d: %s\n", __LINE__, #x); return 1; } } while (0)
int main() {
    // Reserve the guest address interval without touching hundreds of MB.
    // Only the instruction window and the small data-record window are used.
    std::unique_ptr<uint8_t[]> guest(new uint8_t[0x10006000]);
    std::memset(guest.get(), 0xA5, 0x50000);
    std::memset(guest.get() + 0x10005800, 0xA5, 0x400);
    const auto snapshot = [&]() {
        std::vector<uint8_t> bytes(guest.get(), guest.get() + 0x50000);
        bytes.insert(bytes.end(), guest.get() + 0x10005800, guest.get() + 0x10005C00);
        return bytes;
    };
    for (const Site& site : kSites) write_word(guest.get() + site.pc, site.original);
    for (const DurationRecord& record : kDurationRecords)
        for (uint32_t word = 0; word < 4; ++word) write_word(guest.get() + record.address + word * 4, record.original[word]);
    CHECK(sizeof kDurationRecords / sizeof kDurationRecords[0] == 36);
    const auto original = snapshot();
    CHECK(transition(guest.get(), false, false));
    CHECK(snapshot() == original); // original EU behavior remains exact
    CHECK(transition(guest.get(), false, true));
    for (const Site& site : kSites) {
        CHECK(read_word(guest.get() + site.pc) == site.mixed);
        CHECK((site.mixed & 0xFFFF0000u) == (site.original & 0xFFFF0000u));
    }
    for (const DurationRecord& record : kDurationRecords)
        for (uint32_t word = 0; word < 4; ++word)
            CHECK(read_word(guest.get() + record.address + word * 4) == (word == 2 ? record.mixed_duration : record.original[word]));
    CHECK(transition(guest.get(), true, false));
    CHECK(snapshot() == original); // later same-edition session restores every byte
    guest[kSites[2].pc] ^= 4; // unknown opcode/image, while earlier sites still match
    const auto corrupt = snapshot();
    CHECK(!transition(guest.get(), false, true));
    CHECK(snapshot() == corrupt); // validation precedes ALL writes
    guest[kSites[2].pc] ^= 4;
    // A late, unchanged identity word must also prevent every earlier write.
    guest[kDurationRecords[35].address + 12] ^= 1;
    const auto corrupt_record = snapshot();
    CHECK(!transition(guest.get(), false, true));
    CHECK(snapshot() == corrupt_record);
    guest[kDurationRecords[35].address + 12] ^= 1;
    CHECK(transition(guest.get(), false, true));
    guest[kDurationRecords[35].address + 8] ^= 1;
    const auto corrupt_mixed = snapshot();
    CHECK(!transition(guest.get(), true, false));
    CHECK(snapshot() == corrupt_mixed);
    CHECK(!transition(nullptr, false, true));
    std::puts("PASS exact original/mixed/restored timing words and atomic fail-closed transition");
    return 0;
}
