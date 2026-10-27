/*
 * Entry detours for lifted guest functions (docs/ROLLBACK.md section 20).
 *
 * The lifted code calls guest functions directly (C++ calls, or a tail-call
 * trampoline that ends in the same host entry), so the runtime's indirect-call
 * hook (patch 0016) cannot see them. A detour rewrites the first bytes of the
 * host function: a 5-byte jmp to a relay next to it that jumps to the hook;
 * the hook gets the guest context and can run the original through a
 * trampoline (the moved prologue instructions, then a jmp back).
 *
 * Only the prologue shapes clang-cl emits for lifted functions are accepted
 * (push, sub rsp, mov reg/reg, vmovaps to the stack); anything else is refused
 * and the detour is not installed. Install on the main thread before the
 * function can run elsewhere (the first 8 bytes are swapped with one aligned
 * store).
 *
 * x86-64 only, and only where the process may write its own code
 * (t5p_code_patching: Windows, Linux; a notarized macOS app may not).
 *
 * macOS online builds (T5DR_HOOK_SLOTS, CMake T5DR_MACOS_ONLINE): no code is
 * patched. The lifter gave every function on src/rollback/hook_slots.txt a
 * slot (ppu_lifter.py --hook-slots): the function first calls the hook in its
 * slot, if any, instead of its body, and the body is a function of its own
 * (func_X__orig, the "original"). detour() stores the hook into the slot.
 * Every call reaches it -- direct calls, tail calls, the function table --
 * as every call reaches the patched entry on x86-64. A function that is not
 * on the list is refused (and noted).
 */
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include "../platform/t5_win.h"
#include <stdint.h>
#include <string.h>
#include <atomic>
#include <algorithm>
#include <array>
#include <ctype.h>
#include <stdio.h>
#include <stdlib.h>

#include "rb.h"
#include "rb_detour.h"

struct ppu_context;
typedef struct { uint64_t addr; void (*func)(ppu_context*); const char* name; } func_entry;
#ifdef PS3_GAME_DLL
extern "C" const func_entry* ppu_game_table;
extern "C" uint64_t ppu_game_table_count;
#define function_table       ppu_game_table
#define function_table_count ppu_game_table_count
#else
extern "C" const func_entry function_table[];
extern "C" const uint64_t  function_table_count;
#endif

#if defined(T5DR_HOOK_SLOTS)
/* The lifter's slot table (ppu_recomp.h, ppu_lifter.py --hook-slots): same layout as its
 * ppu_hook_entry. */
extern "C" {
struct hook_entry { uint32_t addr; uint32_t slot; void (*orig)(ppu_context*); };
extern void (*ppu_hook_slots[])(ppu_context*);
extern const hook_entry ppu_hook_table[];
extern const uint32_t ppu_hook_count;
}
#endif

namespace rb {

namespace {

/* Length of one prologue instruction, 0 = not a shape we move. */
size_t insn_len(const uint8_t* p)
{
    size_t n = 0;
    uint8_t rex = 0;
    if ((p[0] & 0xF0) == 0x40) { rex = p[0]; n = 1; }
    const uint8_t op = p[n];
    if (op >= 0x50 && op <= 0x57) return n + 1;                                   /* push r */
    if (op >= 0xB8 && op <= 0xBF) return n + ((rex & 8) ? 9 : 5);                /* mov r, imm32 / imm64 (import stubs: mov ecx, nid) */
    if (rex == 0x48 && op == 0x83 && p[n + 1] == 0xEC) return n + 3;              /* sub rsp, ib */
    if (rex == 0x48 && op == 0x81 && p[n + 1] == 0xEC) return n + 6;              /* sub rsp, id */
    if ((op == 0x89 || op == 0x8B) && (p[n + 1] & 0xC0) == 0xC0) return n + 2;    /* mov r, r */
    if (!rex && op == 0xC5) {                                                     /* VEX2: vmovaps/vmovups xmm <-> [rsp + d] */
        const uint8_t o2 = p[2], m = p[3];
        if (o2 != 0x28 && o2 != 0x29 && o2 != 0x10 && o2 != 0x11) return 0;
        const uint8_t mod = m >> 6, rm = m & 7;
        if (mod == 3) return 4;
        if (rm != 4 || p[4] != 0x24) return 0;                                   /* [rsp + ...] only */
        if (mod == 1) return 6;
        if (mod == 2) return 9;
        return 0;
    }
    return 0;
}

/* one page of relays/trampolines near the code */
uint8_t* g_pool = nullptr; size_t g_pool_used = 0; constexpr size_t kPool = 0x10000;
uint8_t* pool_take(const void* near_to, size_t n)
{
    if (!g_pool) g_pool = (uint8_t*)t5p_exec_alloc_near(near_to, kPool);
    if (!g_pool) return nullptr;
    const intptr_t dist = (intptr_t)((uintptr_t)g_pool - (uintptr_t)near_to);
    if (dist > 0x7FFF0000ll || dist < -0x7FFF0000ll) return nullptr;
    if (g_pool_used + n > kPool) return nullptr;
    uint8_t* p = g_pool + g_pool_used; g_pool_used += (n + 15) & ~(size_t)15;
    return p;
}
void put_abs_jmp(uint8_t* p, const void* to)   /* jmp [rip+0]; dq to -- 14 bytes */
{
    p[0] = 0xFF; p[1] = 0x25; memset(p + 2, 0, 4);
    const uint64_t v = (uint64_t)(uintptr_t)to; memcpy(p + 6, &v, 8);
}
} // namespace

#ifdef PS3_GAME_DLL
bool detour_ready() { return function_table != nullptr && function_table_count > 0; }
#else
bool detour_ready() { return function_table_count > 0; }
#endif

GuestFn host_of_guest(uint32_t addr)
{
    for (uint64_t k = 0; k < function_table_count; k++)
        if ((uint32_t)function_table[k].addr == addr) return function_table[k].func;
    return nullptr;
}

bool detour(uint32_t guest, GuestFn hook, GuestFn* orig)
{
    GuestFn h = host_of_guest(guest);
    if (!h) { note("detour %08X: no lifted function", guest); return false; }
#if defined(T5DR_HOOK_SLOTS)
    for (uint32_t k = 0; k < ppu_hook_count; k++) {
        const hook_entry& e = ppu_hook_table[k];
        if (e.addr != guest) continue;
        if (orig) *orig = e.orig;
        __atomic_store_n(&ppu_hook_slots[e.slot], hook, __ATOMIC_RELEASE);
        return true;
    }
    note("detour %08X: no hook slot (src/rollback/hook_slots.txt) -- not installed", guest);
    return false;
#elif !defined(T5P_X64)
    (void)hook; (void)orig;
    note("detour %08X: no code detours on this CPU -- not installed", guest);
    return false;
#else
    if (!t5p_code_patching()) { note("detour %08X: this build may not patch its code -- not installed", guest); return false; }
    uint8_t* code = (uint8_t*)(void*)h;
    size_t moved = 0;
    while (moved < 5) {
        const size_t l = insn_len(code + moved);
        if (!l) { note("detour %08X: prologue byte %02X %02X %02X at +%zu not understood -- not installed", guest, code[moved], code[moved + 1], code[moved + 2], moved); return false; }
        moved += l;
    }
    uint8_t* relay = pool_take(code, 16);
    uint8_t* tramp = pool_take(code, moved + 16);
    if (!relay || !tramp) { note("detour %08X: no memory near the code", guest); return false; }
    put_abs_jmp(relay, (const void*)hook);
    memcpy(tramp, code, moved);
    put_abs_jmp(tramp + moved, code + moved);
    t5p_icache_flush(g_pool, kPool);
    if (orig) *orig = (GuestFn)(void*)tramp;

    uint8_t patch[8]; memcpy(patch, code, 8);
    patch[0] = 0xE9;
    const int32_t rel = (int32_t)((intptr_t)relay - (intptr_t)(code + 5));
    memcpy(patch + 1, &rel, 4);
    if (!t5p_code_write(code, patch, 8)) { note("detour %08X: VirtualProtect failed", guest); return false; }
    return true;
#endif
}

} // namespace rb

