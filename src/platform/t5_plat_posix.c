/* POSIX half of t5_plat.h: macOS (arm64 and x86-64) and Linux.
 *
 * Status (2026-10-19): written on Windows and checked there with
 * clang -fsyntax-only for x86_64-apple-darwin, arm64-apple-darwin and
 * x86_64-linux-gnu against declaration-only headers (tests/posix_sysroot,
 * tests/test_macos_port.py). It has NOT run on a Mac. docs/MACOS.md says
 * what to test first.
 *
 * The one part with real design in it is the write watch, the rollback
 * snapshot's "which guest pages changed since the last commit". Windows has it
 * in the kernel (MEM_WRITE_WATCH + GetWriteWatch). Here it is done with page
 * protection: an armed range is read-only, the first write to a host page
 * faults, the handler marks the page dirty and makes it writable again, and a
 * reset collects the dirty pages and protects them again. Differences a caller
 * must know about:
 *
 *  - Granularity is the host page: 16 KB on Apple Silicon, 4 KB elsewhere.
 *    A dirty 16 KB page is reported as its four 4 KB pages (the rollback code
 *    thinks in 4 KB pages).
 *  - The kernel does not fault on our behalf: read(2)/recv(2) into a
 *    protected page fail with EFAULT instead of being recorded. Host code that
 *    lets the kernel write guest memory calls t5p_write_watch_touch() on the
 *    destination first (docs/MACOS.md lists the runtime's call sites).
 *  - A range is armed by its first reset (or first query): what was written
 *    before that is not reported. rb_state.cpp resets before it uses a range,
 *    as it does on Windows.
 *  - The guest memory must be host-page aligned (mmap, not calloc).
 *  - Nothing else may change the protection of pages inside an armed range
 *    (a debugging guard page there would be made writable by the first write).
 *
 * A write that races a reset is never lost: the handler unprotects first and
 * marks second, and a reset protects a page before it clears its mark (state
 * DIRTY -> RESETTING -> protect -> CLEAN only if still RESETTING), so a write
 * after the protect faults again and lands in the next period.
 */
#if !defined(_WIN32)

#if defined(__linux__) && !defined(_GNU_SOURCE)
#  define _GNU_SOURCE 1                 /* dladdr, RTLD_DEFAULT */
#endif
#if defined(__APPLE__) && !defined(_DARWIN_C_SOURCE)
#  define _DARWIN_C_SOURCE 1
#endif

#include "t5_plat.h"

#include <dlfcn.h>
#include <pthread.h>
#include <errno.h>
#include <fcntl.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <time.h>
#include <unistd.h>
#if defined(__APPLE__)
#  include <libkern/OSCacheControl.h>   /* sys_icache_invalidate */
#endif

/* ---- process -------------------------------------------------------------- */

void t5p_exit_now(unsigned code)
{
    /* No atexit handlers, no static destructors: what TerminateProcess(self)
     * does. stdio buffers are lost the same way, so flush the two logs. */
    fflush(stdout);
    fflush(stderr);
    _exit((int)(code & 0xFFu));
}

#if defined(__APPLE__)
#  define T5P_GAME_MODULE "t5dr_game.dylib"
#else
#  define T5P_GAME_MODULE "t5dr_game.so"
#endif

void* t5p_game_symbol(const char* name)
{
    /* RTLD_NOLOAD: only if the game module is already loaded (game-module
     * build); the monolithic executable has none. */
    void* h = dlopen(T5P_GAME_MODULE, RTLD_LAZY | RTLD_NOLOAD);
    if (!h) return NULL;
    void* sym = dlsym(h, name);
    dlclose(h);                           /* NOLOAD took a reference; the loader keeps its own */
    return sym;
}

int t5p_getenv_os(const char* name, char* buf, size_t cap)
{
    const char* v = getenv(name);         /* one environment on POSIX; the runtime does not cache it here */
    if (cap) buf[0] = 0;
    if (!v) return 0;
    if (cap) { strncpy(buf, v, cap - 1); buf[cap - 1] = 0; }
    return 1;
}

void t5p_setenv_os(const char* name, const char* value)
{
    setenv(name, value, 1);
}

