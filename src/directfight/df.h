/* T5DR direct fight -- shared declarations (src/directfight/, docs/DIRECTFIGHT.md). */
#pragma once
#include <stdint.h>
#include <string.h>
#include <stdlib.h>

extern "C" uint8_t* vm_base;

namespace df {

/* guest memory (big-endian) */
inline uint32_t rd32(uint32_t a) { uint32_t v; memcpy(&v, vm_base + a, 4); return _byteswap_ulong(v); }
inline uint64_t rd64(uint32_t a) { uint64_t v; memcpy(&v, vm_base + a, 8); return _byteswap_uint64(v); }
inline uint16_t rd16(uint32_t a) { uint16_t v; memcpy(&v, vm_base + a, 2); return _byteswap_ushort(v); }
inline uint8_t  rd8(uint32_t a)  { return vm_base[a]; }
inline void wr32(uint32_t a, uint32_t v) { v = _byteswap_ulong(v); memcpy(vm_base + a, &v, 4); }
inline void wr16(uint32_t a, uint16_t v) { v = _byteswap_ushort(v); memcpy(vm_base + a, &v, 2); }
inline void wr8(uint32_t a, uint8_t v)   { vm_base[a] = v; }

void note(const char* fmt, ...);

/* mode manager (df_hooks.cpp): object address once found, current/next mode id */
uint32_t mode_manager();
uint32_t mode_cur();
uint32_t mode_next();

/* pad injection: while on, pad `port` reads exactly `buttons` (CELL_PAD_CTRL_*
 * packed DIGITAL1 low byte / DIGITAL2 high byte); routed to the netplay hooks
 * when netplay owns the pads, to our own cellPadGetData override otherwise */
void inject(int port, bool on, uint16_t buttons);
bool netplay_on();
uint64_t gcall(uint32_t code, uint64_t a0 = 0, uint64_t a1 = 0, uint64_t a2 = 0);

/* fight driver (df_fight.cpp) */
bool fight_configured();                 /* T5_FIGHT or T5_FIGHT_FILE given */
void fight_init();                       /* parse the environment (static init time) */
void fight_on_frame(uint32_t f);         /* main thread, top of every frame */

/* pad bits */
enum : uint16_t {
    B_SELECT = 0x0001, B_L3 = 0x0002, B_R3 = 0x0004, B_START = 0x0008,
    B_UP = 0x0010, B_RIGHT = 0x0020, B_DOWN = 0x0040, B_LEFT = 0x0080,
    B_L2 = 0x0100, B_R2 = 0x0200, B_L1 = 0x0400, B_R1 = 0x0800,
    B_TRIANGLE = 0x1000, B_CIRCLE = 0x2000, B_CROSS = 0x4000, B_SQUARE = 0x8000,
};

} // namespace df
