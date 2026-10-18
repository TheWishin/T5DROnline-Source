## Desync hunt (branch desync-hunt, 2026-10-19)

Real players saw desyncs with no rollback before them (0.1.9 match 2, 1.0.0
19:38 match 1) and, in the owner's 1.0.0 logs of 2026-10-18, more: after an
opponent switch every frame different from the first compared one (Heihachi
vs Kazuya and Heihachi vs Heihachi on stage 29, two opponents: 4,998 of 5,221
and 7,393 of 7,619 frames), a rematch against Mokujin likewise, and in other
matches 829-1,298 mismatching frames that began mid-round and ended at the
next round (Jin vs Dragunov, Kazuya vs Heihachi). None of it reproduced with
two games on one PC as the tests ran them.

**The cause: the title's second random generator.** 0x3AFC3C is a shuffled
LCG (x * 0x19660D + 0x3C6EF35F, a 32-word table) kept in the calling thread's
TLS -- state at TLS+0, a "seeded" byte at +0x10094, the last draw at +0x10098,
the table at +0x1009C; only the main thread draws from it, so it lives in the
main thread's TLS block 0x0E000000. Netplay reseeded the Mersenne Twister and
the C rand() at its sync points, never this one. Most of the game draws from
it: the fighters' move effects, the camera (0x878CC: angle and distance of a
camera move), the game mode's set-up, and also effect and stage tasks beside
the scene (the stage emitter 0xA1768, ~10 draws a frame; effects that spawn
9-11 particles when they first play). Three ways it went apart between PCs:

1. *History.* Its state at a match depended on everything the process had
   drawn since boot: a game that had played other opponents and one just
   started began the fight from different states -- the opponent-switch
   desyncs.
2. *Timing.* An effect plays its first burst on the frame its data has come
   in from the file thread, which no loader drain waits for: a frame or a few
   apart on two PCs (two runs of one scripted match in one process: the burst
   at frame 470 in one, 477 in the other), and every draw after that differed.
3. *The select screen.* The game mode's set-up picks Mokujin's fighter for the
   match from it (0x121E0C <- 0x5A304 <- 0x53C88, game mode phase 2), before
   lockstep frame 0, after however many draws each PC's select screen made:
   Mokujin copied Feng on one PC and Kazuya on the other (0x1009094C 0x1001F
   vs 0x1000F) -- the ingame-select agent's "Mokujin desyncs" too.

**Why it was gameplay, not cosmetic.** The camera words are left out of the
hashes as display state, and so is +0x6C8 of each fighter block (0x10090708,
0x10090FD8): the fighter's camera-projected screen x. But 0x808D8 compares the
two and writes which fighter stands on the left (+0x1C2/+0x1C3 of the blocks
at 0x10090040 / 0x10090910), and that decides which way an up or down tap
sidesteps. Two PCs with different camera draws turned the same sidestep
different ways (the first differing words of every such run: the side flags,
then the fighters' processed input, DOWN on one PC and UP on the other), and
the fight came apart -- or, when the round ended the same way, came back
together at the next round: the mid-round transients of the owner's logs.
The side flags were in the hash all along (they flagged it); the camera
draws were not.

**The fix** (`src/rollback/rb_rand.cpp`, `src/netplay/t5_hooks.cpp`
`reseed()`; T5_TLS_RAND=0 turns it off):

- the scene (the scene task 0x10BD8: menus, game mode, fight) draws from the
  TLS generator as before; every other draw on the main thread -- effect and
  stage tasks, render passes -- comes from a private generator in host
  memory, so they can no longer move the scene's sequence, whenever they run
  (a rollback's draw cut, which skips some of them in re-simulated frames,
  cannot either);
- netplay reseeds the TLS generator at every sync point (frame 0 of a
  session, every scene barrier) from the match seed, like the Twister and
  rand(): the process's history no longer reaches a match;
- with a direct-fight session set up, the generator is pinned to the session
  seed (T5_NET_SEED, the lobby's, the same on both PCs before the handshake)
  at every boundary while the select mode runs, so the game mode's set-up
  (Mokujin's pick) draws the same on both PCs however long the select took.

The TLS block (0x0E000000, 128 KB) is in the rollback state already
(`rb_state.cpp` kSave): a restore puts the generator back with the frame,
and the re-simulation draws the same numbers (rb_equiv_test --lag and
--force below: equal on every frame).

The hashes keep the camera words out and the side flags in (comments at
kDefaultHashSkip / kGameSkip).

**New tools.**

- `tools/rb_equiv_test.py`: one game, the same scripted match twice (netplay's
  local mode: both players scripted with motion inputs, the rollback loop
  running, a fixed seed and clock), compared frame by frame on the final
  gameplay hash. The test run adds `--lag N` (T5_NET_LOCAL_LAG: the second
  player's input known N frames late -- predicted, mispredicted, rolled back
  as against a peer N frames away), `--force every:depth` (T5_RB_NET_FORCE:
  rollbacks with the same inputs), `--cpus N`, `--test-env` (any hardware
  stand-in below); `--full` hashes without the skip list (T5_RB_HASH_FULL),
  `--dump` diffs the words around the first difference (T5_RB_DUMP_AT,
  `tools/rb_desync_diff.py --first-diff`). A deterministic game gives the
  same hash on every frame, at any fps, with or without rollbacks; before the
  fix no two runs of Jin vs Dragunov did (all twelve apart from frame 1546).
- `tools/fight_flow_test.py`: `--cpus1/--cpus2` (affinity + PS3_CPUS),
  `--hitch2 MS[:MIN:MAX]` (T5_TEST_HITCH: the joiner's main thread stalls
  while its other threads run on), `--gamedata1/2` (a player's own save),
  `--clock2 S`, `--fresh-every K --fresh-role alt` (opponent switches against
  fresh games), `--colors` (costumes), `--moves` (motion inputs: electrics,
  hellsweeps, qcf/hcb, dashes, sidesteps, throws, ki charge -- a random mash
  almost never does them).
- Runtime (patch 0040): `PS3_TEST_FS_DELAY=ms[:ms_per_MB]`, a slow or cold disk
  on one PC. Diagnostics: `T5_RAND_TRACE=1|2|3` (rand() and TLS-generator
  calls per thread and caller, distinct caller chains with mode and phase,
  per-frame draws), `T5_RB_WFT_NET=from:frames` (the write-fault tracer in the
  netplay loop).

**What was tested** (this PC, Ryzen 9 7950X, other agents' games running;
fixed build unless marked):

RESULTS_TABLE

**Left open.** Two PCs that differ in the CPU's make (Intel vs AMD) or a real
display at 240/500 Hz were stood in for, not used. The private generator
makes effect particles and stage emitters differ between the two PCs' screens
(display only, as the camera may).
