# Glossary

The recurring vocabulary of these units, in one place. Terms are defined here
once; the rest of the site links back rather than re-explaining them.

## Hardware and platform

`SMEG+`
:   The Magneti Marelli infotainment head unit fitted to Peugeot, Citroën and DS
    vehicles roughly 2012–2017. The subject of this whole site.

`NAV` / `AUDIO_BT` / `AUDIO_BT_256`
:   The three build variants of the firmware. `NAV` has navigation; the two
    `AUDIO_BT` builds do not. Each is a separate image with its own symbol map
    and its own patch addresses — an address from one build is meaningless on
    another. See [Patch reference](PATCHES.md).

PowerPC
:   The big-endian CPU architecture the application image runs on. Patch bytes
    are PowerPC machine code.

e300 / MPC5121e
:   The SoC (Freescale MPC5121e) and its core (e300): plain 32-bit big-endian
    PowerPC with no vendor extensions, which is why `tools/ppcemu.py` can run the
    shipped image. See [Emulation](EMULATION.md).

VxWorks / BSP
:   The real-time operating system and its Board Support Package — the low-level
    layer that boots the unit before the application starts. See
    [Boot & update chain](FLASH_CHAIN.md).

Renesas MCU
:   The front-panel microcontroller. The updater reflashes it as one of its
    phases, which is one reason the unit reboots mid-update.

## The firmware image and its parts

`f_BigQuick.bin`
:   The application image as shipped: an `0x800`-byte header, an `0x08` marker,
    then a zlib stream that inflates to the raw PowerPC image at `0x01000000`.
    It is **not** encrypted. Patching happens here.

`system.bin`
:   The media partition — a gzip'd tar holding ring tones, fonts, logos, the
    cheatcode list, version markers and more. See
    [Media partition](MEDIA_PARTITION.md).

`system_ctrl.bin`
:   The per-file CRC manifest for everything inside `system.bin`. Editing a file
    in the partition means recomputing its record here.

`smeg.inf`
:   The version-marker file **inside** the media partition. It holds `GUI_VER`,
    which System Information shows on the GUI item's page (read); `32.01` was not seen on
    the one page looked at (2026-09-27). See [Version strings](VERSION_STRINGS.md).

`UpgPlugin.out`
:   The updater plugin on the stick. The unit loads and calls it **before** it
    checks the contract, and while it is on a mounted stick the unit re-offers the
    update at every start. See [The update flow](UPGRADE_FLOW.md).

`USER_DATA`
:   The partition the *car* owns — paired phones, navigation destinations,
    presets, settings. It is not shipped in the package, which is why editing a
    copy inside `system.bin` appears to do nothing, and why overwriting it is
    destructive and unrecoverable by reflashing.

## Integrity and protection

`contract.dat`
:   The signed media contract. Its RSA-OAEP records let the unit verify the
    package has not been tampered with. A modified package must be re-sealed or
    the unit rejects it. See [Media protection](MEDIA_PROTECTION.md).

`CheckTrustedSource()`
:   The routine that validates the contract. When it fails, the unit shows
    string 2099.

`CheckType`
:   A contract record's check kind: 1 size, 2 CRC32, 3 spot check; any other value
    fails. What it means in the `*_ctrl.bin` manifests is still open. See
    [Media protection](MEDIA_PROTECTION.md).

String 2099
:   The on-screen error *"the update file is protected and cannot be copied"* —
    what you see when the contract does not match the package.

CRC cascade
:   The chain of checksums (file → manifest → module → root) that must all be
    recomputed, in order, after any change. `tools/patch_smeg.py` rebuilds it.

`SIZE` / `SIZE_n`
:   Computed fields in `system.bin.inf`: `SIZE` is the sum of the file sizes in
    the tar; `SIZE_n` is the same rounded up per file to *n* KiB.

## Audio and the AUX chain

`IsAUXSRCAvailable()`
:   `C_HMI_AUDIO_APP_BASE`'s check that decides whether AUX appears in the source
    list. Patched so AUX no longer greys out without a signal. **Confirmed on
    hardware.**

