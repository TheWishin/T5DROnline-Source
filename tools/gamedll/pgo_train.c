/* Instrumented training builds only (build_game_dll.py --pgo-gen, tools/pgo_train.py); never in a
 * player's DLL. LLVM's profile runtime (clang_rt.profile) is linked into the DLL, which has no C
 * runtime start-up: its static initializer runs from ppu_game_init like every other one, it may not
 * register an exit handler, and the game is ended by the training script, not by exit(). So the
 * counters are written when the script asks: T5_PGO_TRIGGER=<prefix>; a file <prefix>.write makes
 * this thread write the profile (LLVM_PROFILE_FILE names it) and answer with <prefix>.write.ok,
 * <prefix>.reset zeroes the counters (<prefix>.reset.ok). */
#include <stdint.h>
#include <stddef.h>

int  __llvm_profile_write_file(void);
void __llvm_profile_reset_counters(void);
char* getenv(const char*);

__declspec(dllimport) void* __stdcall CreateThread(void*, size_t, unsigned long (__stdcall*)(void*), void*,
                                                   unsigned long, unsigned long*);
__declspec(dllimport) void __stdcall Sleep(unsigned long);
__declspec(dllimport) unsigned long __stdcall GetFileAttributesA(const char*);
__declspec(dllimport) int __stdcall DeleteFileA(const char*);
__declspec(dllimport) void* __stdcall CreateFileA(const char*, unsigned long, unsigned long, void*, unsigned long,
                                                  unsigned long, void*);
__declspec(dllimport) int __stdcall CloseHandle(void*);

/* the profile runtime's initializer registers its own atexit writer; nothing runs at exit here */
int atexit(void (*fn)(void)) { (void)fn; return 0; }

/* what the profile runtime (built for the static C runtime) takes from the C runtime's static part
 * and from oldnames.lib, which this DLL does not link */
void* malloc(size_t);
void abort(void);
int _fileno(void*);
__declspec(dllimport) unsigned long __stdcall GetCurrentProcessId(void);
uintptr_t __security_cookie = 0x2B992DDFA232ull;
void __security_check_cookie(uintptr_t c) { if (c != __security_cookie) abort(); }
int getpid(void) { return (int)GetCurrentProcessId(); }
int fileno(void* f) { return _fileno(f); }
char* strdup(const char* s)
{
    size_t n = 0;
    while (s[n]) n++;
    char* d = (char*)malloc(n + 1);
    if (d) for (size_t i = 0; i <= n; i++) d[i] = s[i];
    return d;
}
char* strrchr(const char* s, int c)
{
    const char* last = 0;
    for (;; s++) {
        if (*s == (char)c) last = s;
        if (!*s) return (char*)last;
    }
}

static char s_prefix[512];

static void path_of(char* p, const char* what, const char* ok)    /* <prefix>.<what><ok> */
{
    size_t n = 0;
    for (const char* s = s_prefix; *s && n < 560; ) p[n++] = *s++;
    p[n++] = '.';
    for (const char* s = what; *s; ) p[n++] = *s++;
    for (const char* s = ok; *s; ) p[n++] = *s++;
    p[n] = 0;
}

static int take(const char* what)
{
    char p[600];
    path_of(p, what, "");
    if (GetFileAttributesA(p) == 0xFFFFFFFFu) return 0;
    DeleteFileA(p);
    return 1;
}

static void answer(const char* what)
{
    char p[600];
    path_of(p, what, ".ok");
    void* h = CreateFileA(p, 0x40000000u /* GENERIC_WRITE */, 0, 0, 2 /* CREATE_ALWAYS */, 0x80, 0);
    if (h && h != (void*)(intptr_t)-1) CloseHandle(h);
}

__declspec(dllexport) int t5dr_pgo_write(void) { return __llvm_profile_write_file(); }

static unsigned long __stdcall watcher(void* unused)
{
    (void)unused;
    for (;;) {
        Sleep(50);
        if (take("reset")) { __llvm_profile_reset_counters(); answer("reset"); }
        if (take("write")) { __llvm_profile_write_file(); answer("write"); }
    }
}

/* a static constructor: ppu_game_init runs it with the others (.CRT$XCU) */
__attribute__((constructor)) static void pgo_train_start(void)
{
    const char* p = getenv("T5_PGO_TRIGGER");
    if (!p || !*p) return;
    size_t n = 0;
    while (p[n] && n < 500) { s_prefix[n] = p[n]; n++; }
    s_prefix[n] = 0;
    CreateThread(0, 0, watcher, 0, 0, 0);
}
