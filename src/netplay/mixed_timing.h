/* Same-edition EU uses its original timing constants. Only mixed sessions and
 * their format-9 recordings select the reviewed US deadlines. */
#pragma once
#include <stdint.h>
#include <stddef.h>
namespace np { namespace mixed_timing {
struct Site { uint32_t pc, original, mixed; };
#include "mixed_timing_sites.inc"
struct DurationRecord { uint32_t address, original[4], mixed_duration; };
#include "mixed_announcer_durations.inc"
static constexpr const char kManifest[] = "cedb59b33fb633f3f57d0a417382a80035e65ac89c8a8bc0ecd0e1d56c4b2c48";
inline uint32_t read_word(const uint8_t* p)
{ return (uint32_t)p[0] << 24 | (uint32_t)p[1] << 16 | (uint32_t)p[2] << 8 | p[3]; }
inline void write_word(uint8_t* p, uint32_t v)
{ p[0] = (uint8_t)(v >> 24); p[1] = (uint8_t)(v >> 16); p[2] = (uint8_t)(v >> 8); p[3] = (uint8_t)v; }
/* Validate every site before changing any: a modified image cannot be half
 * patched. The main frame thread calls this before any round logic runs. */
inline bool transition(uint8_t* guest, bool was_mixed, bool mixed)
{
    if (!guest) return false;
    for (const Site& site : kSites)
        if (read_word(guest + site.pc) != (was_mixed ? site.mixed : site.original)) return false;
    /* These immutable records supply a timer consumed by the round controller,
     * including its transition/fade path. They cannot be treated as audio-only.
     * Validate the complete records, including unchanged identity words. */
    for (const DurationRecord& record : kDurationRecords)
        for (uint32_t word = 0; word < 4; ++word) {
            const uint32_t expected = word == 2 && was_mixed ? record.mixed_duration : record.original[word];
            if (read_word(guest + record.address + word * 4) != expected) return false;
        }
    for (const Site& site : kSites) write_word(guest + site.pc, mixed ? site.mixed : site.original);
    for (const DurationRecord& record : kDurationRecords)
        write_word(guest + record.address + 8, mixed ? record.mixed_duration : record.original[2]);
    return true;
}
void update();
} }
