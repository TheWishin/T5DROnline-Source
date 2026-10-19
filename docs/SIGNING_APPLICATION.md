# SignPath Foundation: application pack

Everything to paste into the application for free code signing. How the signing works once
we are accepted is in [RELEASING.md](RELEASING.md), "Code signing".

SignPath Foundation signs open source projects for free and is the publisher of what it signs.
Its rules are on https://signpath.org/terms (read 2026-10-18). The application form is at
https://signpath.org/apply. Fields reported by applicants: the public repository, the license, the
download address and a description. The form may ask more. Answer from this page.

## 0. Before you apply

Tick each line.

- [ ] The repository and the license: MIT, file `LICENSE` in the repository root. No commercial
      dual license.
- [ ] Nothing proprietary in what we sign. We sign only `T5DR Online.exe` and `runtime/t5dr.exe`,
      built from this source. The zip also carries other people's open source programs (LLVM, CPython,
      Tcl/Tk, pycryptodome, ps3recomp, at3_standalone). We do not sign those.
- [ ] No malware, no hacking tools. The project is a game port. It contains no part of the game.
- [ ] Maintained and released: releases are on https://github.com/TheWishin/T5DROnline/releases.
- [ ] The download page says what the program does: the README of the public repository does.
- [ ] Two-factor login (MFA) on your GitHub account and, once you have it, on SignPath.
- [ ] A mailbox you read. SignPath answers by e-mail.
- [ ] The two open points in section 6 are settled, or go into the application as questions.
- [ ] Do **not** add SignPath's credit line to the README yet. It says "certificate by SignPath
      Foundation". Add it after the acceptance (section 7).

SignPath decides alone and gives no appeal. They look at the project's reputation too. A one-person
project with a short history may be asked questions. Answer them from sections 2 to 5.

## 1. Paste into the form

**Project name:** T5DR Online

**Public repository (source):** https://github.com/TheWishin/T5DROnline-Source

**License:** MIT

**Download address (free):** https://github.com/TheWishin/T5DROnline/releases

**Home page:** https://github.com/TheWishin/T5DROnline

**What is signed:** two Windows programs (`.exe`) inside the release zip: the launcher starter
`T5DR Online.exe` and the game runtime `runtime/t5dr.exe`.

**Short description:**

> T5DR Online is an open source Windows port of the PlayStation 3 fighting game Tekken 5: Dark
> Resurrection. The game's code is translated ahead of time on the player's own PC into a normal
> Windows program, so no emulator is needed. It adds online play with rollback netcode.

**Long description:**

> T5DR Online runs Tekken 5: Dark Resurrection (PS3, PSN release) natively on Windows. Players use
> their own copy of the game. The release zip, the repository and the releases contain no part of the
> game: no game files, no translated game code, no keys. A check in the build refuses to make a zip
> that holds any of these.
>
> The zip holds a launcher (Python and tkinter, with a private copy of CPython), the runtime
> `t5dr.exe` (C and C++, Direct3D 12, built from our code and the MIT-licensed ps3recomp library with our
> patches), a pinned LLVM toolchain and our scripts. On the player's PC the launcher builds the game
> from the player's own package into a DLL with the bundled compiler. Online play uses a small lobby
> server (also in this repository) and a direct connection between the two players' PCs.
>
> Users: people who own the game and want to play it on Windows, also online against friends.
> The project is developed in the open. Releases are made only by the maintainer.
>
> The signed programs are: `T5DR Online.exe` (a 124 KB starter that opens the launcher) and
> `runtime/t5dr.exe` (the game runtime). Both are built from the repository by the GitHub Actions
> workflow described below.

**Artifact type:** exe files in a zip (we send a zip with the two files to SignPath; the release zip
itself is a plain zip).

## 2. The build in CI

- Workflow: [`.github/workflows/release.yml`](../.github/workflows/release.yml), "Release".
- It runs on a GitHub-hosted runner (`windows-latest`) when the maintainer pushes a version tag
  `vMAJOR.MINOR.PATCH[-suffix]` on a commit of `main`. Nobody else can start it: tags are protected by
  a repository ruleset, and the workflow stops if the person who started it is not the repository owner.
- The build is fully scripted in the repository (`tools/package_release.py` and the files it
  calls). Nothing is built by hand.
- Pinned inputs: LLVM 23.1.3 (official archive, SHA-256 checked), CPython 3.12.10, pycryptodome 4.0.0
  (hash-checked), ps3recomp at one commit plus the patches in `patches/ps3recomp/`, the MSVC and
  Windows SDK of the runner image.
- Programs built in the run: `runtime/t5dr.exe` (CMake, Ninja, clang-cl, static C runtime) and
  `T5DR Online.exe` (MSVC `cl.exe` and `link.exe`, from `launcher/stub/t5dr_stub.c`).
- Checks in the same run, before anything is signed or published: the game-data guard on the
  tracked files, a scan of the folder and of the zip for game files, lifted code and keys, a check of
  every program's imports, and a smoke test of the unpacked zip with a bare PATH. The repository's
  unit tests run on every push (`.github/workflows/ci.yml`).
- Signing step: the two programs are uploaded as a GitHub Actions artifact and sent to SignPath with
  the official `signpath/github-action-submit-signing-request` action. The maintainer approves each
  request in SignPath. The signed files come back and the build checks that each is the built file
  plus a valid signature, and nothing else.
- Then the zip, `SHA256SUMS` and the release notes are made. The release is created as a draft.

## 3. Artifacts and paths

