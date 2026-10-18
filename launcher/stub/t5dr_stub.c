/* "T5DR Online.exe" -- starts the launcher with the Python that ships in the
 * release folder (python\pythonw.exe launcher\t5dr_launcher.pyw), or with an
 * installed Python when the folder has none. No console window.
 *
 * Built by tools/package_release.py as an ordinary Windows application: static C
 * runtime, version information, icon and manifest (t5dr_stub.rc, written there).
 * The first builds (a 3.5 KB exe with its own entry point and no resources) were
 * flagged by 3 of 71 machine-learning scanners on VirusTotal. The 1.0.0 build (clang-cl,
 * with these resources) still got 2 ML hits, so the default is now MSVC (cl.exe + link.exe
 * with /guard:cf, /DYNAMICBASE, /NXCOMPAT): package_release.py --stub-compiler msvc|clang.
 * The release workflow signs the exe when a signing service is set up (docs/RELEASING.md).
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

/* Paths of any length (a folder deeper than MAX_PATH was cut off silently),
 * any characters: wide-char APIs only, up to Windows' 32767-character limit. */
#define PATH_CAP 32768
static wchar_t dir[PATH_CAP], py[PATH_CAP], script[PATH_CAP], cmd[3 * PATH_CAP];

int WINAPI wWinMain(HINSTANCE inst, HINSTANCE prev, PWSTR args, int show)
{
    (void)inst; (void)prev; (void)args; (void)show;
    DWORD n = GetModuleFileNameW(NULL, dir, PATH_CAP);
    if (n == 0 || n >= PATH_CAP) return 2;
    while (n && dir[n - 1] != L'\\') n--;
    dir[n] = 0;                                   /* folder of this exe, with trailing '\' */

    lstrcpyW(script, dir); cat(script, L"launcher\\t5dr_launcher.pyw", PATH_CAP);
    lstrcpyW(py, dir);     cat(py, L"python\\pythonw.exe", PATH_CAP);
    if (!exists(py)) lstrcpyW(py, L"pythonw.exe");   /* installed Python on PATH */

    cmd[0] = 0;
    cat(cmd, L"\"", 3 * PATH_CAP); cat(cmd, py, 3 * PATH_CAP);
    cat(cmd, L"\" \"", 3 * PATH_CAP); cat(cmd, script, 3 * PATH_CAP);
    cat(cmd, L"\"", 3 * PATH_CAP);

    STARTUPINFOW si; PROCESS_INFORMATION pi;
    for (unsigned i = 0; i < sizeof si; i++) ((char*)&si)[i] = 0;
    si.cb = sizeof si;
    if (!CreateProcessW(NULL, cmd, NULL, NULL, FALSE, 0, NULL, dir, &si, &pi)) {
        MessageBoxW(NULL, L"Could not start the launcher.\n\nThe folder must contain python\\pythonw.exe "
                          L"and launcher\\t5dr_launcher.pyw -- extract the whole zip again.",
                    L"T5DR Online", MB_ICONERROR);
        return 1;
    }
    CloseHandle(pi.hThread);
    CloseHandle(pi.hProcess);
    return 0;
}
