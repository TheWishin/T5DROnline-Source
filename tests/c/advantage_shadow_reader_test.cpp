/* Synthetic memory only: these tests check decoding/safety, not the RPCS3
 * address claims. No game, runtime dependency, or real guest data is needed.
 * Kept unexecuted for this change at the maintainer's request. */
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <map>
#include <utility>
#include <vector>

#include "../../src/training/advantage_shadow_reader.h"

using namespace training::shadow;

static int checks = 0, failures = 0;
#define CHECK(c) do { ++checks; if (!(c)) { ++failures; \
    printf("FAIL %s:%d: %s\n", __FILE__, __LINE__, #c); } } while (0)

namespace {
const uint32_t p1 = 0x10090030u, p2 = 0x10090900u;
/* These addresses deliberately belong to the fake memory fixture only. */
const uint32_t root = 0x20000u, child = 0x20100u;
const uint32_t root_name = 0x30000u, child_name = 0x30100u;
const uint32_t recovery = 0x40000u, child_recovery = 0x40200u;
const uint32_t indirect = 0x50000u;

struct FakeMemory {
    std::map<uint32_t, uint8_t> bytes;
    std::map<uint16_t, uint32_t> moves;
    std::vector<std::pair<uint32_t, size_t> > reads;
    std::vector<uint16_t> resolved;
    uint32_t expected_indirect = indirect;
    bool wrong_indirect = false;

    void zero(uint32_t a, size_t n)
    {
        for (size_t i = 0; i < n; ++i) bytes[a + (uint32_t)i] = 0;
    }
    void u8(uint32_t a, uint8_t value) { bytes[a] = value; }
    void u16(uint32_t a, uint16_t value)
    {
        u8(a, (uint8_t)(value >> 8)); u8(a + 1, (uint8_t)value);
    }
    void u32(uint32_t a, uint32_t value)
    {
        u16(a, (uint16_t)(value >> 16)); u16(a + 2, (uint16_t)value);
    }
    void name(uint32_t a, const char* value)
    {
        for (size_t i = 0; i <= strlen(value); ++i) u8(a + (uint32_t)i, (uint8_t)value[i]);
    }
    void move(uint32_t a, uint32_t name_pointer, uint16_t id, uint32_t recovery_pointer)
    {
        zero(a, 0x4C);
        u32(a, name_pointer); u32(a + 0x10, 0x01020304u);
        u32(a + 0x14, recovery_pointer); u16(a + 0x1C, id);
        u16(a + 0x1E, 0x1234); u16(a + 0x44, 7); u16(a + 0x46, 9);
    }
    void entry(uint32_t a, unsigned index, uint16_t id, uint16_t frames = 17, uint16_t type = 0x41)
    {
        a += index * 0x18;
        u16(a + 8, id); u16(a + 0x10, frames); u16(a + 0x16, type);
    }
    static bool read(void* context, uint32_t a, void* out, size_t n)
    {
        FakeMemory& memory = *(FakeMemory*)context;
        memory.reads.push_back(std::make_pair(a, n));
        if ((uint64_t)a + n > 0x100000000ull) return false;
        for (size_t i = 0; i < n; ++i)
            if (memory.bytes.find(a + (uint32_t)i) == memory.bytes.end()) return false;
        for (size_t i = 0; i < n; ++i)
            ((uint8_t*)out)[i] = memory.bytes[a + (uint32_t)i];
        return true;
    }
    static bool resolve(void* context, uint32_t base, uint16_t id, uint32_t* pointer)
    {
        FakeMemory& memory = *(FakeMemory*)context;
        memory.resolved.push_back(id);
        if (base != memory.expected_indirect) memory.wrong_indirect = true;
        const auto found = memory.moves.find(id);
        if (found == memory.moves.end()) return false;
        *pointer = found->second;
        return true;
    }
    MemoryAccess access(bool resolver = false)
    {
        MemoryAccess a;
        a.context = this; a.read = read;
        a.resolve_move = resolver ? resolve : nullptr;
        return a;
    }
    FakeMemory()
    {
        zero(p1 - 0x1C, 0x1200);
        u8(0x100947B3u, 0x12); u8(0x1009482Bu, 0x34);
        for (unsigned player = 0; player < 2; ++player) {
            const uint32_t base = player ? p2 : p1;
            u32(base - 0x1C, 5 + player); u16(base + 0xC0, 20 + player);
            u8(base + 0x144, 1); u32(base + 0x10, root);
            u32(base + 0x0C, indirect);
        }
        zero(root_name, 64); zero(child_name, 64);
        name(root_name, "attack_root"); name(child_name, "attack_child");
        move(root, root_name, 10, 0); move(child, child_name, 11, 0);
    }
};

bool has_name(const Sample& s, const char* name)
{
    for (unsigned i = 0; i < s.continuation_count; ++i)
        if (!strcmp(s.continuation[i], name)) return true;
    return false;
}

void test_production_rejects_conflicting_move_pointer_mapping()
{
    FakeMemory m;
    /* The known source layout stores a position float here, so even this
     * readable fake pointer must never be followed by the production path. */
    Sample s;
    ReadDetails d;
    CHECK(!read_sample(m.access(true), p1, 0, s, &d));
    CHECK(!s.valid); CHECK(m.resolved.empty());
    CHECK(!strcmp(d.status, "mapping_conflict_position_x"));
    CHECK(d.raw_move_word == root);
    for (const auto& request : m.reads) {
        const uint64_t begin = request.first, end = begin + request.second;
        CHECK(!(begin < root + 0x4C && end > root));
        CHECK(!(begin < root_name + 64 && end > root_name));
        CHECK(!(begin < indirect + 0x1E4 && end > indirect));
    }
}

void test_claimed_fields_are_decoded_big_endian()
{
    FakeMemory m;
    Sample s;
    ReadDetails d;
    CHECK(read_fixture_sample(m.access(), p1, 0, s, &d));
    CHECK(s.valid); CHECK(s.anim_frame == 5); CHECK(s.anim_length == 20);
    CHECK(s.hitbox_active); CHECK(s.move_ptr == root); CHECK(s.char_id == 0x12);
    CHECK(!strcmp(s.name, "attack_root")); CHECK(s.graph_complete);
    CHECK(d.move_base_indirect == indirect); CHECK(d.move_id == 10);
    CHECK(d.tech_id == 0x1234); CHECK(d.hit_rank == 0x01020304u);
    CHECK(d.recovery_ptr == 0); CHECK(d.startup_from == 7); CHECK(d.startup_to == 9);
    CHECK(read_fixture_sample(m.access(), p2, 1, s));
    CHECK(s.anim_frame == 6); CHECK(s.anim_length == 21); CHECK(s.char_id == 0x34);
    /* P2 character ID uses its separate supplied address, never P1+0x8D0. */
    CHECK(0x100947B3u + 0x8D0 != 0x1009482Bu);
}

void test_null_and_invalid_samples()
{
    Sample s;
    FakeMemory m;
    MemoryAccess missing_reader = m.access(); missing_reader.read = nullptr;
    CHECK(!read_fixture_sample(missing_reader, p1, 0, s)); CHECK(!s.valid);
    m.u32(p1 + 0x10, 0);
    CHECK(read_fixture_sample(m.access(), p1, 0, s));
    CHECK(s.valid); CHECK(s.move_ptr == 0); CHECK(s.name[0] == 0); CHECK(!s.graph_complete);
    CHECK(!read_fixture_sample(m.access(), 0x10, 0, s)); CHECK(!s.valid);
    CHECK(!read_fixture_sample(m.access(), p1, 2, s)); CHECK(!s.valid);

    m.u32(p1 + 0x10, root); m.u32(p1 - 0x1C, 21);
    CHECK(!read_fixture_sample(m.access(), p1, 0, s)); CHECK(!s.valid);
    m.u32(p1 - 0x1C, 5); m.u8(p1 + 0x144, 2);
    CHECK(!read_fixture_sample(m.access(), p1, 0, s)); CHECK(!s.valid);
    m.u8(p1 + 0x144, 1); m.bytes.erase(p1 + 0xC1);
    CHECK(!read_fixture_sample(m.access(), p1, 0, s)); CHECK(!s.valid);
}

void test_pointer_and_string_bounds()
{
    Sample s;
    const uint32_t invalid[] = { 1u, 0xFFFFu, root + 1, 0xFFFFFFF0u, 0xF0000000u };
    for (uint32_t pointer : invalid) {
        FakeMemory m; m.u32(p1 + 0x10, pointer);
        CHECK(!read_fixture_sample(m.access(), p1, 0, s)); CHECK(!s.valid);
    }
    FakeMemory m;
    m.bytes.erase(root + 0x4B); /* Whole move span must be readable. */
    CHECK(!read_fixture_sample(m.access(), p1, 0, s)); CHECK(!s.valid);
    m.move(root, root_name, 10, 0);
    m.u32(root, 0xFFFFFFF0u);
    CHECK(!read_fixture_sample(m.access(), p1, 0, s)); CHECK(!s.valid);
    m.u32(root, root_name);
    for (unsigned i = 0; i < 64; ++i) m.u8(root_name + i, 'x');
    CHECK(!read_fixture_sample(m.access(), p1, 0, s)); CHECK(!s.valid);
    m.u8(root_name + 63, 0);
    CHECK(read_fixture_sample(m.access(), p1, 0, s)); CHECK(strlen(s.name) == 63);
    m.name(root_name, "safe\nforged_log_line");
    CHECK(!read_fixture_sample(m.access(), p1, 0, s)); CHECK(!s.valid);
    m.name(root_name, "safe"); m.u8(root_name + 1, 0x80);
    CHECK(!read_fixture_sample(m.access(), p1, 0, s)); CHECK(!s.valid);
    m.name(root_name, "safe"); m.bytes.erase(root_name + 2);
    CHECK(!read_fixture_sample(m.access(), p1, 0, s)); CHECK(!s.valid);
}

void test_recovery_requires_explicit_resolver()
{
    FakeMemory m;
    m.u32(root + 0x14, recovery); m.zero(recovery, 16 * 0x18);
    m.entry(recovery, 0, 11);
    /* Even a plausible-looking +0x1E0 value is not a verified move-array
     * interpretation. The production reader must not derive a pointer here. */
    m.zero(indirect, 0x1E4); m.u32(indirect + 0x1E0, child);
    Sample s;
    CHECK(read_fixture_sample(m.access(), p1, 0, s));
    CHECK(s.valid); CHECK(!s.graph_complete); CHECK(!has_name(s, "attack_child"));
    m.moves[11] = child;
    CHECK(read_fixture_sample(m.access(true), p1, 0, s));
    CHECK(s.graph_complete); CHECK(has_name(s, "attack_child")); CHECK(!m.wrong_indirect);
    m.u32(p1 + 0x0C, 0);
    CHECK(read_fixture_sample(m.access(true), p1, 0, s)); CHECK(!s.graph_complete);
}

void test_markers_cycles_and_recovery_entry_bound()
{
    FakeMemory m;
    m.u32(root + 0x14, recovery); m.zero(recovery, 17 * 0x18);
    m.entry(recovery, 0, 0); m.entry(recovery, 1, 0x8000); m.entry(recovery, 2, 0xFFFF);
    m.entry(recovery, 3, 11, 17, 0x50);
    m.entry(recovery, 15, 11); m.entry(recovery, 16, 12); /* Outside the notes' limit. */
    m.u32(child + 0x14, child_recovery); m.zero(child_recovery, 16 * 0x18);
    m.entry(child_recovery, 0, 10);
    m.moves[10] = root; m.moves[11] = child;
    Sample s;
    ReadDetails d;
    CHECK(read_fixture_sample(m.access(true), p1, 0, s, &d));
    CHECK(s.valid); CHECK(s.graph_complete); CHECK(has_name(s, "attack_child"));
    CHECK(d.graph_moves == 2); CHECK(d.recovery_entries <= 32);
    CHECK(s.continuation_count <= 2);
    for (uint16_t id : m.resolved) CHECK(id != 0 && id < 0x8000 && id != 12);
    for (const auto& request : m.reads) {
        const uint64_t begin = request.first, end = begin + request.second;
        CHECK(!(begin < recovery + 17 * 0x18 && end > recovery + 16 * 0x18));
    }
}

void test_bad_descendant_does_not_invalidate_root()
{
    FakeMemory m;
    m.u32(root + 0x14, recovery); m.zero(recovery, 16 * 0x18);
    m.entry(recovery, 0, 11); m.moves[11] = child;
    m.u8(child_name, '\n');
    Sample s;
    CHECK(read_fixture_sample(m.access(true), p1, 0, s));
    CHECK(s.valid); CHECK(!s.graph_complete); CHECK(!has_name(s, "attack_child"));
    m.moves[11] = 0xFFFFFFF0u;
    CHECK(read_fixture_sample(m.access(true), p1, 0, s)); CHECK(s.valid); CHECK(!s.graph_complete);
}

void test_graph_budget()
{
    FakeMemory m;
    /* A synthetic chain longer than the fixed graph budget must terminate,
     * declare incomplete, and keep the root's readable sample available. */
    for (unsigned i = 0; i < 40; ++i) {
        const uint32_t ptr = 0x60000u + i * 0x100;
        const uint32_t np = 0x70000u + i * 0x100;
        const uint32_t rp = 0x80000u + i * 0x200;
        char name[40]; snprintf(name, sizeof name, "chain_%u", i);
        m.zero(np, 64); m.name(np, name); m.zero(rp, 16 * 0x18);
        m.move(ptr, np, (uint16_t)(100 + i), rp);
        m.entry(rp, 0, (uint16_t)(101 + i)); m.moves[(uint16_t)(100 + i)] = ptr;
    }
    m.u32(p1 + 0x10, 0x60000u);
    Sample s;
    ReadDetails d;
    CHECK(read_fixture_sample(m.access(true), p1, 0, s, &d));
    CHECK(s.valid); CHECK(!s.graph_complete); CHECK(d.graph_moves <= 32);
    CHECK(s.continuation_count <= 31); CHECK(m.resolved.size() <= 32);
}
} // namespace

int main()
{
    test_production_rejects_conflicting_move_pointer_mapping();
    test_claimed_fields_are_decoded_big_endian();
    test_null_and_invalid_samples();
    test_pointer_and_string_bounds();
    test_recovery_requires_explicit_resolver();
    test_markers_cycles_and_recovery_entry_bound();
    test_bad_descendant_does_not_invalidate_root();
    test_graph_budget();
    if (!failures) printf("PASS %d checks\n", checks);
    return failures ? 1 : 0;
}

