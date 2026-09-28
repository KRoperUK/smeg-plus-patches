---
hide:
  - navigation
  - toc
---

# SMEG+ Patches

Reverse-engineering notes and tooling for PSA / Stellantis **SMEG+** head units — the
Magneti Marelli infotainment fitted to Peugeot, Citroën and DS vehicles around 2012–2017.

The project started with one concrete problem: an aftermarket CarPlay / Android-Auto
piggyback injects its audio into the head unit's AUX input, and the pain is having to switch
the unit to AUX by hand every time. That is still the goal, but the work underneath it — the
signed media contract, the checksum cascade, the settings partitions — generalises to any
patch you want to make to one of these units.

!!! warning "No vendor firmware here"

    This site documents **our own** reverse-engineering and tooling. It contains no
    Peugeot / Citroën / DS / Stellantis / Magneti Marelli firmware, upgrade packages,
    symbol maps, or other copyrighted binaries. You supply your own legally obtained
    package. The licence key material needed to re-seal a package is recovered from that
    package at runtime and is never stored here.

## Start here

<div class="grid cards" markdown>

-   :lucide-car:{ .lg .middle } __I own one of these cars__

    ---

    Build a package, put it on a stick safely, flash it, and get back if it goes wrong.

    1. [What is reachable](CAPABILITIES.md): what can and cannot be changed
    2. [Running the tools](RUNNING.md): one command builds a package
    3. [Flashing](FLASHING.md#the-test-loop-end-to-end): the whole test loop, parked
    4. [Recovery](RECOVERY.md): before you need it

-   :lucide-microscope:{ .lg .middle } __I want the firmware internals__

    ---

    How the application image is built, what has been read closely, and how claims are
    checked.

    1. [Architecture](ARCHITECTURE.md) and the [Firmware map](FIRMWARE_MAP.md)
    2. [The source scheduler](SCHEDULER.md), [the audio module](AUDIO_MODULE.md),
       [the AUX chain](AUX_CHAIN.md)
    3. [Emulation](EMULATION.md): running firmware functions on a desktop
    4. [Verification](VERIFICATION.md): what was proven, and how

</div>

## Find your way in

The site is organised by the part of the firmware you are touching. Start with whichever
card matches what you are trying to do.

<div class="grid cards" markdown>

-   :lucide-compass:{ .lg .middle } __Get orientated__

    ---

    What can and cannot be changed on these units, and how the whole firmware fits
    together. **Read this before starting work.**

    [:lucide-arrow-right: What is reachable](CAPABILITIES.md) ·
    [Architecture](ARCHITECTURE.md)

-   :lucide-shield-check:{ .lg .middle } __The chain that protects it__

    ---

    The boot and update sequence, the signed media contract, and why version strings
    are not a safe marker.

    [:lucide-arrow-right: Boot & update chain](FLASH_CHAIN.md) ·
    [Media protection](MEDIA_PROTECTION.md) ·
    [Version strings](VERSION_STRINGS.md)

-   :lucide-cpu:{ .lg .middle } __The application image__

    ---

    The PowerPC image inside `f_BigQuick.bin`: the patch reference, the AUX
    auto-switch chain gate by gate, how it was verified by emulation, and the
    cross-platform toolchain for reading and writing PowerPC.

    [:lucide-arrow-right: Patch reference](PATCHES.md) ·
    [The AUX chain](AUX_CHAIN.md) ·
    [Emulation](EMULATION.md) ·
    [Toolchain](TOOLCHAIN.md)

-   :lucide-music:{ .lg .middle } __The media partition__

    ---

    `system.bin`: ring tones, fonts, logos, strings, the cheatcode list — every
    replaceable asset and its risk level.

    [:lucide-arrow-right: Media partition](MEDIA_PARTITION.md) ·
    [Ring tones](RINGTONES.md) ·
    [Customising](CUSTOMISING.md) ·
    [Cheatcodes & spy](CHEATCODES.md) ·
    [Cartography](CARTOGRAPHY.md)

-   :lucide-terminal:{ .lg .middle } __Build & flash__

    ---

    Running the tools, preparing the stick, the in-car update, and what has actually
    been confirmed on hardware.

    [:lucide-arrow-right: Running the tools](RUNNING.md) ·
    [Flashing](FLASHING.md) ·
    [Hardware verification](VERIFICATION.md)

-   :lucide-book-open:{ .lg .middle } __Reference__

    ---

    The vocabulary of these units in one place, and the repository's own release
    process.

    [:lucide-arrow-right: Glossary](GLOSSARY.md) ·
    [Releasing](RELEASING.md)

</div>

## Target

Developed against `SMEG5.43.A.R2` (CD 26482, 19-09-17) on a **NAV** unit in a 2015 Peugeot
208. The `AUDIO_BT` and `AUDIO_BT_256` builds are supported too; each is a separate image
with its own symbol map and patch addresses.

## Status

A patched, **contract re-sealed** package has been flashed to a real unit successfully: the
media check passed, the application image was written, and the unit came back up working.

- [x] **The re-seal works** — string 2099 (*"the update file is protected and cannot be
  copied"*) never appeared, which was the blocker for the whole project.
- [x] **`IsAUXSRCAvailable()`** — AUX no longer greys out without a signal, and it is back in
  the SRC cycle.
- [x] **Custom ring tone** audio. A *renamed* tone still showed its stock name on the car
  (2026-09-27), so names are not solved — see [Ring tones](RINGTONES.md#names).
- [x] **`SPYSTORE` backs up `/USER_DATA`** — the `spy-dump-userdata` patch, confirmed on a car.
- [ ] **The automatic AUX switch.** The original handler patch rested on a wrong premise: the
  handler follows the saved AUX *setting*. `aux-signal-switch` routes the real signal event
  instead — verified under emulation, not yet flashed. See [The AUX signal path](AUX_SIGNAL.md).
- [ ] **Boot to AUX.** `aux-boot-default` alone is falsified on hardware; the three-edit
  `aux-boot-restore` is the current candidate, not yet flashed. See
  [The AUX chain](AUX_CHAIN.md#how-the-boot-source-is-actually-chosen).

### Every patch set, by status

Generated from the `status` field of each `patches/*.json` by `tools/patch_status.py`, so it
cannot disagree with the patch reference.

<!-- patch-status:panel -->
- **Confirmed on hardware:** `aux-always-available`, `aux-autoswitch`, `spy-dump-userdata`
- **Flashed, effect not yet confirmed:** `spy-dump-userdata-partition`
- **Candidates awaiting a car test:** `aux-boot-restore`, `aux-signal-switch`, `aux-sticky`
- **Falsified on hardware:** `aux-boot-default`
- **Diagnostic builds, not for driving:** `diagnostic-logging`, `diagnostic-logmask`, `diagnostic-logsink`

Per-patch detail: [Patch reference](PATCHES.md#patch-sets-in-this-repository).
<!-- /patch-status:panel -->

See [Hardware verification](VERIFICATION.md) for the full picture, and the
[repository issues](https://github.com/KRoperUK/smeg-plus-patches/issues) for what is being
worked on.

## The short version of the hard-won lessons

- **The unit keeps its own state.** Settings live on a separate `/USER_DATA` partition, not in
  the package. Editing the copy inside `system.bin` can appear to do nothing.
- **Payloads are version- and value-checked.** A source value the unit does not recognise is
  ignored silently, and it falls back — so validate against the real enum rather than guessing.
- **Build, then check, then flash.** `tools/preflight.py` runs as part of the build and fails
  it; most of the wasted trips in this project were things it would have caught.
