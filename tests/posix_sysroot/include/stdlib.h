/* Declaration-only stand-in (tests/test_macos_port.py): names, types and the
 * macOS/glibc differences that matter follow the real headers. Not a libc. */
#pragma once
#include <stddef.h>
#if defined(__APPLE__)
#  include <alloca.h>
#  include <stdint.h>
#endif
#define EXIT_SUCCESS 0
#define EXIT_FAILURE 1
#define RAND_MAX 0x7fffffff
typedef struct { int quot, rem; } div_t;
typedef struct { long quot, rem; } ldiv_t;
#ifdef __cplusplus
extern "C" {
#endif
void*  malloc(size_t n);
void*  calloc(size_t n, size_t sz);
void*  realloc(void* p, size_t n);
void   free(void* p);
int    posix_memalign(void** p, size_t align, size_t n);
void*  aligned_alloc(size_t align, size_t n);
char*  getenv(const char* name);
int    setenv(const char* name, const char* value, int overwrite);
int    unsetenv(const char* name);
int    putenv(char* s);
int    atoi(const char* s);
long   atol(const char* s);
long long atoll(const char* s);
double atof(const char* s);
long   strtol(const char* s, char** end, int base);
unsigned long strtoul(const char* s, char** end, int base);
long long strtoll(const char* s, char** end, int base);
unsigned long long strtoull(const char* s, char** end, int base);
double strtod(const char* s, char** end);
float  strtof(const char* s, char** end);
int    abs(int v);
long   labs(long v);
long long llabs(long long v);
div_t  div(int a, int b);
int    rand(void);
void   srand(unsigned s);
void   qsort(void* base, size_t n, size_t sz, int (*cmp)(const void*, const void*));
void*  bsearch(const void* key, const void* base, size_t n, size_t sz, int (*cmp)(const void*, const void*));
int    system(const char* cmd);
char*  realpath(const char* path, char* resolved);
int    mkstemp(char* tmpl);
char*  mkdtemp(char* tmpl);
int    atexit(void (*fn)(void));
void   exit(int code) __attribute__((noreturn));
void   _Exit(int code) __attribute__((noreturn));
void   abort(void) __attribute__((noreturn));
size_t mbstowcs(wchar_t* d, const char* s, size_t n);
size_t wcstombs(char* d, const wchar_t* s, size_t n);
#if defined(__APPLE__)
uint32_t arc4random(void);
void     arc4random_buf(void* buf, size_t n);
uint32_t arc4random_uniform(uint32_t upper);
#endif
#ifdef __cplusplus
}
#endif
