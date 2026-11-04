#include "../../src/replay/viewer.h"
#include "../../src/replay/blob.h"
#include <cstdio>
#include <cstdlib>
#include <memory>

static unsigned checks;
#define CHECK(x) do { ++checks; if (!(x)) { std::fprintf(stderr, "FAIL line %d: %s\n", __LINE__, #x); std::exit(1); } } while (0)

static void commands()
{
    rv::Viewer v;
    CHECK(v.verified && !v.paused && v.speed == 1.0 && v.control == 0);
    CHECK(v.permit_frame());
    CHECK(v.command("pause", 100, 0, 1000));
    CHECK(!v.permit_frame());
    CHECK(v.command("step", 100, 0, 1000));
    CHECK(v.paused && v.permit_frame());
    CHECK(!v.permit_frame());
    CHECK(v.command("step", 101, 0, 1000));
    CHECK(v.command("pause", 101, 0, 1000));
    CHECK(!v.permit_frame());
    CHECK(v.command("resume", 101, 0, 1000));
    CHECK(v.permit_frame() && v.permit_frame());
    for (const char* rate : {"0.25", "0.5", "1", "2", "4", "1.0", "2.0", "4.0"})
        CHECK(v.command(std::string("speed ") + rate, 100, 0, 1000));
    CHECK(v.speed == 4.0);
    CHECK(v.command("seek 0", 100, 50, 1000));
    uint32_t target = 9999;
    CHECK(!v.take_seek(nullptr));
    CHECK(v.take_seek(&target) && target == 50);
    CHECK(!v.take_seek(&target));
    CHECK(v.command("seek 10000", 100, 50, 1000));
    CHECK(v.take_seek(&target) && target == 1000);
    CHECK(v.command("seek 4294967295", 100, 0, 0xffffffffu));
    CHECK(v.take_seek(&target) && target == 0xffffffffu);
    CHECK(v.command("seek 999999999999999999999999999999", 100, 0, 1000));
    CHECK(v.take_seek(&target) && target == 1000);
    CHECK(v.command("control 2", 600, 0, 1000));
    CHECK(!v.verified && v.control == 2 && v.unverified_from == 600);
    CHECK(v.command("control 0", 700, 0, 1000));
    CHECK(!v.verified && v.control == 0 && v.unverified_from == 600);
    CHECK(v.command("seek 200", 700, 0, 1000));
    CHECK(v.take_seek(&target) && target == 200 && !v.verified);
    CHECK(v.command("control 1", 200, 0, 1000));
    CHECK(!v.verified && v.control == 1 && v.unverified_from == 200);

    for (const char* bad : {"", " ", "seek", "seek -1", "seek +1", "seek 0x10", "seek 10x",
                            "seek 1 2",
                            "pause 1", "resume 1", "step 1", "control", "control -1", "control 3",
                            "control 01", "speed", "speed 0", "speed -1", "speed 1.5", "speed nan",
                            "speed inf", "speed 1x", "speed 2 4", "stop", "seek 1\npause"}) {
        const rv::Viewer before = v;
        CHECK(!v.command(bad, 0, 0, 1000));
        CHECK(v.paused == before.paused && v.speed == before.speed && v.control == before.control &&
              v.verified == before.verified && v.unverified_from == before.unverified_from &&
              v.seek_pending == before.seek_pending && v.seek_frame == before.seek_frame &&
              v.step_pending == before.step_pending);
    }
    CHECK(!v.command("seek 1", 100, 100, 0));
    CHECK(v.command("  pause \r\n", 100, 0, 1000));
}

