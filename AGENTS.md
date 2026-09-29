# AGENTS.md

Guidance for AI coding agents (and the humans supervising them) working in this
repository. It is the single brief: `CLAUDE.md` and `.github/copilot-instructions.md` point
here. Read it before making changes.

## What this project is

Reverse-engineering notes and tooling for **PSA/Stellantis SMEG+** head units. The motivating
problem: an aftermarket CarPlay/Android-Auto piggyback feeds audio into the unit's AUX input,
and the unit kept starting on the radio. It now **boots to AUX** — `aux-autoswitch` +
`aux-boot-default` + `aux-boot-restore`, confirmed on the NAV 5.43.A.R2 unit, built by
`builds/aux-boot.json`. Switching to AUX when a signal appears is **not being pursued**;
`aux-signal-switch` exists as an emulated candidate only.

Two things in a package are patchable, and both paths are implemented and used on the car:

* **Application patches** — in-place edits to the PowerPC image inside
  `AppBin/f_BigQuick.bin`, applied and checksum-cascaded by `tools/patch_smeg.py`.
* **Media-partition edits** — ring tones, logos, the seed settings database, rebuilt by
  `tools/patch_media.py`. Files can be **replaced**, not added.

## Hard rules

1. **Never commit vendor firmware.** No Peugeot/Citroën/DS/Stellantis/Magneti Marelli
   binaries, no upgrade packages, no symbol maps, no extracted images or tones. The repo
   documents and patches; it does not distribute. `.gitignore` blocks the usual
   extensions, but check before you commit. If a task seems to need a vendor binary in
   the repo, it needs a synthetic fixture instead.
2. **Never upload firmware anywhere** — no CI artefacts, no release assets, no issue
   attachments.
3. **Conventional commit titles.** The repository squash-merges, so **the PR title
   becomes the commit on `main`** and drives Release Please. `feat:` → minor,
   `fix:` → patch, `feat!:`/`fix!:` (or a `BREAKING CHANGE:` footer) → major, everything
   else → no release. See [docs/RELEASING.md](docs/RELEASING.md). Getting this wrong
   silently produces no release.
   **This is enforced** by `tools/check_commit_msg.py` in two places — a `commit-msg` hook
   and a CI check on the PR title. The description starts lower case. Check a title before
   you push: `python3 tools/check_commit_msg.py --title "feat: ..."`.
4. **Warn the user before anything that can destroy their settings.** Some changes are not
   recoverable by reflashing because they overwrite state the *car* owns rather than state
   we ship. Shipping a `USER_DATA` payload is the example: it replaces databases on the
   unit's user partition, which hold paired phones, navigation destinations and presets.
   Say so plainly, in those terms, and wait to be told it is acceptable. Never treat a
   person's "I don't care about my settings" as covering a *different* person's car.

   `build_package.py` enforces this: a manifest with `user_data` is refused unless it also
   sets `accept_data_loss: true`, and the warning is printed either way.

5. **`main` is protected.** No direct pushes — work on a branch and open a PR. Deletion,
   force-push and non-linear history are blocked.
6. **A release PR needs a human approval click. That is expected — do not automate it.**
   Release Please opens its PR with the default `GITHUB_TOKEN`, and GitHub will not run
   workflows on a PR created that way until someone approves them, so the release PR sits
   at `BLOCKED` with **no checks reported** and every run showing `action_required`. That
   is the designed behaviour, not a fault, and it is deliberately left to a person:
   approving a release is a decision, not a chore.

   If you are an agent, **do not** work around it — do not call the run-approval API, do
   not add a PAT, do not weaken the ruleset. Report that the release PR is waiting on a
   human and move on. The same applies to merging a release PR.

## How to run things

The CLI tools need nothing but `uv`: every script declares its own dependencies in a PEP 723
header. A header opened with `# /// script` must be closed with `# ///`, or uv refuses the file;
`tests/test_script_headers.py` checks every tool.

```sh
uv run tools/build_package.py --manifest builds/aux-boot.json
uv run tools/patch_smeg.py --help
uv run tools/patch_studio.py                  # the Qt GUI (fetches PySide6)
```