| File in the release zip | Built from | Signed |
|---|---|---|
| `T5DR Online.exe` | `launcher/stub/t5dr_stub.c` (+ icon, manifest, version info) | yes |
| `runtime/t5dr.exe` | `CMakeLists.txt`, `src/`, ps3recomp + `patches/ps3recomp/` | yes |
| `python/` (CPython 3.12.10) | python.org, unchanged | no (signed by the Python Software Foundation) |
| `toolchain/llvm/` (clang-cl, lld-link) | llvm.org 23.1.3, unchanged | no (not ours) |
| Scripts: `launcher/`, `tools/`, `lobby/` | this repository | not signable |

In the build, the folder is `dist/T5DR-Online-<version>/`. The two files to sign are copied to
`dist/to-sign/` with the same relative paths. The artifact configuration (the XML to put into SignPath) is in
[RELEASING.md](RELEASING.md), "A. SignPath Foundation". It signs exactly these two paths.

`t5dr_game.dll` (the player's own game code) is built later on the player's PC. It is never
shipped and never signed.

## 4. Who releases

One person: the repository owner, GitHub account **TheWishin**. The owner is the only maintainer,
has the only write access to the repositories, tags the release and approves the signing request.
Proposed SignPath roles: Author, Reviewer and Approver are all the owner.

## 5. How releases are verified

1. The tag build runs the checks in section 2.
2. The release is created as a **draft**. Only the owner sees it.
3. The owner downloads the zip from the draft and scans it on VirusTotal. The owner publishes the
   release only when the scan is clean. A flagged build stays a draft; we fix it and tag a new version.
4. Every release lists the SHA-256 of the zip, the commit it was built from, the compiler and Python
   versions, and links the Actions run that built it. `SHA256SUMS` is attached.
5. Players can check the signature: right-click `T5DR Online.exe`, Properties, Digital Signatures.
6. Before pushing a tag the owner runs `tools/release_preflight.py`, which repeats the
   workflow's build and checks on a local PC.

## 6. Owner checklist: two open points

Two things are not decided. Nothing here is a guess about SignPath's answer. Settle them before you
send the application, or send the application with the questions in it and wait for the answer.
Nobody applies for you: you send the form yourself.

**Point 1. Which repository builds the signed release?**

- Facts. SignPath's origin check compares the repository of the build with the repository named in the
  SignPath project (source repository URL, branch, commit, build job). Our releases are built by
  `release.yml` in `TheWishin/T5DROnline-Dev`, which is private. The same code and the same workflow
  file are public in `TheWishin/T5DROnline-Source`, but that mirror has other commit hashes and
  carries no tags (a `v*` tag there would start a release run). SignPath's terms do not say whether
  the repository must be public. Applicants' write-ups say it must.
- [ ] Ask SignPath in the application. Paste: *"Our releases are built by GitHub Actions in a private
      repository that mirrors the public one (link). Which repository should the SignPath project
      name? May the signed build run in the private repository?"*
- [ ] Write down their answer here: ______________________
- [ ] If the build must run in the public repository: that is a change to how releases are made
      (the secrets go into that repository, and it would need its own way to start a release run
      without a tag). Decide how before changing anything.
- [ ] If the private repository is accepted: put the secrets and variables into
      `T5DROnline-Dev` (RELEASING.md, "A. SignPath Foundation"). Install the SignPath GitHub app there.

**Point 2. Who is named as the team?**

- Facts. SignPath's terms ask for the team roles and members on the code signing policy page
  (Author, Reviewer, Approver). The project also wants no visible contributors on the public
  repository. The repository owner's GitHub account `TheWishin` is already public as the owner.
  SignPath Foundation is the publisher shown in Windows, not you.
- [ ] Choose how the roles are written in the policy text (section 7):
      - [ ] the account name `TheWishin` (the text below),
      - [ ] a role only ("the repository owner"), if SignPath accepts that. Ask them first,
      - [ ] none: use Azure Artifact Signing instead (RELEASING.md, "B."). Then the certificate
            shows your validated name, and Azure only takes a person in the USA or Canada.
- [ ] Write down their answer here: ______________________

**Before you send**

- [ ] MFA on your GitHub and SignPath accounts.
- [ ] The contact e-mail in the form is an address you read. Keep it out of this repository.
- [ ] The SignPath credit line is not in the README yet (section 0).

## 7. After the acceptance: text for the public README

SignPath's terms ask for a **code signing policy** on the project's home page and on the download
pages, the credit line, a privacy statement and the team roles. Paste this into the README of
https://github.com/TheWishin/T5DROnline (and into the release notes template):

> ### Code signing policy
>
> Free code signing provided by [SignPath.io](https://about.signpath.io), certificate by
> [SignPath Foundation](https://signpath.org/).
>
> - What is signed: `T5DR Online.exe` and `runtime/t5dr.exe`, in the release zips only. They are built
>   from the public source by GitHub Actions. Nothing else is signed.
> - Roles (wording depends on section 6, point 2): Author, Reviewer and Approver: the repository owner,
>   GitHub account TheWishin. Every
>   release is approved by hand.
> - Every team member uses two-factor login on GitHub and SignPath.
> - Privacy: T5DR Online makes network connections for online play: to the lobby server you pick
>   in the Online tab (your name, rating, match results and your IP address) and to the other
>   player's PC during a match. The launcher also asks GitHub for the newest release at most once an
>   hour (an update check: GitHub sees your IP address, nothing else is sent). It sends no analytics.

(Not the standard "no transfer" sentence: it would be false for a game with an online mode.)

Add the same credit line to each release's notes. The release workflow builds the notes from
`CHANGELOG.md` and a download table, so put one line into the table text in
`tools/release_notes.py` when the time comes.
