/* The historical first gameplay-hash block contains C/C++ runtime globals,
 * not one relocatable struct. Keep a strict per-edition ELF-image guard over
 * every byte, and compare the stateful callback count plus engine math data.
 * Unexpected mutations (including stdio) fail closed instead of disappearing.
 * This helper only reads guest memory and writes the supplied hash-byte copy.
 */
#pragma once
#include <stdint.h>
#include <string.h>
#include <vector>
#include "cross_hash.h"
#include "../platform/elf_data_reference.h"

namespace np { namespace cross_hash { namespace first_block {

static constexpr uint32_t kUSBase = 0x1008E000u, kUSLength = 0xB80u;
static constexpr uint32_t kEUBase = 0x1008E840u, kEULength = 0xB48u;
static constexpr uint32_t kBytes = 4u + 4u + 3u * 0x48u + 0x78u;
struct Result { uint32_t bytes, unresolved; };
struct MathRange { uint32_t us, eu, len; };
static constexpr MathRange kMathRanges[] = {
    { 0x1008E760u, 0x1008EFE0u, 0x48u },
    { 0x1008E7A8u, 0x1008F028u, 0x48u },
    { 0x1008E7F0u, 0x1008EF98u, 0x48u },
    { 0x1008E0F0u, 0x1002B0D0u, 0x78u },
};

/* The only changing common word is the C runtime's atexit-callback vector
 * index. US 3A8A7C and its paired EU routine decrement it when registering a
 * callback; 3A8978 grows the vector. Its numeric value remains in the hash.
 * EU additionally caches argc/argv at CRT entry 10368. Their getters 10258 /
 * 10268 have no direct callers or escaped function pointers in either known
 * executable; supported launches have exactly the one program argument.
 */
inline uint32_t validate(const uint8_t* bytes, const uint8_t* reference,
                         uint32_t length, bool eu, uint32_t* callback_index)
{
    if (!bytes || !reference || length != (eu ? kEULength : kUSLength)) return 1;
    const uint32_t counter = eu ? 0x1A8u : 0x1B0u;
    uint32_t unresolved = 0;
    for (uint32_t i = 0; i < length; ++i) {
        if (i >= counter && i < counter + 4u) continue;
        if (eu && i >= 0xB40u) continue; // handled by the explicit CRT argument invariant below
        if (bytes[i] != reference[i]) ++unresolved;
    }
    *callback_index = read_be(bytes + counter);
    if (eu && (read_be(bytes + 0xB40u) != 1u || read_be(bytes + 0xB44u) != 0x10770000u)) ++unresolved;
    return unresolved;
}

struct Reference {
    std::vector<uint8_t> bytes;
    bool good = false;
    explicit Reference(bool eu) {
        good = t5game::load_elf_data_range(t5game::elf_arg(), eu ? kEUBase : kUSBase,
                                          eu ? kEULength : kUSLength, &bytes);
    }
};

inline void dump_failure_once(const uint8_t* current, const Reference& reference,
                              bool eu, uint32_t unresolved, const char* reason)
{
    static bool written = false;
    const char* diagnostic = getenv("T5_NET_DESYNC_DUMP");
    if (written || !diagnostic || atoi(diagnostic) < 1) return;
    written = true;
    const uint32_t length = eu ? kEULength : kUSLength;
    const uint32_t counter = eu ? 0x1A8u : 0x1B0u;
    int first_bad = -1;
    if (current && reference.good) {
        for (uint32_t i = 0; i < length; ++i) {
            if (i >= counter && i < counter + 4u) continue;
            if (eu && i >= 0xB40u) continue;
            if (current[i] != reference.bytes[i]) { first_bad = (int)i; break; }
        }
    }
    if (current) if (FILE* file = fopen("prefix_guard_actual.bin", "wb")) {
        fwrite(current, 1, length, file); fclose(file);
    }
    if (FILE* file = fopen("prefix_guard_reference.bin", "wb")) {
        fwrite(reference.bytes.data(), 1, reference.bytes.size(), file); fclose(file);
    }
    if (FILE* file = fopen("prefix_guard_failure.json", "wb")) {
        fprintf(file, "{\"schema\":1,\"base\":%u,\"length\":%u,\"program\":%u,\"reference_good\":%s,"
                      "\"unresolved\":%u,\"reason\":\"%s\",\"first_immutable_mismatch_offset\":%d,"
                      "\"callback_index\":%u,\"argc\":%u,\"argv\":%u}\n",
                eu ? kEUBase : kUSBase, length, (unsigned)t5game::game(), reference.good ? "true" : "false",
                unresolved, reason, first_bad, current ? read_be(current + counter) : 0,
                eu && current ? read_be(current + 0xB40u) : 0, eu && current ? read_be(current + 0xB44u) : 0);
        fclose(file);
    }
}

inline Result append(const uint8_t* guest, uint8_t* out, uint32_t cap)
{
    const bool eu = t5game::game() == t5game::Game::EU_ONLINE;
    static const Reference reference(eu);
    if (!guest || !out || cap < kBytes || !reference.good) {
        dump_failure_once(guest ? guest + (eu ? kEUBase : kUSBase) : nullptr, reference, eu, 1,
                          !reference.good ? "reference_unavailable" : "short_or_missing_output");
        return { 0, 1 };
    }
    uint32_t callback_index = 0;
    const uint32_t unresolved = validate(guest + (eu ? kEUBase : kUSBase), reference.bytes.data(),
                                        (uint32_t)reference.bytes.size(), eu, &callback_index);
    if (unresolved) dump_failure_once(guest + (eu ? kEUBase : kUSBase), reference, eu, unresolved,
                                     eu && (read_be(guest + kEUBase + 0xB40u) != 1u || read_be(guest + kEUBase + 0xB44u) != 0x10770000u)
                                     ? "crt_argument_invariant" : "immutable_byte_change");
    write_be(out, 0x43525431u); // CRT1: every otherwise omitted byte passed the immutable-image guard
    write_be(out + 4u, callback_index);
    uint32_t n = 8;
    /* Paired, byte-identical math roles: double limits, long-double limits,
     * float limits and the extended power-of-ten coefficients. The latter
     * moved from US writable .data into EU read-only .rodata. In particular,
     * FLT_MAX is read by engine functions 19BE4 / 19C6C and stays compared.
     * The full per-edition prefix guard above also refuses any numeric change
     * outside these explicitly serialized roles.
     */
    for (const MathRange& range : kMathRanges) {
        memcpy(out + n, guest + (eu ? range.eu : range.us), range.len);
        n += range.len;
    }
    return { n, unresolved };
}

} } } // namespace np::cross_hash::first_block
