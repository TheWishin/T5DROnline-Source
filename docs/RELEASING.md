# Making a release

Releases are built and published by GitHub Actions
(`.github/workflows/release.yml`) when a version tag is pushed. Nobody needs a
GitHub token on their PC: the workflow publishes with its own `GITHUB_TOKEN`.
Only the owner's account can start it: the owner, or the owner's own release tooling,
which pushes with the owner's git login.

How the zip is put together, and why, is in [RELEASE.md](RELEASE.md). This page
is the procedure.

## Two repositories (since 2026-10-17)

Like Tekken 6 Native Online:

- **TheWishin/T5DROnline-Dev** (private): all code, history, CI and the release
  workflow. `origin` of every checkout.
- **TheWishin/T5DROnline** (public): only README.md, README.de.md,
  TROUBLESHOOTING.md and LICENSE, in one commit by a neutral author (no
  contributors shown), plus the Releases with the zips.

Never push source to the public repository. Its content is made with
`python tools/make_public_repo.py --out C:/T5DR-public` and committed there as
`T5DR Online <noreply@t5dr-online.invalid>` (a separate clone, remote `public`).
Update it when the player README changes (amend + force-push keeps it at one
commit).

## One-time setup (the owner, in the GitHub web UI)

Only the owner's account (TheWishin) may publish releases: the owner, or the
owner's release tooling, which pushes with the owner's own git login (the owner's
choice, 2026-10-17).

**0. The token that lets the private workflow publish into the public repo.**

1. github.com -> your picture -> **Settings** -> **Developer settings** ->
   **Personal access tokens** -> **Fine-grained tokens** -> **Generate new token**.
2. Name `T5DR release`, Expiration e.g. 1 year, Resource owner `TheWishin`.
3. **Repository access** -> **Only select repositories** -> `TheWishin/T5DROnline`
   (the public one only).
4. **Permissions** -> Repository permissions -> **Contents: Read and write**
   (Metadata: Read-only is added by itself). Nothing else.
5. **Generate token** and copy it (it is shown once).
6. In **T5DROnline-Dev** -> Settings -> Secrets and variables -> Actions ->
   **New repository secret**: name `PUBLIC_RELEASE_TOKEN`, paste, **Add secret**.

Nobody else ever sees the token; the workflow uses it only in the publish job.

**1. Nobody else has write access** to either repository (Settings ->
Collaborators and teams: no one, or only Read).

**2. A tag ruleset -- only the admin creates, moves or deletes release tags.**

Settings -> Rules -> Rulesets -> **New ruleset** -> **New tag ruleset**:

- Ruleset name `release tags`, Enforcement status **Active**.
- **Bypass list** -> **Add bypass** -> **Repository admin** (role), "Always allow".
- **Target tags** -> **Add target** -> **Include by pattern** -> `v*`.
- Rules: tick **Restrict creations**, **Restrict updates**, **Restrict
  deletions** (keep **Block force pushes** ticked).
- **Create**.

**3. The `release` environment -- publishing only from `v*` tags.** It exists
since the first release (GitHub created it then).

Settings -> Environments -> `release`:

- **Deployment branches and tags**: choose **Selected branches and tags** ->
  **Add deployment branch or tag rule** -> Ref type **Tag** -> pattern `v*` ->
  **Add rule**.
- **Required reviewers**: off, so a release can finish without a click
  without a click. Tick it and add `TheWishin` if every publish should wait for
  the owner's approval (then leave **Prevent self-review** off).
- No secrets, no variables, no wait timer. **Save protection rules**.

The workflow's owner check (`github.actor` and `github.triggering_actor` must be
the repository owner, for tag pushes and manual runs) is the last guard: a run
started by anyone else stops before it builds anything.

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

4. **Preflight (required):** `python tools/release_preflight.py --version 0.1.0-preview`
   runs what the release workflow runs (changelog, guard, patch series, the zip with
   `--release`, the binary checks, the zip smoke test, unit tests) on this PC. Tag only
   when it prints `PREFLIGHT OK`. (0.1.5-preview's first run failed on the runner at the
   binary check; the preflight finds that in ~4 minutes locally.)

5. **Push `main`** and wait for CI to be green.

6. **Tag and push the tag:**

       git tag -a v0.1.0-preview -m "T5DR Online 0.1.0-preview"
       git push origin v0.1.0-preview

   The tag must point at a commit on `main`.

