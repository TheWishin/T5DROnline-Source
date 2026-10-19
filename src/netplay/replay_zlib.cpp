/*
 * zlib streams for the replay files (src/netplay/replay.cpp): stb_image_write's
 * deflate and stb_image's inflate (public domain / MIT, ps3recomp libs/codec),
 * compiled here as static copies so nothing depends on which runtime object
 * happens to be linked. Python's zlib reads and writes the same streams
 * (launcher/replays.py).
 */
#include <stdlib.h>
#include <string.h>

#if defined(__clang__)
#pragma clang diagnostic push
#pragma clang diagnostic ignored "-Wunused-function"
#pragma clang diagnostic ignored "-Wunused-but-set-variable"
#pragma clang diagnostic ignored "-Wsign-compare"
#pragma clang diagnostic ignored "-Wdeprecated-declarations"
#endif
#define STB_IMAGE_WRITE_STATIC
#define STB_IMAGE_WRITE_IMPLEMENTATION
#define STBIW_ASSERT(x)
#define STBI_WRITE_NO_STDIO
#include "stb_image_write.h"

#define STB_IMAGE_STATIC
#define STB_IMAGE_IMPLEMENTATION
#define STBI_ONLY_PNG
#define STBI_NO_STDIO
#define STBI_NO_LINEAR
#define STBI_NO_HDR
#define STBI_ASSERT(x)
#include "stb_image.h"
#if defined(__clang__)
#pragma clang diagnostic pop
#endif

/* deflate with a zlib header; the caller frees the result with free() */
unsigned char* rp_zlib_compress(const unsigned char* data, int len, int* out_len)
{
    return stbi_zlib_compress((unsigned char*)data, len, out_len, 8);
}

/* inflate a zlib stream; nullptr on a broken stream; free() the result */
unsigned char* rp_zlib_decompress(const unsigned char* data, int len, int* out_len)
{
    return (unsigned char*)stbi_zlib_decode_malloc_guesssize((const char*)data, len, 256 * 1024, out_len);
}
