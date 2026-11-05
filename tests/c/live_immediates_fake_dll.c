#include <stdint.h>
#ifndef OMIT_CAPABILITY
__declspec(dllexport) const uint32_t t5dr_game_live_immediate_abi = TEST_ABI;
__declspec(dllexport) const char t5dr_game_live_immediate_manifest[] = TEST_SHA;
#else
__declspec(dllexport) const uint32_t unrelated_test_export = 1;
#endif
