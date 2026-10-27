/* Declaration-only stand-in (tests/test_macos_port.py): names, types and the
 * macOS/glibc differences that matter follow the real headers. Not a libc. */
#pragma once
#include <sys/types.h>
#include <time.h>
struct stat {
    unsigned long long st_dev;
    unsigned long long st_ino;
    mode_t             st_mode;
    unsigned int       st_nlink;
    uid_t              st_uid;
    gid_t              st_gid;
    off_t              st_size;
#if defined(__APPLE__)
    struct timespec    st_atimespec;
    struct timespec    st_mtimespec;
    struct timespec    st_ctimespec;
#  define st_atime st_atimespec.tv_sec
#  define st_mtime st_mtimespec.tv_sec
#  define st_ctime st_ctimespec.tv_sec
#else
    struct timespec    st_atim;
    struct timespec    st_mtim;
    struct timespec    st_ctim;
#  define st_atime st_atim.tv_sec
#  define st_mtime st_mtim.tv_sec
#  define st_ctime st_ctim.tv_sec
#endif
};
#define S_IFMT   0170000
#define S_IFDIR  0040000
#define S_IFREG  0100000
#define S_ISDIR(m) (((m) & S_IFMT) == S_IFDIR)
#define S_ISREG(m) (((m) & S_IFMT) == S_IFREG)
#define S_IRWXU 0000700
#define S_IRUSR 0000400
#define S_IWUSR 0000200
#define S_IXUSR 0000100
#define S_IRWXG 0000070
#define S_IRWXO 0000007
#ifdef __cplusplus
extern "C" {
#endif
int stat(const char* path, struct stat* st);
int lstat(const char* path, struct stat* st);
int fstat(int fd, struct stat* st);
int mkdir(const char* path, mode_t mode);
int chmod(const char* path, mode_t mode);
mode_t umask(mode_t m);
#ifdef __cplusplus
}
#endif
