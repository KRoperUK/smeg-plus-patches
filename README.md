# smeg-plus-patches

Reverse-engineering notes and tooling for **PSA / Stellantis "SMEG+"** infotainment head
units, the Magneti Marelli units fitted to Peugeot, Citroën and DS vehicles around 2012–2017.

The motivating problem: an aftermarket CarPlay / Android-Auto piggyback (such as CarABC /
AutoABC) feeds its audio into the head unit's **AUX** input, and the unit keeps starting on the
radio. The patches here make the unit **boot straight to AUX**, and the tooling around them
(re-sealing the signed media contract, rebuilding the checksum cascade, custom ring tones)
applies to any change you want to make to one of these units.

Developed against **Peugeot 208 (2015), SMEG+ iV1, `NAV`, firmware `SMEG5.43.A.R2`** (CD 26482,
19-09-17). Patch addresses are per build and per firmware version.

**Docs site:** <https://smeg.kroper.uk/>

> ## No vendor firmware is included
> This repository contains **only original reverse-engineering notes and scripts**.
> It does **not** contain any Peugeot / Citroën / DS / Stellantis / Magneti Marelli
> firmware, upgrade packages, symbol maps, or other copyrighted binaries — those are
> not distributed here and `.gitignore` is set up to keep them out.
>
> To use these tools you must supply your **own** legally obtained firmware upgrade
> package. You are responsible for complying with the laws and licence terms that apply
> to your own device and software.

## Status

| what | status |
|---|---|
| re-sealed package accepted by the unit (no string 2099) | confirmed on hardware |
| AUX always available (`IsAUXSRCAvailable()`) | confirmed on hardware |
| **boot to AUX** (`aux-autoswitch` + `aux-boot-default` + `aux-boot-restore`) | **confirmed on hardware** (NAV 5.43.A.R2) |
| custom ring tone audio | confirmed on hardware |
| custom ring tone *names* (an application-image patch) | built and verified offline; not yet confirmed on a car |
| switching to AUX when a signal appears (`aux-signal-switch`) | emulated candidate only; not pursued |

Every patch set and its hardware status is in the
[patch reference](docs/PATCHES.md#patch-sets-in-this-repository); the car tests behind each
status are in [Hardware verification](docs/VERIFICATION.md#later-car-tests).

## Quick start: boot to AUX

You need [uv](https://docs.astral.sh/uv/) and your own stock upgrade package laid out as
`SMEG_PLUS_UPG/…`.

1. **Build.** Edit `package` and `out` in [`builds/aux-boot.json`](builds/aux-boot.json), then:

    ```sh
    uv run tools/build_package.py --manifest builds/aux-boot.json
    ```

    This applies the patch sets (checking the original bytes first), rebuilds the checksum
    cascade, re-seals `contract.dat` and runs the pre-flight check, in the order that works.
    The build is application-image only: it does not touch the car's paired phones,
    destinations or presets.

2. **Copy to a stick** (MBR + FAT32):

    ```sh
    uv run tools/prepare_usb.py --package <out>/SMEG_PLUS_UPG --target /Volumes/<stick> --eject
    ```

    It copies, re-reads every file to prove the copy, and removes the files macOS leaves on FAT.

3. **Flash, parked with the engine running.** The updater reboots the unit. Remove the stick
   once the normal screen is back. See [Flashing](docs/FLASHING.md#the-test-loop-end-to-end).

Other builds (ring tones, diagnostics, candidates) are listed in
[Running the tools](docs/RUNNING.md).

## How it works, briefly

- The application is `AppBin/f_BigQuick.bin`: a 0x800-byte header, a `0x08` marker at `0x800`,
  then a zlib stream from `0x801` inflating to a raw **PowerPC** image at `0x01000000`. The
  shipped symbol maps line up with it, so patches are located by symbol, not by pattern.
- Every edit walks a chain of checksums back to the root manifest, and `contract.dat` seals the
  package; `tools/patch_contract.py` re-seals it with key material recovered from your own
  image at runtime. See [Media protection](docs/MEDIA_PROTECTION.md).
- At boot the source scheduler restores the last source, but AUX's boot request is excluded
  from that restore, so a timer falls back to FM. `aux-boot-restore` lets AUX take part and
  `aux-boot-default` makes AUX the restore target. See
  [The AUX chain](docs/AUX_CHAIN.md#how-the-boot-source-is-actually-chosen).

## Tools

The main tools are below. Every tool, with its `--help`, is on the generated
[Tool reference](https://smeg.kroper.uk/TOOLS/) page (`docs/TOOLS.md`).

| tool | purpose |
|---|---|
| `tools/build_package.py` | **start here** — manifest → patched, media-rebuilt, re-sealed and pre-flighted package |
| `tools/preflight.py` | validate a built package offline before it goes on a stick |
| `tools/prepare_usb.py` | copy a package to a stick and verify the copy |
| `tools/verify_package.py` | audit a package's checksum cascade |
| `tools/spy_read.py` | read a `SPYTAKE` capture: how the boot source was chosen, AUX events |
| `tools/patch_smeg.py`, `patch_media.py`, `patch_contract.py` | the individual steps `build_package.py` runs |
| `tools/ringtones.py`, `patch_studio.py` | ring tone conversion, and a Qt front-end |
| `tools/ppcemu.py`, `ppcdis.py`, `survey.py`, `xref.py` | the analysis tools: emulator, disassembler, whole-image inventory, cross-references |

## Documentation

The docs site has two starting points: **car owners** (what is reachable → running the tools →
flashing → recovery) and **researchers** (architecture → firmware map → the scheduler, audio
module and AUX chain → emulation → verification). Start at <https://smeg.kroper.uk/>.

## Development

The CLI tools need nothing but `uv`. The GUI, tests and docs build want a virtualenv (Python
3.13, because Homebrew's `python3` is 3.14, where `ensurepip` is broken and PySide6 has no
wheels):

```sh
uv venv --seed --python 3.13 .venv
uv pip install --python .venv/bin/python -r requirements-dev.txt -r requirements-gui.txt -r requirements-docs.txt
.venv/bin/python -m pytest tests -q
pre-commit install       # pre-commit, commit-msg and pre-push hooks
```

The tests build a **synthetic package from scratch**, so no vendor firmware is needed. Lint,
formatting and the no-firmware and no-PII guards run on every commit; the tests, a strict docs
build and a `bandit` scan run on push. See [`CONTRIBUTING.md`](CONTRIBUTING.md), and
[`AGENTS.md`](AGENTS.md) for AI agents.

## Licence

MIT — see [`LICENSE`](LICENSE). The scripts are the author's own work. No third-party
firmware is covered by, or included under, this licence. See [`NOTICE.md`](NOTICE.md)
for the trademark and no-firmware statements.
