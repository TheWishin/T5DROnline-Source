#!/usr/bin/env python3
"""Measure slow_core availability with fixed native, single-thread CPU work.

This calibrates scheduling availability, not Ivy Bridge instruction latency,
cache size, memory bandwidth or SMT efficiency. The requested i3-3240 proxy is
55-60% of this Zen 4 PC's unthrottled throughput. A busy percentage alone is
not a calibration. Games must use the accepted mask, duty and period together.

    python tools/calibrate_slow_core.py --cpus 0xF000 --out build/pacing/calibration

Takes two heavy slots atomically for timing, releases both after each duty
measurement; exits if unavailable. Use --build-only to prepare the tiny native
DLL without measuring. Requires Windows clang-cl and lld-link; no SDK or CRT.
"""
import argparse
import ctypes
import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import statistics
import subprocess
import sys
import time
import uuid

import slow_core

SOURCE = r'''
/* Fixed work, baseline SSE2, no AVX2/FMA and no game-derived code. */
#if defined(__AVX__) || defined(__AVX2__) || defined(__FMA__)
#error calibration probe must use the baseline ISA
#endif
int _fltused = 0; /* no CRT is needed by either fixed-work kernel */
__declspec(dllexport) unsigned long long integer_work(unsigned long long n) {
    unsigned long long x = 0x123456789abcdef0ULL;
    for (unsigned long long i = 0; i < n; ++i) {
        x ^= x >> 12; x ^= x << 25; x ^= x >> 27;
        x *= 0x2545f4914f6cdd1dULL;
    }
    return x;
}
__declspec(dllexport) double float_work(unsigned long long n) {
    double x = 0.125, y = 0.375, z = 0.625, w = 0.875;
    for (unsigned long long i = 0; i < n; ++i) {
        x = x * 0.9999999 + 0.00000001;
        y = y * 0.9999999 + 0.00000002;
        z = z * 0.9999999 + 0.00000003;
        w = w * 0.9999999 + 0.00000004;
    }
    return x + y + z + w;
}
'''
LOCK_ROOT = Path('C:/T5DROnline/build/int115')


def build_probe(out, clang):
    out.mkdir(parents=True, exist_ok=True)
    source, obj, dll = out / 'single_thread.c', out / 'single_thread.obj', out / 'single_thread.dll'
    source.write_text(SOURCE, encoding='utf-8')
    commands = [[str(clang), '/nologo', '/c', '/O2', '/GS-', '/clang:-march=x86-64',
                 '/clang:-mno-avx', '/clang:-ffp-contract=off', str(source), '/Fo' + str(obj)],
                [str(Path(clang).with_name('lld-link.exe')), '/DLL', '/NOENTRY', '/NODEFAULTLIB',
                 '/OUT:' + str(dll), str(obj)]]
    with (out / 'build.log').open('w', encoding='utf-8') as log:
        for cmd in commands:
            log.write(json.dumps(cmd) + '\n'); log.flush()
            subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, check=True)
    return dll, commands


class TimingSlots:
    """Reserve both slots or undo the partial reservation immediately."""
    def __init__(self, label, root=LOCK_ROOT, wait_seconds=0):
        self.label, self.root, self.held = label, root, []
        self.borrowed = False
        self.wait_seconds, self.waited_s = wait_seconds, 0
        self.token = str(uuid.uuid4())

    def __enter__(self):
        token = os.environ.get('PERF122_TIMING_LOCK_TOKEN')
        files = os.environ.get('PERF122_TIMING_LOCK_FILES')
        if token and files:
            locks = [Path(p) for p in json.loads(files)]
            if len(set(locks)) < 2 or any(token not in p.read_text() for p in locks):
                raise RuntimeError('invalid inherited timing-slot reservation')
            self.held, self.borrowed = locks, True
            return self
        started = time.monotonic()
        announced = -60.0
        self.incomplete = {}
        try:
            while True:
                for name in ('HEAVY2.lock', 'HEAVY3.lock', 'HEAVY.lock'):
                    lock = self.root / name
                    try:
                        handle = lock.open('x', encoding='utf-8')
                    except OSError as exc:
                        busy = (isinstance(exc, FileExistsError) or
                                getattr(exc, 'winerror', None) in (32, 33, 303) or
                                isinstance(exc, PermissionError) and lock.exists())
                        if busy:
                            continue
                        raise
                    # Track ownership before writing: even a write failure must
                    # undo a successful exclusive creation.
                    self.held.append(lock)
                    with handle as f:
                        st = os.fstat(f.fileno())
                        self.incomplete[lock] = (st.st_dev, st.st_ino)
                        f.write('Codex-perf122-calibration pid=%d token=%s %s %s\n' %
                                (os.getpid(), self.token,
                                 datetime.datetime.now(datetime.timezone.utc).isoformat(), self.label))
                    self.incomplete.pop(lock, None)
                    if len(self.held) == 2:
                        self.waited_s = time.monotonic() - started
                        return self
                self.__exit__(None, None, None)
                if time.monotonic() - started >= self.wait_seconds:
                    raise RuntimeError('two heavy slots unavailable; no timing was run')
                if time.monotonic() - started - announced >= 60:
                    announced = time.monotonic() - started
                    print('Waiting for two timing slots (%.0f s); no partial reservation retained.' % announced,
                          file=sys.stderr, flush=True)
                time.sleep(.05)
        except BaseException:
            # Python does not call __exit__ when __enter__ itself fails.
            self.__exit__(None, None, None)
            raise

    def __exit__(self, *_exc):
        if self.borrowed:
            self.held.clear()
            return
        for lock in self.held:
            try:
                st = lock.stat()
                same_incomplete = getattr(self, 'incomplete', {}).get(lock) == (st.st_dev, st.st_ino)
                if same_incomplete or self.token in lock.read_text():
                    lock.unlink()
            except FileNotFoundError:
                pass
        self.held.clear()
        getattr(self, 'incomplete', {}).clear()


