# Version strings — display, sources and gating

## What the System Info screen shows

| field | value on SMEG5.43.A.R2 | source |
|---|---|---|
| Main SMEG software | `5.43.A.R2` | `smeg.inf` -> `VER:` |
| Display version | `cd 26482` | `media.inf` -> `VER:` (observed on the car, 2026-09-27) |
| Bluetooth | `1.2.0` | Bluetooth firmware |
| BootROM / uBoot / Renesas | as flashed | their own images |

The application does **not** carry these strings for display. The image contains the
path `/SYSTEM/Data_base/smeg.inf`, i.e. it reads the **media partition** copy. So:

- Patching `AppBin/f_BigQuick.bin` never changes any version string.
- Changing `VER:`/`GUI_VER:` in a *module* `smeg.inf` (`AUDIO_BT/smeg.inf`) is used by
  the updater but does not change what the screen shows — the displayed copy is
  `Data_base/smeg.inf` **inside `system.bin`**.
- A media-partition edit, which `tools/patch_media.py` (or `build_package.py`'s `media`
  section) performs, changes that copy — but no on-screen field is known to reflect it (see
  below).

`AUDIO_BT/smeg.inf` and the tar's `Data_base/smeg.inf` currently hold identical content,
which is why it is easy to assume editing one affects the other.

## The updater gates on these strings

From `upgrade.out` strings:

```
(UpgradeTask) The version on media.inf not allows an upgrade
(UpgradeTask): Actual BSP (%f) is very old... The new version of the BSP need to format the NAND.
(GetUBootVersionMedia): field 'VER:' not found!
(ManageHarmoniesVersions) Harmonies are not compatibles, new Harmony must be erased
(ManageRenesasUpdateAndReboot) Renesas version '%s' == Mot. File version '%s'
manageBootRomUpdateAndReboot: BootRom already done.
ManageBigQuickUpdate: '%s' is a cantidate!
```

So versions are compared, and the comparisons drive more than "update or skip":

- `media.inf` has an explicit gate — **"not allows an upgrade"** — so a wrong value
  there can *block* the package.
- UBoot versions are parsed numerically (`%02d.%02d`) and a missing/unparsable `VER:`
  is an error, so an invented series is not guaranteed to parse.
- Harmony compatibility and BSP age are version-driven, and those branches do
  destructive things (erase the harmony images, format the NAND).

## Why not to invent a version

- Bumping `smeg.inf` `VER:` to e.g. `5.43.A.R3` makes the application look newer, so the
  updater applies it — but it changes nothing visible (display reads the media copy) and
  nothing functional (content is whatever was patched).
- An unrecognised series such as `5.43.X.R1` may not parse, landing on the
  "not allows an upgrade" path or, worse, triggering a harmony/BSP re-flash.
- `media.inf` is the one with the hard gate; do not edit it as a marker.

!!! warning "There is no known safe on-screen build marker"

    `GUI_VER` was bumped to `32.01` on a real flash and was not seen on the unit; the
    Display-version screen read `cd 26482`, which is `media.inf` verbatim *(observed, see
    [Two display findings](AUX_CHAIN.md#two-display-findings))*. The only version the screen
    is known to show comes from `media.inf`, which the updater gates on — do not edit it.

    Judge a flash by behaviour instead: an audible replaced ring tone proves the media
    partition landed, and `preflight.py` or a `SPYTAKE` capture proves the patched bytes.
    See [Hardware verification](VERIFICATION.md).
