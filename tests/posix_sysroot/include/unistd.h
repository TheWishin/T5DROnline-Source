/* Declaration-only stand-in (tests/test_macos_port.py): names, types and the
 * macOS/glibc differences that matter follow the real headers. Not a libc. */
#pragma once
#include <sys/types.h>
#if defined(__APPLE__)
#  define _SC_PAGESIZE 29
#  define _SC_NPROCESSORS_CONF 57
#  define _SC_NPROCESSORS_ONLN 58
#else
#  define _SC_PAGESIZE 30
#  define _SC_NPROCESSORS_CONF 83
#  define _SC_NPROCESSORS_ONLN 84
#endif
#define _SC_PAGE_SIZE _SC_PAGESIZE
#define F_OK 0
#define X_OK 1
#define W_OK 2
#define R_OK 4
#define STDIN_FILENO 0
#define STDOUT_FILENO 1
#define STDERR_FILENO 2
#ifdef __cplusplus
extern "C" {
#endif
ssize_t read(int fd, void* buf, size_t n);
ssize_t write(int fd, const void* buf, size_t n);
ssize_t pread(int fd, void* buf, size_t n, off_t off);
ssize_t pwrite(int fd, const void* buf, size_t n, off_t off);
off_t   lseek(int fd, off_t off, int whence);
int     close(int fd);
int     dup(int fd);
int     dup2(int a, int b);
int     pipe(int fds[2]);
int     fsync(int fd);
int     ftruncate(int fd, off_t n);
void    _exit(int code) __attribute__((noreturn));
long    sysconf(int name);
pid_t   getpid(void);
pid_t   getppid(void);
pid_t   fork(void);
int     execv(const char* path, char* const argv[]);
int     execvp(const char* file, char* const argv[]);
unsigned sleep(unsigned s);
int     usleep(unsigned int usec);
int     unlink(const char* path);
int     rmdir(const char* path);
int     access(const char* path, int mode);
int     chdir(const char* path);
char*   getcwd(char* buf, size_t n);
int     isatty(int fd);
int     gethostname(char* name, size_t n);
int     link(const char* a, const char* b);
int     symlink(const char* a, const char* b);
ssize_t readlink(const char* path, char* buf, size_t n);
uid_t   getuid(void);
#if defined(__APPLE__)
int     syscall(int n, ...);
#else
long    syscall(long n, ...);
#endif
#ifdef __cplusplus
}
#endif
