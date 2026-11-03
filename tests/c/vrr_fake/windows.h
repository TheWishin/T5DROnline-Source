#ifndef VRR_FAKE_WINDOWS_H
#define VRR_FAKE_WINDOWS_H
#include <stdint.h>
typedef void* HANDLE;
typedef int32_t LONG;
typedef uint32_t DWORD;
typedef int64_t LONGLONG;
typedef struct { LONGLONG QuadPart; } LARGE_INTEGER;
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