/* ---- call tracer (diagnostics) ---------------------------------------------
 * T5_RB_CALLTRACE=addr,addr,... or @file (hex guest addresses, one per line or
 * comma separated): every call of those lifted functions goes to rb_calls.log
 * with the logical frame, whether it ran in a re-simulated frame, the guest
 * thread, r3..r8 at entry and r3 at return. Functions whose prologue the
 * detour cannot move are skipped (noted). */
#include <vector>
#include <string>
#include <utility>
#include "sys_ppu_thread.h"

namespace rb {
namespace {
constexpr int kTraceMax = 192;
GuestFn g_tr_orig[kTraceMax];
uint32_t g_tr_addr[kTraceMax];
FILE* g_tr_log = nullptr;

void trace_call(int i, ppu_context* ctx)
{
    const uint64_t a3 = ctx->gpr[3], a4 = ctx->gpr[4], a5 = ctx->gpr[5], a6 = ctx->gpr[6], a7 = ctx->gpr[7], a8 = ctx->gpr[8];
    const uint64_t tid = ctx->thread_id;
    const uint32_t f = sim_frame(); const int rs = bypass_on() ? 1 : 0;
    g_tr_orig[i](ctx);
    fprintf(g_tr_log, "C %u %d t%llu %06X %llx %llx %llx %llx %llx %llx -> %llx\n", f, rs, (unsigned long long)tid, g_tr_addr[i],
            (unsigned long long)a3, (unsigned long long)a4, (unsigned long long)a5, (unsigned long long)a6, (unsigned long long)a7,
            (unsigned long long)a8, (unsigned long long)ctx->gpr[3]);
    fflush(g_tr_log);   /* a test game is usually killed: keep every line */
}
template <int I> void trace_hook(ppu_context* ctx) { trace_call(I, ctx); }
template <int... I> constexpr std::array<GuestFn, sizeof...(I)> make_hooks(std::integer_sequence<int, I...>) { return { &trace_hook<I>... }; }
} // namespace

void calltrace_install()
{
    const char* e = getenv("T5_RB_CALLTRACE");
    if (!e || !*e) return;
    std::string text;
    if (*e == '@') {
        if (FILE* fp = fopen(e + 1, "rb")) { char b[4096]; size_t n; while ((n = fread(b, 1, sizeof b, fp)) > 0) text.append(b, n); fclose(fp); }
    } else text = e;
    static const auto hooks = make_hooks(std::make_integer_sequence<int, kTraceMax>{});
    g_tr_log = fopen("rb_calls.log", "w");
    int n = 0, skipped = 0;
    const char* p = text.c_str();
    while (*p && n < kTraceMax) {
        while (*p && !isxdigit((unsigned char)*p)) p++;
        if (!*p) break;
        char* z; const uint32_t a = (uint32_t)strtoul(p, &z, 16); p = z;
        g_tr_addr[n] = a;
        if (detour(a, hooks[n], &g_tr_orig[n])) n++; else skipped++;
    }
    note("call trace: %d functions traced, %d skipped (rb_calls.log)", n, skipped);
}

} // namespace rb
