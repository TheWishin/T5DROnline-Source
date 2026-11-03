/* Replay paths are UTF-8 internally. Python passes a Unicode environment block
 * on Windows; the ANSI CRT environment and file APIs lose characters outside
 * the current code page. Keep the conversion at the replay I/O boundary. */
#pragma once

#include "../platform/t5_win.h"
#include <cstdio>
#include <cstdlib>
#include <string>

namespace replay_paths {

#if defined(_WIN32)
inline std::wstring wide(const char* text)
{
    if (!text || !*text) return {};
    const int n = MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, text, -1, nullptr, 0);
    if (!n) return {};
    std::wstring out((size_t)n, L'\0');
    if (!MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, text, -1, &out[0], n)) return {};
    out.resize((size_t)n - 1);
    return out;
}
#endif

inline std::string env(const char* key)
{
#if defined(_WIN32)
    const std::wstring name = wide(key);
    if (name.empty()) return {};
    DWORD cap = GetEnvironmentVariableW(name.c_str(), nullptr, 0);
    while (cap) {
        std::wstring value((size_t)cap, L'\0');
        const DWORD n = GetEnvironmentVariableW(name.c_str(), &value[0], cap);
        if (!n) return {};
        if (n >= cap) { cap = n; continue; }   /* the value grew between calls */
        const int bytes = WideCharToMultiByte(CP_UTF8, WC_ERR_INVALID_CHARS, value.c_str(), (int)n, nullptr, 0, nullptr, nullptr);
        if (!bytes) return {};
        std::string out((size_t)bytes, '\0');
        if (!WideCharToMultiByte(CP_UTF8, WC_ERR_INVALID_CHARS, value.c_str(), (int)n, &out[0], bytes, nullptr, nullptr)) return {};
        return out;
    }
    return {};
#else
    const char* value = getenv(key);
    return value ? value : "";
#endif
}

inline FILE* open(const char* path, const char* mode)
{
#if defined(_WIN32)
    const std::wstring p = wide(path), m = wide(mode);
    return p.empty() || m.empty() ? nullptr : _wfopen(p.c_str(), m.c_str());
#else
    return path ? fopen(path, mode) : nullptr;
#endif
}

/* Live replay handles keep the platform sharing flags, with UTF-8 converted
 * locally so unrelated t5p_* callers retain their existing path contract. */
inline intptr_t open_read_shared(const char* path)
{
#if defined(_WIN32)
    const std::wstring p = wide(path);
    if (p.empty()) return -1;
    HANDLE h = CreateFileW(p.c_str(), GENERIC_READ,
                          FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
                          nullptr, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, nullptr);
    return h == INVALID_HANDLE_VALUE ? (intptr_t)-1 : (intptr_t)h;
#else
    return t5p_open_read_shared(path);
#endif
}

inline intptr_t create_write_shared(const char* path, int* busy)
{
#if defined(_WIN32)
    if (busy) *busy = 0;
    const std::wstring p = wide(path);
    if (p.empty()) return -1;
    HANDLE h = CreateFileW(p.c_str(), GENERIC_WRITE, FILE_SHARE_READ | FILE_SHARE_DELETE,
                          nullptr, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, nullptr);
    if (busy) *busy = h == INVALID_HANDLE_VALUE && GetLastError() == ERROR_SHARING_VIOLATION;
    return h == INVALID_HANDLE_VALUE ? (intptr_t)-1 : (intptr_t)h;
#else
    return t5p_create_write_shared(path, busy);
#endif
}
inline int replace(const char* from, const char* to)
{
#if defined(_WIN32)
    const std::wstring a = wide(from), b = wide(to);
    return !a.empty() && !b.empty() && MoveFileExW(a.c_str(), b.c_str(), MOVEFILE_REPLACE_EXISTING) != 0;
#else
    return t5p_replace_file(from, to);
#endif
}

inline void make_directory(const char* path)
{
#if defined(_WIN32)
    const std::wstring p = wide(path);
    if (!p.empty()) CreateDirectoryW(p.c_str(), nullptr);
#else
    CreateDirectoryA(path, nullptr);
#endif
}

} // namespace replay_paths