For the tests, lint and docs, build the venv (Python 3.13, because Homebrew's `python3` is
3.14, where `ensurepip` is broken and PySide6 has no wheels). `.venv/` is gitignored:

```sh
uv venv --seed --python 3.13 .venv
uv pip install --python .venv/bin/python -r requirements-dev.txt -r requirements-gui.txt -r requirements-docs.txt
```

`requirements-dev.txt` brings `unicorn` and `capstone`. Without them the emulator and
disassembler tests **skip** rather than fail, so a venv missing them looks green and is not
what CI runs.

```sh
.venv/bin/python -m pytest tests -q                       # full suite, no firmware needed
.venv/bin/python -m pytest tests/test_patch_smeg.py -q    # one file
.venv/bin/python -m ruff check tools tests                # lint (E9 + F + SIM115)
.venv/bin/python -m ruff format --check tools tests       # formatting, as CI checks it
.venv/bin/python -m zensical build --strict               # docs; a broken anchor fails it
.venv/bin/zensical serve                                  # live docs preview on :8000
python3 tools/check_commit_msg.py --title "feat: ..."     # check a PR title
```

CI runs `ruff check`, `ruff format --check`, `pytest tests -q` and `zensical build --clean`.
`pre-commit install` wires three hook stages:

* **every commit:** whitespace/EOF/YAML hygiene, `ruff check --fix`, `ruff format`,
  `tools/check_no_firmware.sh` and `tools/check_no_pii.py`;
* **commit-msg:** `tools/check_commit_msg.py`;
* **push:** `pytest`, `zensical build --strict` and `bandit`.

So a push that would fail CI fails locally first. GUI tests skip without PySide6 and run
headless via `QT_QPA_PLATFORM=offscreen`.

Behavioural claims about the NAV image are tested against **your own** image, never in CI:
`SMEG_NAV_IMAGE=<your f_BigQuick.bin> .venv/bin/python -m pytest -m firmware -q`
(`tests/test_firmware_nav.py`; skipped when the variable is unset). The `AUDIO_BT` variants
have the same in `tests/test_firmware_audio_bt.py`, via `SMEG_AUDIO_BT_IMAGE` and
`SMEG_AUDIO_BT_256_IMAGE`. Each module's own symbol map ships in its `system.bin` under
`Application/PKG/`.

## Platforms: macOS and Windows

Developed on an Apple-silicon Mac and also worked on from an **x86_64 Windows 11** machine.
Both have to keep working. Nothing here needs WSL, but the POSIX shell scripts (`tools/*.sh`)
do need a `sh` — on Windows that means **Git Bash**. `tools/check_no_firmware.sh` is a
`pre-commit` hook entry, and a CRLF shebang makes it fail with "bad interpreter".
`.gitattributes` pins text files to LF so Git for Windows' default `core.autocrlf=true`
cannot reintroduce that. **Do not remove it.**

| | macOS | Windows 11 (x86_64) |
|---|---|---|
| interpreter | `python3` | `py -3` |
| python in the venv | `.venv/bin/python` | `.venv\Scripts\python.exe` |
| venv creation | `uv venv --seed --python 3.13 .venv` | the same command |
| ffmpeg | `brew install ffmpeg` | `winget install -e --id Gyan.FFmpeg` |
| copy an overlay onto a package | `rsync -a overlay/ PKG_mod/` | `patch_smeg.py --copy-package`, or `robocopy` |
| headless Qt | `QT_QPA_PLATFORM=offscreen` | `$env:QT_QPA_PLATFORM="offscreen"` |

Pin **Python 3.13** on both; `uv` fetches it.

**Known Windows gap:** the two `pre-push` entries in `.pre-commit-config.yaml` hard-code
`sh -c 'PY=.venv/bin/python; …'`. That assumes a POSIX `sh` *and* a Unix venv layout, so on
Windows they do not run — Git Bash supplies the first, not the second. Run those checks by
hand.

## How a package is put together

A user-supplied upgrade package is `SMEG_PLUS_UPG/<module>/…`, where `<module>` is one of
`NAV`, `AUDIO_BT`, `AUDIO_BT_256`. Two things inside it are patchable, in independent formats:

