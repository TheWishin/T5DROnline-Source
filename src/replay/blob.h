// Internal, build-bound replay checkpoint metadata. Never accepted across builds.
#pragma once
#include <cstdint>
#include <cstring>
#include <type_traits>
#include <vector>

namespace rv {
inline bool object_fits(uint32_t address, uint32_t base, uint32_t length, uint32_t size) {
    return size <= length && address >= base && address - base <= length - size && !(address & 3u);
}
struct Writer {
    std::vector<uint8_t> bytes;
    template<class T> void pod(const T& v) {
        static_assert(std::is_trivially_copyable_v<T>);
        const auto* p = reinterpret_cast<const uint8_t*>(&v);
        bytes.insert(bytes.end(), p, p + sizeof v);
    }
    void blob(const std::vector<uint8_t>& b) {
        pod(static_cast<uint32_t>(b.size()));
        bytes.insert(bytes.end(), b.begin(), b.end());
    }
};
struct Reader {
    const std::vector<uint8_t>& bytes;
    size_t pos = 0;
    template<class T> bool pod(T* v) {
        static_assert(std::is_trivially_copyable_v<T>);
        if (pos > bytes.size() || sizeof(T) > bytes.size() - pos) return false;
        std::memcpy(v, bytes.data() + pos, sizeof(T)); pos += sizeof(T); return true;
    }
    bool blob(std::vector<uint8_t>* b) {
        uint32_t n;
        if (!pod(&n) || n > bytes.size() - pos) return false;
        b->assign(bytes.begin() + pos, bytes.begin() + pos + n); pos += n; return true;
    }
    bool done() const { return pos == bytes.size(); }
};
} // namespace rv
