/* Declaration-only stand-in (tests/test_macos_port.py): names, types and the
 * macOS/glibc differences that matter follow the real headers. Not a libc. */
#pragma once
#include <sys/types.h>
#if defined(__APPLE__)
typedef unsigned int sigset_t;
#else
typedef struct { unsigned long __val[16]; } sigset_t;
#endif
typedef int sig_atomic_t;
union sigval { int sival_int; void* sival_ptr; };
typedef struct {
    int   si_signo;
    int   si_errno;
    int   si_code;
    pid_t si_pid;
    uid_t si_uid;
    int   si_status;
    void* si_addr;
    union sigval si_value;
    long  si_band;
    unsigned long __pad[7];
} siginfo_t;
struct sigaction {
    union {
        void (*__sa_handler)(int);
        void (*__sa_sigaction)(int, siginfo_t*, void*);
    } __sigaction_u;
    sigset_t sa_mask;
    int      sa_flags;
};
#define sa_handler   __sigaction_u.__sa_handler
#define sa_sigaction __sigaction_u.__sa_sigaction
typedef struct { void* ss_sp; size_t ss_size; int ss_flags; } stack_t;
#define SIG_DFL ((void (*)(int))0)
#define SIG_IGN ((void (*)(int))1)
#define SIG_ERR ((void (*)(int))-1)
#define SIGHUP  1
#define SIGINT  2
#define SIGQUIT 3
#define SIGILL  4
#define SIGTRAP 5
#define SIGABRT 6
#define SIGFPE  8
#define SIGKILL 9
#define SIGSEGV 11
#define SIGPIPE 13
#define SIGALRM 14
#define SIGTERM 15
#if defined(__APPLE__)
#  define SIGBUS     10
#  define SIGURG     16
#  define SIGUSR1    30
#  define SIGUSR2    31
#  define SA_ONSTACK 0x0001
#  define SA_RESTART 0x0002
#  define SA_RESETHAND 0x0004
#  define SA_NODEFER 0x0010
#  define SA_SIGINFO 0x0040
#  define SIG_BLOCK   1
#  define SIG_UNBLOCK 2
#  define SIG_SETMASK 3
#  define MINSIGSTKSZ 32768
#  define SIGSTKSZ    131072
#  define SS_DISABLE  0x0004
#else
#  define SIGBUS     7
#  define SIGUSR1    10
#  define SIGUSR2    12
#  define SA_ONSTACK 0x08000000
#  define SA_RESTART 0x10000000
#  define SA_RESETHAND 0x80000000
#  define SA_NODEFER 0x40000000
#  define SA_SIGINFO 0x00000004
#  define SIG_BLOCK   0
#  define SIG_UNBLOCK 1
#  define SIG_SETMASK 2
#  define MINSIGSTKSZ 2048
#  define SIGSTKSZ    8192
#  define SS_DISABLE  2
#endif
#ifdef __cplusplus
extern "C" {
#endif
int  sigaction(int sig, const struct sigaction* act, struct sigaction* old);
int  sigemptyset(sigset_t* set);
int  sigfillset(sigset_t* set);
int  sigaddset(sigset_t* set, int sig);
int  sigdelset(sigset_t* set, int sig);
int  sigismember(const sigset_t* set, int sig);
int  sigprocmask(int how, const sigset_t* set, sigset_t* old);
int  pthread_sigmask(int how, const sigset_t* set, sigset_t* old);
int  sigaltstack(const stack_t* ss, stack_t* old);
int  raise(int sig);
int  kill(pid_t pid, int sig);
void (*signal(int sig, void (*fn)(int)))(int);
#ifdef __cplusplus
}
#endif
