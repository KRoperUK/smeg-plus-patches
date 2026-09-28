# Flashing notes

!!! warning "Re-seal the package before flashing"

    The unit validates the media against a signed contract, and will reject a patched
    package with *"The update file is protected and cannot be copied."* (string 2099)
    unless the contract is regenerated. `build_package.py` does it for you, in the right
    order. By hand, the patch step must write a **full** package (`--copy-package`), or the
    re-seal finds no `contract.dat`:

    ```sh
    uv run tools/build_package.py  --manifest builds/<scheme>.json      # recommended
    # or, by hand:
    uv run tools/patch_smeg.py     --src SMEG_PLUS_UPG --out SMEG_PLUS_UPG_mod --copy-package
    uv run tools/patch_contract.py --package SMEG_PLUS_UPG_mod
    ```

    A **stock** package needs no such step and can be flashed as-is (including a
    rollback). See [Media protection](MEDIA_PROTECTION.md).

These are generic notes for applying a patched SMEG+ package. They are not a substitute
for the update instructions that came with your vehicle/software. Do this at your own
risk.

## Shipping settings: the `USER_DATA` payload, and why it does not land

A package can carry a `USER_DATA` payload — `NAV/USER_DATA/user_data/sqlite/…` — which the updater
copies over the unit's live settings partition. **It does not work on this unit**, for these
reasons:

- The copy is `xcopy_blk("/bd0/SMEG_PLUS_UPG/NAV/USER_DATA", "/USER_DATA")`, hard-coded, in the
  block that continues **Phase 1** of `UpgradeTask`.
- The destination directory is named from what the updater reads off the stick, and **FAT gives
  out uppercase 8.3 short names**. The application reads its live settings from lowercase
  `/USER_DATA/user_data/sqlite/`, so the payload lands in an uppercase `SQLITE/` sibling and is
  never opened.

