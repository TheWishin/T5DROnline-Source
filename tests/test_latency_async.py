"""Patch 0119: latency events remain bounded when the disk writer stalls."""
import os
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest

from helpers import ROOT


class LatencyWriter(unittest.TestCase):
    def test_stalled_sink_does_not_block_producers_and_reports_loss(self):
        clang = shutil.which("clang-cl") or r"C:\Program Files\LLVM\bin\clang-cl.exe"
        trees = [os.environ.get("PS3RECOMP_DIR"), os.path.join(ROOT, "deps", "ps3recomp")]
        tree = next((Path(p) for p in trees if p and
                     (Path(p) / "runtime/platform/lat_log.c").is_file()), None)
        if os.name != "nt" or not Path(clang).is_file() or tree is None:
            self.skipTest("Windows clang-cl and prepared runtime required")
        runtime = tree / "runtime/platform/lat_log.c"
        if "LAT_ROWS = 4096" not in runtime.read_text(encoding="utf-8"):
            self.skipTest("prepared runtime needs patch 0119")
        driver = r'''
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
static HANDLE entered, resume_io;
static volatile LONG block_next;
static int forbid_wake, late_wakes;
static BOOL test_setevent(HANDLE h) {
    if (forbid_wake) ++late_wakes;
    return SetEvent(h);
}
static size_t test_fwrite(const void* p, size_t n, size_t c, FILE* f) {
    if (InterlockedExchange(&block_next, 0)) {
        SetEvent(entered);
        if (WaitForSingleObject(resume_io, 10000) != WAIT_OBJECT_0) ExitProcess(19);
    }
    return fwrite(p, n, c, f);
}
#define fwrite test_fwrite
#define SetEvent test_setevent
#include "lat_log.c"
#undef fwrite
#undef SetEvent
unsigned char* vm_base = NULL;
static DWORD WINAPI producer(LPVOID arg) {
    const unsigned id = (unsigned)(uintptr_t)arg;
    for (unsigned n = 0; n < 20000; ++n) lat_log_at_('T', n, "%u %u", id, n);
    return 0;
}
int main(void) {
    entered = CreateEventW(NULL, TRUE, FALSE, NULL);
    resume_io = CreateEventW(NULL, TRUE, FALSE, NULL);
    if (!lat_log_init()) return 10;
    if (s_dump) {
        unsigned char guest[64];
        for (unsigned i = 0; i < sizeof guest; ++i) guest[i] = (unsigned char)i;
        vm_base = guest;
        lat_log_flip_call(91);
        char path[MAX_PATH * 2];
        snprintf(path, sizeof path, "%s.dump", getenv("PS3_LATENCY_LOG"));
        WIN32_FILE_ATTRIBUTE_DATA attrs;
        if (!GetFileAttributesExA(path, GetFileExInfoStandard, &attrs) || attrs.nFileSizeLow != 28) return 17;
        /* The first record reached disk without closing: the old 50-ms flush
         * cadence is preserved. A second record must drain on normal close. */
        lat_log_flip_call(92);
        writer_stop();
        if (s_dump) return 18;
        lat_log_flip_call(93); /* disabled after closure; no binary write */
        return 0;
    }
    if (s_sync) {
        char oversized[2048]; memset(oversized, 'x', sizeof oversized - 1); oversized[2047] = 0;
        lat_log_('T', "%s", oversized);
        return s_dropped == 1 ? 0 : 16; /* final close must report this loss */
    }
    /* First drain an ordered, lossless trace and check the file externally. */
    for (unsigned n = 0; n < 100; ++n) lat_log_at_('O', n, "%u", n);
    Sleep(150);
    InterlockedExchange(&block_next, 1);
    lat_log_('B', "blocked sink");
    if (WaitForSingleObject(entered, 2000) != WAIT_OBJECT_0) return 11;
    HANDLE threads[4];
    for (unsigned i = 0; i < 4; ++i) threads[i] = CreateThread(NULL, 0, producer, (LPVOID)(uintptr_t)i, 0, NULL);
    /* The disk sink remains blocked until after every producer completes.
     * Holding the queue lock across I/O would fail this assertion. */
    const DWORD done = WaitForMultipleObjects(4, threads, TRUE, 3000);
    SetEvent(resume_io);
    if (done != WAIT_OBJECT_0) return 12;
    for (unsigned i = 0; i < 4; ++i) CloseHandle(threads[i]);
    if (!InterlockedCompareExchange64(&s_dropped, 0, 0)) return 13;
    /* atexit drains the bounded queue and records cumulative drops. */
    printf("producer-completion=ok trace_dropped=%lld\n", (long long)s_dropped);
    writer_stop();
    forbid_wake = 1;
    const unsigned written = s_write;
    const LONG64 dropped = s_dropped;
    enqueue("late\n", 5); /* producer admitted before stop but queued after it */
    if (s_write != written || s_dropped != dropped + 1 || late_wakes) return 14;
    return 0;
}
'''
        with tempfile.TemporaryDirectory() as folder:
            tmp = Path(folder)
            (tmp / "driver.c").write_text(driver, encoding="utf-8")
            vcvars = Path(r"C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat")
            if not vcvars.is_file():
                self.skipTest("Visual Studio environment required")
            (tmp / "compile.cmd").write_text(
                '@echo off\ncall "' + str(vcvars) + '" >nul\n"' + clang +
                '" /nologo /O2 /W4 /I "' + str(runtime.parent) +
                '" driver.c /Fe:driver.exe\n', encoding="utf-8")
            build = subprocess.run(["cmd", "/c", str(tmp / "compile.cmd")], cwd=tmp,
                                   capture_output=True, text=True, timeout=60)
            self.assertEqual(build.returncode, 0, build.stdout + build.stderr)
            env = os.environ.copy()
            env.update(PS3_LATENCY_LOG=str(tmp / "trace.log"), PS3_LATENCY_SYNC="0",
                       PS3_LATENCY_DUMP="", PS3_LATENCY_WATCH="",
                       OPENRECOMP_HOME=str(tmp / "home"), APPDATA=str(tmp / "appdata"),
                       LOCALAPPDATA=str(tmp / "localappdata"))
            run = subprocess.run([str(tmp / "driver.exe")], cwd=tmp, env=env,
                                 capture_output=True, text=True, timeout=20)
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            lines = (tmp / "trace.log").read_text().splitlines()
            self.assertEqual([l for l in lines if l.startswith("O ")],
                             [f"O {n} {n}" for n in range(100)])
            drops = [int(l.split("=", 1)[1]) for l in lines if l.startswith("# trace_dropped=")]
            self.assertTrue(drops and drops[-1] > 0)
            self.assertEqual(len([l for l in lines if l.startswith("T ")]) + drops[-1], 80000)
            for identity in range(4):
                values = [int(l.split()[3]) for l in lines
                          if l.startswith("T ") and int(l.split()[2]) == identity]
                self.assertEqual(values, sorted(set(values)))
            env.update(PS3_LATENCY_SYNC="1", PS3_LATENCY_LOG=str(tmp / "sync.log"))
            sync = subprocess.run([str(tmp / "driver.exe")], cwd=tmp, env=env,
                                  capture_output=True, text=True, timeout=20)
            self.assertEqual(sync.returncode, 0, sync.stdout + sync.stderr)
            self.assertIn("# trace_dropped=1", (tmp / "sync.log").read_text())
            env.update(PS3_LATENCY_SYNC="0", PS3_LATENCY_DUMP="0:10",
                       PS3_LATENCY_LOG=str(tmp / "dump.log"))
            dump = subprocess.run([str(tmp / "driver.exe")], cwd=tmp, env=env,
                                  capture_output=True, text=True, timeout=20)
            self.assertEqual(dump.returncode, 0, dump.stdout + dump.stderr)
            records = (tmp / "dump.log.dump").read_bytes()
            self.assertEqual(len(records), 56)
            for offset, sequence in ((0, 91), (28, 92)):
                seq, qpc = struct.unpack_from("<Iq", records, offset)
                self.assertEqual(seq, sequence)
                self.assertGreater(qpc, 0)
                self.assertEqual(records[offset + 12:offset + 28], bytes(range(16)))


if __name__ == "__main__":
    unittest.main()
