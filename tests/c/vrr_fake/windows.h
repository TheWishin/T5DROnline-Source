#ifndef VRR_FAKE_WINDOWS_H
#define VRR_FAKE_WINDOWS_H
#include <stdint.h>
typedef void* HANDLE;
typedef int32_t LONG;
typedef uint32_t DWORD;
typedef int64_t LONGLONG;
typedef struct { LONGLONG QuadPart; } LARGE_INTEGER;
/* The fakes get their own link names. With mingw-w64 gcc 15.2 (GitHub's
 * windows-2025 image, 2026-11) the default libraries pull kernel32's import
 * member for Sleep, and a fake named Sleep then fails to link: "multiple
 * definition of `Sleep'". The header under test and the fakes in
 * vrr_wait_test.c both see these macros, so the test still drives every call. */
#define CreateWaitableTimerExW vrr_fake_CreateWaitableTimerExW
#define CreateWaitableTimerW vrr_fake_CreateWaitableTimerW
#define CloseHandle vrr_fake_CloseHandle
#define QueryPerformanceCounter vrr_fake_QueryPerformanceCounter
#define InterlockedCompareExchange vrr_fake_InterlockedCompareExchange
#define SetWaitableTimer vrr_fake_SetWaitableTimer
#define CancelWaitableTimer vrr_fake_CancelWaitableTimer
#define WaitForMultipleObjects vrr_fake_WaitForMultipleObjects
#define WaitForSingleObject vrr_fake_WaitForSingleObject
#define Sleep vrr_fake_Sleep
#define FALSE 0
#define TIMER_ALL_ACCESS 0
#define WAIT_OBJECT_0 0u
#define WAIT_FAILED 0xffffffffu
HANDLE CreateWaitableTimerExW(void*, void*, DWORD, DWORD);
HANDLE CreateWaitableTimerW(void*, int, void*);
int CloseHandle(HANDLE);
int QueryPerformanceCounter(LARGE_INTEGER*);
LONG InterlockedCompareExchange(volatile LONG*, LONG, LONG);
int SetWaitableTimer(HANDLE, const LARGE_INTEGER*, LONG, void*, void*, int);
int CancelWaitableTimer(HANDLE);
DWORD WaitForMultipleObjects(DWORD, const HANDLE*, int, DWORD);
DWORD WaitForSingleObject(HANDLE, DWORD);
void Sleep(DWORD);
#endif
