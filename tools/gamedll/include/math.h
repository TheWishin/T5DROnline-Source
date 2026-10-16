/* Minimal <math.h> for the header-free game DLL build (tools/build_game_dll.py).
 * Our own declarations of the C functions; they resolve to ucrtbase.dll, which is
 * part of Windows 10/11. Functions ucrtbase does not export are inline here. */
#pragma once
#include "crt_common.h"
T5_BEGIN
#define INFINITY __builtin_inff()
#define NAN __builtin_nanf("")
#define HUGE_VAL __builtin_huge_val()
#define HUGE_VALF __builtin_huge_valf()
#define isnan(x) __builtin_isnan(x)
#define isinf(x) __builtin_isinf(x)
#define isfinite(x) __builtin_isfinite(x)
#define isnormal(x) __builtin_isnormal(x)
#define signbit(x) __builtin_signbit(x)
#define fpclassify(x) __builtin_fpclassify(FP_NAN, FP_INFINITE, FP_NORMAL, FP_SUBNORMAL, FP_ZERO, x)
#define FP_NAN 2
#define FP_INFINITE 1
#define FP_ZERO 0
#define FP_SUBNORMAL (-2)
#define FP_NORMAL (-1)
#define T5_M1(n) T5_CRT double n(double); T5_CRT float n##f(float);
#define T5_M2(n) T5_CRT double n(double, double); T5_CRT float n##f(float, float);
T5_M1(sqrt) T5_M1(floor) T5_M1(ceil) T5_M1(trunc) T5_M1(round) T5_M1(rint) T5_M1(nearbyint)
T5_M1(exp) T5_M1(exp2) T5_M1(log) T5_M1(log2) T5_M1(log10) T5_M1(sin) T5_M1(cos) T5_M1(tan)
T5_M1(asin) T5_M1(acos) T5_M1(atan) T5_M1(sinh) T5_M1(cosh) T5_M1(tanh) T5_M1(cbrt)
T5_M2(pow) T5_M2(fmod) T5_M2(atan2) T5_M2(fmin) T5_M2(fmax) T5_M2(copysign) T5_M2(remainder) T5_M2(hypot)
T5_CRT double fma(double, double, double); T5_CRT float fmaf(float, float, float);
T5_CRT double ldexp(double, int);
T5_CRT double frexp(double, int*); T5_CRT float frexpf(float, int*);
T5_CRT long lrint(double); T5_CRT long lrintf(float);
T5_CRT long long llrint(double); T5_CRT long long llrintf(float);
T5_CRT long lround(double); T5_CRT long lroundf(float);
T5_CRT double modf(double, double*); T5_CRT float modff(float, float*);
static __inline double fabs(double x) { return __builtin_fabs(x); }
static __inline float fabsf(float x) { return __builtin_fabsf(x); }
static __inline float ldexpf(float x, int e) { return (float)ldexp(x, e); }
T5_END
