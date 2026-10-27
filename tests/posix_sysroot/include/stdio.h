/* Declaration-only stand-in (tests/test_macos_port.py): names, types and the
 * macOS/glibc differences that matter follow the real headers. Not a libc. */
#pragma once
#include <stddef.h>
#include <stdarg.h>
#include <sys/types.h>
typedef struct __sFILE FILE;
typedef off_t fpos_t;
#define EOF (-1)
#define BUFSIZ 1024
#define FILENAME_MAX 1024
#define SEEK_SET 0
#define SEEK_CUR 1
#define SEEK_END 2
#define _IOFBF 0
#define _IOLBF 1
#define _IONBF 2
#ifdef __cplusplus
extern "C" {
#endif
#if defined(__APPLE__)
extern FILE* __stdinp;
extern FILE* __stdoutp;
extern FILE* __stderrp;
#  define stdin  __stdinp
#  define stdout __stdoutp
#  define stderr __stderrp
#else
extern FILE* stdin;
extern FILE* stdout;
extern FILE* stderr;
#endif
int    fflush(FILE* f);
FILE*  fopen(const char* path, const char* mode);
FILE*  freopen(const char* path, const char* mode, FILE* f);
FILE*  fdopen(int fd, const char* mode);
int    fclose(FILE* f);
size_t fread(void* p, size_t sz, size_t n, FILE* f);
size_t fwrite(const void* p, size_t sz, size_t n, FILE* f);
char*  fgets(char* s, int n, FILE* f);
int    fputs(const char* s, FILE* f);
int    puts(const char* s);
int    fputc(int c, FILE* f);
int    putc(int c, FILE* f);
int    putchar(int c);
int    fgetc(FILE* f);
int    getc(FILE* f);
int    getchar(void);
int    ungetc(int c, FILE* f);
int    fseek(FILE* f, long off, int whence);
long   ftell(FILE* f);
int    fseeko(FILE* f, off_t off, int whence);
off_t  ftello(FILE* f);
void   rewind(FILE* f);
int    feof(FILE* f);
int    ferror(FILE* f);
void   clearerr(FILE* f);
int    fileno(FILE* f);
int    setvbuf(FILE* f, char* buf, int mode, size_t n);
void   setbuf(FILE* f, char* buf);
int    printf(const char* fmt, ...) __attribute__((format(printf, 1, 2)));
int    fprintf(FILE* f, const char* fmt, ...) __attribute__((format(printf, 2, 3)));
int    sprintf(char* b, const char* fmt, ...) __attribute__((format(printf, 2, 3)));
int    snprintf(char* b, size_t n, const char* fmt, ...) __attribute__((format(printf, 3, 4)));
int    vprintf(const char* fmt, va_list ap);
int    vfprintf(FILE* f, const char* fmt, va_list ap);
int    vsprintf(char* b, const char* fmt, va_list ap);
int    vsnprintf(char* b, size_t n, const char* fmt, va_list ap);
int    scanf(const char* fmt, ...);
int    fscanf(FILE* f, const char* fmt, ...);
int    sscanf(const char* s, const char* fmt, ...);
int    vsscanf(const char* s, const char* fmt, va_list ap);
void   perror(const char* s);
int    rename(const char* from, const char* to);
int    remove(const char* path);
FILE*  tmpfile(void);
FILE*  popen(const char* cmd, const char* mode);
int    pclose(FILE* f);
ssize_t getline(char** line, size_t* cap, FILE* f);
#ifdef __cplusplus
}
#endif
