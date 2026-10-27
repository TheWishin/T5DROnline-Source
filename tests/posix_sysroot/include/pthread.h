/* Declaration-only stand-in (tests/test_macos_port.py): names, types and the
 * macOS/glibc differences that matter follow the real headers. Not a libc. */
#pragma once
#include <sys/types.h>
#include <time.h>
#include <sched.h>
#if defined(__APPLE__)
typedef struct { long __sig; char __opaque[56]; } pthread_mutex_t;
typedef struct { long __sig; char __opaque[8]; } pthread_mutexattr_t;
typedef struct { long __sig; char __opaque[40]; } pthread_cond_t;
typedef struct { long __sig; char __opaque[8]; } pthread_condattr_t;
typedef struct { long __sig; char __opaque[192]; } pthread_rwlock_t;
typedef struct { long __sig; char __opaque[16]; } pthread_rwlockattr_t;
typedef struct { long __sig; char __opaque[8]; } pthread_once_t;
typedef struct { long __sig; char __opaque[56]; } pthread_attr_t;
typedef struct _opaque_pthread_t* pthread_t;
typedef unsigned long pthread_key_t;
typedef unsigned int mach_port_t;
#  define PTHREAD_MUTEX_INITIALIZER {0x32AAABA7, {0}}
#  define PTHREAD_COND_INITIALIZER {0x3CB0B1BB, {0}}
#  define PTHREAD_RWLOCK_INITIALIZER {0x2DA8B3B4, {0}}
#  define PTHREAD_ONCE_INIT {0x30B1BCBA, {0}}
#else
typedef union { char __size[40]; long __align; } pthread_mutex_t;
typedef union { char __size[4]; int __align; } pthread_mutexattr_t;
typedef union { char __size[48]; long long __align; } pthread_cond_t;
typedef union { char __size[4]; int __align; } pthread_condattr_t;
typedef union { char __size[56]; long __align; } pthread_rwlock_t;
typedef union { char __size[8]; long __align; } pthread_rwlockattr_t;
typedef int pthread_once_t;
typedef union { char __size[56]; long __align; } pthread_attr_t;
typedef unsigned long pthread_t;
typedef unsigned int pthread_key_t;
#  define PTHREAD_MUTEX_INITIALIZER { { 0 } }
#  define PTHREAD_COND_INITIALIZER { { 0 } }
#  define PTHREAD_RWLOCK_INITIALIZER { { 0 } }
#  define PTHREAD_ONCE_INIT 0
#endif
#define PTHREAD_MUTEX_NORMAL     0
#define PTHREAD_MUTEX_ERRORCHECK 1
#define PTHREAD_MUTEX_RECURSIVE  2
#define PTHREAD_MUTEX_DEFAULT    PTHREAD_MUTEX_NORMAL
#define PTHREAD_CREATE_JOINABLE  1
#define PTHREAD_CREATE_DETACHED  2
#ifdef __cplusplus
extern "C" {
#endif
int pthread_create(pthread_t* t, const pthread_attr_t* a, void* (*fn)(void*), void* arg);
int pthread_join(pthread_t t, void** ret);
int pthread_detach(pthread_t t);
pthread_t pthread_self(void);
int pthread_equal(pthread_t a, pthread_t b);
void pthread_exit(void* ret) __attribute__((noreturn));
int pthread_kill(pthread_t t, int sig);
int pthread_attr_init(pthread_attr_t* a);
int pthread_attr_destroy(pthread_attr_t* a);
int pthread_attr_setstacksize(pthread_attr_t* a, size_t n);
int pthread_attr_getstacksize(const pthread_attr_t* a, size_t* n);
int pthread_attr_setdetachstate(pthread_attr_t* a, int s);
int pthread_mutex_init(pthread_mutex_t* m, const pthread_mutexattr_t* a);
int pthread_mutex_destroy(pthread_mutex_t* m);
int pthread_mutex_lock(pthread_mutex_t* m);
int pthread_mutex_trylock(pthread_mutex_t* m);
int pthread_mutex_unlock(pthread_mutex_t* m);
int pthread_mutexattr_init(pthread_mutexattr_t* a);
int pthread_mutexattr_destroy(pthread_mutexattr_t* a);
int pthread_mutexattr_settype(pthread_mutexattr_t* a, int type);
int pthread_cond_init(pthread_cond_t* c, const pthread_condattr_t* a);
int pthread_cond_destroy(pthread_cond_t* c);
int pthread_cond_wait(pthread_cond_t* c, pthread_mutex_t* m);
int pthread_cond_timedwait(pthread_cond_t* c, pthread_mutex_t* m, const struct timespec* abs);
int pthread_cond_signal(pthread_cond_t* c);
int pthread_cond_broadcast(pthread_cond_t* c);
int pthread_condattr_init(pthread_condattr_t* a);
int pthread_condattr_destroy(pthread_condattr_t* a);
int pthread_rwlock_init(pthread_rwlock_t* l, const pthread_rwlockattr_t* a);
int pthread_rwlock_destroy(pthread_rwlock_t* l);
int pthread_rwlock_rdlock(pthread_rwlock_t* l);
int pthread_rwlock_tryrdlock(pthread_rwlock_t* l);
int pthread_rwlock_wrlock(pthread_rwlock_t* l);
int pthread_rwlock_trywrlock(pthread_rwlock_t* l);
int pthread_rwlock_unlock(pthread_rwlock_t* l);
int pthread_key_create(pthread_key_t* k, void (*dtor)(void*));
int pthread_key_delete(pthread_key_t k);
void* pthread_getspecific(pthread_key_t k);
int pthread_setspecific(pthread_key_t k, const void* v);
int pthread_once(pthread_once_t* o, void (*fn)(void));
int pthread_setschedparam(pthread_t t, int policy, const struct sched_param* p);
int pthread_getschedparam(pthread_t t, int* policy, struct sched_param* p);
#if defined(__APPLE__)
int pthread_setname_np(const char* name);
int pthread_getname_np(pthread_t t, char* name, size_t n);
int pthread_threadid_np(pthread_t t, uint64_t* id);
mach_port_t pthread_mach_thread_np(pthread_t t);
void* pthread_get_stackaddr_np(pthread_t t);
size_t pthread_get_stacksize_np(pthread_t t);
#else
int pthread_setname_np(pthread_t t, const char* name);
int pthread_getname_np(pthread_t t, char* name, size_t n);
#endif
#ifdef __cplusplus
}
#endif