`HandleAudioAuxInputStatusChnged()`
:   The media app's AUX handler. It reacts to changes of the saved AUX input
    **setting**, not the AUX signal. `aux-signal-switch` (a candidate) makes it
    follow the signal instead. See
    [The AUX chain](AUX_CHAIN.md#what-the-handler-actually-reacts-to).

`Auxiliary_Status`
:   The saved AUX input setting (0–3, from the menu), held at
    `C_MODULE_AUDIO+0x8c`; what `Get_aux_status` returns. Not the signal.

`Get_AUX_signal_status`
:   The query for whether an AUX signal is actually present.

`0xcb` / `0xcc`
:   `AUDIO_AUX_INPUT_STATUS_CHANGED` (the saved setting changed) and
    `AUDIO_AUX_SIGNAL_STATUS_CHANGED` (the signal changed). The stock media app
    handles only `0xcb`. See [The AUX signal path](AUX_SIGNAL.md).

`st_audio`
:   `C_MODULE_AUDIO+0x74`, the audio module's lifecycle state (0 closed, 1 open,
    2 restart, 9 early-started, 10 started, `0x28` error). Signal events are
    dropped below 10. See [The audio module](AUDIO_MODULE.md).

`C_MGR_SRC`
:   The source scheduler. It takes every HMI source request, picks a winner, and
    restores the saved source at boot. See [The source scheduler](SCHEDULER.md).

`Last_Source` / `Last_Source_Priority`
:   The saved scheduler position and priority (`C_MGR_SRC+0xb4`, `+0xac`),
    restored by `StartUp` at boot. AUX is (7, 20).

`Sched_Pos`
:   A request's scheduler position: `POS_TUNER` 1, `POS_AUX` 7.

`ScheduledInit`
:   `C_MGR_SRC+0x370`: up to 10 (position, priority) pairs that the boot restore
    compares against `Last_Source`. If nothing matches within 7.5 s, the init timer
    picks position 1 — the tuner.

`PrOnly`
:   Request byte `+0x28`, set from `ActivateSource`'s `bool` argument. A request
    with it set skips the boot restore, which is why stock AUX never resumes. See
    [How HMI apps request sources](HMI_SOURCES.md).

`ActivateSource(bool)` / `ForceSchedulerPosition`
:   The HMI's source request (its `bool` becomes `PrOnly`), and the scheduler call
    that moves an already-initialised source to the front.

## Diagnostics

Cheatcode
:   A hidden service code, listed in `cheatcodes.sqlite` and reached from a
    hidden entry screen. Each code's behaviour is a `libcheatcode_*` library on
    the unit. See [Cheatcodes & spy](CHEATCODES.md).

`CATCLN` / `SPYCLN` / `MSDREFRESH ON`
:   The three codes that **destroy data**. See the danger box in
    [Cheatcodes & spy](CHEATCODES.md).

`C_BCM_SPY` / `SPYSTORE`
:   The on-unit diagnostics/spy subsystem and the action that dumps its data to
    a USB stick. The `spy-dump-userdata` patch repurposes part of its copy loop
    to also back up `/USER_DATA`.

`SPYTAKE` / `RAMDISK_SPY`
:   The full user collect: every trace buffer (71 on the car), written to
    `SPY/<stamp>/TAR/*-USER.tar.gz`, then a reboot. Inside, `RAMDISK_SPY/<id>/`
    holds one buffer per module as `<ms>::<event>` text — `25300` is `C_MGR_SRC`,
    `06301` the media app. It holds the VIN and personal data. See
    [The test loop](FLASHING.md#the-test-loop-end-to-end).

`HARMONY`
:   The skin/theme module that owns the car's on-screen look. Five skins ship;
    custom artwork is gated. See [What is reachable](CAPABILITIES.md).

`ZA files`
:   Danger-zone / speed-camera data files the unit can ingest.

## Analysis

`C_HMI_*` / `C_BCM_*` / `C_MODULE_*` / `C_SRV_*` / `com_MM_*`
:   The code layers: HMI apps; business components and their DBUS server/client
    pairs; hardware owners; services; generated DBUS proxies. See
    [Architecture](ARCHITECTURE.md) and [Firmware map](FIRMWARE_MAP.md).

Materialised reference
:   A `lis` + `addi`/`ori` pair that builds an address. It is how most calls here
    are made (through `mtctr`/`bctrl`), and what `callers.py` misses.

Survey / family
:   `tools/survey.py`'s per-function inventory of an image; a family is the class
    prefix, e.g. `C_MGR_SRC`. See [Firmware map](FIRMWARE_MAP.md).

Evidence tiers
:   *Executed*, *read*, *inferred*, *not known* — how every claim on this site is
    tagged. See [Verification](VERIFICATION.md).

## Project process

`GUI_VER`
:   A version field in the partition's `smeg.inf`. Harmless to change, but it was
    shown on the GUI item's page of System Information by the code *(read)*, but `32.01`
    was not seen on the page looked at (2026-09-27), so it is not yet a confirmed build
    marker. See [Version strings](VERSION_STRINGS.md#is-gui_ver-visible).

Release Please
:   The automation that turns Conventional Commit titles on `main` into releases.
    See [Releasing](RELEASING.md).
