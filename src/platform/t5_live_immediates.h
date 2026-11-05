/* A mixed-edition timing patch is usable only when the loaded translated
 * code actually reloads every reviewed immediate. Old or partial game DLLs
 * fail this check; the loader/import ABI stays unchanged.
 */
#pragma once
#include <stdint.h>
#include <string.h>

#if defined(PS3_GAME_DLL)
# ifndef WIN32_LEAN_AND_MEAN
#  define WIN32_LEAN_AND_MEAN
# endif
# ifndef NOMINMAX
#  define NOMINMAX
# endif
# include "t5_win.h"
#elif defined(__has_include)
# if __has_include("ppu_live_immediates.h")
#  include "ppu_live_immediates.h"
# endif
#endif

namespace t5game {

inline bool live_immediate_manifest_matches(uint32_t abi, const char* actual, const char* expected)
{
    if (abi != 1u || !actual || !expected) return false;
    for (unsigned i = 0; i < 64; ++i) {
        const char c = expected[i];
        if (!((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f')) || actual[i] != c) return false;
    }
    return actual[64] == 0 && expected[64] == 0;
}

inline bool has_live_immediates(const char* expected_sha256)
{
#if defined(PS3_GAME_DLL)
    const void* abi_symbol = t5p_game_symbol("t5dr_game_live_immediate_abi");
    const char* manifest = (const char*)t5p_game_symbol("t5dr_game_live_immediate_manifest");
    if (!abi_symbol || !manifest) return false;
    uint32_t abi;
    memcpy(&abi, abi_symbol, sizeof abi);
    return live_immediate_manifest_matches(abi, manifest, expected_sha256);
#elif defined(T5DR_LIVE_IMMEDIATE_ABI) && defined(T5DR_LIVE_IMMEDIATE_MANIFEST_SHA256)
    return live_immediate_manifest_matches(T5DR_LIVE_IMMEDIATE_ABI,
                                           T5DR_LIVE_IMMEDIATE_MANIFEST_SHA256, expected_sha256);
#else
    (void)expected_sha256;
    return false;
#endif
}

} // namespace t5game
