#include "rsx_clips_ring.h"
#include <climits>
#include <cstdio>
#include <cstdlib>

static unsigned checks;
#define CHECK(expr) do { ++checks; if (!(expr)) { \
    std::fprintf(stderr, "FAIL line %d: %s\n", __LINE__, #expr); std::exit(1); } } while (0)

static clips::Segment segment(std::size_t bytes, long long start, long long end) {
    clips::Segment result;
    result.bytes.assign(bytes, static_cast<unsigned char>(start));
    result.start = start;
    result.end = end;
    return result;
}

int main() {
    clips::Ring timed(100, 30);
    CHECK(timed.segments().empty());
    CHECK(timed.bytes() == 0);
    for (int t = 0; t < 30; t += 2) CHECK(timed.push(segment(1, t, t + 2)));
    CHECK(timed.segments().size() == 15);
    CHECK(timed.bytes() == 15);
    CHECK(timed.segments().front().start == 0);
    CHECK(timed.push(segment(1, 30, 32)));
    CHECK(timed.segments().front().start == 2);
    CHECK(timed.segments().back().end == 32);
    CHECK(timed.segments().size() == 15);
    // Every export begins with an independent segment, never a coded tail.
    CHECK(timed.push(segment(1, 33, 35)));
    CHECK(timed.segments().front().start == 6);
    CHECK(timed.segments().back().end - timed.segments().front().start <= 30);

    clips::Ring bytes(8, 100);
    CHECK(bytes.push(segment(3, 0, 2)));
    CHECK(bytes.push(segment(3, 2, 4)));
    CHECK(bytes.push(segment(2, 4, 6)));
    CHECK(bytes.bytes() == 8);
    CHECK(bytes.push(segment(5, 6, 8)));
    CHECK(bytes.segments().size() == 2);
    CHECK(bytes.segments().front().start == 4);
    CHECK(bytes.bytes() == 7);
    CHECK(!bytes.push(segment(9, 8, 10)));
    CHECK(bytes.bytes() == 7);
    CHECK(bytes.segments().back().end == 8);

    CHECK(!bytes.push(segment(0, 8, 10)));
    CHECK(!bytes.push(segment(1, -1, 10)));
    CHECK(!bytes.push(segment(1, 8, 8)));
    CHECK(!bytes.push(segment(1, 9, 8)));
    CHECK(!bytes.push(segment(1, 8, 109)));
    CHECK(!bytes.push(segment(1, 5, 9)));
    CHECK(!bytes.push(segment(1, 7, 7)));
    CHECK(bytes.bytes() == 7);
    CHECK(bytes.segments().size() == 2);
    CHECK(bytes.push(segment(1, 7, 9))); // overlap allowed, monotonic clock
    CHECK(bytes.push(segment(1, 1000, 1002))); // gap ages old data out
    CHECK(bytes.segments().size() == 1);
    CHECK(bytes.bytes() == 1);
    bytes.clear();
    CHECK(bytes.bytes() == 0);
    CHECK(bytes.segments().empty());
    CHECK(bytes.push(segment(8, 0, 2)));
    CHECK(bytes.bytes() == 8);

    clips::Ring stopped(100, 30);
    CHECK(stopped.push(segment(2, 0, 2)));
    CHECK(stopped.push(segment(2, 2, 4)));
    stopped.expire(-1);
    CHECK(stopped.bytes() == 4);
    stopped.expire(32);
    CHECK(stopped.segments().size() == 1);
    CHECK(stopped.segments().front().start == 2);
    stopped.expire(1000);
    CHECK(stopped.segments().empty());
    CHECK(stopped.bytes() == 0);

    clips::Ring no_bytes(0, 30), no_time(8, 0), negative_time(8, -1);
    CHECK(!no_bytes.push(segment(1, 0, 2)));
    CHECK(!no_time.push(segment(1, 0, 2)));
    CHECK(!negative_time.push(segment(1, 0, 2)));
    clips::Ring maximum(4, LLONG_MAX);
    CHECK(maximum.push(segment(1, LLONG_MAX - 2, LLONG_MAX)));
    CHECK(maximum.bytes() == 1);

    // A short MP4 can retain a much larger stream allocation. Bound allocated
    // capacity too, rather than claiming a payload-only RAM limit.
    clips::Ring allocations(8, 100);
    auto reserved = segment(1, 0, 2);
    reserved.bytes.reserve(9);
    CHECK(!allocations.push(std::move(reserved)));
    CHECK(allocations.bytes() == 0);
    auto small = segment(1, 0, 2);
    small.bytes.reserve(8);
    const auto charged = small.bytes.capacity();
    CHECK(allocations.push(std::move(small)));
    CHECK(allocations.bytes() == charged);
    CHECK(allocations.push(segment(1, 2, 4)));
    CHECK(allocations.segments().size() == 1);
    CHECK(allocations.bytes() == 1);

    // Repeated saves can finalize very short segments. Bound metadata as well
    // as vector storage, including a producer repeating the same timestamp.
    clips::Ring many(100000, 100);
    for (int i = 0; i < 2000; ++i) CHECK(many.push(segment(1, 0, 1)));
    CHECK(many.segments().size() == 512);
    CHECK(many.bytes() == 512);

    // Repeated variable bitrate/time pressure, including near signed limits.
    clips::Ring stress(257, 71);
    long long clock = LLONG_MAX - 1000000;
    unsigned random = 1234567;
    for (int i = 0; i < 20000; ++i) {
        random = random * 1664525u + 1013904223u;
        const std::size_t count = 1 + random % 257;
        const long long length = 1 + (random >> 8) % 8;
        CHECK(stress.push(segment(count, clock, clock + length)));
        std::size_t actual = 0;
        long long previous = -1;
        for (const auto& item : stress.segments()) {
            actual += item.bytes.capacity();
            CHECK(item.start >= clock + length - 71);
            CHECK(item.start >= previous);
            CHECK(item.bytes.front() == static_cast<unsigned char>(item.start));
            previous = item.start;
        }
        CHECK(actual == stress.bytes());
        CHECK(actual <= 257);
        clock += length + ((random >> 16) % 4);
    }
    std::printf("PASS: %u clips ring checks\n", checks);
}
