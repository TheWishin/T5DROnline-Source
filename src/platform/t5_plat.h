/* What src/ needs from the host beyond the Win32 subset the runtime's POSIX
 * shim provides (t5_win.h). One small interface per job; docs/MACOS.md has
 * the inventory this came from.
 *
 * Windows: every function is a static inline wrapper around the exact Win32
 * call the code made before (same flags, same order), so the Windows build
 * compiles to the same code. Elsewhere they are declared here and implemented
 * in t5_plat_posix.c (macOS and Linux). That file is checked with
 * clang -fsyntax-only for x86_64/arm64 macOS and x86_64 Linux
 * (tests/test_posix_syntax.py); it has not run on a Mac yet.
 *
 * Include it through t5_win.h. Plain C, usable from C and C++. */
#pragma once

#include <stddef.h>
#include <stdint.h>
#include <string.h>

#if defined(_WIN32)
/* <windows.h> comes first, from t5_win.h (with the file's own LEAN/NOMINMAX). */
#  include <intrin.h>                      /* __rdtsc, _mm_getcsr */
#endif

#ifdef __cplusplus
extern "C" {
#endif

/* ---- paths --------------------------------------------------------------- */
#if defined(_WIN32)
#  define T5P_SEP "\\"
#else
#  define T5P_SEP "/"
#endif

/* ---- the host program counter in a vectored-exception CONTEXT ------------- */
#if defined(_WIN32)
#  define T5P_CTX_PC(c) ((c)->Rip)
#else
#  define T5P_CTX_PC(c) ((c)->Pc)          /* win32_compat.h: Pc on x86-64 and arm64 */
#endif

/* ---- a word another thread writes, read for a decision ----------------------
 * (the kernel semaphore peeks of the loader drain). Windows/x86 keep the plain
 * volatile read they always had; elsewhere it is an acquire load, so what that
 * thread wrote before the word is visible after it -- arm64 is not TSO. */
#if defined(_WIN32)
#  define T5P_PEEK_I32(p) (*(volatile const int32_t*)(p))
#else
#  define T5P_PEEK_I32(p) __atomic_load_n((const int32_t*)(p), __ATOMIC_ACQUIRE)
#endif

/* ---- architecture ---------------------------------------------------------- */
#if defined(_M_X64) || defined(__x86_64__)
#  define T5P_X64 1
#elif defined(_M_ARM64) || defined(__aarch64__)
#  define T5P_ARM64 1
#endif

#if !defined(_WIN32)
/* ======================= POSIX: declared, t5_plat_posix.c ================== */

/* Process */
void     t5p_exit_now(unsigned code);
void*    t5p_game_symbol(const char* name);
int      t5p_getenv_os(const char* name, char* buf, size_t cap);
void     t5p_setenv_os(const char* name, const char* value);
int      t5p_module_of(const void* addr, char* name, size_t cap, uintptr_t* base);
double   t5p_process_uptime_s(void);

/* Time */
uint64_t t5p_cycles(void);
uint64_t t5p_thread_cycles(void);

/* Files */
int      t5p_replace_file(const char* from, const char* to);
int      t5p_file_stamp(const char* path, uint64_t* stamp);
intptr_t t5p_open_read_shared(const char* path);
intptr_t t5p_create_write_shared(const char* path, int* busy);
long     t5p_read(intptr_t h, void* buf, unsigned long n);
long     t5p_write(intptr_t h, const void* buf, unsigned long n);
void     t5p_close(intptr_t h);
unsigned long t5p_os_error(void);

/* Guest memory write watch */
int      t5p_write_watch_available(void* probe);
int      t5p_write_watch(int reset, void* base, size_t len, void** addrs, uintptr_t* count, uint32_t* gran);
int      t5p_write_watch_reset(void* base, size_t len);
void     t5p_write_watch_touch(void* addr, size_t len);

/* Patching host code */
int      t5p_code_patching(void);
void*    t5p_exec_alloc_near(const void* target, size_t size);
int      t5p_code_write(void* dst, const void* src, size_t n);
void     t5p_icache_flush(void* p, size_t n);

/* FP environment */
uint32_t t5p_fp_control(void);

#else
/* ============================ Windows: inline ============================== */

/* End the process now: no atexit handlers, no static destructors, no flush
 * of other threads' work (what TerminateProcess(GetCurrentProcess()) did at
 * every call site). */
static inline void t5p_exit_now(unsigned code) { TerminateProcess(GetCurrentProcess(), (UINT)code); }

/* A symbol the game module exports (the game-DLL build's t5dr_game.dll), or
 * NULL: the monolithic t5dr.exe has no such module. */
static inline void* t5p_game_symbol(const char* name)
{
    HMODULE dll = GetModuleHandleA("t5dr_game.dll");
    return dll ? (void*)GetProcAddress(dll, name) : NULL;
}

/* The OS environment block (not the C runtime's copy, not the runtime's
 * getenv cache): 1 when the variable is set. */
static inline int t5p_getenv_os(const char* name, char* buf, size_t cap)
{
    if (cap) buf[0] = 0;
    return GetEnvironmentVariableA(name, buf, (DWORD)cap) != 0;
}
/* Set it in the OS block and in the C runtime's copy (main() reads it later). */
static inline void t5p_setenv_os(const char* name, const char* value)
{
    SetEnvironmentVariableA(name, value);
    _putenv_s(name, value);
}

/* The module (exe/DLL) that holds `addr`: its file name and load address.
 * 1 = found. */
static inline int t5p_module_of(const void* addr, char* name, size_t cap, uintptr_t* base)
{
    HMODULE mod = NULL;
    if (!GetModuleHandleExA(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
                            (LPCSTR)addr, &mod) || !mod)
        return 0;
    GetModuleFileNameA(mod, name, (DWORD)cap);
    if (base) *base = (uintptr_t)mod;
    return 1;
}

/* Seconds since this process was created (wall clock). */
static inline double t5p_process_uptime_s(void)
{
    FILETIME ct, et, kt, ut;
    GetProcessTimes(GetCurrentProcess(), &ct, &et, &kt, &ut);
    FILETIME nowft; GetSystemTimeAsFileTime(&nowft);
    ULARGE_INTEGER a, b; a.LowPart = nowft.dwLowDateTime; a.HighPart = nowft.dwHighDateTime;
    b.LowPart = ct.dwLowDateTime; b.HighPart = ct.dwHighDateTime;
    return (double)(a.QuadPart - b.QuadPart) / 1e7;
}

/* Raw cycle counter (x86-64: the TSC; POSIX: nanoseconds). Callers calibrate
 * it against QueryPerformanceCounter, so only the two being in the same unit
 * as t5p_thread_cycles matters. */
static inline uint64_t t5p_cycles(void) { return __rdtsc(); }
/* CPU time of the calling thread in t5p_cycles units (QueryThreadCycleTime
 * counts TSC ticks; POSIX: CLOCK_THREAD_CPUTIME_ID nanoseconds). */
static inline uint64_t t5p_thread_cycles(void) { ULONG64 c = 0; QueryThreadCycleTime(GetCurrentThread(), &c); return c; }

/* Replace `to` with `from` in one step (rename over an existing file): 1 = done. */
static inline int t5p_replace_file(const char* from, const char* to) { return MoveFileExA(from, to, MOVEFILE_REPLACE_EXISTING) != 0; }
/* An opaque stamp of the file's last write; 1 = the file exists. */
static inline int t5p_file_stamp(const char* path, uint64_t* stamp)
{
    WIN32_FILE_ATTRIBUTE_DATA a;
    if (!GetFileAttributesExA(path, GetFileExInfoStandard, &a)) return 0;
    *stamp = ((uint64_t)a.ftLastWriteTime.dwHighDateTime << 32) | a.ftLastWriteTime.dwLowDateTime;
    return 1;
}
/* Open for reading while another process may replace or delete the file
 * (FILE_SHARE_DELETE: the launcher's os.replace must never fail because the
 * game has the file open). -1 = failed. */
static inline intptr_t t5p_open_read_shared(const char* path)
{
    HANDLE h = CreateFileA(path, GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
                           NULL, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, NULL);
    return h == INVALID_HANDLE_VALUE ? (intptr_t)-1 : (intptr_t)h;
}
/* Create (or empty) a file for writing that others may read, rename or delete
 * while it is open (a live stream the launcher uploads as it grows). -1 =
 * failed; *busy = another process still has it open in a way that forbids
 * this (Windows' sharing violation: worth another try; never on POSIX). */
static inline intptr_t t5p_create_write_shared(const char* path, int* busy)
{
    HANDLE h = CreateFileA(path, GENERIC_WRITE, FILE_SHARE_READ | FILE_SHARE_DELETE, NULL, CREATE_ALWAYS,
                           FILE_ATTRIBUTE_NORMAL, NULL);
    if (busy) *busy = h == INVALID_HANDLE_VALUE && GetLastError() == ERROR_SHARING_VIOLATION;
    return h == INVALID_HANDLE_VALUE ? (intptr_t)-1 : (intptr_t)h;
}
/* Bytes read, 0 at the end, -1 on an error. */
static inline long t5p_read(intptr_t h, void* buf, unsigned long n)
{
    DWORD got = 0;
    if (!ReadFile((HANDLE)h, buf, (DWORD)n, &got, NULL)) return -1;
    return (long)got;
}
/* Bytes written, -1 on an error. */
static inline long t5p_write(intptr_t h, const void* buf, unsigned long n)
{
    DWORD wr = 0;
    if (!WriteFile((HANDLE)h, buf, (DWORD)n, &wr, NULL)) return -1;
    return (long)wr;
}
static inline void t5p_close(intptr_t h) { CloseHandle((HANDLE)h); }
/* The last file or OS call's error number (for a log line). */
static inline unsigned long t5p_os_error(void) { return GetLastError(); }

/* Pages of [base, base+len) written since the last reset -- GetWriteWatch on
 * a reservation made with MEM_WRITE_WATCH (boot_main.cpp, PS3_VM_WRITE_WATCH=1).
 * In: *count = room in addrs. Out: *count pages, *gran = page size.
 * 0 = done (the GetWriteWatch convention). */
static inline int t5p_write_watch(int reset, void* base, size_t len, void** addrs, uintptr_t* count, uint32_t* gran)
{
    ULONG_PTR c = (ULONG_PTR)*count;
    DWORD g = 0;
    const UINT rc = GetWriteWatch(reset ? WRITE_WATCH_FLAG_RESET : 0, base, (SIZE_T)len, addrs, &c, &g);
    *count = (uintptr_t)c;
    if (gran) *gran = (uint32_t)g;
    return (int)rc;
}
static inline int t5p_write_watch_reset(void* base, size_t len) { return (int)ResetWriteWatch(base, (SIZE_T)len); }
/* Was the guest memory around `probe` reserved so it can be watched? */
static inline int t5p_write_watch_available(void* probe)
{
    void* addrs[4]; ULONG_PTR count = 4; DWORD gran = 0;
    return GetWriteWatch(0, probe, 0x1000, addrs, &count, &gran) == 0;
}
/* Host code is about to write [addr, addr+len) of tracked memory from the
 * kernel side (a file read into guest memory). Nothing to do here: the
 * Windows write watch sees kernel writes. */
static inline void t5p_write_watch_touch(void* addr, size_t len) { (void)addr; (void)len; }

/* Can this build patch its own machine code (rollback entry detours)? */
static inline int t5p_code_patching(void) { return 1; }
/* Executable, writable memory within +-2 GB of `target` (rel32 jumps). */
static inline void* t5p_exec_alloc_near(const void* target, size_t size)
{
    SYSTEM_INFO si; GetSystemInfo(&si);
    const uintptr_t gran = si.dwAllocationGranularity;
    const uintptr_t t = (uintptr_t)target;
    for (uintptr_t d = gran; d < (1ull << 30); d += gran) {
        for (int s = 0; s < 2; s++) {
            const uintptr_t a = s ? ((t + d) & ~(gran - 1)) : ((t - d) & ~(gran - 1));
            void* p = VirtualAlloc((void*)a, size, MEM_RESERVE | MEM_COMMIT, PAGE_EXECUTE_READWRITE);
            if (p) return p;
        }
    }
    return NULL;
}
static inline void t5p_icache_flush(void* p, size_t n) { FlushInstructionCache(GetCurrentProcess(), p, n); }
/* Write n (<= 16) bytes over live code: made writable, an 8-byte aligned
 * prefix in one atomic store (no thread sees half a jump), back to its old
 * protection, instruction cache flushed. 1 = done. */
static inline int t5p_code_write(void* dst, const void* src, size_t n)
{
    DWORD old = 0;
    if (!VirtualProtect(dst, 16, PAGE_EXECUTE_READWRITE, &old)) return 0;
    if (n == 8 && ((uintptr_t)dst & 7) == 0) {
        uint64_t v; memcpy(&v, src, 8);
        __atomic_store_n((volatile uint64_t*)dst, v, __ATOMIC_SEQ_CST);
    } else memcpy(dst, src, n);
    VirtualProtect(dst, 16, old, &old);
    FlushInstructionCache(GetCurrentProcess(), dst, 16);
    return 1;
}

/* The FP control word guest code runs under: MXCSR's control bits (x86-64). */
static inline uint32_t t5p_fp_control(void) { return _mm_getcsr() & 0xFFC0u; }

#endif /* _WIN32 */

#ifdef __cplusplus
}
#endif