int t5p_module_of(const void* addr, char* name, size_t cap, uintptr_t* base)
{
    Dl_info di;
    memset(&di, 0, sizeof di);
    if (!dladdr(addr, &di) || !di.dli_fbase) return 0;
    if (cap) {
        strncpy(name, di.dli_fname ? di.dli_fname : "?", cap - 1);
        name[cap - 1] = 0;
    }
    if (base) *base = (uintptr_t)di.dli_fbase;
    return 1;
}

/* "Since the process was created": since this file's constructor ran, which
 * is before main() and close enough for the one log that wants it
 * (rb_measure.cpp lines its timeline up with process start). */
static struct timespec s_start_wall;
__attribute__((constructor)) static void t5p_note_start(void)
{
    clock_gettime(CLOCK_REALTIME, &s_start_wall);
}
double t5p_process_uptime_s(void)
{
    struct timespec now;
    clock_gettime(CLOCK_REALTIME, &now);
    return (double)(now.tv_sec - s_start_wall.tv_sec) + (double)(now.tv_nsec - s_start_wall.tv_nsec) / 1e9;
}

/* ---- time ------------------------------------------------------------------ */

uint64_t t5p_cycles(void)
{
    struct timespec ts;
#if defined(CLOCK_MONOTONIC_RAW)
    clock_gettime(CLOCK_MONOTONIC_RAW, &ts);
#else
    clock_gettime(CLOCK_MONOTONIC, &ts);
#endif
    return (uint64_t)ts.tv_sec * 1000000000ull + (uint64_t)ts.tv_nsec;
}

uint64_t t5p_thread_cycles(void)
{
    struct timespec ts;
    if (clock_gettime(CLOCK_THREAD_CPUTIME_ID, &ts) != 0) return 0;
    return (uint64_t)ts.tv_sec * 1000000000ull + (uint64_t)ts.tv_nsec;
}

/* ---- files ------------------------------------------------------------------- */

int t5p_replace_file(const char* from, const char* to)
{
    return rename(from, to) == 0;         /* atomic, and allowed while a reader has `to` open */
}

int t5p_file_stamp(const char* path, uint64_t* stamp)
{
    struct stat st;
    if (stat(path, &st) != 0) return 0;
#if defined(__APPLE__)
    *stamp = (uint64_t)st.st_mtimespec.tv_sec * 1000000000ull + (uint64_t)st.st_mtimespec.tv_nsec;
#else
    *stamp = (uint64_t)st.st_mtim.tv_sec * 1000000000ull + (uint64_t)st.st_mtim.tv_nsec;
#endif
    return 1;
}

intptr_t t5p_open_read_shared(const char* path)
{
    /* POSIX never stops a rename or unlink because a file is open. */
    const int fd = open(path, O_RDONLY | O_CLOEXEC);
    return fd < 0 ? (intptr_t)-1 : (intptr_t)fd;
}

intptr_t t5p_create_write_shared(const char* path, int* busy)
{
    /* POSIX never refuses a second opener, a rename or an unlink of an open file. */
    if (busy) *busy = 0;
    const int fd = open(path, O_WRONLY | O_CREAT | O_TRUNC | O_CLOEXEC, 0644);
    return fd < 0 ? (intptr_t)-1 : (intptr_t)fd;
}

long t5p_read(intptr_t h, void* buf, unsigned long n)
{
    for (;;) {
        const ssize_t r = read((int)h, buf, (size_t)n);
        if (r < 0 && errno == EINTR) continue;
        return (long)r;
    }
}

long t5p_write(intptr_t h, const void* buf, unsigned long n)
{
    /* All of it, as WriteFile on a file does: a short write is retried. */
    const char* p = (const char*)buf;
    unsigned long done = 0;
    while (done < n) {
        const ssize_t w = write((int)h, p + done, (size_t)(n - done));
        if (w < 0 && errno == EINTR) continue;
        if (w <= 0) return -1;
        done += (unsigned long)w;
    }
    return (long)done;
}

void t5p_close(intptr_t h) { close((int)h); }

unsigned long t5p_os_error(void) { return (unsigned long)errno; }

