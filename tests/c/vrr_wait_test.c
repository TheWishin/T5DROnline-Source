/* Fake OS backend exercises the exact Windows wait wrapper without a game,
 * Windows SDK, wall-clock sleeping, or a device. */
#define _WIN32 1
#include <assert.h>
#include <stddef.h>
#include <stdio.h>
#include "host_pacer_win.h"

static int64_t now_us, timer_due;
static int fail_high_res, fail_all, fail_arm, early_events, calls, closes;
static volatile LONG* cancel_after_wait;
HANDLE CreateWaitableTimerExW(void* a, void* b, DWORD c, DWORD d)
{ (void)a; (void)b; (void)c; (void)d; return fail_high_res || fail_all ? NULL : (HANDLE)1; }
HANDLE CreateWaitableTimerW(void* a, int b, void* c)
{ (void)a; (void)b; (void)c; return fail_all ? NULL : (HANDLE)1; }
int CloseHandle(HANDLE h) { (void)h; closes++; return 1; }
int QueryPerformanceCounter(LARGE_INTEGER* q) { q->QuadPart = now_us++; return 1; }
LONG InterlockedCompareExchange(volatile LONG* p, LONG x, LONG old)
{ LONG v = *p; if (v == old) *p = x; return v; }
int SetWaitableTimer(HANDLE h, const LARGE_INTEGER* d, LONG p, void* a, void* b, int c)
{
    (void)h; (void)p; (void)a; (void)b; (void)c;
    assert(d->QuadPart < 0); /* QPC never passed as a positive Windows date */
    assert(d->QuadPart >= -40000); /* service/cancellation ceiling */
    timer_due = now_us + (-d->QuadPart + 9) / 10;
    return !fail_arm;
}
int CancelWaitableTimer(HANDLE h) { (void)h; return 1; }
DWORD WaitForMultipleObjects(DWORD n, const HANDLE* h, int all, DWORD ms)
{
    (void)h; (void)all; (void)ms; calls++;
    if (cancel_after_wait) { ++*cancel_after_wait; cancel_after_wait = NULL; }
    if (n == 2 && early_events > 0) { early_events--; now_us += 50; return WAIT_OBJECT_0 + 1; }
    now_us = timer_due; return WAIT_OBJECT_0;
}
DWORD WaitForSingleObject(HANDLE h, DWORD ms) { (void)h; now_us += ms * 1000; return WAIT_OBJECT_0; }
void Sleep(DWORD ms) { now_us += ms * 1000; }
static void reset(void)
{
    hp_wait_close(); now_us = timer_due = 0;
    fail_high_res = fail_all = fail_arm = early_events = calls = 0;
    cancel_after_wait = NULL;
}
int main(void)
{
    reset(); early_events = 100;
    const int64_t deadline = 16683;
    while (now_us < deadline)
        hp_wait_until_qpc(deadline, 1000000, (HANDLE)2, NULL, 0, 0, 1);
    assert(now_us - deadline < 10); assert(calls > 100); /* early wakes preserve deadline */
    reset(); fail_high_res = 1;
    hp_wait_result r = hp_wait_until_qpc(8000, 1000000, NULL, NULL, 0, 0, 0);
    assert(r.fallback && now_us >= 8000); /* ordinary timer fallback */
    reset(); fail_all = 1;
    r = hp_wait_until_qpc(8000, 1000000, NULL, NULL, 0, 0, 0);
    assert(r.fallback && now_us >= 8000 && now_us < 9100);
    reset(); fail_arm = 1;
    r = hp_wait_until_qpc(3000, 1000000, NULL, NULL, 0, 0, 0);
    assert(r.fallback && now_us >= 3000);
    reset(); volatile LONG generation = 3; cancel_after_wait = &generation;
    hp_wait_until_qpc(1000000, 1000000, NULL, &generation, 3, 0, 0);
    assert(generation == 4 && now_us < 5000); /* reset/shutdown cancels wait */
    reset(); hp_wait_until_qpc(1000, 1000000, NULL, NULL, 0, 2000, 0);
    assert(now_us >= 1000 && now_us < 1100); /* spin bounded to 200 us */
    hp_wait_close(); assert(closes > 0);
    puts("PASS: early events, one-shot relative timer, fallback, cancellation, bounded spin");
    return 0;
}