7. **The owner checks it on VirusTotal, then publishes.** The run (Actions -> Release) builds
   and checks the zip (about 7 minutes) and creates the release in the public repository as a
   **draft**: only the owner sees it. The owner downloads the zip from the draft (public
   repository -> Releases -> the draft), uploads it to https://www.virustotal.com, and clicks
   **Publish release** only when it is clean (owner's rule, 2026-10-18). If a scanner flags it:
   leave the draft, report the detection names, fix, tag a new version.

8. **Check the release page**: the zip and `SHA256SUMS` are attached, the notes
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
| code signing | only when a signing service is set up (see "Code signing"), only for tag runs: `package_release.py --sign-stage prepare`, the service signs `T5DR Online.exe` and `runtime/t5dr.exe`, `--sign-stage finish` installs them. Without the secrets this step is skipped |
| package | `tools/package_release.py --release`: stages everything, builds the runtime host with the pinned clang-cl and `T5DR Online.exe` with MSVC (see "The launcher stub"), self-tests the bundled Python, scans folder and zip, writes `SHA256SUMS` |
| guard on the zip | `package_release.py --scan-only` on the zip once more |
| smoke test | `tools/smoke_release.py`: unpack into a fresh folder; layout, version stamp, bundled Python with a bare `PATH`, `prereqs.py` finds everything inside the folder, clang-cl version, `t5dr.exe` and the starter import only Windows DLLs, every signature is `Valid` (signed releases). Then (informational only) the launcher renders offscreen and `T5DR Online.exe` starts it |
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
image's MSVC libraries and Windows SDK (static C runtime), and the starter `T5DR Online.exe`
built by the runner's MSVC (`cl.exe`, `link.exe`). To move a pin:
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
  failed jobs** (owner only). Approve again when it reaches publish. A signed release asks for
  the SignPath approval again.
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

## The launcher stub: MSVC or clang-cl

`T5DR Online.exe` (123 KB) is built by `tools/package_release.py`. Two compilers can build it:

- **MSVC** (the default): `cl.exe` and `link.exe` with `/O2 /MT /GS /guard:cf` and
  `/DYNAMICBASE /NXCOMPAT /GUARD:CF /RELEASE`, the same icon, version info and manifest.
  This is the file Microsoft's own tools make. Some machine-learning scanners like it better.
- **clang-cl**: the build of 1.0.0.

The two give different files, so the scanners can judge them differently. Pick by the VirusTotal result
of the zip:

| VirusTotal result for the MSVC stub | What to do |
|---|---|
| Clean | Nothing. MSVC is the default. |
| Still flagged by ML engines | Try clang-cl (below), upload that zip, keep whichever is cleaner. Then report the rest (see "Reporting false positives"). |

How to switch:

- **Release workflow:** GitHub -> T5DROnline-Dev -> Settings -> Secrets and variables -> Actions ->
  **Variables** -> **New repository variable**: name `T5DR_STUB_COMPILER`, value `clang` (or `msvc`).
  Set it before you push the tag. Delete the variable to go back to the default.
- **Dry run:** Actions -> Release -> Run workflow -> **stub_compiler** = `clang` or `msvc`.
- **On this PC:** `python tools/package_release.py ... --stub-compiler clang`, or set the
  environment variable `T5DR_STUB_COMPILER`.

The zip's `release.json` says which compiler was used (`stub_compiler`). If MSVC is not found,
the build warns and uses clang-cl. On the runner MSVC is always there.

## Code signing

Code signing puts a publisher name on our programs. It is **off** today. The release workflow signs
only when the secrets of a signing service exist. Without them it does nothing and the release is
built as before. We prepared two services: SignPath (free for open source) and Azure Artifact Signing
(paid). You need only one.

### What is signed

- `T5DR Online.exe` and `runtime/t5dr.exe`. A DLL that we add next to them later is signed too.
- Not signed, on purpose:
  - `python/`. python.org signs its own files (publisher "Python Software Foundation"), and
    `vcruntime140.dll` is signed by Microsoft. Checked on CPython 3.12.10.
  - `toolchain/llvm/`. LLVM's Windows binaries are **not** signed (checked on 23.1.3). They are not our
    programs, so we do not sign them.
  - pycryptodome's `.pyd` files. They are unsigned too, and not ours.
- `t5dr_game.dll` is built on the player's PC from the player's own game. Nobody can sign it.

### What changes for players

- Windows shows a publisher name on `T5DR Online.exe` (right-click, Properties, Digital Signatures),
  not "Unknown publisher".
- SmartScreen ("Windows protected your PC") is about reputation. Reputation grows with downloads and
  time. A signature does not switch the warning off on the first day.
- Some virus scanners judge unsigned programs by guesswork (machine learning). A signature from a known
  publisher makes a false alarm less likely. It does not rule it out. Keep reporting false positives.
- Publisher name: with SignPath it is "SignPath Foundation" (they are the legal publisher of what they
  sign). With Azure it is the name you validate for the account. For a person that is the name on
  the ID, plus city, state and country.

### How a signed release runs

1. You push the tag as always. The workflow builds the first half: everything is staged and checked.
2. The two programs go to the signing service. SignPath waits for your click (it e-mails you);
   the workflow waits up to 30 minutes for it. Azure signs at once.
3. The second half installs the signed copies. It checks that each is the built file plus a signature
   that Windows reports as `Valid`, and nothing else changed. If not, the run stops.
4. The zip, the checks, the smoke test and the draft release go on as before. The release notes say
   which files are signed.

Only tag runs are signed. Dry runs (pushes to a branch) are not, so they never wait for you.
To test the setup, use Actions -> Release -> Run workflow and tick **sign**. It never publishes.

### Which one

| | SignPath Foundation | Azure Artifact Signing |
|---|---|---|
| Cost | Free for approved open source projects | Paid Azure subscription (no free or trial one). Basic includes 5,000 signatures a month. The price is on Azure's pricing page (about 10 USD a month at launch). Billed in full every month from the day the account exists |
| Who can get it | An open source project with an OSI license, public source, released, maintained. SignPath decides, no appeal | A person in the USA or Canada, or an organization in the USA, Canada, EU, UK, Australia, New Zealand, Japan, South Korea, Singapore, Switzerland, Norway or Israel |
| Wait | Review by SignPath (days to weeks, not stated) | Identity check: 1 to 20 business days |
| Publisher shown | SignPath Foundation | The validated name |
| Each release | You approve it in SignPath's web page | Automatic |
| Their rules | Code signing policy page, team roles listed, MFA on GitHub and SignPath, build from the repository | Keep the secret safe; the certificate lasts 3 days, so the workflow timestamps |

The text for the SignPath application is ready in [SIGNING_APPLICATION.md](SIGNING_APPLICATION.md).
SignPath is the first choice: free, and the publisher is not you. Azure is the plan B if SignPath says no.

### A. SignPath Foundation: your steps

1. Read [SIGNING_APPLICATION.md](SIGNING_APPLICATION.md). Check the list "Before you apply".
2. Apply at https://signpath.org/apply with the text from that page.
3. Wait for SignPath's e-mail. Turn on two-factor login (MFA) for your SignPath and GitHub accounts.
4. In SignPath, make the **artifact configuration** (it can be the project's default one) from this XML.
   It signs exactly the two programs:

       <artifact-configuration xmlns="http://signpath.io/artifact-configuration/v1">
         <zip-file>
           <pe-file-set>
             <include path="T5DR Online.exe"/>
             <include path="runtime/t5dr.exe"/>
             <for-each>
               <authenticode-sign/>
             </for-each>
           </pe-file-set>
         </zip-file>
       </artifact-configuration>

   A DLL added later needs one more `<include path="runtime/name.dll"/>` line.
5. In SignPath, make an API token for a user who may submit signing requests for the project's
   signing policy. Copy it.
6. Install the SignPath GitHub app on the repository where releases are built, if SignPath asks for it
   (github.com/apps/signpath). Follow the setup mail from SignPath for the policy file in the repository.
7. GitHub -> the repository -> Settings -> Secrets and variables -> Actions:
   - **Secret** `SIGNPATH_API_TOKEN`: the token.
   - **Variables** `SIGNPATH_ORGANIZATION_ID`, `SIGNPATH_PROJECT_SLUG`, `SIGNPATH_SIGNING_POLICY_SLUG`,
     and, if the configuration from step 4 is not the default one, `SIGNPATH_ARTIFACT_CONFIGURATION_SLUG`.
   (A variable may also be a secret. The workflow takes either.)
8. Test: Actions -> Release -> Run workflow -> tick **sign**. Approve the request in SignPath.
9. Add the code signing policy and the credit line from SIGNING_APPLICATION.md to the public README
   (SignPath's terms ask for it).

If SignPath's policy forbids re-runs of signed builds (`disallow_reruns`), "Re-run failed jobs"
(see "Re-running") will not be signed. Push a fresh tag instead.

### B. Azure Artifact Signing: your steps

(Microsoft renamed "Trusted Signing" to "Artifact Signing". Older guides use the old name.)

1. Check that you qualify (table above). For a person: you must live in the USA or Canada.
2. Make a paid Azure subscription (pay-as-you-go). In it, register the resource provider
   `Microsoft.CodeSigning`.
3. Azure portal -> **Artifact Signing Accounts** -> Create. Pick a region and the **Basic** plan.
4. In the account: **Identity validations** -> New -> Public. A person uses the Verified ID check
   (government ID and the Microsoft Authenticator app). Wait for **Completed**.
5. **Certificate profiles** -> Create -> **Public Trust**, with that identity.
6. Microsoft Entra -> App registrations -> New. Add a client secret. Give this app the role
   **Artifact Signing Certificate Profile Signer** on the account (Access control).
7. GitHub -> the repository -> Settings -> Secrets and variables -> Actions:
   - **Secrets** `AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET`.
   - `ARTIFACT_SIGNING_ENDPOINT`: the regional address, for example `https://weu.codesigning.azure.net`
     (West Europe) or `https://eus.codesigning.azure.net` (East US). It must be the region of the account.
   - `ARTIFACT_SIGNING_ACCOUNT`: the account name. `ARTIFACT_SIGNING_PROFILE`: the profile name.
   (These three may be variables or secrets.)
8. Test: Actions -> Release -> Run workflow -> tick **sign**.
9. Put the client secret's end date in your calendar. When it runs out, signing stops (the workflow
   then fails and says so).

### Switching and checking

- Both set up: SignPath is used. The repository variable `SIGNING_PROVIDER` (`signpath`, `azure`
  or `none`) overrides this. `none` turns signing off for all runs.
- Half set up (a token, but no organization ID, for example): the run stops and names what is missing,
  so a release is never made unsigned by mistake.
- Check a downloaded zip: unpack it, then
  `python tools/code_signing.py verify "T5DR Online.exe" runtime/t5dr.exe` (from a checkout), or
  right-click the file -> Properties -> Digital Signatures. `release.json` in the zip lists the
  signed files.
- Local test without a service: `tools/package_release.py --sign-stage prepare`, sign
  `dist/to-sign/*` yourself, then `--sign-stage finish --signed-dir DIR`. `--accept-untrusted-signature`
  allows a self-signed test certificate.

## Reporting false positives

A scanner on VirusTotal that flags our zip or `T5DR Online.exe` is usually guessing: names like
"Suspicious", "Gen", "ML.Score" mean a machine-learning model, not a known virus. The vendors fix such
cases after a report, often within days. Report each one.

**What to send each vendor**

1. The file: `T5DR Online.exe` (123 KB, small enough for every form). The zip is 90 MB, which most
   forms refuse. Give the zip as a link, and its SHA-256 from `SHA256SUMS`. A draft release is not
   visible to vendors, so use the released zip, or a download link you control.
2. The VirusTotal link of the scan, and the detection name the vendor showed.
3. This text (copy it):

       Open-source game launcher, MIT license. "T5DR Online.exe" only starts python\pythonw.exe with
       launcher\t5dr_launcher.pyw from its own folder (source: launcher/stub/t5dr_stub.c). The zip holds
       no game files. Source: https://github.com/TheWishin/T5DROnline-Source
       Release: <the GitHub release link>. SHA-256 of the zip: <hash>. Detection: <name> by <scanner>.
       Please check and remove the false positive.

**Where** (the e-mail addresses and forms are from VirusTotal's own list of false-positive contacts,
https://docs.virustotal.com/docs/false-positive-contacts, and the vendors' pages; look there if one fails)

| Scanner | Where |
|---|---|
| Webroot | The vendor form https://www.webroot.com/us/en/business/support/vendor-dispute-contact-us. Or upload the file at https://snup.webrootcloudav.com/SkyStoreFileUploader/upload.aspx and choose the reason "False Positive detection". (VirusTotal also lists https://support.threatintel.opentext.com/tools/change-request.php, which Webroot uses for web addresses.) |
| Trapmine | E-mail fp@trapmine.com |
| Symantec | https://symsubmit.symantec.com -> **Clean software incorrectly detected**. Upload the file or give a link. Add your e-mail; the tracking number goes there. |
| Bkav | E-mail fpreport@bkav.com (or bkav@bkav.com) |
| SecureAge | https://www.secureage.com/support/report-false-positive (put the file in a ZIP first). Or https://www.secureage.com/contact-us. Help: docs@secureage.com |
| Bitdefender | E-mail virus_submission@bitdefender.com, or the form https://www.bitdefender.com/consumer/support/answer/29358/ (business form: https://www.bitdefender.com/business/support/en/77211-343057-submitting-sample-files-and-websites-for-analysis.html). Choose **False positive**. Put big files in a ZIP. |

Bitdefender's engine is also inside ALYac, Arcabit, Emsisoft, G Data and VIPRE. When Bitdefender
removes its detection, those usually follow. If one still flags after a week, report to it too:

| Scanner | Where |
|---|---|
| ALYac | E-mail esrc@estsecurity.com |
| Arcabit | E-mail vt.fp@arcabit.pl |
| Emsisoft | E-mail submit@emsisoft.com or fp@emsisoft.com, or https://www.emsisoft.com/en/support/contact/ |
| G Data | https://www.gdata.de/help/en/general/GeneralInformation/submitFileAppURL/ |
| VIPRE | https://helpdesk.vipre.com/hc/en-us/requests/new |

After a vendor answers, open the VirusTotal page of the zip and press **Reanalyze**. Vendors update
their detections on their own schedule. Do not publish the release while a scanner still flags it
(the owner's rule); fix, report, and scan again.

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
