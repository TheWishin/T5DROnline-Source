#pragma once
#include "crt_common.h"
#include <stdarg.h>
T5_BEGIN
typedef struct _iobuf { void* _Placeholder; } FILE;
T5_CRT FILE* __acrt_iob_func(unsigned);
#define stdin  (__acrt_iob_func(0))
#define stdout (__acrt_iob_func(1))
#define stderr (__acrt_iob_func(2))
#define EOF (-1)
T5_CRT int __stdio_common_vfprintf(unsigned long long, FILE*, const char*, void*, va_list);
T5_CRT int __stdio_common_vsprintf(unsigned long long, char*, size_t, const char*, void*, va_list);
T5_CRT int fflush(FILE*);
T5_CRT int fputc(int, FILE*);
T5_CRT int fputs(const char*, FILE*);
T5_CRT int puts(const char*);
T5_CRT size_t fwrite(const void*, size_t, size_t, FILE*);
static __inline int vfprintf(FILE* f, const char* fmt, va_list ap) { return __stdio_common_vfprintf(0, f, fmt, 0, ap); }
static __inline int vprintf(const char* fmt, va_list ap) { return vfprintf(stdout, fmt, ap); }
static __inline int fprintf(FILE* f, const char* fmt, ...) { va_list ap; va_start(ap, fmt); int r = vfprintf(f, fmt, ap); va_end(ap); return r; }
static __inline int printf(const char* fmt, ...) { va_list ap; va_start(ap, fmt); int r = vfprintf(stdout, fmt, ap); va_end(ap); return r; }
static __inline int vsnprintf(char* b, size_t n, const char* fmt, va_list ap) { int r = __stdio_common_vsprintf(2, b, n, fmt, 0, ap); return r < 0 ? -1 : r; }
static __inline int snprintf(char* b, size_t n, const char* fmt, ...) { va_list ap; va_start(ap, fmt); int r = vsnprintf(b, n, fmt, ap); va_end(ap); return r; }
static __inline int putchar(int c) { return fputc(c, stdout); }
T5_END