/* ---- guest memory write watch ---------------------------------------------- */

enum { WW_CLEAN = 0, WW_DIRTY = 1, WW_RESETTING = 2 };
#define WW_MAX_RANGES 64
#define WW_UNIT       0x1000u            /* what callers count in: 4 KB pages */

typedef struct {
    uintptr_t base;                       /* host-page aligned */
    size_t    len;                        /* multiple of the host page */
    uint8_t*  state;                      /* one WW_* per host page */
} ww_range;

static ww_range         s_ww[WW_MAX_RANGES];
static int              s_ww_n;           /* published with release after the slot is filled */
static size_t           s_page;           /* host page size */
static int              s_ww_installed;
static struct sigaction s_ww_prev[2];     /* SIGSEGV, SIGBUS */
static pthread_mutex_t  s_ww_lock = PTHREAD_MUTEX_INITIALIZER;

static void ww_chain(int sig, siginfo_t* si, void* uc)
{
    const struct sigaction* prev = &s_ww_prev[sig == SIGBUS];
    if ((prev->sa_flags & SA_SIGINFO) && prev->sa_sigaction) { prev->sa_sigaction(sig, si, uc); return; }
    if (prev->sa_handler == SIG_IGN) return;
    if (prev->sa_handler && prev->sa_handler != SIG_DFL) { prev->sa_handler(sig); return; }
    signal(sig, SIG_DFL);                 /* re-run the access and die as we would have */
}

static void ww_fault(int sig, siginfo_t* si, void* uc)
{
    const uintptr_t a = (uintptr_t)si->si_addr;
    const int n = __atomic_load_n(&s_ww_n, __ATOMIC_ACQUIRE);
    for (int i = 0; i < n; i++) {
        const ww_range* r = &s_ww[i];
        if (a - r->base >= r->len) continue;
        const size_t pg = (a - r->base) / s_page;
        /* Writable first, marked second: a reset that runs in between finds
         * the page CLEAN and leaves it alone, and the mark lands in the next
         * period -- the retried store is never lost. */
        mprotect((void*)(r->base + pg * s_page), s_page, PROT_READ | PROT_WRITE);
        __atomic_store_n(&r->state[pg], (uint8_t)WW_DIRTY, __ATOMIC_RELEASE);
        return;
    }
    ww_chain(sig, si, uc);
}

static size_t ww_page_size(void)
{
    if (!s_page) {
        const long ps = sysconf(_SC_PAGESIZE);
        s_page = ps > 0 ? (size_t)ps : 4096u;
    }
    return s_page;
}

static int ww_install(void)                /* under s_ww_lock */
{
    if (s_ww_installed) return 1;
    ww_page_size();
    struct sigaction sa;
    memset(&sa, 0, sizeof sa);
    sa.sa_sigaction = ww_fault;
    sa.sa_flags = SA_SIGINFO | SA_ONSTACK;
    sigemptyset(&sa.sa_mask);
    if (sigaction(SIGSEGV, &sa, &s_ww_prev[0]) != 0) return 0;
    if (sigaction(SIGBUS, &sa, &s_ww_prev[1]) != 0) return 0;   /* macOS reports some protection faults as SIGBUS */
    s_ww_installed = 1;
    return 1;
}

int t5p_write_watch_available(void* probe)
{
    /* What the guest reservation must be for ranges in it to be armed. */
    return ((uintptr_t)probe % ww_page_size()) == 0;
}

/* The armed range holding [base, base+len), arming it (all clean, read-only)
 * if it is new. NULL when it cannot be tracked: not host-page aligned, or it
 * overlaps an armed range without lying inside it (a fault is credited to one
 * range only, so overlapping ranges would lose writes). */
