# 1.2.0 low-end work: experimental SIMD, remaining sound and lightning work

Item 6 is **partial**. Patch `0104-low-end.patch` contains an experimental,
**default-off** baseline-x64 SIMD path for `vmx_vmaddfp`. It does not change
SPU sound arithmetic, the renderer, the protocol or the default simulation.
No speedup or bit-identity result has been measured in this working copy.
Nothing was built or run.

## Switch and scope

The compile cap is `PPU_VMX_SOFT2=1`, supplied when compiling the lifted PPU
code. Without it (`0`, the default), the existing scalar implementation is
compiled. This is deliberately not an enabled launcher option: normal Build
Game stays on the proven path. Builds defining `__FMA__` and non-x64 builds
also retain the existing implementation. No additional instruction-set
requirement beyond baseline x64 SSE2 is introduced by the experimental path.

The work addresses the four scalar single-precision software FMA lanes that
`RENDER_PERF.md`, “1.1.7 … GitHub #12”, identifies as 4.4% of the stand-in's main
thread. Each pair now evaluates the existing double-product, TwoSum and
round-to-odd sequence with SSE2 double arithmetic. Finite float products and
sums fit in normal doubles, including float subnormal inputs. The final
round-to-odd adjustment and conversion remain the scalar reference's exact
operations. There is no reassociation, approximation or non-fused float
multiply/add substitution.

The VMX path keeps `x*z+y`, big-endian lane order, VSCR NJ input/output flush,
NaN canonicalisation and destination aliasing. Any non-finite input or
noncanonical MXCSR takes the original scalar path. Compiling with fast-math,
reassociation or contraction invalidates the reasoning; `-ffp-contract=off`
must remain in force. This reasoning does not replace the tests below.

## Tests and acceptance gates for the maintainer

Added, not executed:

- `tests/test_low_end_120.py`: source guards for default-off policy, finite and
  MXCSR gates, exact operand order, scalar fallback, patch hunk counts and the
  native harness wiring. Missing old patch fails these guards.
- `tests/c/vmx_soft2_test.c`: compile against the prepared runtime with
  `-DPPU_VMX_SOFT2=1`, baseline x64 and `-ffp-contract=off`. It compares the
  actual VMX result to the pre-change scalar calculation bit for bit, both
  NJ modes and all destination aliases. It covers signed zeros, subnormal
  boundaries, cancellation/ties, overflow, Inf, signalling/quiet NaNs and
  payloads; 500,000 random vectors and 1,000,000 direct finite helper lanes.
  Old headers fail compilation: the new helper/implementation marker must
  exist, so an unchanged scalar path cannot produce a vacuous pass.

A prepared runtime is absent here, so whole-series application, header
compilation and numeric checks remain unproved. Before enabling the cap:

1. Apply the complete patch series in the maintainer's separate authorized
   source tree and compile/run the native harness for baseline x64. Add
   forced halfway/cancellation and exponent-sweep cases if any failure occurs.
   The native runner registers it as `vmx_soft2`:
   `python tests/run_ps3recomp_tests.py --ps3recomp PREPARED_TREE --only vmx_soft2`.
2. Run the existing `runtime/ppu/tests/test_fp_det.c`, FP vector comparisons,
   and `tools/fp_audit.py --strict` against both game DLL builds, following
   `docs/NETPLAY.md` “Same game state on every CPU”.
3. Compare cap-off/cap-on CPU time per frame across repeated baseline builds
   on a CPU without FMA3 (or the documented stand-in), using
   `tools/fight_bench.py` and `tools/perf_compare.py`. Finite scanning, copies
   and scalar rounding correction may outweigh saved arithmetic. Reject the
   optimization if it has no repeatable gain.
4. Require a real **two-PC pair with 0 mismatches**, baseline cap-on versus
   existing baseline cap-off and versus hardware-FMA builds, in lockstep and
   rollback under jitter. Compare every confirmed frame and final result
   hash. Defaults and old clients retain their existing behavior.

## Sound core cost: investigation remains

Existing patches 0027, 0041 and 0064 already reduce sound-core cost; patch0064
requires bit-for-bit equivalence with the prior `SPU_NEAR_FLOAT` algorithm.
The 1.1.7 measurements still identify the sound core as about 0.3 of a core,
a fixed audio-rate cost. Moving its priority or processor did not prove a
faster game. This patch intentionally makes no further sound change without
a profile showing a reducible cost and an equivalence harness.

On an already-running maintainer build with matching PDB/line tables, sample
its sound thread with `tools/thread_sampler.py --exe <exe> --pid <pid>
--threads spu --secs 10 --hz 2000 --json <private-output>`. Compare per-thread
CPU from repeated `fight_bench.py --json` runs, not game FPS alone. Existing
`spu_int_sse` and `spu_near_float_sse` suites and the documented `SPU_SELFCHECK`
checks are required for any subsequent sound helper change. Collect outputs
only in the maintainer's private game workspace, never in this source clone.

## Cheaper lightning: not implemented

There is no verified render signature that isolates the EWGF lightning from
other scene effects in this clone. Patch0079's `PS3_EFFECTS=0` skips a broad
class of transparent depth-tested scene draws: sparks, flames, smoke, mist,
haze, glare and waterfalls. Calling that a “cheaper lightning” setting would
misrepresent it and could hide useful hit cues. No address or shader hash is
guessed, and no launcher setting is added for an unimplemented feature.

The maintainer needs a capture/per-draw profile (`RSX_GPU_PASSES=2`,
`RSX_DRAW_CSV`, existing tools) that identifies the lightning and proves a
cheaper host-only rendering method retains onset, duration and visibility.
`tools/effects_test.py` already scripts EWGF, including a slow-GPU case, and
checks effect duration; its aggregate draw-count metric must be augmented
for a future reduced-draw implementation so a legitimately cheaper effect
does not fail just because it has fewer draws. Patch0085's semaphore ACQUIRE
behavior must stay enabled: reducing the animation's simulation lifetime is
not a cosmetic optimization. Game/visual checks and a real pair with
**0 mismatches** remain necessary for any eventual renderer fix.
