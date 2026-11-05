#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include "../../src/netplay/cross_hash.h"

using namespace np::cross_hash;
static int checks = 0;
#define CHECK(x) do { ++checks; if (!(x)) { fprintf(stderr, "FAIL line %d: %s\n", __LINE__, #x); return 1; } } while (0)

int main(int argc, char** argv)
{
    /* Private dump analysis may exercise the exact production serializer on a
     * single US-coordinate region without booting either edition. */
    if (argc == 6 && !strcmp(argv[1], "--canonicalize")) {
        const uint32_t region = (uint32_t)strtoul(argv[2], nullptr, 16);
        FILE* in = fopen(argv[3], "rb"); if (!in) return 2;
        uint8_t bytes[0x6000]; const size_t len = fread(bytes, 1, sizeof bytes, in); fclose(in);
        const uint32_t unresolved = canonicalize_for_edition(region, bytes, (uint32_t)len, atoi(argv[5]) != 0);
        printf("unresolved=%u\n", unresolved);
        FILE* out = fopen(argv[4], "wb"); if (!out) return 3;
        const bool ok = fwrite(bytes, 1, len, out) == len; fclose(out); return ok ? 0 : 4;
    }
    uint8_t bytes[8];
    write_be(bytes, 0x10091120u); write_be(bytes + 4, 0xCAFEBABEu);
    CHECK(canonicalize_for_edition(0x1009009Cu, bytes, sizeof bytes, true) == 1);
    CHECK(read_be(bytes) == 0x10090910u); /* known fighter link */
    CHECK(read_be(bytes + 4) == 0xCAFEBABEu); /* unknown value at known pointer field */
    write_be(bytes, 0x10091120u);
    canonicalize_for_edition(0x100900D0u, bytes, 4, true);
    CHECK(read_be(bytes) == 0x10091120u); /* scalar/health bytes cannot be normalized */
    canonicalize_for_edition(0x10095168u, bytes, 4, true);
    CHECK(read_be(bytes) == 0x10091120u); /* RNG words cannot be normalized */
    canonicalize_for_edition(0x1009009Cu, bytes, 4, false);
    CHECK(read_be(bytes) == 0x10091120u); /* a US pointer keeps its US identity */
    write_be(bytes, 0x10000BE8u);
    CHECK(canonicalize_for_edition(0x10091D1Cu, bytes, 4, true) == 0);
    CHECK(read_be(bytes) == 0x10000BD8u); /* exact paired Controller Setup referent */
    write_be(bytes, 0x10000BE9u);
    CHECK(canonicalize_for_edition(0x10091D1Cu, bytes, 4, true) == 1);
    CHECK(read_be(bytes) == 0x10000BE9u); /* no borrowed neighbour shift */
    write_be(bytes, 0x003D7884u);
    canonicalize_for_edition(0x1008EB90u, bytes, 4, true);
    CHECK(read_be(bytes) == 0x003C7100u);
    write_be(bytes, 0x003D7888u);
    CHECK(canonicalize_for_edition(0x1008EB90u, bytes, 4, true) == 1);
    CHECK(read_be(bytes) == 0x003D7888u); /* unexpected image marker remains visible */
    write_be(bytes, 0x003C7100u);
    CHECK(canonicalize_for_edition(0x1008EB90u, bytes, 4, true) == 1); /* unknown EU value cannot alias US identity */
    CHECK(canonicalize_for_edition(0x1008EB90u, bytes, 4, false) == 0);
    write_be(bytes, 0x40000010u);
    CHECK(canonicalize_for_edition(0x1008EBA0u, bytes, 4, true) == 0);
    CHECK(read_be(bytes) == 1u); /* semantic identity of the unique loop-control root */
    write_be(bytes, 0x40000160u);
    CHECK(canonicalize_for_edition(0x1008EBA0u, bytes, 4, false) == 0);
    CHECK(read_be(bytes) == 1u); /* the US side uses the same semantic identity */
    write_be(bytes, 0u);
    canonicalize_for_edition(0x1008EBA0u, bytes, 4, true);
    CHECK(read_be(bytes) == 0u); /* absent object remains distinct */
    write_be(bytes, 0x40000011u);
    CHECK(canonicalize_for_edition(0x1008EBA0u, bytes, 4, true) == 1);
    CHECK(read_be(bytes) == 0x40000011u); /* invalid pointer remains visible and blocks comparison */
    CHECK(valid_control_pointer(0));
    CHECK(valid_control_pointer(0x40000010u));
    CHECK(!valid_control_pointer(0x3FFFFFF0u));
    CHECK(!valid_control_pointer(0x45EFFFF0u)); /* object end would exceed supported heap */
    CHECK(!valid_control_pointer(0x40000001u));
    uint8_t object[0x28], scalar[16], old[16];
    for (unsigned i = 0; i < sizeof object; ++i) object[i] = (uint8_t)i;
    append_control_state(object, scalar);
    CHECK(!memcmp(scalar, object + 0x18, 16));
    memcpy(old, scalar, 16); object[8] ^= 1; /* mutex scheduling word */
    append_control_state(object, scalar);
    CHECK(!memcmp(scalar, old, 16));
    object[0x24] ^= 1; append_control_state(object, scalar);
    CHECK(memcmp(scalar, old, 16) != 0); /* every object status/value word remains compared */
    append_control_state(nullptr, scalar);
    for (uint8_t v : scalar) CHECK(v == 0);
    write_be(bytes, 0x10091120u);
    canonicalize_for_edition(0x1009009Cu, bytes, 3, true);
    CHECK(read_be(bytes) == 0x10091120u); /* no partial-word overread/write */
    CHECK(pointer_field(0x10091DDCu));
    CHECK(!pointer_field(0x10091DDAu));
    CHECK(!pointer_field(0x10091E60u)); /* numeric word between option pointers */
    uint8_t combat[12];
    write_be(combat, 0x10090850u); write_be(combat + 4, 0x10091120u); write_be(combat + 8, 0x10090850u);
    CHECK(canonicalize_for_edition(0x10090170u, combat, sizeof combat, true) == 0);
    CHECK(read_be(combat + 4) == 0x10090910u); /* P1's live opponent link */
    CHECK(read_be(combat) == 0x10090850u && read_be(combat + 8) == 0x10090850u); /* neighboring scalars untouched */
    write_be(combat, 0x10090850u);
    CHECK(canonicalize_for_edition(0x10090A44u, combat, 4, true) == 0);
    CHECK(read_be(combat) == 0x10090040u); /* P2's live opponent link */
    write_be(combat, 0u);
    CHECK(canonicalize_for_edition(0x10090A44u, combat, 4, true) == 0 && read_be(combat) == 0u);
    write_be(combat, 0xDEADBEEFu);
    CHECK(canonicalize_for_edition(0x10090A44u, combat, 4, true) == 1 && read_be(combat) == 0xDEADBEEFu);
    write_be(bytes, 0x1000104Eu);
    CHECK(canonicalize_for_edition(0x100902FCu, bytes, 4, true) == 0);
    CHECK(read_be(bytes) == 0x1000103Eu);
    write_be(bytes, 0x10001050u);
    CHECK(canonicalize_for_edition(0x100902FCu, bytes, 4, true) == 0);
    CHECK(read_be(bytes) == 0x10001040u);
    write_be(bytes, 0x1000104Fu);
    CHECK(canonicalize_for_edition(0x100902FCu, bytes, 4, true) == 1);
    CHECK(read_be(bytes) == 0x1000104Fu);
    write_be(bytes, 0x1000104Eu);
    CHECK(canonicalize_for_edition(0x100902F8u, bytes, 4, true) == 0);
    CHECK(read_be(bytes) == 0x1000104Eu);
    write_be(bytes, 0x1000110Eu);
    CHECK(canonicalize_for_edition(0x10090BCCu, bytes, 4, true) == 0);
    CHECK(read_be(bytes) == 0x100010FEu);
    write_be(bytes, 0x10001110u);
    CHECK(canonicalize_for_edition(0x10090BCCu, bytes, 4, true) == 1);
    CHECK(read_be(bytes) == 0x10001110u);
    write_be(bytes, 0x46FA1B32u);
    CHECK(canonicalize_for_edition(0x100902FCu, bytes, 4, true) == 0);
    CHECK(read_be(bytes) == 0x46FA1B32u);
    write_be(bytes, 0x46FA1B34u);
    CHECK(canonicalize_for_edition(0x100902FCu, bytes, 4, true) == 0);
    CHECK(read_be(bytes) == 0x46FA1B34u); // a different heap cursor remains different
    write_be(bytes, 0x46FA1B33u);
    CHECK(canonicalize_for_edition(0x100902FCu, bytes, 4, true) == 1);
    write_be(bytes, 0x46FA1B32u);
    CHECK(canonicalize_for_edition(0x1009009Cu, bytes, 4, true) == 1); // not an actor link
    write_be(bytes, 0x50000000u);
    CHECK(canonicalize_for_edition(0x100902FCu, bytes, 4, true) == 1);
    puts("PASS typed pointers, unknown targets, scalar/RNG protection, control-object identity and state");
    printf("PASS %d checks\n", checks);
    return 0;
}
