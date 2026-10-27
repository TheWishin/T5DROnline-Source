/* Declaration-only stand-in (tests/test_macos_port.py): names, types and the
 * macOS/glibc differences that matter follow the real headers. Not a libc. */
#pragma once
#define signbit(x)  __builtin_signbit(x)
#define isnan(x)    __builtin_isnan(x)
#define isinf(x)    __builtin_isinf(x)
#define isfinite(x) __builtin_isfinite(x)
#define isnormal(x) __builtin_isnormal(x)
#define NAN         __builtin_nanf("")
#define INFINITY    __builtin_inff()
#define HUGE_VAL    __builtin_huge_val()
#define HUGE_VALF   __builtin_huge_valf()
#define M_PI        3.14159265358979323846
#define M_PI_2      1.57079632679489661923
#define M_SQRT2     1.41421356237309504880
#define M_LN2       0.69314718055994530942
#define M_E         2.71828182845904523536
#ifdef __cplusplus
extern "C" {
#endif
#define T5_MATH1(n) double n(double x); float n##f(float x);
T5_MATH1(sqrt) T5_MATH1(fabs) T5_MATH1(floor) T5_MATH1(ceil) T5_MATH1(trunc) T5_MATH1(nearbyint) T5_MATH1(rint)
T5_MATH1(round) T5_MATH1(exp) T5_MATH1(exp2) T5_MATH1(log) T5_MATH1(log2) T5_MATH1(log10) T5_MATH1(sin) T5_MATH1(cos)
T5_MATH1(tan) T5_MATH1(asin) T5_MATH1(acos) T5_MATH1(atan) T5_MATH1(sinh) T5_MATH1(cosh) T5_MATH1(tanh) T5_MATH1(cbrt)
#undef T5_MATH1
double fma(double x, double y, double z); float fmaf(float x, float y, float z);
double ldexp(double x, int e); float ldexpf(float x, int e);
double frexp(double x, int* e); float frexpf(float x, int* e);
double modf(double x, double* i); float modff(float x, float* i);
double pow(double x, double y); float powf(float x, float y);
double atan2(double y, double x); float atan2f(float y, float x);
double fmod(double x, double y); float fmodf(float x, float y);
double hypot(double x, double y); float hypotf(float x, float y);
double fmin(double x, double y); float fminf(float x, float y);
double fmax(double x, double y); float fmaxf(float x, float y);
double copysign(double x, double y); float copysignf(float x, float y);
long lround(double x); long lroundf(float x);
long long llround(double x); long long llroundf(float x);
long lrint(double x); long lrintf(float x);
#ifdef __cplusplus
}
#endif