* **the application** — `<module>/AppBin/f_BigQuick.bin`: a 0x800-byte header, a `0x08`
  marker at 0x800, then a zlib stream from 0x801 inflating to a raw PowerPC image based at
  `0x01000000`. Not encrypted. The shipped `abs_symbols_base.txt.gz` lines up exactly, so
  patches are located by symbol, never by pattern.
* **the media partition** — `<module>/system.bin`: a gzip'd tar extracted to a read-only
  `/SYSTEM/` on the unit. Holds ring tones, the seed settings database, logo bundles. Adding
  a file would need a new `system_ctrl.bin` record; the format is known, but no updater has
  been handed a record count it did not ship with, so the tools refuse.

Every edit walks a chain of checksums back to the root manifest:

```
f_BigQuick.bin -> f_BigQuick.bin.inf -> smeg.inf (BIGQUICK_CRC32) -> <module>_ctrl.bin -> ctrl.bin
system.bin     -> system_ctrl.bin + system.bin.inf (CRC + SIZE/SIZE_n) -> <module>_ctrl.bin -> ctrl.bin
```

On top of that, `contract.dat` seals the package; a modified package that is not re-sealed is
rejected on the unit with string 2099. **Ordering fails silently:** 1. application patches,
2. media rebuild against the **already application-patched** package, 3. contract re-seal
**last**. `tools/build_package.py` owns that ordering — prefer it over running the tools by
hand.

Data-driven layers:

* `patches/*.json` — one patch set per behaviour, keyed by `variants.<module>`: the file paths
  its cascade touches, the firmware version it was derived from, and a list of
  `{addr, expect, bytes}` (plus `"data": true` for a non-code edit such as a string). Each set
  carries `summary` and `status` (`confirmed` / `flashed` / `never-flashed` / `falsified` /
  `diagnostic`); the status tables in `docs/PATCHES.md` and `docs/index.md` are generated from
  them by `tools/patch_status.py`. **A new `patches/*.json` beats new Python.**
* `builds/*.json` — whole-build manifests for `build_package.py`: package, module, patch sets,
  media tones/names/settings, `seal`, and optionally `user_data`.

## The reverse-engineering toolchain

Per-platform setup is in [docs/TOOLCHAIN.md](docs/TOOLCHAIN.md); none of it is needed to run
the tools or the tests. What matters when writing code here:

- **`clang` can target PowerPC**, so a patch's `bytes` can come from source —
  `clang --target=powerpc-unknown-none-eabi -mbig-endian -O2 -ffreestanding -c` works, because
  the e300 is plain big-endian PowerPC. **On macOS the `clang` on `PATH` is Apple's and has no
  PowerPC backend**; use `$(brew --prefix llvm)/bin/clang`. On Windows the LLVM installer's
  `clang` is fine.
- **`ld.lld -m elf32ppc -Ttext=<addr>`** places that code at a patch address, and needs an
  explicit **`--image-base=0`** or it rejects any address below its `0x10000000` default.
  `llvm-objcopy -O binary --only-section=.text` then emits the injectable bytes.
- **`llvm-mc --triple=powerpc --show-encoding`** assembles one instruction and prints its
  encoding — the cheap way to write a small `bytes` field.
- **`rizin`'s `rz-diff`** compares two firmware versions, which is how a version shift is
  re-derived. Its PPC *assembler* is not self-contained (it needs `RZ_PPC_AS`); assemble
  with LLVM instead.
- **Ghidra** is the decompiler. Import `tools/mkelf.py`'s ELF with language
  **`PowerPC:BE:32:default`** — there is no `e300` language ID, and the core has no vendor
  extensions.

A routine *larger* than the site it replaces is not solved. There is no usable code cave in
`.text` — every large run of zeros is `.rodata` (sqlite3 and utf8proc tables), so live data.
A trampoline would have to live *past the end of the image*: the container header carries the
**inflated size at offset `0x04`** (`0x02604450` on the NAV image) and no compressed size, so
the image can be grown and that field updated, but whether the loader maps the appended region
**executable** is untested. Do not claim a trampoline works until that is settled on hardware.

