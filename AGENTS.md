# AGENTS.md

Guidance for AI coding agents (and the humans supervising them) working in this
repository. Read this before making changes.

## What this project is

Reverse-engineering notes and tooling for **PSA/Stellantis SMEG+** head units. The
headline goal is an **AUX auto-switch**: an aftermarket CarPlay/Android-Auto piggyback
feeds audio into the unit's AUX input, and the unit should select AUX by itself.

The work is split in two:

* **Application patches** — in-place edits to the PowerPC image inside
  `AppBin/f_BigQuick.bin`, applied and checksum-cascaded by `tools/patch_smeg.py`.
  This is the shipped, tested path.
* **Media-partition edits** — ringing tones, the cheatcode menu, version markers. These
  need `system.bin` unpacked, edited and repacked. **This path is not finished** — see
  issue #35 for the tool and #36 for the one open detail.

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
   and a CI check on the PR title. If you are an agent, write the message in the right form
   the first time; `--title` will tell you before you push:
   `python3 tools/check_commit_msg.py --title "feat: ..."`.
4. **Warn the user before anything that can destroy their settings.** Some changes are not
   recoverable by reflashing because they overwrite state the *car* owns rather than state
   we ship. Shipping a `USER_DATA` payload is the current example: it replaces databases on
   the unit's user partition, which hold paired phones, navigation destinations and presets.
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

```sh
.venv/bin/python -m pytest tests -q        # the suite, no firmware required
.venv/bin/python -m ruff check tools tests # lint (E9 + F)
.venv/bin/python tools/patch_studio.py     # the GUI
.venv/bin/zensical serve                   # live docs preview
```

`pre-commit install` wires the `pre-commit`, `commit-msg` **and** `pre-push` hooks in one
go. The fast checks (lint, hygiene, no-firmware) run per commit; the slow ones (tests,
strict docs build, `bandit`) run on push, so a push that would go red in CI fails locally
first.

