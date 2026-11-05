/* Read an initialized guest data range from a local ELF, including zero-filled
 * BSS. This is a reference for immutable-data validation, never a VM snapshot. */
#pragma once
#include <stdint.h>
#include <stdio.h>
#include <limits.h>
#include <vector>

namespace t5game {
inline uint64_t elf_be(const uint8_t* p, unsigned bytes)
{
    uint64_t value = 0;
    for (unsigned i = 0; i < bytes; ++i) value = (value << 8) | p[i];
    return value;
}
inline bool load_elf_data_range(const char* path, uint32_t base, uint32_t len, std::vector<uint8_t>* out)
{
    if (!path || !out || !len || len > 0x10000u) return false;
    FILE* fp = fopen(path, "rb");
    if (!fp) return false;
    struct Close { FILE* p; ~Close() { fclose(p); } } close{fp};
    uint8_t header[64];
    if (fread(header, 1, sizeof header, fp) != sizeof header || header[0] != 0x7Fu ||
        header[1] != 'E' || header[2] != 'L' || header[3] != 'F' || header[4] != 2 || header[5] != 2) return false;
    if (fseek(fp, 0, SEEK_END) || ftell(fp) < 0) return false;
    const uint64_t file_size = (uint64_t)ftell(fp);
    const uint64_t phoff = elf_be(header + 32, 8);
    const uint64_t entsize = elf_be(header + 54, 2), count = elf_be(header + 56, 2);
    if (entsize < 56 || !count || count > 128 || phoff > file_size || count * entsize > file_size - phoff) return false;
    const uint64_t end = (uint64_t)base + len;
    for (uint64_t i = 0; i < count; ++i) {
        const uint64_t where = phoff + i * entsize;
        if (where > LONG_MAX || fseek(fp, (long)where, SEEK_SET)) return false;
        uint8_t ph[56];
        if (fread(ph, 1, sizeof ph, fp) != sizeof ph) return false;
        if (elf_be(ph, 4) != 1) continue;
        const uint64_t off = elf_be(ph + 8, 8), va = elf_be(ph + 16, 8);
        const uint64_t filesz = elf_be(ph + 32, 8), memsz = elf_be(ph + 40, 8);
        if (filesz > memsz || off > file_size || filesz > file_size - off || memsz > UINT64_MAX - va) return false;
        if ((uint64_t)base < va || end > va + memsz) continue;
        std::vector<uint8_t> bytes(len, 0);
        const uint64_t delta = (uint64_t)base - va;
        if (delta < filesz) {
            const uint64_t available = filesz - delta;
            const size_t copy = (size_t)(available < len ? available : len);
            if (off + delta > LONG_MAX || fseek(fp, (long)(off + delta), SEEK_SET) ||
                fread(bytes.data(), 1, copy, fp) != copy) return false;
        }
        out->swap(bytes);
        return true;
    }
    return false;
}
} // namespace t5game