Observed on a car, with the log to prove it — see
[the second flash](VERIFICATION.md#second-flash-the-user_data-retry-2026-09-14). A flash with a
correctly-laid-out payload ran the copy, and the unit's own settings dump afterwards still read
the factory `supervisor.Last_Source`.

Two other things the same log and updater binary settled:

- The live directory holds a `.inf` sidecar beside every database (`up_common.sqlite.inf`).
  `C_UPGRADE::ManageSQLiteFiles` says `We have to generate the .inf file!`; the generated file
  found on the stick is exactly `CRC32: <signed decimal>\r\n`, and its value matches the edited
  database. `build_package.py` writes that pair up front and pre-flight rejects a missing or
  stale sidecar.
- `C_UPGRADE::RestoreDataFromUSB` copies from a **per-unit** directory, `/bd0/<unit-id>/`, not
  from the package path. `C_UPGRADE::SaveDataOnUSB` is what creates it, and it did not run.

### Working around it: give the directory a long-filename entry

The updater names each destination directory after what it reads off the stick, and it reads
**long filenames** but not the FAT "lowercase base" bit. So the fix is to make the payload's
`sqlite` directory carry a long-filename entry.

macOS will not write one for an 8.3-valid name like `sqlite` — it stores the short name
`SQLITE` with that bit set and no LFN, which is precisely how this goes wrong. Renaming does
not help; it does the same thing. The entry has to be written or corrected directly:

1. Name the directory something that *needs* an LFN, e.g. `sqlite_dat`, so macOS writes one.
2. Unmount the volume (`diskutil unmount`, not eject — eject removes the device node), then
   rewrite that one LFN entry's characters to `sqlite`. The short name and its entry checksum
   are untouched, and it is a single 32-byte read-modify-write:

   ```sh
   diskutil unmount /Volumes/SMEGUPDATE
   sudo python3 tools/fix_userdata_case.py --dry-run /dev/rdisk4s1
   sudo python3 tools/fix_userdata_case.py /dev/rdisk4s1
   diskutil mount /dev/disk4s1
   ```

3. Before flashing, unmount once more and run the read-only check against the FAT volume:

   ```sh
   python3 tools/fix_userdata_case.py --check /dev/disk4s1
   ```

   It must print `OK: FAT long-filename entry is exactly 'sqlite'`. Finder displaying lowercase
   is not proof: the checker rejects short-name `SQLITE` even when its FAT lowercase-display bit
   is set, because that is the exact representation the updater mishandles.

!!! warning "Not shown to work on hardware"

    The filesystem half is verified: the directory reads back as `sqlite`, and the `.inf` is
    present. A flash laid out this way still did not change the setting — see
    [the later flash report](VERIFICATION.md#later-flash-report-the-case-workaround-package).
    Prefer an application-image patch (boot to AUX is one) or a media-partition edit.

## Prepare the USB stick

- Use a stick of **8 GB or more** (a package with navigation TTS data is roughly 1 GB).
- Format it **FAT32** (`MS-DOS (FAT)`), partition scheme **Master Boot Record**.
  - macOS: Disk Utility → select the **device** (not the volume) → Erase →
    Format "MS-DOS (FAT)", Scheme "Master Boot Record".
- Copy the package folder to the **root** of the stick, so you end up with:

```
/Volumes/USB/SMEG_PLUS_UPG/ctrl.bin
/Volumes/USB/SMEG_PLUS_UPG/contract.dat
/Volumes/USB/SMEG_PLUS_UPG/NAV_ctrl.bin
/Volumes/USB/SMEG_PLUS_UPG/upgrade.out
/Volumes/USB/SMEG_PLUS_UPG/NAV/…
/Volumes/USB/SMEG_PLUS_UPG/AUDIO_BT/…
/Volumes/USB/SMEG_PLUS_UPG/BSP/…
…
```

!!! warning "The folder must be called `SMEG_PLUS_UPG` — especially with a `USER_DATA` payload"

    The ordinary update is found by scanning, but the settings payload is **not**.
    `C_UPGRADE::UpgradeTask` checks one literal path —
    `IsDirExist("/bd0/SMEG_PLUS_UPG/NAV/USER_DATA")` — and only then runs
    *"Copy of /USERDATA from /bd0 to NAND"*. Both the folder name and the module are
    hard-coded in that string.

    So a build written to, say, `SMEG_PLUS_UPG_auxdefault` still flashes normally and its
    payload is **skipped without a word**, which looks exactly like the setting having had no
    effect. `tools/preflight.py` fails on this, and `build_package.py` says so at build time.

### Let the tool do the copy

```sh
python3 tools/prepare_usb.py --package out/SMEG_PLUS_UPG --target /Volumes/USB
python3 tools/prepare_usb.py --package out/SMEG_PLUS_UPG --target /Volumes/USB --dry-run
python3 tools/prepare_usb.py --package out/SMEG_PLUS_UPG --target /Volumes/USB --eject
```

It checks the layout, the target and the free space **before copying anything**, says which
target it is about to write to first, then copies and **re-reads every file back off the stick
and compares checksums**.

That last step is the one that matters: a stick pulled mid-copy, or a copy tool that leaves
AppleDouble `._*` files beside the package, produces an update failure in the car that looks
like a firmware fault. `._*` and `.DS_Store` count as a **failure, not
a warning**: the updater does not expect them, so the exit code is non-zero and nothing is
left to judgement.

A data-only copy does not stop macOS writing `._*` files. The kernel tags every newly created
file with a `com.apple.provenance` attribute, and FAT can only store that as a `._*` shadow
beside it. After copying, the tool deletes the shadow of each file and directory it wrote, and
nothing else. Any other litter inside the package still fails the check.

macOS also creates `.Spotlight-V100` and `.fseventsd` at the stick's **root** when it mounts it,
and Spotlight indexing a freshly written stick keeps the volume busy, so `diskutil eject` can
fail until retried. The folders are outside `SMEG_PLUS_UPG`, which is all the updater reads.
On macOS `prepare_usb` therefore:

- writes `.metadata_never_index` at the root and runs `mdutil -i off` (a refusal is reported,
  not fatal);
- removes those two folders after the copy is verified;
- with `--eject`, ejects the stick, retrying with a back-off while it is busy.

`--keep-index` skips all of this. Without `--eject`, eject with `diskutil eject` before
unplugging.

It only ever writes inside `--target`, and refuses to copy a package into itself.

**It also refuses to write into a package that is already there.** Copying into a directory
that already holds one silently merges the two, and the result still passes every checksum
its own manifests declare — so nothing downstream notices, and the stick ends up flashing
something nobody built. Remove the old copy first, or point `--target` at a clean one.

`--force` continues past a filesystem complaint — a non-FAT32 or non-MBR target is refused by
default, with the Disk Utility steps below. The probing is macOS-only and deliberately
conservative: when it cannot tell, it says so rather than guessing, because refusing a
perfectly good stick is worse than not checking.

## Before you go to the car

**Audit the package first.** It is the cheapest check available and catches the failure that
is most expensive to find in the car — a record that disagrees with the file it describes,
which the unit treats as a bad flash:

```sh
python3 tools/verify_package.py --package out/SMEG_PLUS_UPG
```

It checks every `*.inf` sidecar against the file beside it, `smeg.inf` against the module
image, each `<MODULE>_ctrl.bin` against its module's files, and `ctrl.bin` against each module
manifest. Exit is non-zero if anything disagrees; `--json` is there for scripting.

It also **warns** (without failing) about a stock-shaped `*ctrl.bin` whose trailing CRC32 is
wrong, which packages built by older versions of the tools carry. Units have accepted them,
which suggests the trailer is not checked *(inferred)*, but rebuilding makes the manifests
match stock. `preflight.py` reports the same warning.

It looks for each CRC as a *value* in the manifest rather than parsing the record layout
(documented in [Boot & update chain](FLASH_CHAIN.md)), so it stays correct if a manifest's
layout ever differs.

### Keeping a rollback package

Keep an untouched copy of the original package before you flash anything, and audit it too —
**a rollback you have not checked is not a rollback**. Re-flash it the same way as any other
package; the original application content differs from the patched one, so it is rewritten.
Copying it to the stick with `tools/prepare_usb.py` verifies the copy on the way.

Confirm the patched image is present and the checksums agree, e.g. for a NAV unit:

```sh
python3 - <<'PY'
import zlib
print(hex(zlib.crc32(open('SMEG_PLUS_UPG_mod/NAV/AppBin/f_BigQuick.bin','rb').read())))
PY
cat SMEG_PLUS_UPG_mod/NAV/AppBin/f_BigQuick.bin.inf
grep BIGQUICK SMEG_PLUS_UPG_mod/NAV/smeg.inf
```

The `.inf` value and `smeg.inf`'s `BIGQUICK_CRC32` must both equal the CRC printed above.

## In the car

- **Parked**, ignition on, **engine running**. The update takes over 20 minutes and reboots
  the unit several times; never start one while driving, and the unit must not lose power.
- Insert the stick into the vehicle USB port and let the unit detect the update; follow
  the on-screen prompts.
- The updater is incremental: an already-current unit will report the boot ROM as done
  and skip the Renesas MCU, and will rewrite the application when its content differs.
- Do not remove the stick or cut power until it reboots.
- When the normal UI is back, **remove the stick**. While `SMEG_PLUS_UPG/UpgPlugin.out` is on a
  mounted stick, the unit offers the update again at every start (read; see
  [The update flow](UPGRADE_FLOW.md)).

## What you will see

The full run takes **over 20 minutes**, and the unit reboots several times on the way.
The screens alternate between the normal touchscreen UI and a blue bootloader screen with
yellow monospace text.

```
UPDATE LEVEL                 (touchscreen)  media detected
  Identification of media...
  Checking compatibility...
Software update.             (touchscreen)  same version number in both lines is normal
  From version:      CD 26482
  To version number: CD 26482
  Keep the engine running.
  The system will restart.
  Continue?  Yes / No
        |
        v
PEUGEOT                      (splash)       reboot
        |
        v
Renesas Upd...               (bootloader)   front-panel MCU
AppBin Upgrade...            (bootloader)   <-- the application image is written here
AppBin flashing
        |
        v
Phase 0   formatting /SYSTEM                  (bootloader)
Phase 0   defragmenting /USER-DATA/BACKUP
Phase 3   Uncompress /SYSTEM
Phase 3   Check the result of uncompression of /SYSTEM/
          Check progression : 6%
Phase 5   Uncompress /SD_DIR  ->  /SD_DIR_TTS
Phase 6   Management of UserGuide
Phase 6   Management of ZA files
          "The product must reboot in 2 s"   <-- the updater reboots itself here
        |
        v
PEUGEOT  ->  normal UI        (splash)       done
```

The `Phase 0 / 3 / 5` numbering and the `Uncompress` lines are the updater working
through the media partition; the free-space figures on those screens change as partitions
are rewritten. Reboots are expected after the BootROM, U-Boot, Renesas and application
steps — see [Boot and update chain](FLASH_CHAIN.md).

The bootloader screens carry a header identifying the media being flashed. Check it
matches your package — `Upgrade version` comes from `SUBVER` in `upgrade.out.inf` and
`Media version` from `VER` in `media.inf`:

```
Media version :        26482
Upgrade version :      5.3.3
BootRom version :      BSP-215.6.PLUSINT May 26 2017, 13:23:13
UBoot version :        06.03 Apr 22 2013 - 15:57:07
Hardware ID :          155
Hardware diversity :   NAV
Renesas version :      05.e3.01
```

!!! danger "If you see the protected-file error"

    *"The update file is protected and cannot be copied."* (string 2099) means the media
    does not match the signed contract — the re-seal step was skipped, or was run against
    the wrong directory. The unit will refuse the update. Rebuild and re-seal; nothing is
    written.

## Verify

The version strings do **not** change when re-flashing the same release, so verify by
behaviour. System Information will still read the same `SMEG5.43.A.R2` / `CD 26482` after
a successful patched flash — see [Version strings](VERSION_STRINGS.md).

What to check depends on the build. After each, capture (step 5 of
[the test loop](#the-test-loop-end-to-end)):

- **`aux-autoswitch` / `aux-always-available`:** the **AUX tile stays selectable with nothing
  plugged in** (on stock it greys out), and **SRC steps through to AUX**. The unit does not
  switch to AUX by itself: the handler follows the AUX *setting*, not the signal.
- **Boot to AUX (`builds/aux-boot.json`):** the unit **starts on AUX** at every boot, whatever
  source was playing before. A capture shows AUX's request with PrOnly false and AUX
  acknowledged at once.
- **Ring tone names (`media.names`):** the phone's ringtone menu lists the new name.
- **`aux-signal-switch` (candidate, emulated only):** on FM, start playback into AUX — does it
  switch? See [The AUX signal path](AUX_SIGNAL.md).

## The test loop, end to end

1. **Build.** `uv run tools/build_package.py --manifest builds/<scheme>.json` — it patches,
   rebuilds the media partition and the checksum cascade, re-seals, and runs preflight.
2. **Stick.** `uv run tools/prepare_usb.py --package <out>/SMEG_PLUS_UPG --target /Volumes/<stick> --eject`.
3. **Car.** Parked, engine running; accept the update; do not remove the stick until the normal
   UI is back. Then remove it — it re-offers the update while present.
4. **Observe** the behaviour under test, over at least two restarts.
5. **Capture.** Dial `SPYTAKE`: the unit collects every trace buffer, then reboots. Then, with a
   stick in, dial `SPYSTORE`, which copies `SPY/<stamp>/` to it. If the package is still on
   that stick, decline the update offer.
6. **Read.** `tools/spy_read.py` reads the archive in memory and redacts the VIN, device
    addresses and long numbers by default:

    ```sh
    uv run tools/spy_read.py /Volumes/<stick>/SPY/<stamp>          # how the boot source was chosen
    uv run tools/spy_read.py /Volumes/<stick>/SPY/<stamp> --aux    # AUX lines from 25300, 06301, 15400
    uv run tools/spy_read.py /Volumes/<stick>/SPY/<stamp> --list   # every buffer
    uv run tools/spy_read.py /Volumes/<stick>/SPY/<stamp> --show 25300
    ```

    The boot report lists each source request with its PrOnly flag, the ScheduledInit table,
    and which source was acknowledged first. When that is the tuner about 7500 ms after
    `Last_Source`, it calls it the init timer's fallback, which is inferred from the timing.
    Redaction is best-effort: it catches VIN-shaped tokens, VIN byte runs, device addresses
    and phone-length numbers, but not a phone's *name*.

    By hand:

    ```sh
    mkdir cap && tar -xzf /Volumes/<stick>/SPY/<stamp>/TAR/*-USER.tar.gz -C cap
    less cap/RAMDISK_SPY/25300/*.bin   # C_MGR_SRC: requests, Last_Source, the restore table
    less cap/RAMDISK_SPY/06301/*.bin   # the media app: AUX activation, PrOnly
    less cap/RAMDISK_SPY/15400/*.bin   # the audio module (the id is inferred)
    ```

    The buffers are plain text, one `<ms since boot>::<event>` per line. `traces.bin` beside
    the archive is only the VxWorks exception log. If no restore matched at boot, FM wins on
    the 7.5 s init timer: in `25300` that shows as a tuner acknowledgement about 7500 ms after
    `Last_Source` is read. See [The AUX chain](AUX_CHAIN.md#how-the-boot-source-is-actually-chosen).

!!! danger "A capture is personal data"

    A spy capture and a settings dump hold the car's **VIN**, paired phones and other personal
    settings. Keep them on your own machine: never commit one, and never attach one to a
    public issue.

## Rollback

Flash the untouched original package the same way as any other (see
[Keeping a rollback package](#keeping-a-rollback-package)). If something has already gone wrong, see [Recovery](RECOVERY.md) — including what is *not*
documented, which is worth reading before you need it.

For a plain rollback, flash the **untouched original** package. `--stock` is a canary for the
packaging path, not a substitute for the original:

```sh
uv run tools/patch_smeg.py     --src ORIGINAL_PKG --out out/SMEG_PLUS_UPG --copy-package --stock
uv run tools/patch_contract.py --package out/SMEG_PLUS_UPG
```

`--stock` applies **no patches** but does everything else — re-packs, rebuilds the checksum
cascade and verifies it end to end — and `patch_contract.py` then re-seals it, which a
re-compressed image needs (its size changes). If a re-sealed stock package is refused by the
unit, the fault is in the packaging or sealing rather than in any patch. *(These two commands
were run on the stock NAV package: the contract re-sealed and decrypted cleanly, and preflight
reported no problems.)*