`.venv/` is gitignored, so a fresh clone has none — build it first (Python 3.13, because
Homebrew's `python3` is 3.14, where `ensurepip` is broken and PySide6 has no wheels):
`uv venv --seed --python 3.13 .venv && uv pip install --python .venv/bin/python PySide6 pytest zensical ruff`.

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

Pin **Python 3.13** on both. The reason above is macOS-specific — Homebrew's `python3` is
3.14, where `ensurepip` is broken — but pinning the same version on Windows keeps the two
machines identical, and `uv` will fetch 3.13 for you.

**Known Windows gap:** the two `pre-push` entries in `.pre-commit-config.yaml` hard-code
`sh -c 'PY=.venv/bin/python; …'`. That assumes a POSIX `sh` *and* a Unix venv layout, so on
Windows they do not run — Git Bash supplies the first, not the second.

## The reverse-engineering toolchain

The analysis half of the project needs more than `uv`. Per-platform setup is in
[docs/TOOLCHAIN.md](docs/TOOLCHAIN.md); what matters when writing code here is:

- **`clang` can target PowerPC**, so a patch's `bytes` can come from source instead of from
  memory — `clang --target=powerpc-unknown-none-eabi -mbig-endian -O2 -ffreestanding -c`
  works, because the e300 is plain big-endian PowerPC.
  **On macOS the `clang` on `PATH` is Apple's and has no PowerPC backend**; use
  `$(brew --prefix llvm)/bin/clang`. On Windows the LLVM installer's `clang` is fine.
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
  extensions. `capstone` and `unicorn` come from the `dev` extra.

The toolchain produces **bytes**. Injecting a routine *larger* than the site it replaces is
still **not solved**, but the blocker is now characterised rather than vague: there is no
usable code cave in `.text` — every large run of zeros in the image is `.rodata` (sqlite3 and
utf8proc tables), so it is live data and unsafe to execute. A trampoline would therefore have
to live *past the end of the image*, which is mechanically expressible: the container header
carries the **inflated size at offset `0x04`** (`0x02604450` on the NAV image, verified) and
no compressed size, because the zlib stream is self-delimiting. So the image can be grown and
that field updated. What remains unverified is whether the loader maps the appended region
**executable**. Do not claim a trampoline works until that is settled on hardware.

## Testing without firmware

`tests/helpers.py` builds a **synthetic package from scratch** — header + zlib container,
`.inf`, `smeg.inf`, module and root manifests — so the whole patch/repack path is
exercisable without any vendor file. Use it. Adding a fixture is cheap; adding a binary
is not allowed.

Building those tests immediately caught two fixture bugs, so it is worth the effort.

## Areas and their traps

| area | notes |
|---|---|
| `tools/patch_smeg.py` | Checks `expect` bytes before writing, then rebuilds the whole CRC cascade. Prefer adding a `patches/*.json` entry over new code. Refuses a build the image is not — see `tools/fingerprint.py`. |
| `tools/fingerprint.py` | Identifies which build an image is from the recorded `expect` bytes, and exits non-zero when it is ambiguous or unknown. It **reports ambiguity rather than choosing**: `AUDIO_BT` and `AUDIO_BT_256` declare the same addresses and the same bytes, so they cannot be told apart. |
| `tools/ringtones.py` | Needs ffmpeg for non-WAV input, but degrades gracefully. Slot formats matter: ring/status tones are 16-bit **mono 44.1 kHz**, wait tones 16-bit **stereo 8 kHz**. |
| `tools/patch_studio.py` | Qt GUI. Set `QT_QPA_PLATFORM=offscreen` to test it headlessly. |
| `tools/elfsyms.py` | The package's `*.out` updater binaries are unstripped PowerPC ELFs. Before reverse-engineering anything in the flash chain, check whether it already has a name. |
| `tools/ppcemu.py` | Executes one function at a time on an emulated PowerPC core (Unicorn). Reachability is proof; stub return values are assumptions. Prefer it over reasoning about a branch by eye — it has already overturned one conclusion. |
| `tools/ppcdis.py`, `xref.py`, `callers.py`, `mkelf.py` | The analysis tools every patch address was derived with. Need `capstone`. Untested — see #38. |
| the toolchain | Per-machine, not bundled: `clang`/`ld.lld`/`llvm-mc`/`rizin`/Ghidra. On macOS only `lld` lands on `PATH`, and Apple's `clang` cannot target PowerPC. See [docs/TOOLCHAIN.md](docs/TOOLCHAIN.md). |
| `docs/` | Published with Zensical to <https://smeg.kroper.uk/>. A broken anchor fails the build; run `zensical build` before pushing docs. |

## Firmware knowledge that is easy to get wrong

- The application image is **not** encrypted: `f_BigQuick.bin` is a 0x800-byte header, a
  `0x08` marker at 0x800, then a **zlib stream** from 0x801, inflating to a raw PPC image
  at `0x01000000`. The shipped `abs_symbols_base.txt.gz` lines up with it exactly, so
  patch by symbol, not by pattern.
- Addresses are **per build**. `AUDIO_BT` and `AUDIO_BT_256` usually match each other;
  the NAV build is offset. Never copy an address between builds without checking.
  `tools/fingerprint.py` identifies the build from the recorded `expect` bytes, and
  `patch_smeg.py` calls it — but it **cannot separate `AUDIO_BT` from `AUDIO_BT_256`**,
  because those two variants declare the same addresses *and* the same bytes. It reports
  that as ambiguous and exits non-zero rather than picking one; do not paper over it by
  having it guess.
- Addresses are also **per firmware version**. The NAV image from `SMEG_5.42.B.R4` is the
  5.43 one displaced by 152 bytes, so every address in `patches/*.json` is wrong on it —
  and the AUX handler differs by more than the shift. Every variant declares the version it
  came from (`"firmware": "5.43.A.R2"`) and `patch_smeg.py` refuses any other image; the
  `expect` bytes alone are **not** a sufficient guard (two entries match at the same address
  on 5.42). Do not defeat either check. See [docs/PATCHES.md](docs/PATCHES.md).
- The media partition is a gzip'd **tar**, and `system_ctrl.bin` holds a per-file CRC for
  everything inside it. `SIZE`/`SIZE_n` in `system.bin.inf` are computable — `SIZE` is the
  sum of the file sizes in the tar, `SIZE_n` the same rounded up per file to *n* KiB.
- **Version strings are not a safe marker.** Display reads `Data_base/smeg.inf` *inside*
  the media partition, so patching the app image changes nothing visible. Editing
  `media.inf` can block the update outright. `GUI_VER` is the only safe visible field.
- The **updater reboots** the unit during the BootROM and Renesas steps. Never propose
  updating while driving.
- **A modified package must be re-sealed** before flashing, or the unit rejects it with
  string 2099. Always run `tools/patch_contract.py` after any change that alters a file
  the contract covers. See `docs/MEDIA_PROTECTION.md`.
- The contract's RSA key material lives in the firmware image and must **never** be
  committed or reproduced in docs. `patch_contract.py` extracts it from the user's own
  package at runtime; keep it that way.

## Working style

- Prefer **data-driven** changes: a new `patches/*.json` beats new Python.
- The patches are **not validated on hardware** by the maintainer. Say so plainly; do not
  claim a patch "works". Report what was verified statically and what needs a car test.
- Add a regression test for any bug fixed, and a synthetic fixture for any new file
  format.
- Keep docs current in the same PR — the user-facing pages are the product here.

## Related documents

- [README.md](README.md) — overview and tool table
- [CONTRIBUTING.md](CONTRIBUTING.md) — the human-facing version of the rules above
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — how the whole firmware fits together
- [docs/FLASH_CHAIN.md](docs/FLASH_CHAIN.md) — the boot and update chain
- [docs/PATCHES.md](docs/PATCHES.md) — exact addresses and bytes
- [docs/AUX_CHAIN.md](docs/AUX_CHAIN.md) — the AUX auto-switch gate by gate, and which claims are executed rather than read
- [docs/TOOLCHAIN.md](docs/TOOLCHAIN.md) — the cross-platform analysis toolchain: compiling, linking and diffing PowerPC