static void checkpoints()
{
    rv::Checkpoints<int> c(4, 300);
    CHECK(c.due(50));
    CHECK(!c.at_or_before(50));
    c.add(50, 5);
    CHECK(!c.due(349) && c.due(350));
    CHECK(!c.at_or_before(49));
    CHECK(c.at_or_before(50)->state == 5);
    for (uint32_t frame : {350u, 650u, 950u, 1250u, 1550u}) c.add(frame, frame / 10);
    CHECK(c.size() == 4);
    CHECK(c.at_or_before(700)->frame == 50);  /* origin survives eviction */
    CHECK(c.at_or_before(950)->frame == 950);
    CHECK(c.at_or_before(1000)->state == 95);
    CHECK(c.at_or_before(9999)->frame == 1550);
    c.add(1250, 42);
    CHECK(c.size() == 4 && c.at_or_before(1250)->state == 42);
    c.discard_after(1000);
    CHECK(c.size() == 2 && c.at_or_before(9999)->frame == 950);
    CHECK(c.due(1250) && !c.due(100));
    c.clear();
    CHECK(c.size() == 0 && c.due(0));

    rv::Checkpoints<std::unique_ptr<int>> owned(0, 0);
    owned.add(0, std::make_unique<int>(4));
    owned.add(1, std::make_unique<int>(8));
    owned.add(2, std::make_unique<int>(16));
    CHECK(owned.size() == 2 && *owned.at_or_before(1)->state == 4 && *owned.at_or_before(2)->state == 16);
    CHECK(owned.due(3));
    rv::Checkpoints<int> edge;
    edge.add(0xfffffffeu, 1);
    CHECK(!edge.due(0) && !edge.due(0xffffffffu));
}

static void blobs()
{
    CHECK(rv::object_fits(0x10624C80u, 0x10000000u, 0x770000u, 0x100u));
    CHECK(rv::object_fits(0x40123400u, 0x40000000u, 0x5F00000u, 0x100u));
    CHECK(!rv::object_fits(0x10624C81u, 0x10000000u, 0x770000u, 0x100u));
    CHECK(!rv::object_fits(0x1076FF04u, 0x10000000u, 0x770000u, 0x100u));
    CHECK(!rv::object_fits(0x0FFFFFFCu, 0x10000000u, 0x770000u, 0x100u));
    rv::Writer writer;
    const uint32_t marker = 0x01234567;
    const uint64_t count = 0xffffffffffffffffull;
    const std::vector<uint8_t> bytes{0, 1, 2, 255};
    writer.pod(marker); writer.pod(count); writer.blob(bytes); writer.blob({});
    rv::Reader reader{writer.bytes};
    uint32_t m = 0; uint64_t n = 0;
    std::vector<uint8_t> out{9};
    CHECK(reader.pod(&m) && m == marker);
    CHECK(reader.pod(&n) && n == count);
    CHECK(reader.blob(&out) && out == bytes);
    CHECK(reader.blob(&out) && out.empty());
    CHECK(reader.done());
    CHECK(!reader.pod(&m));
    CHECK(m == marker);
    for (size_t size = 0; size < sizeof(marker); ++size) {
        std::vector<uint8_t> truncated(writer.bytes.begin(), writer.bytes.begin() + size);
        rv::Reader r{truncated};
        m = 42;
        CHECK(!r.pod(&m) && m == 42 && r.pos == 0);
    }
    rv::Writer blob;
    blob.blob(bytes);
    for (size_t size = 0; size < blob.bytes.size(); ++size) {
        std::vector<uint8_t> truncated(blob.bytes.begin(), blob.bytes.begin() + size);
        rv::Reader r{truncated};
        out = {9};
        CHECK(!r.blob(&out) && out == std::vector<uint8_t>{9});
    }
    std::vector<uint8_t> corrupt(4, 255);
    rv::Reader bad{corrupt};
    CHECK(!bad.blob(&out));
    rv::Reader beyond{bytes};
    beyond.pos = bytes.size() + 1;
    CHECK(!beyond.pod(&m));
    CHECK(!beyond.blob(&out));
}

int main()
{
    commands();
    checkpoints();
    blobs();
    std::printf("PASS %u checks\n", checks);
}
