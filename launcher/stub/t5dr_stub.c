/* "T5DR Online.exe" -- starts the launcher with the Python that ships in the
 * release folder (python\pythonw.exe launcher\t5dr_launcher.pyw), or with an
 * installed Python when the folder has none. No console window. Its own command
 * line goes on to the launcher ("T5DR Online.exe" --search ranked: a desktop
 * shortcut or Steam's launch options, README "Start a search from a shortcut").
 *
 * Built by tools/package_release.py as an ordinary Windows application: static C
 * runtime, version information, icon and manifest (t5dr_stub.rc, written there).
 * The first builds (a 3.5 KB exe with its own entry point and no resources) were
 * flagged by 3 of 71 machine-learning scanners on VirusTotal. The 1.0.0 build (clang-cl,
 * with these resources) still got 2 ML hits, so the default is now MSVC (cl.exe + link.exe
 * with /guard:cf, /DYNAMICBASE, /NXCOMPAT): package_release.py --stub-compiler msvc|clang.
 * The release workflow signs the exe when a signing service is set up (docs/RELEASING.md).
 *
 * Variants for the antivirus experiments (package_release.py --stub-variant, tools/stub_variants.py,
 * docs/RELEASING.md "The launcher stub"). Without any of these macros this file is the default build:
 *   T5DR_STUB_NO_PATH_FALLBACK  never run a pythonw.exe found on PATH: only the one in the folder.
 *   T5DR_STUB_INPROCESS         no child process: load python\python312.dll into this process and call
 *                               Py_Main, as pythonw.exe itself does (pythonw.exe is a 100 KB program that
 *                               imports Py_Main). sys.executable is still python\pythonw.exe (argv[0]).
 */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdlib.h>   /* __argc, __wargv */

#ifdef T5DR_STUB_INPROCESS
/* python312.lib (the Python that is bundled) resolves this; /DELAYLOAD:python312.dll, so the DLL
 * is loaded from the folder's python\ by LoadLibraryExW in wWinMain before the first call. */
__declspec(dllimport) int Py_Main(int argc, wchar_t** argv);
#endif

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

#if defined(T5DR_STUB_NO_PATH_FALLBACK) || defined(T5DR_STUB_INPROCESS)
static int fail(void)
{
    MessageBoxW(NULL, L"Could not start the launcher.\n\nThe folder must contain python\\pythonw.exe "
                      L"and launcher\\t5dr_launcher.pyw -- extract the whole zip again.",
                L"T5DR Online", MB_ICONERROR);
    return 1;
}
#endif

int WINAPI wWinMain(HINSTANCE inst, HINSTANCE prev, PWSTR args, int show)
{
    (void)inst; (void)prev; (void)args; (void)show;
    DWORD n = GetModuleFileNameW(NULL, dir, PATH_CAP);
    if (n == 0 || n >= PATH_CAP) return 2;
    while (n && dir[n - 1] != L'\\') n--;
    dir[n] = 0;                                   /* folder of this exe, with trailing '\' */

    lstrcpyW(script, dir); cat(script, L"launcher\\t5dr_launcher.pyw", PATH_CAP);
    lstrcpyW(py, dir);     cat(py, L"python\\pythonw.exe", PATH_CAP);
#if defined(T5DR_STUB_NO_PATH_FALLBACK) || defined(T5DR_STUB_INPROCESS)
    if (!exists(py) || !exists(script)) return fail();
#else
    if (!exists(py)) lstrcpyW(py, L"pythonw.exe");   /* installed Python on PATH */
#endif

#ifdef T5DR_STUB_INPROCESS
    {
        static wchar_t dll[PATH_CAP];
        static wchar_t* argv[64];
        int argn = 0;
        lstrcpyW(dll, dir); cat(dll, L"python\\python312.dll", PATH_CAP);
        SetCurrentDirectoryW(dir);                /* where the child process of the default build starts */
        if (!LoadLibraryExW(dll, NULL, LOAD_WITH_ALTERED_SEARCH_PATH)) return fail();
        argv[argn++] = py; argv[argn++] = script;
        for (int i = 1; __wargv && i < __argc && argn < 63; i++)
            argv[argn++] = __wargv[i];            /* this exe's own arguments, for the launcher */
        argv[argn] = NULL;
        return Py_Main(argn, argv);
    }
#else
    cmd[0] = 0;
    cat(cmd, L"\"", 3 * PATH_CAP); cat(cmd, py, 3 * PATH_CAP);
    cat(cmd, L"\" \"", 3 * PATH_CAP); cat(cmd, script, 3 * PATH_CAP);
    cat(cmd, L"\"", 3 * PATH_CAP);
    if (args && *args) {                          /* this exe's own arguments, as they were typed */
        cat(cmd, L" ", 3 * PATH_CAP); cat(cmd, args, 3 * PATH_CAP);
    }

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
#endif
}
