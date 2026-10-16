/* The few things a C runtime would give the game DLL (it is linked without one):
 * implicit TLS, static constructors, _fltused -- plus the exports the runtime
 * looks up when it loads the DLL (ps3recomp runtime/ppu/ppu_game_dll.h).
 * Compiled with the same header-free flags as the lifted code. */
#include <stdint.h>

int _fltused = 0x9875;

/* ---- stack probe. A function with more than a page of locals (the lifted SPU
 * skinning jobs have them) calls __chkstk with the frame size in RAX before it
 * moves RSP; touching every page in order lets the guard page grow the stack.
 * Same contract as the CRT's: probes from the caller's RSP down, keeps every
 * register but R10/R11 and the flags, leaves RSP alone. */
__attribute__((naked)) void __chkstk(void)
{
    __asm__ volatile(
        "subq   $16, %rsp\n\t"
        "movq   %r10, (%rsp)\n\t"
        "movq   %r11, 8(%rsp)\n\t"
        "xorq   %r11, %r11\n\t"
        "leaq   24(%rsp), %r10\n\t"          /* the caller's RSP */
        "subq   %rax, %r10\n\t"              /* lowest address the frame will use */
        "cmovbq %r11, %r10\n\t"              /* wrapped below 0: probe everything */
        "movq   %gs:0x10, %r11\n\t"          /* TEB StackLimit: lowest committed page */
        "cmpq   %r11, %r10\n\t"
        "jae    2f\n\t"
        "andw   $0xF000, %r10w\n\t"
        "1:\n\t"
        "leaq   -0x1000(%r11), %r11\n\t"
        "movb   $0, (%r11)\n\t"
        "cmpq   %r11, %r10\n\t"
        "jne    1b\n\t"
        "2:\n\t"
        "movq   (%rsp), %r10\n\t"
        "movq   8(%rsp), %r11\n\t"
        "addq   $16, %rsp\n\t"
        "ret");
}

/* ---- implicit TLS: the directory the loader reads (what the CRT's tlssup provides) */
typedef void (__stdcall *t5_tls_callback)(void*, unsigned long, void*);
unsigned long _tls_index = 0;
#pragma section(".tls", read, write)
#pragma section(".tls$ZZZ", read, write)
#pragma section(".CRT$XLA", read)
#pragma section(".CRT$XLZ", read)
#pragma section(".rdata$T", read)
__declspec(allocate(".tls")) char _tls_start = 0;
__declspec(allocate(".tls$ZZZ")) char _tls_end = 0;
__declspec(allocate(".CRT$XLA")) t5_tls_callback __xl_a = 0;
__declspec(allocate(".CRT$XLZ")) t5_tls_callback __xl_z = 0;
typedef struct {
    uint64_t start, end, index, callbacks;
    uint32_t zero_fill, characteristics;
} t5_tls_directory;
__declspec(allocate(".rdata$T")) const t5_tls_directory _tls_used = {
    (uint64_t)&_tls_start, (uint64_t)&_tls_end, (uint64_t)&_tls_index, (uint64_t)(&__xl_a + 1), 0, 0
};

/* ---- static constructors (.CRT$XCU: the lifted SPU images register themselves) */
typedef void (*t5_ctor)(void);
#pragma section(".CRT$XCA", read)
#pragma section(".CRT$XCZ", read)
__declspec(allocate(".CRT$XCA")) t5_ctor __xc_a = 0;
__declspec(allocate(".CRT$XCZ")) t5_ctor __xc_z = 0;

__declspec(dllexport) void ppu_game_init(void)
{
    for (t5_ctor* p = &__xc_a + 1; p < &__xc_z; ++p)
        if (*p) (*p)();
}

/* ---- the tail-call trampoline slot: lifted code sets it on every tail call, the
 * runtime drains it after calling into lifted code. One per thread, owned here. */
__declspec(thread) void (*g_trampoline_fn)(void*) = 0;

__declspec(dllexport) void (**ppu_game_tramp_slot(void))(void*)
{
    return &g_trampoline_fn;
}
