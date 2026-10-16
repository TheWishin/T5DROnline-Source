# Making a release

Releases are built and published by GitHub Actions
(`.github/workflows/release.yml`) when a version tag is pushed. Nobody needs a
GitHub token on their PC: the workflow publishes with its own `GITHUB_TOKEN`,
and only after the repository owner approved it on GitHub.

How the zip is put together, and why, is in [RELEASE.md](RELEASE.md). This page
is the procedure.

## One-time setup (the owner, in the GitHub web UI)

Only the owner (TheWishin) may publish releases. Two settings enforce that.

**1. The `release` environment -- every publish waits for the owner's approval.**

Settings -> Environments -> **New environment** -> name `release` ->
**Configure environment**:

- **Required reviewers**: tick it, add `TheWishin`.
- **Prevent self-review**: leave it **off** (unticked), so the owner can approve
  a run they started themselves.
- **Deployment branches and tags**: choose **Selected branches and tags** ->
  **Add deployment branch or tag rule** -> Ref type **Tag** -> pattern `v*` ->
  **Add rule**.
- No secrets, no variables, no wait timer. **Save protection rules**.

**2. A tag ruleset -- only the admin creates, moves or deletes release tags.**

Settings -> Rules -> Rulesets -> **New ruleset** -> **New tag ruleset**:

- Ruleset name `release tags`, Enforcement status **Active**.
- **Bypass list** -> **Add bypass** -> **Repository admin** (role), "Always allow".
- **Target tags** -> **Add target** -> **Include by pattern** -> `v*`.
- Rules: tick **Restrict creations**, **Restrict updates**, **Restrict
  deletions** (keep **Block force pushes** ticked).
- **Create**.

Why both: the main session pushes with the owner's own git credentials, so to
GitHub its pushes *are* the owner's. The ruleset and the workflow's owner check
(`github.actor` and `github.triggering_actor` must be the repository owner, for
tag pushes and manual runs) keep everyone else out, but cannot tell the owner
from a tool using their login. The environment's required reviewer can: the
publish job waits until the owner clicks **Approve** on GitHub (web or the
GitHub mobile app).

Nothing else is needed: Actions are already enabled (CI runs), and the publish
job asks for `contents: write` itself; the build job only reads.

## Cutting a release (the main session)

1. **Pick the version.** `vMAJOR.MINOR.PATCH`, optionally with a suffix:
   `v0.1.0-preview`, `v0.2.0-rc1`, `v0.2.0`. A suffix makes it a GitHub
   *pre-release*. Never reuse a version number.

2. **Changelog.** In `CHANGELOG.md`, add a section for the version above the
   older entries. Its heading must start with the version:

       ## v0.1.0-preview (2026-10-20)

       First public test build: offline play (Arcade, Versus, ...), no online yet.

       ### Game
       - ...

   Everything up to the next `## ` heading becomes the release notes (`###`
   subsections are kept). The workflow fails within a minute if the section is
   missing or empty. Also update the "No release zip is published yet" line at
   the top of `README.md`. Commit on `main`.