def check_target(ratios, low=.55, high=.60):
    """Both kinds of work must pass; do not hide a bad kernel in an average."""
    return bool(ratios) and all(low <= r <= high for r in ratios.values())


def work_once(dll, mask, iterations):
    cmd = [sys.executable, str(Path(__file__).resolve()), '--probe', str(dll),
           '--cpus', hex(mask), '--iterations', str(iterations)]
    return json.loads(subprocess.check_output(cmd, text=True,
                                            creationflags=subprocess.BELOW_NORMAL_PRIORITY_CLASS))


def measure_duty(dll, mask, busy, period, iterations, reps, wait_seconds=0):
    samples = []
    with TimingSlots('slow-core-duty-%d' % busy, wait_seconds=wait_seconds) as slots:
        lock_paths = [str(p) for p in slots.held]
        lock_evidence = {str(p): p.read_text() for p in slots.held}
        waited_s = slots.waited_s
        for rep in range(reps):
            # Bracket each slowed probe to expose unrelated load/boost drift.
            before = work_once(dll, mask, iterations)
            hogs = slow_core.start(mask, busy, period, 45)
            t0 = time.perf_counter()
            try:
                time.sleep(.20)
                from ctypes import wintypes as W
                k = ctypes.WinDLL('kernel32', use_last_error=True)
                k.GetPriorityClass.argtypes = [W.HANDLE]
                hog_classes = {str(lp): k.GetPriorityClass(W.HANDLE(int(p._handle))) for lp, p in hogs}
                if any(c != 0x20 for c in hog_classes.values()):
                    raise RuntimeError('duty-cycle worker did not start at Normal priority')
                slowed = work_once(dll, mask, iterations)
            finally:
                span = time.perf_counter() - t0
                shares = {str(lp): slow_core.cpu_seconds(p) / span for lp, p in hogs}
                for _lp, p in hogs:
                    if p.poll() is None:
                        p.kill()
                    p.wait()
            after = work_once(dll, mask, iterations)
            for kernel in ('integer', 'float'):
                if not before[kernel]['checksum'] == slowed[kernel]['checksum'] == after[kernel]['checksum']:
                    raise RuntimeError('native probe checksum changed')
            ratios = {k: statistics.mean((before[k]['wall_s'], after[k]['wall_s'])) / slowed[k]['wall_s']
                      for k in ('integer', 'float')}
            drift = {k: after[k]['wall_s'] / before[k]['wall_s'] for k in ('integer', 'float')}
            samples.append(dict(repetition=rep + 1, before=before, slowed=slowed, after=after,
                                ratios=ratios, baseline_drift=drift, hog_cpu_fraction=shares,
                                hog_priority_classes=hog_classes))
    ratios = {k: statistics.median(s['ratios'][k] for s in samples) for k in ('integer', 'float')}
    stable = all(.95 <= d <= 1.05 for s in samples for d in s['baseline_drift'].values())
    return dict(busy=busy, period_us=period, samples=samples, median_ratios=ratios,
                baseline_stable_within_5_percent=stable,
                accepted=stable and check_target(ratios), locks=lock_paths,
                lock_evidence=lock_evidence, waited_s=waited_s)


