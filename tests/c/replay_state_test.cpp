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
