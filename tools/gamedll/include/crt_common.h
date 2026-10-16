#pragma once
#include <stddef.h>
#ifdef __cplusplus
#define T5_EXTERN_C extern "C"
#define T5_BEGIN extern "C" {
#define T5_END }
#else
#define T5_EXTERN_C
#define T5_BEGIN
#define T5_END
#endif
#define T5_CRT __declspec(dllimport)
