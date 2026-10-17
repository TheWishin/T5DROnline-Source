/* Instrumented (T5DR_PGO=gen) builds only: clang_rt.profile is built against the
 * static CRT and calls plain getenv; this /MD build has only the import
 * (__imp_getenv, which boot_main.cpp redirects to its env cache). */
extern char* (*__imp_getenv)(const char*);
char* getenv(const char* name) { return __imp_getenv(name); }
