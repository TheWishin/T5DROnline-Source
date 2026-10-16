/* The little of POSIX threads that ps3recomp's SPU MFC-slot and lock-line
 * tests use (pthread_t, pthread_create, pthread_join, sleep), on Win32, so
 * those tests build with clang-cl. Only tests/run_ps3recomp_tests.py puts this
 * directory on an include path; nothing else uses it. */
#pragma once
#ifndef _WIN32
#error "tests/shim/pthread.h is for Windows only"
#endif
#include <windows.h>
#include <process.h>
#include <stdint.h>
#include <stdlib.h>

typedef HANDLE pthread_t;
typedef int pthread_attr_t;

typedef struct { void* (*fn)(void*); void* arg; } pthread_shim_start_t;

static unsigned __stdcall pthread_shim_entry(void* p)
{
    pthread_shim_start_t s = *(pthread_shim_start_t*)p;
    free(p);
    s.fn(s.arg);
    return 0;
}

static inline int pthread_create(pthread_t* t, const pthread_attr_t* attr, void* (*fn)(void*), void* arg)
{
    (void)attr;
    pthread_shim_start_t* s = (pthread_shim_start_t*)malloc(sizeof *s);
    if (!s) return -1;
    s->fn = fn;
    s->arg = arg;
    uintptr_t h = _beginthreadex(NULL, 0, pthread_shim_entry, s, 0, NULL);
    if (!h) { free(s); return -1; }
    *t = (HANDLE)h;
    return 0;
}

static inline int pthread_join(pthread_t t, void** ret)
{
    DWORD w = WaitForSingleObject(t, INFINITE);
    CloseHandle(t);
    if (ret) *ret = NULL;
    return w == WAIT_OBJECT_0 ? 0 : -1;
}

static inline unsigned sleep(unsigned seconds)
{
    Sleep(seconds * 1000u);
    return 0;
}