## Analysis workflow

- **Tag every claim** with how it was established — *executed*, *read*, *inferred* or *not
  known* (see [docs/VERIFICATION.md](docs/VERIFICATION.md)) — and never promote one to a
  higher tier in a doc, a patch `description` or a PR.
- **Most calls are indirect.** The compiler materialises an address (`lis`/`addi`) and calls
  through `mtctr`/`bctrl`; `callers.py` sees only `bl`. `tools/survey.py` inventories every
  function with direct callers, materialised references, data pointers, vtable slots, virtual
  call sites and global reads/writes. Its output derives from the vendor symbol map, so it
  stays **outside** the repository (see [docs/FIRMWARE_MAP.md](docs/FIRMWARE_MAP.md)).
- **Ghidra is one shared server.** `.mcp.json` points at `http://127.0.0.1:8000/mcp`. Start
  one pyghidra-mcp server over HTTP ([docs/TOOLCHAIN.md](docs/TOOLCHAIN.md)); a per-session
  stdio copy fails with `LockException`, because Ghidra lets one process hold a project.
- **Behaviour is checked by execution before a car.** `tools/ppcemu.py` runs one function
  with its callees stubbed. A stub's return value is an assumption, so say what was stubbed.
  Put a lasting behavioural claim in `tests/test_firmware_nav.py`.
