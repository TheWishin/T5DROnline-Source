/* "T5DR Online.exe" -- starts the launcher with the Python that ships in the
 * release folder (python\pythonw.exe launcher\t5dr_launcher.pyw), or with an
 * installed Python when the folder has none. No console window.
 *
 * Built by tools/package_release.py:
 *   clang-cl /O2 /GS- t5dr_stub.c /link /SUBSYSTEM:WINDOWS /ENTRY:start /NODEFAULTLIB kernel32.lib user32.lib
 */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>

static int exists(const wchar_t* p)
{
    DWORD a = GetFileAttributesW(p);
    return a != INVALID_FILE_ATTRIBUTES && !(a & FILE_ATTRIBUTE_DIRECTORY);
}

static void cat(wchar_t* dst, const wchar_t* src, int cap)
{
    int n = lstrlenW(dst);
    while (*src && n < cap - 1) dst[n++] = *src++;
    dst[n] = 0;
}

void start(void)
{
    wchar_t dir[MAX_PATH], py[MAX_PATH], script[MAX_PATH], cmd[3 * MAX_PATH + 16];
    DWORD n = GetModuleFileNameW(NULL, dir, MAX_PATH);
    while (n && dir[n - 1] != L'\\') n--;
    dir[n] = 0;                                   /* folder of this exe, with trailing '\' */

    lstrcpyW(script, dir); cat(script, L"launcher\\t5dr_launcher.pyw", MAX_PATH);
    lstrcpyW(py, dir);     cat(py, L"python\\pythonw.exe", MAX_PATH);
    if (!exists(py)) lstrcpyW(py, L"pythonw.exe");   /* installed Python on PATH */

    cmd[0] = 0;
    cat(cmd, L"\"", 3 * MAX_PATH + 16); cat(cmd, py, 3 * MAX_PATH + 16);
    cat(cmd, L"\" \"", 3 * MAX_PATH + 16); cat(cmd, script, 3 * MAX_PATH + 16);
    cat(cmd, L"\"", 3 * MAX_PATH + 16);

    STARTUPINFOW si; PROCESS_INFORMATION pi;
    for (unsigned i = 0; i < sizeof si; i++) ((char*)&si)[i] = 0;
    si.cb = sizeof si;
    if (!CreateProcessW(NULL, cmd, NULL, NULL, FALSE, 0, NULL, dir, &si, &pi)) {
        MessageBoxW(NULL, L"Could not start the launcher.\n\nThe folder must contain python\\pythonw.exe "
                          L"and launcher\\t5dr_launcher.pyw -- extract the whole zip again.",
                    L"T5DR Online", MB_ICONERROR);
        ExitProcess(1);
    }
    CloseHandle(pi.hThread);
    CloseHandle(pi.hProcess);
    ExitProcess(0);
}