static ww_range* ww_range_for(void* base, size_t len)
{
    pthread_mutex_lock(&s_ww_lock);
    ww_range* found = NULL;
    int overlap = 0;
    if (!ww_install()) { pthread_mutex_unlock(&s_ww_lock); return NULL; }
    const uintptr_t b = (uintptr_t)base & ~(uintptr_t)(s_page - 1);
    const uintptr_t e = ((uintptr_t)base + len + s_page - 1) & ~(uintptr_t)(s_page - 1);
    for (int i = 0; i < s_ww_n && !found; i++) {
        const uintptr_t rb = s_ww[i].base, re = rb + s_ww[i].len;
        if (b >= rb && e <= re) found = &s_ww[i];
        else if (b < re && e > rb) overlap = 1;
    }
    if (!found && !overlap && s_ww_n < WW_MAX_RANGES && (uintptr_t)base % s_page == 0) {
        ww_range* r = &s_ww[s_ww_n];
        r->base = b;
        r->len = (size_t)(e - b);
        r->state = (uint8_t*)calloc(r->len / s_page, 1);
        if (r->state && mprotect((void*)r->base, r->len, PROT_READ) == 0) {
            __atomic_store_n(&s_ww_n, s_ww_n + 1, __ATOMIC_RELEASE);
            found = r;
        } else {
            free(r->state);
            r->state = NULL;
        }
    }
    pthread_mutex_unlock(&s_ww_lock);
    return found;
}

/* Protect a run of RESETTING pages, then mark each CLEAN unless a write
 * faulted in between (the fault handler set it DIRTY again). */
static void ww_close_run(ww_range* r, size_t first, size_t count)
{
    if (!count) return;
    mprotect((void*)(r->base + first * s_page), count * s_page, PROT_READ);
    for (size_t k = first; k < first + count; k++) {
        uint8_t expect = WW_RESETTING;
        __atomic_compare_exchange_n(&r->state[k], &expect, (uint8_t)WW_CLEAN, 0, __ATOMIC_ACQ_REL, __ATOMIC_ACQUIRE);
    }
}

int t5p_write_watch(int reset, void* base, size_t len, void** addrs, uintptr_t* count, uint32_t* gran)
{
    ww_range* r = ww_range_for(base, len);
    if (!r) { *count = 0; return 1; }
    const uintptr_t lo = (uintptr_t)base, hi = lo + len;
    const size_t p0 = (size_t)((lo - r->base) / s_page);
    const size_t p1 = (size_t)((hi - r->base + s_page - 1) / s_page);
    const uintptr_t room = *count;
    uintptr_t n = 0;
    size_t run = 0, run_len = 0;          /* consecutive pages moved to RESETTING */
    for (size_t pg = p0; pg < p1; pg++) {
        if (__atomic_load_n(&r->state[pg], __ATOMIC_ACQUIRE) != WW_DIRTY) {
            ww_close_run(r, run, run_len);
            run_len = 0;
            continue;
        }
        /* a dirty host page = its 4 KB pages inside [lo, hi) */
        const uintptr_t page = r->base + pg * s_page;
        uintptr_t first = page < lo ? lo : page;
        const uintptr_t last = page + s_page > hi ? hi : page + s_page;
        first &= ~(uintptr_t)(WW_UNIT - 1);
        const uintptr_t units = (last - first + WW_UNIT - 1) / WW_UNIT;
        if (n + units > room) break;      /* no room: this page and the rest stay DIRTY */
        for (uintptr_t u = first; u < last; u += WW_UNIT) addrs[n++] = (void*)u;
        if (reset) {
            __atomic_store_n(&r->state[pg], (uint8_t)WW_RESETTING, __ATOMIC_RELAXED);
            if (!run_len) run = pg;
            run_len++;
        }
    }
    ww_close_run(r, run, run_len);
    *count = n;
    if (gran) *gran = WW_UNIT;
    return 0;
}

int t5p_write_watch_reset(void* base, size_t len)
{
    ww_range* r = ww_range_for(base, len);
    if (!r) return 1;
    const size_t p0 = (size_t)(((uintptr_t)base - r->base) / s_page);
    const size_t p1 = (size_t)(((uintptr_t)base + len - r->base + s_page - 1) / s_page);
    for (size_t pg = p0; pg < p1; pg++)
        if (__atomic_load_n(&r->state[pg], __ATOMIC_ACQUIRE) == WW_DIRTY)
            __atomic_store_n(&r->state[pg], (uint8_t)WW_RESETTING, __ATOMIC_RELAXED);
    ww_close_run(r, p0, p1 - p0);         /* CLEAN pages stay CLEAN: the CAS only moves RESETTING */
    return 0;
}

