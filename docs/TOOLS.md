# Tools

Every tool in `tools/`, generated from its own docstring and `--help` by
`tools/tool_reference.py`. Run any of them with `uv run tools/<name>.py`; none needs
setting up (see [Running the tools](RUNNING.md)).

!!! note "Generated page"

    Edit the tool's docstring or arguments, then run `python3 tools/tool_reference.py`.
    A test fails when a tool is missing from this page or its summary has changed.

## Build and flash

| tool | what it does |
|---|---|
| [`build_package.py`](#build-package) | Build a patched SMEG+ package from a manifest, in one command. |
| [`patch_smeg.py`](#patch-smeg) | Apply a SMEG+ patch set to an upgrade package and rebuild its checksum cascade. |
| [`patch_media.py`](#patch-media) | Patch files inside a SMEG+ media partition (`<module>/system.bin`). |
| [`patch_contract.py`](#patch-contract) | Re-encrypt `contract.dat` so the unit will accept a modified package. |
| [`preflight.py`](#preflight) | Pre-flight a SMEG+ package: say what it will do before it goes on a stick. |
| [`verify_package.py`](#verify-package) | Audit a package's checksum cascade before it goes near a car. |
| [`prepare_usb.py`](#prepare-usb) | Put a built package onto a USB stick, and prove it landed. |
| [`fix_userdata_case.py`](#fix-userdata-case) | Rewrite one FAT directory entry so the SMEG+ updater reads 'sqlite', not 'SQLITE'. |
| [`patch_status.py`](#patch-status) | Write each patch set's hardware status into the docs, from `patches/*.json` alone. |

### build-package

`tools/build_package.py`: Build a patched SMEG+ package from a manifest, in one command.

```text
usage: build_package.py [-h] --manifest MANIFEST [--skip-preflight] [--dry-run]

Build a patched SMEG+ package from a manifest, in one command.

Applying a patch by hand means running three or four tools in a specific order with an
`rsync` between each one, and two of those orderings are silent if you get them wrong:

  * the media step must run against the **already application-patched** package, or it
    rebuilds `ctrl.bin` without the application change and quietly drops it;
  * the contract must be re-sealed **last**, or the package is left unsealed and the unit
    refuses it (string 2099).

This tool owns that ordering so a build is a file you can read and re-run, not a sequence
you have to remember. It shells out to the individual tools rather than reimplementing
them, so they stay usable on their own.

Manifest (JSON — no extra dependency):

    {
      "package": "SMEG_PLUS_UPG",
      "out": "SMEG_PLUS_UPG_custom",
      "module": "NAV",
      "app":   { "patches": ["aux-autoswitch"] },
      "media": {
        "tones":  { "ring_tones/ring1RT.wav": "piano-riff.mp3" },
        "splash": { "peugeot": "snoopy.png" },
        "names":  { "ring2": "Piano Riff" },
        "gui_ver": "32.01"
      },
      "seal": true
    }

Every section is optional. `app.patches` names files in `patches/`; `media.tones` maps a
partition-relative destination to a source audio file of any format ffmpeg reads;
`media.splash` maps a marque to an image; `media.names` renames ring1..ring5 in the phone's
ringtone menu. Those names are literals in the application image (#190), so this becomes an
application patch - NAV 5.43.A.R2 only, and each name has a fixed maximum length;
`media.gui_ver` sets `GUI_VER` in the partition's `Data_base/smeg.inf`, which System
Information shows on its GUI item's page (read, #191); the updater does not gate on it.

usage:
    python3 tools/build_package.py --manifest build.json
    python3 tools/build_package.py --manifest build.json --dry-run

options:
  -h, --help           show this help message and exit
  --manifest MANIFEST
  --skip-preflight     do not run the final pre-flight check (not recommended)
  --dry-run            show the steps and what would change, without writing
```

### patch-smeg

`tools/patch_smeg.py`: Apply a SMEG+ patch set to an upgrade package and rebuild its checksum cascade.

```text
usage: patch_smeg.py [-h] --src SRC --out OUT [--patches PATCHES] [--only [ONLY ...]]
                     [--copy-package] [--level LEVEL] [--stock]

Apply a SMEG+ patch set to an upgrade package and rebuild its checksum cascade.

The application for each variant is AppBin/f_BigQuick.bin: a 0x801-byte header
plus a zlib stream holding the PowerPC image loaded at 0x01000000. This tool:

  1. inflates the image,
  2. checks the original bytes at each patch address ("expect") and applies the
     replacement ("bytes"),
  3. re-deflates the image back into the container,
  4. rebuilds the checksum cascade:

        f_BigQuick.bin --crc32--> f_BigQuick.bin.inf
                       --crc32--> smeg.inf  (BIGQUICK_CRC32)
                       --crc32--> <module>_ctrl.bin
        <module>_ctrl.bin --crc32--> ctrl.bin (root manifest)

Only the changed files are written to --out (mirroring their package-relative
paths). Use tools/apply_files.sh to overlay them onto a copy of your package, or
pass --copy-package to have this tool copy the whole package into --out first.

No vendor firmware is bundled with this tool; point --src at your own legally
obtained package.

usage:
    python3 tools/patch_smeg.py --src SMEG_PLUS_UPG --out SMEG_PLUS_UPG_mod
    python3 tools/patch_smeg.py --src SMEG_PLUS_UPG --out out --only NAV

options:
  -h, --help         show this help message and exit
  --src SRC          original package directory
  --out OUT          output directory for changed files
  --patches PATCHES  patch definition JSON
  --only [ONLY ...]  variant name(s) to patch
  --copy-package     copy the whole package into --out before overlaying changes
  --level LEVEL      zlib level for re-packing (default 6)
  --stock            apply no patches, but rebuild and verify the checksum cascade
```

### patch-media

`tools/patch_media.py`: Patch files inside a SMEG+ media partition (`<module>/system.bin`).

```text
usage: patch_media.py [-h] {list,extract,restore,apply} ...

Patch files inside a SMEG+ media partition (`<module>/system.bin`).

`system.bin` is a gzip'd tar that the unit extracts to `/SYSTEM/`. Editing anything in
it means rebuilding the tar, re-gzipping, and repairing the whole checksum chain:

    changed file
      -> system_ctrl.bin    (fixed 264-byte records: [path][pad][type][crc32])
      -> system.bin         (tar + gzip)
      -> system.bin.inf     (CRC32 + the SIZE / SIZE_n fields)
      -> <module>_ctrl.bin  (4-byte big-endian CRC32 per packaged file)
      -> ctrl.bin           (root manifest)

The `SIZE` fields are the uncompressed *contents* size, not the tar or gzip size:

    SIZE   = sum of the file sizes inside the tar (headers and padding excluded)
    SIZE_n = the same, with each file rounded up to an n KiB block

They are read by `UpgPlugin.out` (not `upgrade.out`) for the media space check.

Only **replacing** existing files is supported. Adding one would need a new
`system_ctrl.bin` record; that record format is now fully mapped (see
docs/MEDIA_PARTITION.md) and so is mechanically expressible, but whether the updater
accepts a record count it has never seen is untested — so this tool still refuses.

usage:
    # see what is in the partition
    python3 tools/patch_media.py list --package SMEG_PLUS_UPG --module NAV

    # extract it (and keep a copy of the originals so you can restore them)
    python3 tools/patch_media.py extract --package SMEG_PLUS_UPG --module NAV \
        --tree media --backup backups

    # put an original file back
    python3 tools/patch_media.py restore --backup backups --tree media --only ring_tones/ring1RT.wav

    # rebuild the package with everything that differs in the tree
    python3 tools/patch_media.py apply --package SMEG_PLUS_UPG --module NAV \
        --tree media --out SMEG_PLUS_UPG_mod

positional arguments:
  {list,extract,restore,apply}
    list                list the files in the partition
    extract             extract the partition (and optionally back up the originals)
    restore             put original files back into a tree
    apply               rebuild the package from a tree

options:
  -h, --help            show this help message and exit
```

### patch-contract

`tools/patch_contract.py`: Re-encrypt `contract.dat` so the unit will accept a modified package.

```text
usage: patch_contract.py [-h] --package PACKAGE [--module MODULE] [--out OUT] [--show]

Re-encrypt `contract.dat` so the unit will accept a modified package.

## Background

The head unit validates the update media before copying anything. Losing that check
produces *"The update file is protected and cannot be copied."* (string 2099), which is
what happens if you patch `AppBin/f_BigQuick.bin` and flash the result.

`contract.dat` is a table of per-file checks, encrypted in 256-byte RSA blocks.
`C_BCM_UPGRADE::CheckTrustedSource()` decrypts it on the unit and compares:

| CheckType | field @64 | field @68 | field @72 |
|---|---|---|---|
| 1 | `0xfffefffe` | `0xfffefffe` | file **size** (u32 BE) |
| 2 | `0xfffefffe` | `0xfffefffe` | file **crc32** (u32 BE) |
| 3 | **length** | **offset** | **raw bytes** read from the file |

Each record is 212 bytes: a NUL-padded path in `[0..62]`, the CheckType in `[63]`, then
those fields. Block 0 is a 152-byte header (`19/09/2017`, manifest version, magic
`deadbeef`/`badef00d`).

The unit *decrypts* with a private key, so the file was *encrypted with the public key*.
RSA public encryption is something anyone with the public key can do — and the key pair
is embedded in the firmware image itself. So a modified package can be re-sealed by
recomputing the checks from the files on disk and re-encrypting.

## Key handling

This tool does **not** ship any key material. It extracts the key pair from the
`f_BigQuick.bin` of the package you point it at — i.e. from the firmware you already own —
and uses it for that package only. The plaintext contract and the key are never written
anywhere.

## Usage

    # after patch_smeg.py / patch_media.py have written the changed files into --out
    python3 tools/patch_contract.py --package SMEG_PLUS_UPG_mod --out SMEG_PLUS_UPG_mod

If the package root is also the output (changes applied in place on a *copy* of the
package), one path is enough. The regenerated `contract.dat` is written to `--out`.

    python3 tools/patch_contract.py --package SMEG_PLUS_UPG_mod --show

prints what it would change without writing.

options:
  -h, --help         show this help message and exit
  --package PACKAGE  package directory holding contract.dat and the module images
  --module MODULE    module whose app image carries the key material (default NAV)
  --out OUT          where to write the new contract.dat (default: --package)
  --show             report changes without writing
```

### preflight

`tools/preflight.py`: Pre-flight a SMEG+ package: say what it will do before it goes on a stick.

```text
usage: preflight.py [-h] --package PACKAGE [--module MODULE] [--stock STOCK] [--json]

Pre-flight a SMEG+ package: say what it will do before it goes on a stick.

Every car trip this project has spent was to discover something that was knowable offline.
The three most recent were:

  * `supervisor.Last_Source = 4` — not a valid source, so the unit ignored it and fell back
    to FM. The enum is known; nothing checked the value against it.
  * settings edited in `system.bin` appeared to do nothing, because the unit reads them from
    a separate `/USER_DATA` partition. Nothing said where a change would actually land.
  * a package rejected with string 2099 — the contract. Nothing checked the seal.

This runs those checks, plus the ones that are merely tedious, and reports what it does
**not** know as prominently as what it does. The unknowns are where the car trips went.

usage:
    python3 tools/preflight.py --package SMEG_PLUS_UPG_mod
    python3 tools/preflight.py --package SMEG_PLUS_UPG_mod --stock SMEG_PLUS_UPG
    python3 tools/preflight.py --package SMEG_PLUS_UPG_mod --json

options:
  -h, --help         show this help message and exit
  --package PACKAGE
  --module MODULE
  --stock STOCK      a stock package to compare against (optional)
  --json
```

### verify-package

`tools/verify_package.py`: Audit a package's checksum cascade before it goes near a car.

```text
usage: verify_package.py [-h] --package PACKAGE [--json]

Audit a package's checksum cascade before it goes near a car.

A package is refused by the unit if any of its recorded CRC32s disagree with the files they
describe, and the failure it produces in the car looks like a firmware fault rather than a
packaging one. This reads every record the package carries and checks it against the bytes.

**It never assumes the record layout.** The `*_ctrl.bin` layout is now known
(docs/FLASH_CHAIN.md), but a check that does not depend on it stays correct if a manifest ever
differs. So rather than parse them, this looks for the CRC *as a value*: each manifest must contain, as a raw big-endian
word, the CRC32 of every file it is responsible for. That is layout-free and still catches
the failure that matters, which is a manifest that does not describe what shipped.

What it checks:

  * every `*.inf` sidecar's `CRC32:` field against the file beside it,
  * `smeg.inf`'s `BIGQUICK_CRC32:` against the module's `AppBin/f_BigQuick.bin`,
  * each `<MODULE>_ctrl.bin` against the three files of that module,
  * `ctrl.bin` against each `<MODULE>_ctrl.bin`.

usage:
    python3 tools/verify_package.py --package out/SMEG_PLUS_UPG
    python3 tools/verify_package.py --package out/SMEG_PLUS_UPG --json

options:
  -h, --help         show this help message and exit
  --package PACKAGE  the package directory to audit
  --json             machine-readable output
```

### prepare-usb

`tools/prepare_usb.py`: Put a built package onto a USB stick, and prove it landed.

```text
usage: prepare_usb.py [-h] --package PACKAGE --target TARGET [--dry-run] [--force] [--keep-index]
                      [--eject]

Put a built package onto a USB stick, and prove it landed.

Getting the package onto the stick is the last manual step, and it has already gone wrong
twice: a stick was pulled mid-copy, and `ditto` left AppleDouble `._*` files beside the
package. A silently truncated copy produces an update failure in the car that looks like a
firmware fault, which is an expensive way to find out. This makes both failures loud:

  1. probe the target — the updater wants **MBR + FAT32**, and says how to fix it otherwise
  2. check free space against the package
  3. copy, excluding AppleDouble and `.DS_Store`, using a data-only copy, then delete the
     `._*` shadows macOS still writes for each new file on FAT
  4. **re-read every file from the stick and compare checksums** against the source, which
     is what catches the mid-copy removal
  5. confirm the layout the updater looks for, and count any `._*` left behind as a failure
  6. on macOS: stop Spotlight indexing the stick (`.metadata_never_index`, `mdutil -i off`)
     and remove the `.Spotlight-V100` / `.fseventsd` folders it leaves at the root; indexing
     also held the volume busy so `diskutil eject` failed until retried (`--keep-index` skips)
  7. with `--eject`, eject the stick, retrying while the volume is still busy

It only ever writes inside `--target`, and it prints the target before touching anything.

usage:
    python3 tools/prepare_usb.py --package out/SMEG_PLUS_UPG --target /Volumes/USB
    python3 tools/prepare_usb.py --package out/SMEG_PLUS_UPG --target /Volumes/USB --dry-run
    python3 tools/prepare_usb.py --package out/SMEG_PLUS_UPG --target /Volumes/USB --eject

options:
  -h, --help         show this help message and exit
  --package PACKAGE  the built package directory
  --target TARGET    the mounted USB stick
  --dry-run          check everything, copy nothing
  --force            continue past filesystem warnings
  --keep-index       macOS: leave Spotlight indexing and its folders on the stick alone
  --eject            macOS: eject the stick when done
```

### fix-userdata-case

`tools/fix_userdata_case.py`: Rewrite one FAT directory entry so the SMEG+ updater reads 'sqlite', not 'SQLITE'.

```text
Rewrite one FAT directory entry so the SMEG+ updater reads 'sqlite', not 'SQLITE'.

Why this exists
---------------
A package can carry a USER_DATA payload at
``SMEG_PLUS_UPG/NAV/USER_DATA/user_data/sqlite/up_common.sqlite``. The updater
copies it with ``xcopy_blk("/bd0/SMEG_PLUS_UPG/NAV/USER_DATA", "/USER_DATA")``,
naming each destination directory after what it reads off the stick.

The application reads its live settings from **lowercase** ``/USER_DATA/user_data/sqlite/``.
But ``sqlite`` is a valid 8.3 name, so macOS stores it as the short name ``SQLITE``
with the NT "lowercase base" bit set and **no long-filename entry**. The updater
honours long filenames but not that bit, so it creates an uppercase ``SQLITE``
sibling that the application never opens. Observed on hardware; see
docs/VERIFICATION.md and docs/FLASHING.md.

The fix is to give that one directory a long-filename entry reading ``sqlite``.

Usage
-----
Check a volume or image without writing::

    python3 tools/fix_userdata_case.py --check /dev/diskNsM

To create the required LFN on macOS, first rename ``sqlite`` to a name that needs
one, such as ``sqlite_dat``. Unmount the volume, inspect the planned edit, apply
it through the raw device, then remount and check::

    diskutil unmount /Volumes/<vol>
    sudo python3 tools/fix_userdata_case.py --dry-run /dev/rdiskNsM
    sudo python3 tools/fix_userdata_case.py /dev/rdiskNsM
    diskutil mount /dev/diskNsM
    python3 tools/fix_userdata_case.py --check /dev/diskNsM

It edits one 32-byte entry, read-modify-written inside its 512-byte sector.
Nothing is moved, no cluster is allocated, and the entry checksum is unaffected
because the short name does not change. --dry-run reports and writes nothing.
```

### patch-status

`tools/patch_status.py`: Write each patch set's hardware status into the docs, from `patches/*.json` alone.

```text
usage: patch_status.py [-h] [--check]

Write each patch set's hardware status into the docs, from `patches/*.json` alone.

Status used to be restated by hand in several pages, and they drifted apart (fixed twice in
review). Now each `patches/<name>.json` carries it:

    "summary": "what it changes, one line of Markdown",
    "status": {"state": "never-flashed", "label": "Never flashed", "note": "..."}

`state` is one of STATES below and picks the pill colour; `label` and `note` are free text.
This regenerates the marked blocks in the docs:

    <!-- patch-status:table -->   ...   <!-- /patch-status:table -->    docs/PATCHES.md
    <!-- patch-status:panel -->   ...   <!-- /patch-status:panel -->    docs/index.md

usage:
    python3 tools/patch_status.py            # rewrite the blocks
    python3 tools/patch_status.py --check    # exit 1 if any block is stale (the test runs this)

options:
  -h, --help  show this help message and exit
  --check     fail if a block is out of date
```

## Media: tones, logos, settings

| tool | what it does |
|---|---|
| [`ringtones.py`](#ringtones) | Ring tone / wait tone tool for SMEG+ — inspect, convert and stage custom audio. |
| [`assets.py`](#assets) | The customisable assets in a SMEG+ media partition, with human-readable names. |
| [`splash.py`](#splash) | Brand logo images for SMEG+ — inspect and replace the `Data_base/graphics/logo/*.pkg` bundles. |
| [`guistrings.py`](#guistrings) | Decode and rebuild the GUI string tables (`gui_text_strings_<LANG>.xml.bin`). |
| [`patch_studio.py`](#patch-studio) | Ringtone Studio — a Qt front-end for SMEG+ ring tones and firmware patches. |
| [`dbschema.py`](#dbschema) | Dump the schema of the SQLite databases a SMEG+ unit keeps its state in. |

### ringtones

`tools/ringtones.py`: Ring tone / wait tone tool for SMEG+ — inspect, convert and stage custom audio.

```text
usage: ringtones.py [-h] {list,probe,export,convert,stage,names,rename} ...

Ring tone / wait tone tool for SMEG+ — inspect, convert and stage custom audio.

The unit plays plain PCM WAV:

    ring_tones/ring1RT.wav .. ring5RT.wav     16-bit mono   44100 Hz
    ring_tones/{busy,error,ok,ko}RT.wav       16-bit mono   44100 Hz
    wait_tones/MM_HoldOn_<LANG>_8kHz.wav      16-bit stereo  8000 Hz

`convert` produces a file in exactly the right format from anything ffmpeg can read
(mp3, ogg, flac, m4a, ...). If ffmpeg is not installed, WAV input that is already in
the target format is accepted and copied; anything else is refused with a clear
message. `stage` writes the converted file into an extracted media-partition tree
under the correct name, ready for repacking.

Note: the WAVs live inside the media partition (`system.bin`). Repacking that tar is
tracked separately and is not done here — `stage` prepares the tree.

usage:
    python3 tools/ringtones.py list
    python3 tools/ringtones.py export --tree media/ -o out/
    python3 tools/ringtones.py convert song.mp3 --slot ring1 -o ring1RT.wav
    python3 tools/ringtones.py stage song.ogg --slot ring5 --tree media/
    python3 tools/ringtones.py probe some.wav

positional arguments:
  {list,probe,export,convert,stage,names,rename}
    list                show the slots and the format each expects
    probe               describe an audio file
    export              copy the stock WAVs out of an extracted media tree
    convert             convert a file to a slot's format
    stage               convert and place a file into an extracted media tree
    names               list the ringtone names the phone UI shows
    rename              change one of those names

options:
  -h, --help            show this help message and exit
```

### assets

`tools/assets.py`: The customisable assets in a SMEG+ media partition, with human-readable names.

```text
usage: assets.py [-h] [--tree TREE] {list,export,replace} ...

The customisable assets in a SMEG+ media partition, with human-readable names.

The partition holds 845 files across directories that give no clue what is what —
`ring1RT.wav`, `MM_HoldOn_GED_8kHz.wav`, `AT_O3.png`, `GillSansPSA.ttf`. This knows
what each one is for, and turns the filename into a label a person can act on, so
"replace a ring tone" or "replace the radio logos" is a choice rather than a hunt.

It only ever *replaces* files that already exist: the partition's `system_ctrl.bin`
records are per-file, so adding a new one would need a record that does not exist.

usage:
    python3 tools/assets.py --tree media list
    python3 tools/assets.py --tree media list --group sounds
    python3 tools/assets.py --tree media export --group logos -o stock-logos/
    python3 tools/assets.py --tree media replace --asset radio-logos --with my-logos/
    python3 tools/assets.py --tree media replace --asset ring1 --with piano.mp3

positional arguments:
  {list,export,replace}
    list                everything replaceable, with readable names
    export              copy the current assets out, as a backup or a template
    replace             swap assets in for the current ones

options:
  -h, --help            show this help message and exit
  --tree TREE           an extracted media partition (contains ring_tones/)
```

### splash

`tools/splash.py`: Brand logo images for SMEG+ — inspect and replace the `Data_base/graphics/logo/*.pkg` bundles.

```text
usage: splash.py [-h] [--tree TREE] {list,extract,replace,selftest} ...

Brand logo images for SMEG+ — inspect and replace the `Data_base/graphics/logo/*.pkg` bundles.

Despite the name these are NOT the boot splash. Flashing a replaced one leaves the factory
animation untouched: nothing in the application image references these files, and the boot
artwork lives in a separate NAND "Logo Area" that the USB update flow has no step for. See
docs/MEDIA_PARTITION.md. These images are real marque artwork used elsewhere; that use is
still unidentified, so treat their effect on the unit as unknown.

`Data_base/graphics/logo/` holds one `.pkg` per marque (`peugeot`, `citroen`, `ds`). Each is a
small container holding four 800x480 24-bit images. The first is the Peugeot lion and
wordmark artwork; it is not what the unit shows while starting (see above).

Container layout (verified against the shipped packages):

    0x0000  u32   crc32 of bytes 0x0004..0x0800        (directory integrity)
    0x0004  u32   size of the first chunk, as the offset of the next chunk from 0x0800
    0x0008  u32   uncompressed size of every chunk (800*480*3 + 54 = 1152054)
    0x000c  u32   0
    0x0010  ...   directory records, zero-padded to 0x0800
    ...

Each directory record is a 32-byte NUL-padded name followed by 6 or 7 big-endian u32s; the
last two carry the offset of the *next* chunk's marker byte and that chunk's length + 3.

The data region runs from 0x0800. Every chunk is:

    u8  0x08 marker
    ... a standard zlib stream (deflate level 6) holding one 800x480 24-bit BMP
    u16 an unidentified two-byte trailer, preserved verbatim

The BMPs are ordinary bottom-up 24-bit BMPs, but they are stored **vertically mirrored**:
read with normal BMP semantics the artwork is upside down. That matches the car, where the
splash displays correctly, so the unit flips it when rendering. To make a replacement
display the right way up it must therefore be stored flipped — `replace` does that for you.

Known unknown: the two-byte trailer after each zlib stream has not been identified (it is
not a crc32 or adler32 fragment of the chunk). It is preserved as-is, and a rebuilt package
has not yet been flashed, so treat a replaced splash as unverified until a unit accepts it.

usage:
    python3 tools/splash.py list --tree media/
    python3 tools/splash.py extract --tree media/ -o splash/ --marque peugeot
    python3 tools/splash.py replace --tree media/ --marque peugeot --image mine.png
    python3 tools/splash.py selftest --tree media/

positional arguments:
  {list,extract,replace,selftest}
    list                show the images in each marque's package
    extract             write the images out as BMP
    replace             replace an image and rebuild the package
    selftest            rebuild from the stock images and compare

options:
  -h, --help            show this help message and exit
  --tree TREE           an extracted media partition (contains Data_base/graphics/logo/)
```

### guistrings

`tools/guistrings.py`: Decode and rebuild the GUI string tables (`gui_text_strings_<LANG>.xml.bin`).

```text
usage: guistrings.py [-h] {info,dump,probe,build,patch,diff} ...

Decode and rebuild the GUI string tables (`gui_text_strings_<LANG>.xml.bin`).

The unit shows its user-visible wording from one binary file per language, in the media
partition at `Data_base/boardfs/GUI_STYLE/GUIS_RESSOURCES/gui_texts/`. Despite the name they
are **not XML**:

    0x00  u32  total file size
    0x04  u32  record count
    0x08  u32  offset of the first string (always 0x10 + 12 * count)
    0x0c  u32  zero
    0x10  n * 12-byte records:  u32 id, u32 offset (absolute), u32 length (bytes)
    ...   the string blob: UTF-16BE code units, concatenated, no terminator, no BOM

The directory is sorted by id, the offsets are contiguous, and the blob ends exactly at EOF —
so there is **no internal checksum**; the file's CRC32 lives in `system_ctrl.bin` with the
rest of the partition cascade. A decode followed by a rebuild reproduces the input
byte-for-byte; `probe` checks that on the file you hand it. See docs/GUI_STRINGS.md.

The reader is `C_GUI_StringsManager::LoadStringsFileBinary` and the vendor's own writer is
`C_GUI_StringsManager::buildBinaryStringsFile`, both in the application image; the layout
above is what the disassembly of the two agrees on.

usage:
    # the id -> string table, and what the header says
    python3 tools/guistrings.py dump  media/Data_base/.../gui_texts/gui_text_strings_GB.xml.bin
    python3 tools/guistrings.py info  media/.../gui_text_strings_GB.xml.bin

    # what the format allows, and proof that a rebuild is byte-identical
    python3 tools/guistrings.py probe media/.../gui_text_strings_GB.xml.bin
    python3 tools/guistrings.py probe media/.../gui_texts --lang GB

    # edit a label: dump to JSON, change the value, rebuild (the JSON is the overrides file)
    python3 tools/guistrings.py dump  GB.xml.bin --json > edits.json
    python3 tools/guistrings.py build --base GB.xml.bin --out GB_new.xml.bin --overrides edits.json

    # or in place, keeping every slot the same length so no offset moves
    python3 tools/guistrings.py patch GB.xml.bin --in-place --set 4=CarPlay --pad

    # compare two languages
    python3 tools/guistrings.py diff GB.xml.bin FR.xml.bin

positional arguments:
  {info,dump,probe,build,patch,diff}
    info                the header fields and a structural check
    dump                print the id -> string table
    probe               show the format's own limits and prove the round trip
    build               rebuild a file from a base plus edits (no edits = a byte-for-byte copy)
    patch               apply edits to a file (build with the base filled in)
    diff                compare two string tables

options:
  -h, --help            show this help message and exit
```

### patch-studio

`tools/patch_studio.py`: Ringtone Studio — a Qt front-end for SMEG+ ring tones and firmware patches.

```text
Ringtone Studio — a Qt front-end for SMEG+ ring tones and firmware patches.

**Ringtones tab.** Shows every replaceable tone in the media partition, with its
current state. Per row you can preview it, overwrite it with any audio file
(mp3/ogg/flac/m4a/wav — anything ffmpeg reads), or restore the original that came in the
package. "Extract from package…" pulls the partition out of a package and stores the
originals as a backup, so restore always has something to go back to.

Previewing uses QtMultimedia (QSoundEffect) when available, and otherwise falls back to a
system player (`afplay` on macOS, `paplay`/`aplay` on Linux).

**Pack & patch tab.** Tick the `patches/*.json` definitions you want, point it at a
package and a media tree, and it writes a patched package: the application patches first,
then the media partition rebuild (tar, gzip, `system_ctrl.bin`, `system.bin.inf`, the
module manifest and the root manifest).

usage:
    .venv/bin/python tools/patch_studio.py          # PySide6 + ffmpeg already present
    uv run tools/patch_studio.py                    # fetches PySide6
    python3 tools/patch_studio.py --help            # this text; needs no PySide6
```

### dbschema

`tools/dbschema.py`: Dump the schema of the SQLite databases a SMEG+ unit keeps its state in.

```text
usage: dbschema.py [-h] {schema,from-package} ...

Dump the schema of the SQLite databases a SMEG+ unit keeps its state in.

A unit keeps its settings in ~29 SQLite databases. The seeds ship read-only in the media
partition (`Data_base/sqlite/*.sqlite`, inside `<module>/system.bin`); the live copies are on
the `/USER_DATA` partition the car owns, one `.sqlite` with a `.inf` CRC sidecar. Editing a
seed changes nothing on the unit — see docs/DATABASES.md and docs/MEDIA_PARTITION.md.

This reads a database and prints what is *in* it structurally: tables, columns and their types,
NOT NULL / defaults, the primary key, indexes and foreign keys. It reads **your own** databases
or the ones in **your own** package; it ships no vendor data. The live `up_common`/`up_user`
stores are gzip'd on disk, which is handled transparently.

Because it only reads, it never writes to the file it is given: the bytes are copied to a
throwaway location first, so a live database on `USER_DATA` is not touched and no `-wal`/`-shm`
is created beside it.

usage:
    # a database, or several
    python3 tools/dbschema.py schema path/to/up_common.sqlite

    # every Data_base/sqlite/*.sqlite inside your own media partition, straight from the
    # gzipped tar (a system.bin file) or from an extracted package/module directory
    python3 tools/dbschema.py from-package SMEG_PLUS_UPG/NAV/system.bin
    python3 tools/dbschema.py from-package SMEG_PLUS_UPG/NAV
    python3 tools/dbschema.py from-package media/

    # machine-readable, and with the original CREATE statements
    python3 tools/dbschema.py schema up_common.sqlite --json
    python3 tools/dbschema.py schema up_common.sqlite --sql

positional arguments:
  {schema,from-package}
    schema              dump one or more .sqlite files
    from-package        dump every Data_base/sqlite/*.sqlite in your own media partition

options:
  -h, --help            show this help message and exit
```

## Diagnostics

| tool | what it does |
|---|---|
| [`spy_read.py`](#spy-read) | Read a SPY capture in one command: the boot timeline, the AUX events, any buffer. |

### spy-read

`tools/spy_read.py`: Read a SPY capture in one command: the boot timeline, the AUX events, any buffer.

```text
usage: spy_read.py [-h] [--list | --boot | --aux | --show ID] [--no-redact] source

Read a SPY capture in one command: the boot timeline, the AUX events, any buffer.

`SPYTAKE` collects every module's trace buffer into `SPY/<stamp>/TAR/<stamp>-USER.tar.gz`,
which `SPYSTORE` copies to the stick. Inside, `RAMDISK_SPY/<id>/<stamp>.bin` holds one module's
buffer, mostly text. Reading one by hand meant untarring and grepping; this reads the tar in
memory and never writes the capture anywhere.

SOURCE may be a `SPY/<stamp>` folder (the newest `TAR/*-USER.tar.gz` is used), a `-USER.tar.gz`
itself, or a folder that already contains `RAMDISK_SPY/`.

  --list        every buffer with its size and first line
  --boot        (default) how the boot source was chosen: C_MGR_SRC's trace, the saved
                Last_Source, each source request with its PrOnly flag, the ScheduledInit
                table, and which source won and when
  --aux         only the AUX-related lines from the source manager, media app and audio module
  --show ID     one buffer, e.g. 25300

**Captures hold personal data.** The settings and Bluetooth buffers carry the VIN, device
addresses and phone numbers. Output is redacted by default (`--no-redact` turns it off, for
your own eyes only). Never commit a capture or paste one into an issue.

usage:
    python3 tools/spy_read.py /Volumes/USB/SPY/01_202609280110
    python3 tools/spy_read.py 01_202609280108-USER.tar.gz --aux
    python3 tools/spy_read.py SPY/01_202609280110 --show 25300

positional arguments:
  source       SPY/<stamp> folder, a -USER.tar.gz, or an extracted tree

options:
  -h, --help   show this help message and exit
  --list       every buffer and its first line
  --boot       how the boot source was chosen
  --aux        AUX-related lines only
  --show ID    print one buffer
  --no-redact  show personal data (VIN, addresses)
```

## Firmware analysis

| tool | what it does |
|---|---|
| [`unpack.py`](#unpack) | Inflate a SMEG+ AppBin/f_BigQuick.bin to the raw PowerPC application image. |
| [`fingerprint.py`](#fingerprint) | Identify which SMEG+ build an application image is, and fail loudly when it is unclear. |
| [`survey.py`](#survey) | Inventory every function in a SMEG+ application image: where it sits, what reaches it. |
| [`ppcdis.py`](#ppcdis) | PowerPC (32-bit, big-endian) disassembler for SMEG+ application images. |
| [`ppcemu.py`](#ppcemu) | Execute individual firmware functions on an emulated PowerPC core. |
| [`xref.py`](#xref) | Find code that references a string, address or pointer inside a SMEG+ image. |
| [`callers.py`](#callers) | Find direct (bl) callers of one or more addresses in a SMEG+ PPC image. |
| [`mkelf.py`](#mkelf) | Wrap a raw SMEG+ application image plus its symbol map into a disassemblable ELF. |
| [`elfsyms.py`](#elfsyms) | Read the symbol tables the SMEG+ package ships in plain sight. |
| [`symdiff.py`](#symdiff) | Diff two firmware releases by symbol, so a patch set can be carried across. |
| [`crc_recover.py`](#crc-recover) | Recover CRC parameters from (message, checksum) samples. |
| [`cartography.py`](#cartography) | Read the cartography metadata: name pools, the `.inf` sidecars, `SCC` records, `CCT.DAT`. |
| [`tool_reference.py`](#tool-reference) | Generate docs/TOOLS.md: every tool, its purpose and its `--help`, from the tools themselves. |

### unpack

`tools/unpack.py`: Inflate a SMEG+ AppBin/f_BigQuick.bin to the raw PowerPC application image.

```text
usage: unpack.py [-h] input output

Inflate a SMEG+ AppBin/f_BigQuick.bin to the raw PowerPC application image.

f_BigQuick.bin is a 0x801-byte header followed by a zlib stream. The inflated
image is loaded at 0x01000000 and the release's Application/PKG/abs_symbols_base
map lines up with it, so addresses from the symbol map map 1:1 onto this file.

usage:
    python3 tools/unpack.py SMEG_PLUS_UPG/NAV/AppBin/f_BigQuick.bin app_nav.bin

positional arguments:
  input       f_BigQuick.bin
  output      raw application image to write

options:
  -h, --help  show this help message and exit
```

### fingerprint

`tools/fingerprint.py`: Identify which SMEG+ build an application image is, and fail loudly when it is unclear.

```text
usage: fingerprint.py [-h] [--src SRC] [--image IMAGE] [--patches [PATCHES ...]] [--json]

Identify which SMEG+ build an application image is, and fail loudly when it is unclear.

Patch addresses are per build. `patches/*.json` declares each variant's addresses, and
`patch_smeg.py` guards the *firmware version* by looking for the vendor's build token
(`5.43.A.R2`) inside the image. That leaves the *build* itself — `AUDIO_BT`,
`AUDIO_BT_256`, `NAV` — to be chosen by hand, which is the part that is easy to get
wrong: `AUDIO_BT` and `AUDIO_BT_256` share their patch addresses exactly.

This reads the image and answers that question from the bytes, rather than from what
the operator remembered:

  * inflate the application container,
  * evaluate every variant's recorded `expect` bytes at their addresses,
  * report a unique match, or refuse.

**It deliberately reports ambiguity instead of picking.** On the firmware in this
repository `AUDIO_BT` and `AUDIO_BT_256` carry identical addresses and identical
`expect` bytes, so the recorded probes genuinely cannot tell them apart. A tool that
quietly chose one would be worse than the manual step it replaced. The same applies
when nothing matches: the message names the build tokens actually present.

Both a package directory and a single image file are accepted. A raw inflated image
(the `0x02604450`-byte layout) is detected, since that is what an analysis pass has
lying around.

usage:
    python3 tools/fingerprint.py --src /path/to/SMEG_PLUS_UPG
    python3 tools/fingerprint.py --image app_nav.bin
    python3 tools/fingerprint.py --src PKG --json

options:
  -h, --help            show this help message and exit
  --src SRC             a SMEG+ upgrade package directory
  --image IMAGE         a single application image (container or inflated)
  --patches [PATCHES ...]
                        patch definition JSON files (default: all in patches/)
  --json                machine-readable output
```

### survey

`tools/survey.py`: Inventory every function in a SMEG+ application image: where it sits, what reaches it.

```text
usage: survey.py [-h] --out OUT [--base BASE] image symbols

Inventory every function in a SMEG+ application image: where it sits, what reaches it.

One pass over the whole image produces, for each code symbol in the map:

  * its family (subsystem, from the class-name prefix) and size in instructions,
  * direct callers (`bl`),
  * address-materialisation sites (`lis rX,hi` + `addi`/`ori rX,rX,lo`) that produce its
    address - how this firmware makes most of its calls, via `mtctr`/`bctrl`, and what
    `callers.py` cannot see,
  * pointers to it stored in data (vtables, callback tables), and
  * the strings it materialises the address of - usually trace or log text naming what the
    function does,
  * the vtable slots it occupies, and
  * the globals it reads and writes (`lis rX,hi` + a load or store at `lo(rX)`).

The output is local analysis, written under `--out` and never into this repository: it is
derived from the vendor's symbol map, which AGENTS.md keeps out of the tree.

  functions.tsv   one row per function
  families.tsv    one row per family: count, instructions, share of the image
  unreached.tsv   functions with no caller, reference or pointer found - dead code, or
                  reached some way this scan does not model (computed branch tables)
  vtables.tsv     one row per vtable slot: class, slot offset, function
  virtual_calls.tsv  call sites of the form `lwz vptr,0(obj); lwz rZ,off(vptr); mtctr rZ;
                  bctrl`, with the slot offset they call. The receiver's class is not inferred,
                  so a site is not attributed to one function
  globals.tsv     data symbols with the functions that read and write them

The reference counts are lower bounds. An address built with `addis`+`lwz`, or computed at
run time, is not counted. A function with no references found is not proved unreachable.

usage:
    python3 tools/survey.py NAV.img abs_symbols_base.txt.gz --out ~/smeg-survey
    python3 tools/survey.py NAV/AppBin/f_BigQuick.bin abs_symbols_base.txt --out ~/smeg-survey

positional arguments:
  image        f_BigQuick.bin or an already-inflated image
  symbols      abs_symbols_base.txt, or the .gz as SPYSTORE copies it

options:
  -h, --help   show this help message and exit
  --out OUT    directory for the TSV files
  --base BASE
```

### ppcdis

`tools/ppcdis.py`: PowerPC (32-bit, big-endian) disassembler for SMEG+ application images.

```text
usage: ppcdis.py [-h] [--base BASE] image symbols start end

PowerPC (32-bit, big-endian) disassembler for SMEG+ application images.

Resolves symbols from an absolute symbol map (e.g. Application/PKG/abs_symbols_base.txt)
and annotates indirect calls made through the `lis/addi -> mtctr -> bctrl` idiom that
the compiler emits, so `bctrl` shows the callee name.

usage:
    python3 tools/ppcdis.py IMAGE SYMFILE ADDRESS END
    python3 tools/ppcdis.py app_nav.bin abs_symbols_base.txt 0x0230331c 0x02303460

positional arguments:
  image
  symbols
  start
  end

options:
  -h, --help   show this help message and exit
  --base BASE
```

### ppcemu

`tools/ppcemu.py`: Execute individual firmware functions on an emulated PowerPC core.

```text
usage: ppcemu.py [-h] [--base BASE] --call CALL [--arg ARG] [--patches PATCHES] [--module MODULE]
                 [--stub-all] [--stub STUB] [--trace]
                 image

Execute individual firmware functions on an emulated PowerPC core.

positional arguments:
  image              raw image from tools/unpack.py

options:
  -h, --help         show this help message and exit
  --base BASE        load address (default 0x01000000)
  --call CALL        function address to call
  --arg ARG          register argument (repeatable)
  --patches PATCHES  a patches/*.json to apply first
  --module MODULE    which variant of --patches to apply
  --stub-all         stub every call instead of executing it
  --stub STUB        ADDR=VALUE — stub one callee's return value (repeatable)
  --trace            print the instructions executed
```

### xref

`tools/xref.py`: Find code that references a string, address or pointer inside a SMEG+ image.

```text
usage: xref.py [-h] [--base BASE] image symbols target

Find code that references a string, address or pointer inside a SMEG+ image.

Two things are searched for:

  * literal 4-byte big-endian pointers to the target (data/vtable references), and
  * instruction sequences that materialise the target immediate - the
    `lis rX,hi ; addi/ori rX,rX,lo` idiom the compiler uses for addresses.

Give TARGET as a quoted string (its address is located first) or as 0xADDR.

usage:
    python3 tools/xref.py app_nav.bin abs_symbols_base.txt "Auxiliary_Input"
    python3 tools/xref.py app_nav.bin abs_symbols_base.txt 0x023031dc

positional arguments:
  image
  symbols
  target

options:
  -h, --help   show this help message and exit
  --base BASE
```

### callers

`tools/callers.py`: Find direct (bl) callers of one or more addresses in a SMEG+ PPC image.

```text
usage: callers.py [-h] [--base BASE] image symbols targets [targets ...]

Find direct (bl) callers of one or more addresses in a SMEG+ PPC image.

Only direct branches are found; virtual calls and calls made through function
pointers (`bctrl`) are not, which is normal for C++ code. `survey.py` counts the `lis`/`addi` references
that most calls in this firmware go through.

usage:
    python3 tools/callers.py app_nav.bin abs_symbols_base.txt 0x02324928

positional arguments:
  image
  symbols
  targets      addresses to look for callers of

options:
  -h, --help   show this help message and exit
  --base BASE
```

### mkelf

`tools/mkelf.py`: Wrap a raw SMEG+ application image plus its symbol map into a disassemblable ELF.

```text
usage: mkelf.py [-h] [--base BASE] image symbols output

Wrap a raw SMEG+ application image plus its symbol map into a disassemblable ELF.

Some disassemblers (and debuggers) want a real ELF rather than a flat image. This
produces an ELF32 big-endian PowerPC executable whose .text holds the image at its
load address, with the symbol map attached.

usage:
    python3 tools/mkelf.py app_nav.bin abs_symbols_base.txt app_nav.elf
    objdump -d app_nav.elf            # any PPC-capable objdump / llvm-objdump

positional arguments:
  image
  symbols
  output

options:
  -h, --help   show this help message and exit
  --base BASE
```

### elfsyms

`tools/elfsyms.py`: Read the symbol tables the SMEG+ package ships in plain sight.

```text
usage: elfsyms.py [-h] [--grep GREP] [--cls CLS] [--strings [MATCH]] [--raw] elf

Read the symbol tables the SMEG+ package ships in plain sight.

positional arguments:
  elf                 an .out from the package root

options:
  -h, --help          show this help message and exit
  --grep GREP         only symbols whose name contains this (case-insensitive)
  --cls, --class CLS  only methods of this C++ class, in address order
  --strings [MATCH]   list string literals instead, optionally filtered
  --raw               do not demangle
```

### symdiff

`tools/symdiff.py`: Diff two firmware releases by symbol, so a patch set can be carried across.

```text
usage: symdiff.py [-h] --a IMAGE SYMBOLS --b IMAGE SYMBOLS [--base BASE] [--patch-addr PATCH_ADDR]
                  [--json]

Diff two firmware releases by symbol, so a patch set can be carried across.

Extending the patches to another SMEG release currently means redoing the analysis by hand.
Most of it does not need redoing. The 5.43 and 5.42 NAV images are the same code *displaced by
a constant 152 bytes*, which a naive byte comparison reports as ~80% different — the shift,
not new code. This separates the three cases that matter:

  * **moved, same bytes** — the patch address is mechanical: add the displacement
  * **moved, different bytes** — the address carries over but the patch needs re-deriving
  * **gone or renamed** — nothing to carry

and it reports the displacement rather than making you find it. Point `--patch-addr` at a
site in A and it says whether that site survives into B, and where.

It heeds the rule in `AGENTS.md` either way: a derived address is a *candidate*. Nothing here
patches anything, and a candidate address without the `expect` bytes to back it is not safe to
apply.

usage:
    python3 tools/symdiff.py --a old.bin old_symbols.txt --b new.bin new_symbols.txt
    python3 tools/symdiff.py --a old.bin old_symbols.txt --b new.bin new_symbols.txt \
        --patch-addr 0x02247858

options:
  -h, --help            show this help message and exit
  --a IMAGE SYMBOLS     older release
  --b IMAGE SYMBOLS     newer release
  --base BASE           load address of the images
  --patch-addr PATCH_ADDR
                        a patch site in A to locate in B
  --json
```

### crc-recover

`tools/crc_recover.py`: Recover CRC parameters from (message, checksum) samples.

```text
usage: crc_recover.py [-h] [--package PACKAGE] [--samples SAMPLES] [--root ROOT] [--width WIDTH]

Recover CRC parameters from (message, checksum) samples.

options:
  -h, --help         show this help message and exit
  --package PACKAGE  a map package root; collects from its DESCRI.DAT files
  --samples SAMPLES  a file of '<path> <hex>' lines
  --root ROOT        base for the paths in --samples
  --width WIDTH
```

### cartography

`tools/cartography.py`: Read the cartography metadata: name pools, the `.inf` sidecars, `SCC` records, `CCT.DAT`.

```text
usage: cartography.py [-h] {names,names-round-trip,inf,scc,cct} ...

Read the cartography metadata: name pools, the `.inf` sidecars, `SCC` records, `CCT.DAT`.

positional arguments:
  {names,names-round-trip,inf,scc,cct}
    names               inspect or rewrite a NUL-separated name pool
    names-round-trip    read and write a pool, then compare bytes
    inf                 show a .inf sidecar
    scc                 list the records of a %03dSCC.DST
    cct                 decrypt and show CCT.DAT (needs the firmware image)

options:
  -h, --help            show this help message and exit
```

### tool-reference

`tools/tool_reference.py`: Generate docs/TOOLS.md: every tool, its purpose and its `--help`, from the tools themselves.

```text
usage: tool_reference.py [-h] [--check]

Generate docs/TOOLS.md: every tool, its purpose and its `--help`, from the tools themselves.

The tool tables in README.md, AGENTS.md, CLAUDE.md and docs/RUNNING.md drifted: one was
missing 14 of 31 tools. This page is written from each tool's docstring and `--help` instead.

`--check` compares what should not drift silently - the set of tools, their groups and their
one-line summaries - and not the `--help` text, whose formatting changes between Python
versions (3.13 locally, 3.14 in CI). Re-run without `--check` to refresh the whole page.

usage:
    python3 tools/tool_reference.py            # rewrite docs/TOOLS.md
    python3 tools/tool_reference.py --check    # exit 1 if a tool is missing or its summary changed

options:
  -h, --help  show this help message and exit
  --check     fail if the page is missing a tool
```

## Repository hooks

| tool | what it does |
|---|---|
| [`check_commit_msg.py`](#check-commit-msg) | Validate a Conventional Commits message, or a PR title. |
| [`check_no_pii.py`](#check-no-pii) | Refuse to commit personal data. |

### check-commit-msg

`tools/check_commit_msg.py`: Validate a Conventional Commits message, or a PR title.

```text
usage: check_commit_msg.py [-h] [--title TITLE] [--quiet] [msgfile]

Validate a Conventional Commits message, or a PR title.

Conventional commits are not a style preference here — the repository squash-merges, so the
PR title becomes the commit on `main`, and Release Please reads it to pick the next version
and write `CHANGELOG.md`. A title that does not parse means the release is silently wrong
(or does not happen), which is why this is enforced in two places:

  * as a `commit-msg` hook, so a local commit cannot be made with a bad message;
  * in CI against the PR title, because that is the message that actually lands.

usage:
    check_commit_msg.py .git/COMMIT_EDITMSG     # hook form
    check_commit_msg.py --title "feat: a thing"  # CI form

positional arguments:
  msgfile        a commit message file (what the commit-msg hook passes)

options:
  -h, --help     show this help message and exit
  --title TITLE  validate a string instead, e.g. a PR title
  --quiet
```

### check-no-pii

`tools/check_no_pii.py`: Refuse to commit personal data.

```text

```

## Shared libraries

Imported by the tools above; not run directly.

| module | what it holds |
|---|---|
| `appimage.py` | The application image container, shared by every tool that reads it. |
| `smeglib.py` | The boring, load-bearing parts of a package's checksum chain, in one place. |
| `symbols.py` | Reading the symbol maps the vendor's unstripped ELFs come with. |
