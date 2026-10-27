/* Declaration-only stand-in (tests/test_macos_port.py): names, types and the
 * macOS/glibc differences that matter follow the real headers. Not a libc. */
#pragma once
#include <sys/types.h>
#if defined(__APPLE__)
struct dirent { unsigned long long d_ino; unsigned long long d_seekoff; unsigned short d_reclen; unsigned short d_namlen; unsigned char d_type; char d_name[1024]; };
#else
struct dirent { unsigned long d_ino; long d_off; unsigned short d_reclen; unsigned char d_type; char d_name[256]; };
#endif
#define DT_DIR 4
#define DT_REG 8
typedef struct __dirstream DIR;
#ifdef __cplusplus
extern "C" {
#endif
DIR* opendir(const char* path);
struct dirent* readdir(DIR* d);
int closedir(DIR* d);
#ifdef __cplusplus
}
#endif
