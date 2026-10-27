# Mac vs PC online: the owner's test

Online play on macOS is built and prepared but has **never run on a Mac**: everything was written
and checked on the Windows development PC (`tests/test_macos_port.py` compiles all of `src/` for
arm64 macOS there, syntax only). It stays a test build, off by default, until a Mac-vs-PC match ends
with **0 mismatching frames**. This page is the step list for that test: an Apple silicon Mac
(M5 Pro, macOS 26) and a Windows PC on the same network, two lobby accounts (one per machine: the
same account cannot be logged in twice). What was ported is in docs/MACOS.md ("Status 1.1.5").

Plan about an hour: half of it is the two builds.

## 0. The same code on both machines

Both games must come from the **same commit** (the lobby pairs equal builds only: the build id is
the game's SHA-1, the code id and the netplay version).

- Mac and PC: a checkout of the branch with this page (`git log -1` shows the same hash on both).
- Both: `python tools/build_game.py --code-id` (Mac: `.venv/bin/python ...`) prints **the same 16
  hex digits**. If not, stop: something differs (a patch, CMakeLists.txt, the PGO profile).
- The PC builds from source (a checkout has no prebuilt `t5dr.exe`, so `build_game.py` compiles
  everything with Visual Studio's clang-cl). A release zip's game has another code id and does not
  pair with the Mac.

## 1. Mac: tools

As in the README's "Building on macOS": Xcode command line tools, then

```sh
brew install cmake ninja sdl2 glslang spirv-cross
brew install python-tk@3.12          # Tk for the launcher (Homebrew's Python has none without it)
python3.12 -m venv .venv && .venv/bin/pip install pycryptodome
.venv/bin/python -c "import tkinter; print(tkinter.TkVersion)"    # must print a version
```

(python.org's installer has Tk built in; any Python 3.10+ with Tk works.)

## 2. Mac: build with the online modules

```sh
.venv/bin/python tools/build_game.py --pkg <your.pkg> --rap <your.rap> --out native --macos-online
```

- An earlier offline build in `native/` is fine: the lift step runs again (about 2 minutes) because
  the online build lifts with hook slots (`src/rollback/hook_slots.txt`), and CMake is configured
  again with `-DT5DR_MACOS_ONLINE=ON`.
- Look for these lines: `hook slots: 55 function(s) asked for` (lift; a `WARNING: --hook-slots
  0x...` after it is worth sending), `macOS online modules: on (#define PPU_HOOK_SLOTS 55)`
  (configure), and at the end `built .../native/build/cmake/t5dr (online modules: a test build,
  docs/MACOS_ONLINE_TEST.md)`.
- A compile error here is the first thing to send (the whole output: `src/` has never been compiled
  by Apple's clang). Fixes are usually one line.

## 3. Mac: the math check (5 minutes, before any match)

```sh
.venv/bin/python tools/fp_vectors.py --ps3recomp deps/ps3recomp --compare tests/data/fp_vectors_x64.txt
```

It lifts 55 floating-point and vector instructions with the real lifter, runs each over 100,000
operand sets and compares digests with the PC's. **Expected: every instruction matches, exit code
0.** If `fsqrt`, `fsqrts` or `frsqrte` differ, `deps/ps3recomp` lacks patch 0078 (run step 2 again).
Any other name is a new finding: run `--dump <name> --count 50` on the Mac and on the PC and send
both outputs. Do not play online before this passes -- the match would go out of sync.

## 4. Mac: offline smoke (2 minutes)

```sh
.venv/bin/python tools/run_game.py --out native --log mac-offline.log
```

Title screen, a VS fight against the CPU, quit. Then

```sh
grep -E "\[fp\]|TLS random generator|hook slot|detour" mac-offline.log | head
```

should show `[fp] guest threads: FPCR 0x00000000 ...`, no `FPCR changed` line, `TLS random
generator: the scene's own stream ...` (the hook slots work), and no `no hook slot` line.

## 5. PC: build and lobby

1. Build the same commit: `python tools/build_game.py --pkg <pkg> --rap <rap> --out native`.
2. Start a lobby on the PC for the two of you: `python lobby/run.py host` (or the Online tab's
   **Host for friends**). Windows asks whether Python may accept connections: allow private
   networks. It prints `Friends on your own network: <PC address>:7781#<fingerprint>` -- that line
   is the Mac's server. (The production lobby works too if it accepts this build; a local one keeps
   test builds and test accounts away from players.)
3. Start the launcher from the checkout: `python launcher/t5dr_launcher.pyw`. Its game folder is
   `native` in the checkout by default (Settings shows it). Online tab: server
   `127.0.0.1:7781#<fingerprint>`, **register** account A (any name) and log in.

## 6. Mac: launcher and account

```sh
.venv/bin/python launcher/t5dr_launcher.pyw
```

- Online tab: server = the "Friends on your own network" line, **register** account B, log in.
  The PC's launcher must list B (and B's must list A) **without** "other build"; if it says other
  build, step 0 failed.
- macOS asks once whether `t5dr` (and Python) may accept incoming network connections: **Allow**
  (each new build asks again: the binary changed).
- If the launcher does not start or the tab shows an error, send `launcher.log` (in the checkout's
  root) and the Terminal output. It has run on Windows only; the parts it needs on a Mac (the game is `t5dr`,
  no firewall rules, no window placement) are guarded, but nobody has opened it on a Mac.

## 7. The lockstep test (the gate)

1. On the PC, challenge B (a casual challenge, **not ranked**). Accept on the Mac. Both games start
   (the Mac's window may open behind the launcher).
2. Play at least **three matches** in a row (accept the rematches), different fighters and stages,
   with KOs, a time-out and a perfect if you can. The Mac's keyboard plays as in the README
   ("Building on macOS"); a controller works too.
3. A Mac offers no rollback in this build, so both games run the delay-based lockstep: the Mac's log
   says `rbnet: macOS: rollback not offered (T5_MACOS_ROLLBACK=1 tests it) -- the match runs in
   lockstep`, both say `lockstep starts: frame 0`.
4. After each match, on each machine (the launcher writes the game's log to `native/logs/`):

   Mac: `grep -hE "mismatching|in sync|FPCR" native/logs/game-*.log | tail -5`

   PC (PowerShell): `Select-String -Path native\logs\game-*.log -Pattern "mismatching","in sync" | Select-Object -Last 5`

   **Pass:** every `sync check through frame N: 0 mismatching frame(s) -- in sync` and every
   `session ... ends (...): ... 0 mismatching frame(s)`, and both launchers show the same result.
5. **Fail** (a line with a number above 0, or a match void as "out of sync"): start both launchers
   with `T5_NET_DESYNC_DUMP=1` in the environment (Mac: `T5_NET_DESYNC_DUMP=1 .venv/bin/python
   launcher/t5dr_launcher.pyw`; PC: `$env:T5_NET_DESYNC_DUMP=1; python launcher\t5dr_launcher.pyw`),
   play until it happens again and send both `native/logs/` folders. The dumps name the first
   mismatching frame and the bytes that differ.

## 8. The rollback test (only after 7 passed)

Start the Mac's launcher with `T5_MACOS_ROLLBACK=1 .venv/bin/python launcher/t5dr_launcher.pyw` and
play three more matches. Now both offer rollback: `rbnet: rollback offered`, `rollback mode starts`.
Pass as in 7, and also look at the Mac's speed: the `rbnet:` summary lines every few seconds
(`fps`, `ms per rollback`) and `state: ... commits: X ms each (write watch Y ...)`. The write watch
is page protection on a Mac (a fault per first write to a 16 KB page) and has never been measured:
send those lines whatever they say.

## 9. What to send back

- `--code-id` of both, the fp_vectors result, the build output if step 2 failed.
- Per test (7, 8): both `native/logs/` folders and both `launcher.log` files (they contain the account
  names and the PC's address -- keep them out of public places), and how it felt (frame rate,
  freezes, input lag).

When 7 passes over several matches (and 8, for rollback), online on a Mac can be switched on for
players: the `--macos-online` default and the README; until then it stays this test build.
