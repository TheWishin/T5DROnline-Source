/* Mixed US/EU Online hashes compare identities, rather than guest virtual
 * addresses. This changes only a copy of the hashed bytes, never guest memory.
 * Unknown pointer values remain unchanged so incomplete mappings fail closed.
 * Same-edition sessions must not call this transform.
 *
 * The fields below are object links, vtables and controller-option descriptors,
 * identified from the matched constructors (US 0x1E08C / EU 0x1E114 and their
 * callers). Referent identities are paired by the same instructions, rather
 * than inferred from values looking like addresses. Private instruction-level
 * evidence: build/eu-crossplay-2/edition-audit/{data-map,target-proof}.json. */
#pragma once

#include <stdint.h>
#include "../platform/t5_addr.h"

namespace np { namespace cross_hash {

/* The loop-control object is allocated lazily, at edition-dependent heap
 * addresses. Its identity is this unique root. Its four status/value words
 * are appended to the mixed hash; the first 0x18 bytes hold a kernel mutex,
 * whose lock state schedules access without supplying simulation values. */
inline bool valid_control_pointer(uint32_t address)
{
    return address == 0 || (!(address & 0xFu) && address >= 0x40000000u && address <= 0x45F00000u - 0x28u);
}
inline void append_control_state(const uint8_t* object, uint8_t* out)
{
    for (uint32_t i = 0; i < 16; ++i) out[i] = object ? object[0x18u + i] : 0;
}

inline bool pointer_field(uint32_t field)
{
    const uint32_t fighters[] = { 0x10090040u, 0x10090910u };
    for (uint32_t fighter : fighters) {
        const uint32_t off = field - fighter;
        /* +0x134 is a live actor link, populated during combat. Matched
         * writer US 0xE8D68 / EU 0xEA67C stores an actor pointer and walks
         * the 0x8D0 actor array. Its readers dereference the target's state
         * (+0x148/+0x320/+0xC4), so preserve the target identity in the hash. */
        if (off == 0x5Cu || off == 0x60u || off == 0x64u || off == 0x134u ||
            off == 0x2BCu || off == 0x530u || off == 0x580u || off == 0x5D0u || off == 0x8A0u) return true;
    }
    if (field == 0x10091AB0u || field == 0x10091AB4u ||
        field == 0x10091CFCu || field == 0x10091D1Cu || field == 0x10091D24u) return true;
    /* The controller-setup object's vtable and its twelve child-object links. */
    if (field >= 0x10091DD8u && field <= 0x10091E08u && !(field & 3u)) return true;
    if (field == 0x10091E20u || field == 0x10091E40u || field == 0x10091E48u ||
        field == 0x10091E50u || field == 0x10091E58u) return true;
    /* Two option descriptors: a vtable, then label/value descriptor pointers
     * at eight-byte intervals. The intervening numeric values remain raw. */
    const uint32_t objects[] = { 0x10091E5Cu, 0x10091F38u };
    for (uint32_t object : objects) {
        const uint32_t off = field - object;
        if (off == 0 || (off >= 0x20u && off <= 0xD8u && !(off & 7u))) return true;
    }
    return false;
}

/* Additional read-only referents outside the hook address table. Every exact
 * identity below has paired-instruction evidence. These are not ranges: an
 * unreviewed adjacent pointer is left raw. */
inline uint32_t pointer_value(uint32_t value, bool eu, bool* reviewed = nullptr)
{
    if (reviewed) *reviewed = value == 0;
    if (!value) return 0;
    /* Matched 36DB0/37180 returns the 16-bit command-script base; the paired
     * interpreter 36F34/37304 walks actor+2BC. These paired anchors bracket
     * byte-identical script data. Retain both referent identity and offset. */
    const uint32_t script_base = eu ? 0x10001040u : 0x10001030u;
    if (!(value & 1u) && value >= script_base && value < script_base + 0xD0u) {
        if (reviewed) *reviewed = true;
        return 0x10001030u + (value - script_base);
    }
    struct Identity { uint32_t us, eu; };
    static constexpr Identity identities[] = {
        { 0x1041C170u, 0x1041CB50u },
        { 0x1041C174u, 0x1041CB54u }, /* second word of the same two-player record */
        { 0x1007BEBCu, 0x1007C348u }, { 0x1007BFB8u, 0x1007C44Cu },
        { 0x1009258Cu, 0x10092D9Cu }, /* constructor 0x1E08C / 0x1E114: setup object +0x890 */
        { 0x100504D4u, 0x100504ECu }, { 0x100506F8u, 0x10050724u },
        { 0x10050878u, 0x100508B4u }, { 0x100227C8u, 0x10022D30u },
        { 0x10000BD8u, 0x10000BE8u }, { 0x10000BC0u, 0x10000BD0u },
        { 0x10000C90u, 0x10000CA0u }, { 0x10000C80u, 0x10000C90u },
        { 0x10000CA0u, 0x10000CB0u }, { 0x10000B80u, 0x10000B90u },
        { 0x10000B28u, 0x10000B38u }, { 0x10000B30u, 0x10000B40u },
        { 0x10000B38u, 0x10000B48u }, { 0x10000B40u, 0x10000B50u },
        { 0x10000B48u, 0x10000B58u }, { 0x10000B50u, 0x10000B60u },
        { 0x10000B58u, 0x10000B68u }, { 0x10000B60u, 0x10000B70u },
        { 0x10000B68u, 0x10000B78u }, { 0x10000B70u, 0x10000B80u },
        { 0x10000B78u, 0x10000B88u }, { 0x10000B88u, 0x10000B98u },
    };
    for (const Identity& p : identities) if (value == (eu ? p.eu : p.us)) {
        if (reviewed) *reviewed = true;
        return p.us;
    }
    /* Reverse only existing, reviewed one-to-one address spans. */
    for (const t5game::Span& p : t5game::kEuOnline)
        if (value >= (eu ? p.eu : p.us) && (uint64_t)value < (uint64_t)(eu ? p.eu : p.us) + p.len) {
            if (reviewed) *reviewed = true;
            return p.us + (value - (eu ? p.eu : p.us));
        }
    return value;
}

inline uint32_t read_be(const uint8_t* p)
{
    return (uint32_t)p[0] << 24 | (uint32_t)p[1] << 16 | (uint32_t)p[2] << 8 | p[3];
}
inline void write_be(uint8_t* p, uint32_t v)
{
    p[0] = (uint8_t)(v >> 24); p[1] = (uint8_t)(v >> 16); p[2] = (uint8_t)(v >> 8); p[3] = (uint8_t)v;
}

inline uint32_t canonicalize_for_edition(uint32_t region_us, uint8_t* bytes, uint32_t len, bool eu)
{
    uint32_t unresolved = 0;
    for (uint32_t off = 0; off + 4 <= len; off += 4) {
        const uint32_t field = region_us + off;
        const uint32_t value = read_be(bytes + off);
        if (field == 0x1008EBA0u) {
            if (valid_control_pointer(value)) write_be(bytes + off, value ? 1u : 0u);
            else ++unresolved; /* Keep invalid values raw; the caller refuses the comparison. */
        } else if (pointer_field(field)) {
            /* Actor command cursors also enter loaded move data in the common
             * 256-MB syscall allocation window. Keep those addresses byte-exact:
             * they cannot alias any canonical static image address, and no heap
             * identity is guessed or rewritten. Unequal cursors still differ. */
            const bool script_cursor = field == 0x100902FCu || field == 0x10090BCCu;
            if (script_cursor && !(value & 1u) && value >= 0x40000000u && value < 0x50000000u) continue;
            bool reviewed = false;
            const uint32_t canonical = pointer_value(value, eu, &reviewed);
            if (!reviewed) {
                ++unresolved;
                if (const char* dump = getenv("T5_NET_DESYNC_DUMP")) if (atoi(dump) > 0)
                    fprintf(stderr, "[cross_hash] unresolved typed pointer field %08X value %08X (%s)\n", field, value, eu ? "EU" : "US");
            }
            if (eu) write_be(bytes + off, canonical);
        }
        /* End of the executable image: a layout marker, not executable state.
         * Only the supported EU image's expected boundary is translated. */
        else if (field == 0x1008EB90u) {
            if (value == (eu ? 0x003D7884u : 0x003C7100u)) write_be(bytes + off, 0x003C7100u);
            else ++unresolved;
        }
    }
    return unresolved;
}

inline uint32_t canonicalize(uint32_t region_us, uint32_t actual_addr, uint8_t* bytes, uint32_t len)
{
    (void)actual_addr;
    return canonicalize_for_edition(region_us, bytes, len, t5game::game() == t5game::Game::EU_ONLINE);
}

} } // namespace np::cross_hash
