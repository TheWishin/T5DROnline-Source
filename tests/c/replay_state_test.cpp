/* Synthetic guest memory only: full replay checkpoint validation and live-byte preservation. */
#include <windows.h>
#include <cstdio>
#include <cstring>
#include "../../src/rollback/rb_state.h"
extern "C" { unsigned char* vm_base = nullptr;
int cellGcm_pump_hold(int, unsigned) { return 1; }
void cellGcm_set_sema_acquire_geq(int) {}
void spurs_job_put_track(int) {}
const uint64_t* spurs_job_put_lines(uint32_t* base, uint32_t* pages) { *base = *pages = 0; return nullptr; }
void spurs_job_put_reset() {}
}
namespace rb { void note(const char*, ...) {} void logline(const char*, ...) {} }
#define CHECK(x) do { if (!(x)) { std::printf("FAIL line %d: %s\n", __LINE__, #x); return 1; } } while (0)
int main() {
    vm_base = (unsigned char*)VirtualAlloc(nullptr, 0x50000000ull, MEM_RESERVE, PAGE_READWRITE);
    CHECK(vm_base);
    for (size_t i = 0; i < rb::kSaveN; ++i)
        CHECK(VirtualAlloc(vm_base + rb::kSave[i].base, rb::kSave[i].len, MEM_COMMIT, PAGE_READWRITE));
    // Mixed hashing compares a relocated root's identity AND its scalar state.
    auto be = [](unsigned char* p, uint32_t x) { p[0] = (unsigned char)(x >> 24); p[1] = (unsigned char)(x >> 16); p[2] = (unsigned char)(x >> 8); p[3] = (unsigned char)x; };
    be(vm_base + 0x1008EB90, 0x003C7100);  // supported US image boundary
    unsigned char hash_bytes[0x6000];
    CHECK(rb::state_game_bytes(hash_bytes, sizeof hash_bytes) == 22156);
    rb::state_set_cross_program_hash(true);
    CHECK(rb::state_game_bytes(hash_bytes, sizeof hash_bytes) == 19572);
    be(vm_base + 0x1008EBA0, 0x40001000);
    be(vm_base + 0x40001018, 7);
    be(vm_base + 0x4000101C, 8);
    be(vm_base + 0x40001020, 9);
    be(vm_base + 0x40001024, 10);
    const uint64_t original_hash = rb::state_game_hash();
    CHECK(!rb::state_cross_program_unresolved());
    memcpy(vm_base + 0x40002000, vm_base + 0x40001000, 0x28);
    be(vm_base + 0x1008EBA0, 0x40002000);
    CHECK(rb::state_game_hash() == original_hash);
    for (uint32_t offset : { 0x18u, 0x1Cu, 0x20u, 0x24u }) {
        vm_base[0x40002000 + offset + 3] ^= 1;
        CHECK(rb::state_game_hash() != original_hash);
        vm_base[0x40002000 + offset + 3] ^= 1;
    }
    vm_base[0x100900D0] ^= 1;  // health/scalar cannot disappear in canonicalization
    CHECK(rb::state_game_hash() != original_hash);
    vm_base[0x100900D0] ^= 1;
    const uint32_t serialized = rb::state_game_bytes(hash_bytes, sizeof hash_bytes);
    CHECK(serialized == 19572);
    std::printf("LAYOUT %s", rb::state_game_layout(serialized, rb::state_game_hash()).c_str());
    CHECK(rb::state_game_bytes(hash_bytes, 64) <= 64);
    CHECK(rb::state_cross_program_unresolved() != 0); // a partial static prefix cannot be accepted
    rb::state_set_cross_program_hash(false);
    CHECK(rb::state_game_bytes(hash_bytes, sizeof hash_bytes) == 22156);
    be(vm_base + 0x1008EBA0, 0);
    vm_base[0x10000000] = 0x11;
    vm_base[0x106CECD0] = 0x22;  // music thread's live object
    std::vector<uint8_t> snapshot;
    CHECK(rb::state_capture(&snapshot));
    vm_base[0x10000000] = 0x33;
    vm_base[0x106CECD0] = 0x44;
    vm_base[0x0F800008] = 0x55;  // current GCM FIFO write pointer
    rb::state_add_exclude(0x10001000, 0x1000);  // newly discovered live streaming page
    vm_base[0x10001000] = 0x66;
    CHECK(rb::state_restore(snapshot));
    CHECK(vm_base[0x10000000] == 0x11);
    CHECK(vm_base[0x106CECD0] == 0x44);
    CHECK(vm_base[0x0F800008] == 0x55);
    CHECK(vm_base[0x10001000] == 0x66);
    vm_base[0x10000000] = 0x77;
    snapshot[12] ^= 1;  // unaligned first guest page address
    CHECK(!rb::state_restore(snapshot));
    CHECK(vm_base[0x10000000] == 0x77);  // validation is atomic, no partial writes
    snapshot.clear();
    CHECK(rb::state_capture(&snapshot));  // carries the newly discovered exclusion
    vm_base[0x10000000] = 0x88;
    vm_base[0x10001000] = 0x99;
    CHECK(rb::state_restore(snapshot));
    CHECK(vm_base[0x10000000] == 0x77);
    CHECK(vm_base[0x10001000] == 0x99);
    snapshot.pop_back();
    CHECK(!rb::state_restore(snapshot));
    VirtualFree(vm_base, 0, MEM_RELEASE);
    std::puts("PASS replay state checkpoint");
    return 0;
}