void t5p_write_watch_touch(void* addr, size_t len)
{
    /* One atomic "or 0" per host page: a real store (it faults and is
     * recorded on a protected page) that cannot lose another thread's write. */
    if (!__atomic_load_n(&s_ww_n, __ATOMIC_ACQUIRE) || !len) return;
    const uintptr_t step = ww_page_size();
    uintptr_t a = (uintptr_t)addr;
    const uintptr_t e = a + len;
    while (a < e) {
        __atomic_fetch_or((uint8_t*)a, (uint8_t)0, __ATOMIC_RELAXED);
        a = (a & ~(step - 1)) + step;
    }
}

/* ---- patching host code ----------------------------------------------------- */

int t5p_code_patching(void)
{
#if defined(__x86_64__) && defined(__linux__)
    return 1;
#elif defined(__x86_64__) && defined(__APPLE__)
    /* A hardened-runtime (notarized) app may not write its own text pages.
     * Developer builds without it can opt in. */
    const char* e = getenv("T5DR_CODE_PATCH");
    return e && *e == '1';
#else
    return 0;                             /* arm64: the x86 detour does not apply (docs/MACOS.md: lifter hook slots) */
#endif
}

void* t5p_exec_alloc_near(const void* target, size_t size)
{
#if defined(__x86_64__)
    const uintptr_t gran = 0x10000u, t = (uintptr_t)target;
    for (uintptr_t d = gran; d < (1ull << 30); d += gran) {
        for (int s = 0; s < 2; s++) {
            const uintptr_t a = s ? ((t + d) & ~(gran - 1)) : ((t - d) & ~(gran - 1));
            void* p = mmap((void*)a, size, PROT_READ | PROT_WRITE | PROT_EXEC, MAP_PRIVATE | MAP_ANON, -1, 0);
            if (p == MAP_FAILED) continue;
            const intptr_t dist = (intptr_t)((uintptr_t)p - t);
            if (dist < 0x7FFF0000ll && dist > -0x7FFF0000ll) return p;
            munmap(p, size);              /* a hint only: the kernel put it elsewhere */
        }
    }
#else
    (void)target; (void)size;
#endif
    return NULL;
}

void t5p_icache_flush(void* p, size_t n)
{
#if defined(__APPLE__) && defined(__aarch64__)
    sys_icache_invalidate(p, n);
#elif defined(__aarch64__)
    __builtin___clear_cache((char*)p, (char*)p + n);
#else
    (void)p; (void)n;                     /* x86: coherent instruction cache */
#endif
}

int t5p_code_write(void* dst, const void* src, size_t n)
{
    if (!t5p_code_patching()) return 0;
    const uintptr_t ps = (uintptr_t)sysconf(_SC_PAGESIZE);
    const uintptr_t b = (uintptr_t)dst & ~(ps - 1), e = ((uintptr_t)dst + 16 + ps - 1) & ~(ps - 1);
    if (mprotect((void*)b, e - b, PROT_READ | PROT_WRITE | PROT_EXEC) != 0) return 0;
    if (n == 8 && ((uintptr_t)dst & 7) == 0) {
        uint64_t v; memcpy(&v, src, 8);
        __atomic_store_n((uint64_t*)dst, v, __ATOMIC_SEQ_CST);
    } else memcpy(dst, src, n);
    mprotect((void*)b, e - b, PROT_READ | PROT_EXEC);
    t5p_icache_flush(dst, 16);
    return 1;
}

/* ---- FP environment ------------------------------------------------------------ */

uint32_t t5p_fp_control(void)
{
#if defined(__x86_64__)
    uint32_t m;
    __asm__ volatile("stmxcsr %0" : "=m"(m));
    return m & 0xFFC0u;
#elif defined(__aarch64__)
    uint64_t v;
    __asm__ volatile("mrs %0, fpcr" : "=r"(v));
    return (uint32_t)v;                   /* expected 0: nearest, no FZ, no DN, no AH (docs/MACOS.md) */
#else
    return 0;
#endif
}

#endif /* !_WIN32 */
