# smeg-plus-patches

Reverse-engineering notes and tooling for patching **PSA / Stellantis "SMEG+"**
infotainment firmware so the **AUX audio source is selected automatically** when a
signal appears — the thing you want when an aftermarket CarPlay/Android-Auto piggyback
(such as CarABC / AutoABC) feeds its audio into the head unit's AUX input.

Tested against: **Peugeot 208 (2015), SMEG+ iV1, hardware diversity `NAV`,
firmware `SMEG5.43.A.R2` (CD 26482, 19-09-17)** — but the same approach applies to the
non-NAV (`AUDIO_BT`) builds.

**Status:** a patched, contract re-sealed package has been flashed to a real unit and
accepted — the media check passed, the application image was written, and the
`IsAUXSRCAvailable()` change is confirmed working (AUX no longer greys out). The
**automatic switch itself has not yet been observed working**, and the handler it relied on
turns out to follow the saved AUX input setting rather than the AUX signal (read from
disassembly; see [The AUX chain](docs/AUX_CHAIN.md#what-the-handler-actually-reacts-to)).
See [Hardware verification](docs/VERIFICATION.md).

Current work, none of it yet shown working on a car:

- **Switch on signal:** `aux-signal-switch` routes the real AUX signal event to the handler
  and makes it test the signal. It is verified under emulation, not flashed. See
  [The AUX signal path](docs/AUX_SIGNAL.md).
- **Boot to AUX:** `aux-boot-default` alone is **falsified on hardware** (still FM). The
  current candidate is `aux-boot-restore` (three edits); its two-edit version also still
  booted to FM. See [How the boot source is actually chosen](docs/AUX_CHAIN.md#how-the-boot-source-is-actually-chosen).

> ## No vendor firmware is included
> This repository contains **only original reverse-engineering notes and scripts**.
> It does **not** contain any Peugeot / Citroën / DS / Stellantis / Magneti Marelli
> firmware, upgrade packages, symbol maps, or other copyrighted binaries — those are
> not distributed here and `.gitignore` is set up to keep them out.
>
> To use these tools you must supply your **own** legally obtained firmware upgrade
> package. You are responsible for complying with the laws and licence terms that apply
> to your own device and software.

---

## Background

The head unit's application is delivered as `AppBin/f_BigQuick.bin`: a **0x800-byte
header**, a `0x08` marker at `0x800`, then a **zlib stream** from `0x801` that inflates to a raw **PowerPC** image loaded
at `0x01000000`. The release also ships absolute symbol maps
(`Application/PKG/abs_symbols_base.txt.gz`) which line up with that image, so the
firmware can be patched by symbol rather than by blind search.

The firmware was first thought to contain the auto-switch logic, in
`C_HMI_MEDIA_APP_BASE::HandleAudioAuxInputStatusChnged()`:

```
audio server --DBUS--> C_BCM_HMI_AUDIO_CLIENT::AUDIO_AUX_INPUT_STATUS_CHANGED()
  -> internal message 0xcb
  -> HandleAudioAuxInputStatusChnged() -> SetMediaDeviceState()/ActivateSource()
```

**Correction:** that handler reacts to the saved AUX input *setting* changing, not to an AUX
signal appearing, and stock firmware routes the signal notification only to a menu refresh.
See [What the handler actually reacts to](docs/AUX_CHAIN.md#what-the-handler-actually-reacts-to).
The original reading, and the patches built on it, identified two obstacles:

1. `C_HMI_AUDIO_APP_BASE::IsAUXSRCAvailable()` only reports AUX as available when the
   vehicle configuration already has it and a signal is present.
2. `HandleAudioAuxInputStatusChnged()` **returns early if `GetMediaDevice(AUX)` fails**,
   before it ever calls `ActivateSource()`.

The patch set addresses both. See [`docs/AUX_CHAIN.md`](docs/AUX_CHAIN.md) for the chain as it
is now understood and [`docs/PATCHES.md`](docs/PATCHES.md) for exact addresses and bytes.

## Supported builds / patches

| build | app image | `IsAUXSRCAvailable` | `…StatusChnged +0x10c` |
|---|---|---|---|
| `AUDIO_BT` (512) | `AUDIO_BT/AppBin/f_BigQuick.bin` | `0x02247718` → `li r3,1 ; blr` | `0x023032e8` → `nop` |
| `AUDIO_BT_256` | `AUDIO_BT_256/AppBin/f_BigQuick.bin` | `0x02247718` → `li r3,1 ; blr` | `0x023032e8` → `nop` |
| `NAV` | `NAV/AppBin/f_BigQuick.bin` | `0x02247858` → `li r3,1 ; blr` | `0x02303428` → `nop` |

The `+0x10c` edit is **inert**: the branch it removes is never taken (executed; see
[Emulation](docs/EMULATION.md)). Only the `IsAUXSRCAvailable` edit changes behaviour, and
that change is confirmed on hardware.

Patches are data-driven — see [`patches/aux-autoswitch.json`](patches/aux-autoswitch.json).
Every patch set, and its hardware status, is listed in
[`docs/PATCHES.md`](docs/PATCHES.md#patch-sets-in-this-repository).

## Requirements

- [uv](https://docs.astral.sh/uv/) — the scripts declare their own dependencies, so
  `uv run tools/<script>` needs no setup. See [Running the tools](docs/RUNNING.md).
- `ffmpeg` for audio conversion (mp3/ogg/flac/...); WAV needs nothing.
- Your own SMEG+ upgrade package, laid out as `SMEG_PLUS_UPG/…`
- `capstone` is only needed by the disassembly helper (`tools/ppcdis.py`).

## Usage

### 1. Inspect (optional)

```sh
python3 tools/unpack.py SMEG_PLUS_UPG/NAV/AppBin/f_BigQuick.bin app_nav.bin
```

### 2. Build a package

```sh
uv run tools/build_package.py --manifest builds/aux-only.json   # edit its package/out paths first
```

This applies the patch sets (verifying the original bytes first), rebuilds the media
partition, rebuilds the whole checksum cascade, re-seals `contract.dat`, and runs the
pre-flight check — in that order, which is the part that fails silently by hand. Without the
re-seal the unit refuses the package with string 2099.

```
f_BigQuick.bin -> f_BigQuick.bin.inf + smeg.inf + <module>_ctrl.bin -> ctrl.bin
```

The individual tools (`patch_smeg.py`, `patch_media.py`, `patch_contract.py`) are described in
[Running the tools](docs/RUNNING.md).

### 3. Copy to a stick and flash

```sh
uv run tools/prepare_usb.py --package ~/Downloads/SMEG_PLUS_UPG_auxonly --target /Volumes/USB
```

This checks the stick is MBR + FAT32, copies, re-reads every file, and removes the macOS
`._*` shadows. Then, **parked** with the engine running, run the normal SMEG+ update. See
[`docs/FLASHING.md`](docs/FLASHING.md), including [the test loop](docs/FLASHING.md#the-test-loop-end-to-end).

## Tools

The main ones are below. Every tool, with its `--help`, is on the generated
[Tool reference](https://smeg.kroper.uk/TOOLS/) page (`docs/TOOLS.md`).

| tool | purpose |
|---|---|
| `tools/build_package.py` | **start here** — manifest → patched, media-rebuilt, re-sealed and pre-flighted package |
| `tools/preflight.py` | validate a built package offline before it goes on a stick |
| `tools/unpack.py` | inflate `f_BigQuick.bin` → raw PPC image |
| `tools/patch_contract.py` | regenerate `contract.dat` so a modified package is accepted |
| `tools/patch_smeg.py` | apply a patch set and rebuild the CRC cascade |
| `tools/mkelf.py` | wrap a raw image + symbol map into a disassemblable PPC ELF |
| `tools/ppcdis.py` | PowerPC disassembler with symbol/call resolution |
| `tools/xref.py` | find code that references a string, address or pointer |
| `tools/callers.py` | find direct (`bl`) callers of a function |
| `tools/patch_media.py` | rebuild a media partition (ring tones, resources) |
| `tools/fix_userdata_case.py` | verify/fix the FAT long filename needed for a lowercase `sqlite` payload |
| `tools/ringtones.py` | convert custom audio to the unit's ring/wait tone formats |
| `tools/patch_studio.py` | Qt front-end: ringtone conversion + patch builder (optional) |
| `tools/ppcemu.py` | run a single firmware function on an emulated PowerPC core |
| `tools/elfsyms.py` | read the symbol tables the package ships in `upgrade.out` and friends |
| `tools/cartography.py` | read the map metadata: name pools, `.inf` sidecars, `SCC` records, `CCT.DAT` |
| `tools/crc_recover.py` | recover CRC parameters from `(message, checksum)` samples |
| `tools/fingerprint.py` | identify which build an application image is, or refuse |
| `tools/prepare_usb.py` | copy a package to a stick, verify the copy, check the layout |
| `tools/verify_package.py` | audit a package's checksum cascade before flashing |
| `tools/symdiff.py` | diff two releases by symbol, and locate a patch in another |
| `tools/apply_files.sh` | overlay patched files onto a package copy |
| `tools/survey.py` | inventory every function in an image: callers, indirect references, strings |
| `tools/splash.py` | the marque logo bundles (not the boot splash) |
| `tools/assets.py` | human-readable names for the media partition's replaceable files |
| `tools/check_no_pii.py` | the hook that keeps personal data out of commits |

```sh
pip install capstone
python3 tools/ppcdis.py app_nav.bin abs_symbols_base.txt 0x0230331c 0x02303460
```

## Documentation

Also published as a docs site: <https://smeg.kroper.uk/> (Zensical, built and deployed by GitHub Actions).


| doc | contents |
|---|---|
| [`docs/ANALYSIS.md`](docs/ANALYSIS.md) | **archive** — the original notes, superseded by the AUX chain and emulation pages |
| [`docs/RUNNING.md`](docs/RUNNING.md) | how to run everything with `uv` / `uvx` |
| [`docs/PATCHES.md`](docs/PATCHES.md) | exact addresses and bytes per build |
| [`docs/FLASHING.md`](docs/FLASHING.md) | preparing the USB stick and flashing |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | how the whole firmware fits together: modules, HMI framework, messaging, subsystems, databases |
| [`docs/MEDIA_PROTECTION.md`](docs/MEDIA_PROTECTION.md) | the signed contract that **blocks modified firmware from being flashed** |
| [`docs/FLASH_CHAIN.md`](docs/FLASH_CHAIN.md) | BSP/flash layout, the updater's phases and gates, the manifest format used above |
| [`docs/MEDIA_PARTITION.md`](docs/MEDIA_PARTITION.md) | media partition layout, ringtones and wait tones, and the checksum cascade |
| [`docs/CHEATCODES.md`](docs/CHEATCODES.md) | cheatcode list, entry mechanism, spy/diagnostics system |
| [`docs/RELEASING.md`](docs/RELEASING.md) | conventional commits and the automatic release/changelog flow |
| [`docs/RINGTONES.md`](docs/RINGTONES.md) | ring/wait tone formats, the converter, and the Qt studio |
| [`docs/VERSION_STRINGS.md`](docs/VERSION_STRINGS.md) | what the version screens read, and how the updater gates on them |
| [`docs/AUX_CHAIN.md`](docs/AUX_CHAIN.md) | the AUX auto-switch gate by gate: what has to happen, what is proven, what is still unknown |
| [`docs/EMULATION.md`](docs/EMULATION.md) | executing firmware functions without a car — and what that proved about the AUX patches |
| [`docs/AUX_SIGNAL.md`](docs/AUX_SIGNAL.md) | how the AUX signal is detected, and the switch-on-signal candidate |
| [`docs/VERIFICATION.md`](docs/VERIFICATION.md) | what has been tested on a real unit, and what each test showed |
| [`docs/RECOVERY.md`](docs/RECOVERY.md) | what to do when an update goes wrong |
| [`docs/FIRMWARE_MAP.md`](docs/FIRMWARE_MAP.md) | where the image's code goes, and how much of it has been read |

Every page, including the subsystem readings (scheduler, audio module, HMI sources, update
flow), the glossary and the toolchain, is on the docs site.

## Development environment

The CLI tools need nothing but `uv` — each script declares its own dependencies, so
`uv run tools/<script>` just works. The GUI, tests and docs build want a virtualenv.
`.venv/` is not in the repo; create it once (Python 3.13, because Homebrew's `python3` is
3.14, where `ensurepip` is broken and PySide6 has no wheels):

```sh
uv venv --seed --python 3.13 .venv
uv pip install --python .venv/bin/python -r requirements-dev.txt -r requirements-gui.txt zensical
```

`requirements-dev.txt` brings `unicorn` and `capstone`; without them the emulator tests skip
rather than run.

```sh
.venv/bin/python tools/patch_studio.py        # the GUI
.venv/bin/python -m pytest tests -q           # the test suite
```

Or use plain `pip install -r requirements-dev.txt` for the tests alone (the GUI tests then
skip).

Install the git hooks once — `pre-commit install` wires all three types:

```sh
pre-commit install       # pre-commit, commit-msg and pre-push
```

Lint, formatting, hygiene and the no-firmware and no-PII guards run on every commit; the tests, a strict docs build
and a `bandit` security scan run on push, so a push that would go red in CI fails locally
first. See [`CONTRIBUTING.md`](CONTRIBUTING.md).

## Working with AI agents

Agents should start at [`AGENTS.md`](AGENTS.md): the hard rules (no vendor firmware,
conventional commit titles, `main` is PR-only), how to run the tests and GUI, and the
firmware quirks that are easy to get wrong.

## Contributing

Conventional commit titles (they drive the release), and no vendor firmware in the repo —
see [`CONTRIBUTING.md`](CONTRIBUTING.md).

## Tests

`tests/` builds a **synthetic package from scratch** — no vendor firmware is
needed — and asserts the patch/repack path, the `expect` byte check, the CRC cascade
and the docs nav. Run them with `python -m pytest tests -q`; CI runs the same on every
pull request.

## Licence

MIT — see [`LICENSE`](LICENSE). The scripts are the author's own work. No third-party
firmware is covered by, or included under, this licence. See [`NOTICE.md`](NOTICE.md)
for the trademark and no-firmware statements.
