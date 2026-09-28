# Running the tools

Everything here runs with [uv](https://docs.astral.sh/uv/) — no virtualenv to set up, no
`pip install`. The scripts carry [PEP 723](https://peps.python.org/pep-0723/) inline
metadata, so `uv` installs what each one needs, once, and caches it.

Two invocation styles appear across these docs, and they are equivalent. `uv run` is the
canonical one used everywhere here; if you have built the `.venv/` (see
[Development](#development)) the plain-Python form works too:

=== "uv (recommended)"

    ```sh
    uv run tools/patch_smeg.py     --src SMEG_PLUS_UPG --out SMEG_PLUS_UPG_mod --copy-package
    uv run tools/patch_contract.py --package SMEG_PLUS_UPG_mod
    ```

=== "venv / plain Python"

    ```sh
    .venv/bin/python tools/patch_smeg.py     --src SMEG_PLUS_UPG --out SMEG_PLUS_UPG_mod --copy-package
    .venv/bin/python tools/patch_contract.py --package SMEG_PLUS_UPG_mod
    ```

## From a checkout

```sh
git clone https://github.com/KRoperUK/smeg-plus-patches
cd smeg-plus-patches

uv run tools/patch_studio.py                        # the Qt app (fetches PySide6)
uv run tools/patch_media.py --help                  # media partition patcher
uv run tools/ringtones.py list                      # ring/wait tone slots
uv run tools/patch_smeg.py --help                   # application image patcher
uv run tools/ppcemu.py --help                       # run a firmware function, emulated
uv run tools/elfsyms.py SMEG_PLUS_UPG/upgrade.out    # the updater's own symbol table
```

`uv run <script>` reads the script's own dependency list, so the GUI pulls PySide6 and the
CLI tools pull nothing.

## Without a checkout

`uvx` runs the packaged console scripts straight from the repository:

```sh
uvx --from git+https://github.com/KRoperUK/smeg-plus-patches smeg-patch-media --help
uvx --from git+https://github.com/KRoperUK/smeg-plus-patches smeg-ringtones list
uvx --from git+https://github.com/KRoperUK/smeg-plus-patches smeg-patch --help

# the GUI needs the optional Qt extra
uvx --from 'smeg-plus-patches[gui] @ git+https://github.com/KRoperUK/smeg-plus-patches' smeg-studio
```

| console script | equivalent |
|---|---|
| `smeg-studio` | `tools/patch_studio.py` |
| `smeg-emu` | `tools/ppcemu.py` |
| `smeg-syms` | `tools/elfsyms.py` |
| `smeg-ringtones` | `tools/ringtones.py` |
| `smeg-patch-media` | `tools/patch_media.py` |
| `smeg-patch` | `tools/patch_smeg.py` |
| `smeg-build` | `tools/build_package.py` |
| `smeg-preflight` | `tools/preflight.py` |
| `smeg-prepare-usb` | `tools/prepare_usb.py` |
| `smeg-verify-package` | `tools/verify_package.py` |
| `smeg-fingerprint` | `tools/fingerprint.py` |
| `smeg-assets` | `tools/assets.py` |
| `smeg-splash` | `tools/splash.py` |
| `smeg-cartography` | `tools/cartography.py` |
| `smeg-crc-recover` | `tools/crc_recover.py` |
| `smeg-symdiff` | `tools/symdiff.py` |

The analysis-only tools (`survey.py`, `ppcdis.py`, `xref.py`, `callers.py`, `mkelf.py`) have no
console script; run them from a checkout.

## Development

`.venv/` is gitignored, so a fresh clone does not have one. Build it once — Python
3.13, because Homebrew's `python3` is 3.14 and PySide6 has no wheels for it:

```sh
uv venv --seed --python 3.13 .venv
uv pip install --python .venv/bin/python -r requirements-dev.txt -r requirements-gui.txt -r requirements-docs.txt
```

`requirements-dev.txt` brings `unicorn` and `capstone`; without them the emulator tests skip
rather than run.

```sh
.venv/bin/python -m pytest tests -q
.venv/bin/zensical serve            # live docs preview on :8000
```

The test suite needs **no firmware at all** — it generates a synthetic package, so the
whole patch and repack path is covered in CI.

### On Windows

The tooling is plain Python and runs on Windows 11 (x86_64) as it does on macOS. Three
things differ, and only the first is a daily annoyance:

- **the venv path** — `.venv\Scripts\python.exe` where these pages say `.venv/bin/python`,
  and `py -3` where they say `python3`;
- **`rsync`** — not present on Windows. The cheat sheet below overlays each tool's output
  onto a copy of the package with `rsync -a overlay/ PKG_mod/`; pass `--copy-package` to
  `patch_smeg.py` instead, which does the same job, or use `robocopy`;
- **the shell scripts** — `tools/check_no_firmware.sh` and `tools/apply_files.sh` are POSIX
  `sh`, which Git for Windows supplies as Git Bash. `.gitattributes` pins `.sh` to LF so
  `core.autocrlf=true` cannot give them CRLF endings and break the hook.

## One extra binary

Audio conversion (mp3, ogg, flac, m4a, …) shells out to **ffmpeg**. WAV input that is
already in the target format works without it:

```sh
brew install ffmpeg                  # macOS
```

```powershell
winget install -e --id Gyan.FFmpeg   # Windows
```

## The analysis toolchain

Reading and writing PowerPC — a cross-`clang`, `lld`, `llvm-mc`, Ghidra, and `rz-diff` for
comparing two firmware versions — is a separate, per-machine install. Nothing on this page
needs any of it, and neither do the tests. It is what the patch addresses were originally
derived with, and what you need if you want a patch's bytes to come from assembled or
compiled source rather than from memory.

See [The reverse-engineering toolchain](TOOLCHAIN.md).

## One command per package: the manifest build

Applying a patch by hand means running three or four tools in order with an `rsync` between
each, and two of those orderings fail *silently* if you get them wrong — the media step
against an un-patched package drops the application change, and re-sealing before the last
edit leaves the package rejected by the unit (string 2099).

`tools/build_package.py` owns that ordering. A build becomes a file you can read, commit
and re-run:

```json
{
  "package": "SMEG_PLUS_UPG",
  "out": "SMEG_PLUS_UPG_custom",
  "module": "NAV",
  "app":   { "patches": ["aux-autoswitch"] },
  "media": {
    "tones":  { "ring_tones/ring1RT.wav": { "source": "tone.mp3", "gain_db": 7.4 } },
    "splash": { "peugeot": "logo.png" },
    "names":  { "ring1": "Piano Riff" }
  },
  "seal": true
}
```

```sh
uv run tools/build_package.py --manifest build.json
uv run tools/build_package.py --manifest build.json --dry-run   # show the steps only
```

!!! warning "`user_data` ships to the unit's USER_DATA partition — it can wipe settings"

    `system.bin` extracts to the read-only `/SYSTEM/`, so settings edited there can appear to
    do nothing: the application reads them from `/USER_DATA`, a separate partition holding the
    car's own state — paired phones, navigation destinations, presets. The updater has a step
    that copies a `USER_DATA` payload over it.

    A manifest with a `user_data` section is **refused** unless it also sets
    `accept_data_loss: true`, and the warning prints either way. That flag means a person was
    told what it may cost and agreed to it.

`media.settings` writes integers into the **seed** settings database inside `system.bin`
(`Data_base/sqlite/up_common.sqlite`), as `Section.Name`. The unit reads its live settings from
`/USER_DATA`, so on hardware these edits have not reached the running unit (observed) — treat
them as an experiment, not a lever:

```json
"settings": { "supervisor.Last_Source": 7 }
```

`media.gui_ver` edits `GUI_VER` in the partition's `Data_base/smeg.inf`. It is harmless, but
it is **not visible** on the unit: set to `32.01` on a real flash, it was not seen, and the
Display-version screen read `cd 26482` from `media.inf` (observed, 2026-09-27). It is kept only
for compatibility; there is no known safe on-screen build marker. See
[Version strings](VERSION_STRINGS.md).

!!! warning "Patch sets accumulate, in order"

    Listing several sets in `app.patches` applies each one to the package built so far, so a
    build asking for `["aux-always-available", "aux-boot-default"]` carries both edits. (Up
    to and including v0.6.0 each set was applied to the *stock* source, so all but the last
    were silently reverted — if you built a multi-set package before that, rebuild it.)

Ready-made **schemes** live in `builds/`. Each is a whole build, so a scheme is one command:

| scheme | what it does | needs |
|---|---|---|
| `builds/aux-only.json` | the AUX patches and nothing else — the closest thing to stock that still enables AUX, and the baseline to reach for when something behaves unexpectedly | nothing |
| `builds/aux-boot.json` | AUX selectable, plus `aux-boot-default`, which was meant to resume AUX on every boot and **does not** (falsified on hardware, see [the AUX chain](AUX_CHAIN.md#how-the-boot-source-is-actually-chosen)) | nothing |
| `builds/combined-aux-boot-ringtone.json` | `aux-only` + `aux-boot` + the ring-tone scheme in one package (the updater finds only one `SMEG_PLUS_UPG`). Its boot-to-AUX part is **falsified** (2026-09-27); kept for history | a tone file |
| `builds/aux-boot-restore.json` | the current boot-to-AUX **candidate**: `aux-boot-default` + the three-edit `aux-boot-restore`. Not yet flashed | a tone file |
| `builds/aux-signal-switch.json` | **candidate** switch-on-signal build: adds `aux-sticky` and `aux-signal-switch`. Emulated only; flash it after the `aux-boot-restore` test has been read | a tone file |
| `builds/alien-piano-riff.json` | replaces the stock `Alien` ring tone and renames it (the rename did not show on the car) | a tone file |
| `builds/diagnostic.json` | trace mask only — **incomplete, emits nothing** on its own | nothing |
| `builds/diagnostic-logging.json` | the diagnostic build that should emit (mask + sink); where the output surfaces is issue #94 | nothing |
| `builds/force-aux-default.json` | the `USER_DATA` `Last_Source` experiment — the route **did not change the boot source** on hardware ([Verification](VERIFICATION.md)) | a tone file, and the `/USER_DATA` acknowledgement |
| `builds/aux-default-retry.json` | the retry of that experiment, flashed 2026-09-14: the payload **did not apply** and the unit still booted to FM ([Verification](VERIFICATION.md#second-flash-the-user_data-retry-2026-09-14)) | the `/USER_DATA` acknowledgement |

Each manifest's own `_comment` gives its status in full, and its `package`/`out` paths are the
author's — edit them before use.

```sh
uv run tools/build_package.py --manifest builds/aux-only.json
```

### A note on the schemes as committed

Every path in a manifest (`package`, `out`, tone and splash sources) expands `~` and is read
relative to the manifest file when it is not absolute. The schemes in `builds/` use
`~/Downloads/...` for the stock package and for tone files; edit those to wherever yours are.
A missing tone or image stops the build before any patch work starts.

Every section is optional. `gain_db` is worth setting: the stock tones sit at about
-1 dBFS, so an unmodified music track sounds muted in the car next to them.

## Pre-flight: check a package before it goes on a stick

`tools/build_package.py` runs this automatically at the end of every build and **fails the
build** if it reports a problem. It is step 1 of [the test loop](FLASHING.md#the-test-loop-end-to-end),
which goes on to the stick, the car and reading a spy capture. You can also run it directly:

```sh
uv run tools/preflight.py --package SMEG_PLUS_UPG_auxdefault
uv run tools/preflight.py --package SMEG_PLUS_UPG_auxdefault --json
```

It checks the things that have actually gone wrong, rather than what looks impressive:

- **the contract** — will the unit accept it, or answer with string 2099?
- **the CRC cascade** — image, `.inf`, `smeg.inf`
- **which patches are present**, by reading the bytes at each known address
- **settings values against what the unit accepts** — `supervisor.Last_Source = 4` did not
  start the unit on AUX, and nothing said why. That cost a car trip. The first explanation
  was a `USER_DATA` payload in a folder not named `SMEG_PLUS_UPG`, which is skipped silently
  and looks identical — pre-flight now fails on that — but a later flash was laid out
  correctly and **still** did not apply its payload, so that was not the whole story. See
  [Hardware verification](VERIFICATION.md), and [The AUX chain](AUX_CHAIN.md) for the
  candidate numberings.
- **the firmware version** — every patch address belongs to one version, so it says which one
  this package carries (`firmware 5.43.A.R2`) before anyone decides whether the patches apply.
  Two entries in `patches/` match at the same address on the wrong version, so the bytes alone
  cannot answer this — see [Patch definitions](PATCHES.md).
- **what the update will write**, so the blast radius is visible
- **a `USER_DATA` payload**, which can reset paired phones and presets — and the two ways it
  silently fails to arrive. The updater reads it from the **hard-coded**
  `/bd0/SMEG_PLUS_UPG/NAV/USER_DATA`, so a package folder under any other name, or a payload
  for another module, is skipped while the update otherwise succeeds; pre-flight **fails** on
  both. It also warns about the casing trap that made three flashes do nothing: the payload's
  `sqlite` directory only reaches the unit as lowercase if it carries a long-filename entry.
  See [Flashing](FLASHING.md#working-around-it-give-the-directory-a-long-filename-entry).

And it prints what it **does not know** as prominently as what it does. The unknowns are
where the car trips went.

## Cheat sheet

```sh
# what is in a media partition, and what tones it has
uv run tools/patch_media.py list --package SMEG_PLUS_UPG --module NAV --tones

# pull it out, keeping a copy of the originals for restore
uv run tools/patch_media.py extract --package SMEG_PLUS_UPG --module NAV \
    --tree media --backup backups --backup-tones-only

# put one back
uv run tools/patch_media.py restore --backup backups --tree media \
    --module NAV --only ring_tones/ring1RT.wav

# see what would change, without writing
uv run tools/patch_media.py apply --package SMEG_PLUS_UPG --module NAV \
    --tree media --out overlay --dry-run

# rebuild the package from whatever differs in the tree
uv run tools/patch_media.py apply --package SMEG_PLUS_UPG --module NAV \
    --tree media --out overlay
rsync -a overlay/ SMEG_PLUS_UPG_mod/

# application image patches (the AUX work)
uv run tools/patch_smeg.py --src SMEG_PLUS_UPG --out overlay
rsync -a overlay/ SMEG_PLUS_UPG_mod/

# marque logo bundles (NOT the boot splash — see Media partition); also works in the GUI
uv run tools/splash.py --tree media list
uv run tools/splash.py --tree media replace --marque peugeot --image my-logo.png
uv run tools/splash.py --tree media selftest     # proves the container model

# ALWAYS last, whatever else you changed
uv run tools/patch_contract.py --package SMEG_PLUS_UPG_mod
```

!!! warning "These tools write overlays, not packages"

    `patch_smeg.py` and `patch_media.py` write **only the files they change** (a handful
    of manifests, the image, the tar) into `--out` — they do not produce a complete
    package. Overlay the result onto a copy of your package with `rsync`. Pass
    `--copy-package` to `patch_smeg.py` if you would rather it copy the whole thing.

    `patch_contract.py` is the exception: with no `--out` it rewrites `contract.dat`
    **in place**.

Ordering and the two orderings that matter:

- **Application patch, then media patch.** `patch_smeg` rewrites `NAV_ctrl.bin` and
  `ctrl.bin` for the application image; `patch_media` swaps the `system.bin` records
  *inside those same manifests*. Run the media step against the already-patched package
  and it carries the application change; run it against the stock package and it does not.
- **Contract re-seal last.** It seals whatever the package contains at that moment, so
  anything changed afterwards is unsealed and the unit will reject it (string 2099).

A complete worked example — an application patch plus a custom ring tone — is in
[Ring tones](RINGTONES.md#worked-example-replacing-a-ring-tone).