def native_probe(dll_path, mask, iterations):
    from ctypes import wintypes as W
    k = ctypes.WinDLL('kernel32', use_last_error=True)
    k.GetCurrentProcess.restype = W.HANDLE
    k.SetProcessAffinityMask.argtypes = [W.HANDLE, ctypes.c_size_t]
    # One thread on the first allowed LP; hogs occupy all stand-in LPs.
    if not k.SetProcessAffinityMask(k.GetCurrentProcess(), mask & -mask):
        raise ctypes.WinError(ctypes.get_last_error())
    dll = ctypes.CDLL(str(dll_path))
    k.GetPriorityClass.argtypes = [W.HANDLE]
    priority = k.GetPriorityClass(k.GetCurrentProcess())
    if priority != 0x4000:
        raise RuntimeError('native probe must run at BelowNormal process priority')
    result = dict(process_priority_class=priority, affinity=hex(mask & -mask))
    for name, function, result_type in [('integer', dll.integer_work, ctypes.c_uint64),
                                        ('float', dll.float_work, ctypes.c_double)]:
        function.argtypes, function.restype = [ctypes.c_uint64], result_type
        function(10000)  # fault code pages before starting the timed call
        begin = time.perf_counter()
        cpu_begin = time.process_time()
        checksum = function(iterations)
        result[name] = dict(wall_s=time.perf_counter() - begin,
                            cpu_s=time.process_time() - cpu_begin, checksum=checksum)
    print(json.dumps(result))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--cpus', default='0xF000')
    ap.add_argument('--out', type=Path, default=Path('build/pacing/calibration'))
    ap.add_argument('--clang', type=Path, default=Path('C:/Program Files/LLVM/bin/clang-cl.exe'))
    ap.add_argument('--period-us', type=int, default=4000)
    ap.add_argument('--duties', default='35,40,45', help='candidate busy percentages')
    ap.add_argument('--iterations', type=int, default=200_000_000)
    ap.add_argument('--reps', type=int, default=3)
    ap.add_argument('--wait-seconds', type=float, default=0, help='bounded wait for two timing slots')
    ap.add_argument('--build-only', action='store_true')
    ap.add_argument('--reuse-probe', type=Path, help='reuse this directory\'s already-built native probe')
    ap.add_argument('--probe', type=Path, help=argparse.SUPPRESS)
    a = ap.parse_args()
    if os.name != 'nt':
        ap.error('Windows only')
    mask = slow_core.parse_mask(a.cpus)
    if mask <= 0 or a.period_us < 100 or a.iterations < 1 or a.reps < 1:
        ap.error('positive CPU mask, iterations, repetitions and period >=100 us required')
    home = ((a.probe.resolve().parent if a.probe else a.out.resolve()) / 'home')
    home.mkdir(parents=True, exist_ok=True)
    for key in ('OPENRECOMP_HOME', 'APPDATA', 'LOCALAPPDATA'):
        os.environ[key] = str(home)
    if a.probe:
        native_probe(a.probe.resolve(), mask, a.iterations)
        return
    duties = [int(x) for x in a.duties.split(',')]
    if not duties or any(not 1 <= d <= 90 for d in duties):
        ap.error('duties must be percentages in 1..90')
    out = a.out.resolve()
    if a.reuse_probe:
        out.mkdir(parents=True, exist_ok=True)
        original = a.reuse_probe.resolve()
        for name in ('single_thread.c', 'single_thread.dll', 'build.log'):
            shutil.copy2(original / name, out / name)
        dll, commands = out / 'single_thread.dll', []
        (out / 'reused-probe.json').write_text(json.dumps({'from': str(original),
            'dll_sha256': hashlib.sha256(dll.read_bytes()).hexdigest()}, indent=2), encoding='utf-8')
    else:
        dll, commands = build_probe(out, a.clang)
    if a.build_only:
        print(dll)
        return
    result = dict(mask=hex(mask), probe_lp=hex(mask & -mask), iterations=a.iterations,
                  started_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                  source_sha256=hashlib.sha256((out / 'single_thread.c').read_bytes()).hexdigest(),
                  dll_sha256=hashlib.sha256(dll.read_bytes()).hexdigest(), build_commands=commands,
                  target_ratio=[.55, .60], preferred_ratio=.575, period_us=a.period_us, measurements=[],
                  limitation='Scheduling proxy; does not reproduce Ivy Bridge IPC, cache, memory, SMT or GT 730 GPU.')
    result_path = out / 'calibration.json'
    reservation_deadline = time.monotonic() + a.wait_seconds
    try:
        for duty in duties:
            remaining_wait = max(0, reservation_deadline - time.monotonic())
            row = measure_duty(dll, mask, duty, a.period_us, a.iterations, a.reps, remaining_wait)
            result['measurements'].append(row)
            print('busy=%d ratios=%s accepted=%s' % (duty, row['median_ratios'], row['accepted']), flush=True)
            result_path.write_text(json.dumps(result, indent=2), encoding='utf-8')
            if row['accepted']:
                result['accepted_busy'] = duty
                break
    except Exception as exc:
        result['error'] = str(exc)
        raise
    finally:
        result_path.write_text(json.dumps(result, indent=2), encoding='utf-8')
    if 'accepted_busy' not in result:
        sys.exit('No stable candidate met both throughput targets; inspect calibration.json and refine --duties.')


if __name__ == '__main__':
    main()