- **Runtime evidence comes from the spy collect.** `SPYTAKE` (the unit collects, then
  reboots), then `SPYSTORE` with a stick in. The trace buffers are in
  `SPY/<stamp>/TAR/*-USER.tar.gz` → `RAMDISK_SPY/<buffer>/*.bin`, plain `<ms>::<event>` text
  (`25300` = `C_MGR_SRC`, `06301` = the media app); `tools/spy_read.py` reads them in one
  command. `traces.bin` is only the VxWorks exception log. See
  [docs/FLASHING.md](docs/FLASHING.md#the-test-loop-end-to-end). A capture holds the **VIN
  and personal data**: never commit it, quote it or attach it to an issue.
- **The AUX input handler follows the saved AUX setting, not the signal**
  ([docs/AUX_SIGNAL.md](docs/AUX_SIGNAL.md)). Anything built on "the handler fires when a
  signal appears" is wrong.

## Testing without firmware

`tests/helpers.py` and `tests/media_helpers.py` build a **synthetic package from scratch** —
header + zlib container, `.inf`, `smeg.inf`, tar, module and root manifests — so the whole
patch/repack path is exercisable without any vendor file. Use them. Adding a fixture is cheap;
adding a binary is not allowed.

## Areas and their traps

Every tool, with its `--help`, is on the generated [docs/TOOLS.md](docs/TOOLS.md) page. The
traps:

| area | notes |
|---|---|
| `tools/build_package.py` | Manifest → finished package, in the right order, ending with `preflight.py`. Paths in a manifest expand `~` and are relative to the manifest. `media.names` becomes a generated application patch (the tone names are image literals). |
| `tools/patch_smeg.py` | Checks `expect` bytes before writing, then rebuilds the whole CRC cascade, including each `ctrl` file's trailing CRC32. Every edit must decode as whole PowerPC instructions unless it sets `"data": true`. Refuses a build the image is not — see `tools/fingerprint.py`. |
| `tools/patch_media.py`, `tools/assets.py` | The media partition (`list`/`extract`/`restore`/`apply`), and human-readable names for its replaceable files. Replacing files only; adding one is refused. |
| `tools/patch_contract.py` | Re-seals `contract.dat` with key material extracted at runtime from the user's own image. It must never ship key material. |
| `tools/preflight.py` | Validates a built package offline before it goes on a stick, and reports unknowns as loudly as knowns. |
| `tools/verify_package.py` | Audits a package's whole checksum cascade. It looks for each CRC as a value rather than parsing the `ctrl` record layout, and warns (without failing) about a stale trailing CRC32. |
| `tools/prepare_usb.py` | Copies a package to a stick and re-reads every file back. **Refuses to write into a package already on the stick** — that merges two and the result still passes its own checksums. Junk (`._*`) is a failure, not a warning. On macOS it stops Spotlight indexing the stick and `--eject` retries while the volume is busy. |
| `tools/spy_read.py` | Reads a SPY capture in memory: the boot-source report from `25300`, `--aux`, `--list`, `--show ID`. Redacts the VIN, device addresses and long numbers by default. Tested with a synthetic capture; never commit a real one. |
| `tools/fingerprint.py` | Identifies which build an image is from the recorded `expect` bytes, and exits non-zero when it is ambiguous or unknown. It **reports ambiguity rather than choosing**: `AUDIO_BT` and `AUDIO_BT_256` declare the same addresses and the same bytes, so they cannot be told apart. |
| `tools/ringtones.py` | Needs ffmpeg for non-WAV input, but degrades gracefully. Slot formats matter: ring/status tones are 16-bit **mono 44.1 kHz**, wait tones 16-bit **stereo 8 kHz**. Its `names`/`rename` edit the seed database list, which the unit does not display. |
| `tools/patch_studio.py` | Qt GUI. Set `QT_QPA_PLATFORM=offscreen` to test it headlessly. |
| `tools/ppcemu.py` | Executes one function at a time on an emulated PowerPC core (Unicorn). Reachability is proof; stub return values are assumptions. Prefer it over reasoning about a branch by eye. |
| `tools/survey.py` | Whole-image function inventory, including the references `callers.py` misses. Tested with a synthetic image. Its output is never committed. |
| `tools/ppcdis.py`, `xref.py`, `callers.py`, `mkelf.py` | The analysis tools every patch address was derived with. `ppcdis` needs `capstone`. Covered by `tests/test_analysis_tools.py`. **`callers.py` finds only direct `bl` calls**, so "0 callers" usually means "called indirectly"; use `survey.py` or `xref.py`. |
| `tools/elfsyms.py` | The package's `*.out` updater binaries are unstripped PowerPC ELFs. Before reverse-engineering anything in the flash chain, check whether it already has a name. |
| `tools/symdiff.py` | Symbol-level diff between two releases, and locates a patch site in one nobody has analysed. Reports the **displacement** the images differ by. A derived address is a **candidate**, never a patch. |
| `tools/crc_recover.py` | Recovers CRC parameters from `(message, checksum)` samples; checked against published variants, so a negative result is trustworthy. |
| `tools/appimage.py`, `symbols.py`, `smeglib.py` | Shared leaf modules: the app container, the symbol-map reader (**last name wins** at a duplicate address; reads `.gz` maps), and the CRC/`.inf`/`ctrl` helpers (`swap_crc` replaces **exactly one** occurrence or refuses). |
| `tools/patch_status.py`, `tool_reference.py` | Generate the patch-status tables and `docs/TOOLS.md`; `--check` (run by the tests) fails when they are stale. A new tool must be added to `tool_reference.GROUPS`. |
| `tools/splash.py`, `tools/cartography.py` | The marque logo bundles (**not** the boot splash), and the map metadata that is understood. |
| `tools/fix_userdata_case.py` | Verifies or fixes the FAT long-filename entry a lowercase `sqlite` payload directory needs. |
| `tools/check_commit_msg.py`, `check_no_firmware.sh`, `check_no_pii.py` | The three enforcement hooks: conventional titles, no vendor files, no personal data. |
| `docs/` | Published with Zensical to <https://smeg.kroper.uk/>. A broken anchor fails the build. State the current understanding; test history belongs in `docs/VERIFICATION.md`. |

## Firmware knowledge that is easy to get wrong

- Addresses are **per build**. `AUDIO_BT` and `AUDIO_BT_256` usually match each other;
  the NAV build is offset. Never copy an address between builds without checking.
  `patch_smeg.py` runs `tools/fingerprint.py`, which cannot separate `AUDIO_BT` from
  `AUDIO_BT_256` and says so rather than guessing; do not paper over that.
- Addresses are also **per firmware version**. The NAV image from `SMEG_5.42.B.R4` is the
  5.43 one displaced by 152 bytes, so every address in `patches/*.json` is wrong on it —
  and the AUX handler differs by more than the shift. Every variant declares the version it
  came from (`"firmware": "5.43.A.R2"`) and `patch_smeg.py` refuses any other image; the
  `expect` bytes alone are **not** a sufficient guard (two entries match at the same address
  on 5.42). Do not defeat either check. See [docs/PATCHES.md](docs/PATCHES.md).
- **`system.bin` settings are not the live settings.** It extracts to a read-only `/SYSTEM/`;
  the unit reads its settings from the `USER_DATA` partition, and seed edits do not reach it.
- The media partition is a gzip'd **tar**, and `system_ctrl.bin` holds a per-file check value
  for everything inside it. `SIZE`/`SIZE_n` in `system.bin.inf` are computable — `SIZE` is the
  sum of the file sizes in the tar, `SIZE_n` the same rounded up per file to *n* KiB.
- **Version strings are not a confirmed build marker.** System Information shows the main
  software version and date from the **application image** (a literal and the `g_MBSW_*`
  globals, which also reach the CAN version frame — never patch them), `cd` from the media
  partition's `Data_base/media.inf` (editing `media.inf` can block the update outright), and
  `GUI_VER` on the GUI item's page *(read)*. See `docs/VERSION_STRINGS.md`. Judge a flash by
  behaviour, a replaced ring tone, or a `SPYTAKE` capture.
- The **updater reboots** the unit during the BootROM and Renesas steps. Never propose
  updating while driving.
- **A modified package must be re-sealed** before flashing, or the unit rejects it with
  string 2099. See `docs/MEDIA_PROTECTION.md`.
- The contract's RSA key material lives in the firmware image and must **never** be
  committed or reproduced in docs. `patch_contract.py` extracts it from the user's own
  package at runtime; keep it that way.
- Tone slot formats differ: ring/status tones are 16-bit **mono 44.1 kHz**, wait tones
  16-bit **stereo 8 kHz**.
- **Ring tone names are string literals in the application image**, not settings rows; each
  slot has a fixed maximum length (ring1 7, ring3 15, the others 11). `media.names` becomes an
  application patch whose edits carry `"data": true`. See `docs/RINGTONES.md#names`.
- In the `ctrl` manifests, CheckType 1 holds the file size, 2 its CRC32, and 3 a reflected
  CRC-16 (table polynomial `0xD415`, byte-swapped, sign-extended; `smeglib.ctrl_crc16`).
  The tools recompute each `ctrl` file's trailing CRC32. See `docs/FLASH_CHAIN.md`.

## Working style

- Prefer **data-driven** changes: a new `patches/*.json` beats new Python. After a car test,
  update the set's `status` and re-run `tools/patch_status.py`.
- Each patch set's hardware status is in its JSON and `docs/PATCHES.md`. Do not claim a patch
  "works" beyond that; report what was verified statically and what needs a car test.
- Add a regression test for any bug fixed, and a synthetic fixture for any new file format.
- Keep docs current in the same PR — the user-facing pages are the product here. Write them as
  the current understanding, not as a log of corrections; dated hardware results go in the
  log in `docs/VERIFICATION.md`.
- **Parallel agents that edit the repository each need their own git worktree.** Sharing one
  checkout, one agent's branch switch lands another's commit on the wrong branch.
- **Pace GitHub writes.** Open issues, comments and PRs a couple of minutes apart; a burst of
  issue creation has tripped GitHub's anti-spam and suspended an account.

## Related documents

- [README.md](README.md) — overview and quick start
- [CONTRIBUTING.md](CONTRIBUTING.md) — the human-facing version of the rules above
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — how the whole firmware fits together
- [docs/FLASH_CHAIN.md](docs/FLASH_CHAIN.md) — the boot and update chain
- [docs/PATCHES.md](docs/PATCHES.md) — exact addresses and bytes, and each set's status
- [docs/AUX_CHAIN.md](docs/AUX_CHAIN.md) — how the boot source is chosen, and what the AUX handler does
- [docs/TOOLCHAIN.md](docs/TOOLCHAIN.md) — the cross-platform analysis toolchain