3. **Check locally (recommended).** The local run also checks the zip against
   the real keys and the game files, which CI does not have (see "Local
   build" below). At least:

       python tools/check_no_game_data.py --keys keys/ps3.keys
       python tools/release_notes.py --version 0.1.0-preview --check

4. **Push `main`** and wait for CI to be green.

5. **Tag and push the tag:**

       git tag -a v0.1.0-preview -m "T5DR Online 0.1.0-preview"
       git push origin v0.1.0-preview

   The tag must point at a commit on `main`.

6. **The owner approves.** The run (Actions -> Release) builds and checks the
   zip (estimated 15-25 min), stores zip + `SHA256SUMS` + release notes as the
   run's artifact, then the **publish** job waits. GitHub notifies the owner
   ("deployment review"). Download the artifact from the run's summary page,
   try it, then **Review deployments** -> tick `release` -> **Approve and
   deploy**. **Reject** stops it; nothing is published.

7. **Check the release page**: the zip and `SHA256SUMS` are attached, the notes
   are right, the pre-release badge is there for a suffixed version.

## What the workflow does

Job **build** (`windows-latest`, read-only token):

| step | |
|---|---|
| owner check | tag pushes and manual runs: actor and re-runner must be the owner |
| version | from the tag (`v0.1.0-preview` -> `0.1.0-preview`); refuses other tag shapes and tags not on `main`; a suffix -> pre-release |
| release notes exist | `tools/release_notes.py --check` |
| guard | `tools/check_no_game_data.py` on the tracked files |
| Python | `actions/setup-python` CPython **3.12.10** + `tools/release-requirements.txt` (pycryptodome 4.0.0, hash-checked) -- this interpreter is copied into the zip |
| LLVM | `tools/fetch_llvm.py`: the official **LLVM 23.1.3** `clang+llvm-23.1.3-x86_64-pc-windows-msvc.tar.xz`, SHA-256 checked against the pin |
| MSVC | `ilammy/msvc-dev-cmd` (MSVC + Windows SDK of the runner image), Ninja |
| ps3recomp | `tools/prepare_ps3recomp.py`: the pinned commit + `patches/ps3recomp/*.patch` |
| package | `tools/package_release.py --release`: stages everything, builds the runtime host and `T5DR Online.exe` with the pinned clang-cl, self-tests the bundled Python, scans folder and zip, writes `SHA256SUMS` |
| guard on the zip | `package_release.py --scan-only` on the zip once more |
| smoke test | `tools/smoke_release.py`: unpack into a fresh folder; layout, version stamp, bundled Python with a bare `PATH`, `prereqs.py` finds everything inside the folder, clang-cl version, `t5dr.exe` and the starter import only Windows DLLs. Then (informational only) the launcher renders offscreen and `T5DR Online.exe` starts it |
| notes | `tools/release_notes.py`: the CHANGELOG section + download facts (SHA-256, LLVM/Python versions, ps3recomp pin, commit, run link) |
| artifact | `T5DR-Online-<version>` (zip, `SHA256SUMS`, `RELEASE_NOTES.md`), kept 30 days |

Job **publish** (`ubuntu-latest`, environment `release`, `contents: write`),
only for tag pushes, after approval: owner check again, download the artifact,
`sha256sum -c`, then `gh release create <tag> <zip> SHA256SUMS --verify-tag
--notes-file RELEASE_NOTES.md [--prerelease]`. It is safe to run twice: an
existing draft or half-published release gets its files and notes; a published
release that already has the *same* zip only gets its notes refreshed; a
published release with a *different* zip is never overwritten (yank it first).

What the zip ships, pinned: LLVM 23.1.3 (clang-cl, lld-link, clang's headers),
CPython 3.12.10 with Tcl/Tk 8.6 and pycryptodome 4.0.0, ps3recomp `f17bcd3` +
our patches, and the runtime host built by clang-cl 23.1.3 against the runner
image's MSVC libraries and Windows SDK (static C runtime). To move a pin:
LLVM in `tools/fetch_llvm.py`, Python in `release.yml` (`PYTHON_VERSION`),
pycryptodome in `tools/release-requirements.txt`, ps3recomp in
`tools/build_game.py`. python.org's "embeddable" Python is not used: it has no
tkinter, and the launcher is a tkinter program.

## Dry runs (nothing is published)

- **Actions -> Release -> Run workflow** (owner only), optionally with a
  version to stamp; default `0.0.0-dryrun.<run number>`.
- **Any push to a branch** that changes the release tooling
  (`release.yml`, `tools/package_release.py`, `fetch_llvm.py`,
  `release_notes.py`, `smoke_release.py`, `release-requirements.txt`) runs the
  same build -- so merging a tooling change to `main` tests it before the next
  tag.

Both stop after the artifact. A missing CHANGELOG section is only a warning.

## Re-running

- **The build failed** (a download, the runner): Actions -> the run -> **Re-run
  failed jobs** (owner only). Approve again when it reaches publish.
- **Publish failed half-way**: **Re-run failed jobs** re-runs only publish,
  with the same artifact (same bytes, same checksum), and finishes the release.
- **Rejected, or not approved in time** (GitHub waits 30 days): re-run the
  publish job while the artifact exists (30 days), or push the tag again (below).
- **The code needs a fix and nothing was published yet**: delete the tag,
  fix on `main`, tag again:

      git push origin :refs/tags/v0.1.0-preview
      git tag -d v0.1.0-preview
      # fix, commit, push main, then step 5 again

- **It was published**: do not move the tag. Yank it if needed (below) and
  release the next version (`v0.1.1-preview`, `v0.1.0-preview.2`).

## Yanking a bad release

- **Buggy, but harmless**: Releases -> the release -> **Edit**: put a warning at
  the top of the notes ("Do not use, see v0.1.1-preview"), tick **Set as a
  pre-release**, **Update release**. Links keep working.
- **Must go** (broken zip, wrong files): Releases -> the release -> **Delete**
  (the owner, in the web UI; the main session has no API access). Then remove
  the tag, so no one builds from it by mistake:

      git push origin :refs/tags/v0.1.0-preview
      git tag -d v0.1.0-preview

  Note the withdrawal in `CHANGELOG.md` with the next release. Do not publish
  different bytes under the same version later -- release a new version.
- **Game data in a zip** (the scans exist to make this impossible): delete the
  release at once, as above, and fix the scan so it catches that file before
  anything else.

## Local build

The same commands the workflow runs; output under your own folder. Use
`--jobs` when other builds share the PC.

    python tools/fetch_llvm.py --dest build/<you>/llvm          (or --llvm "C:\Program Files\LLVM" if it is 23.1.3)
    python tools/prepare_ps3recomp.py --dest build/<you>/ps3recomp
    python tools/package_release.py --release --version 0.1.0-preview --llvm build/<you>/llvm ^
        --ps3recomp build/<you>/ps3recomp --out build/<you>/dist --jobs 8 ^
        --keys keys/ps3.keys --game-dir build/recomp --game-dir build/spu --game-dir game
    python tools/smoke_release.py build/<you>/dist/T5DR-Online-0.1.0-preview.zip --version 0.1.0-preview
    python tools/release_notes.py --version 0.1.0-preview ^
        --release-json build/<you>/dist/T5DR-Online-0.1.0-preview/release.json ^
        --sums build/<you>/dist/SHA256SUMS

`--keys` and `--game-dir` add two checks CI cannot do (it has neither keys
nor game files): no key bytes anywhere, and no file byte-identical to a game
file. The smoke test's GUI part opens the launcher window for a few seconds;
`--no-gui` skips it.
