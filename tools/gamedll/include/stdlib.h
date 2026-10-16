#pragma once
#include "crt_common.h"
T5_BEGIN
T5_CRT int atoi(const char*);
T5_CRT long strtol(const char*, char**, int);
T5_CRT unsigned long strtoul(const char*, char**, int);
T5_CRT unsigned long long strtoull(const char*, char**, int);
T5_CRT char* getenv(const char*);
T5_CRT void* malloc(size_t);
T5_CRT void* calloc(size_t, size_t);
T5_CRT void* realloc(void*, size_t);
T5_CRT void free(void*);
T5_CRT __declspec(noreturn) void abort(void);
T5_CRT __declspec(noreturn) void exit(int);
unsigned short _byteswap_ushort(unsigned short);
unsigned long _byteswap_ulong(unsigned long);
unsigned long long _byteswap_uint64(unsigned long long);
unsigned int _rotl(unsigned int, int);
unsigned int _rotr(unsigned int, int);
unsigned long long _rotl64(unsigned long long, int);
unsigned long long _rotr64(unsigned long long, int);
int abs(int);
long long llabs(long long);
T5_END
