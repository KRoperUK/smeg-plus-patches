# Version strings — display, sources and gating

## What the System Information screen shows

Spike #191, stock NAV `SMEG5.43.A.R2`. Read from decompiles and disassembly; nothing here was
executed, and nothing was re-checked on the car.

**Where the values come from.** `C_BCM_VERSION::Init` (`0x0158e010`) builds a list of
version entries (`TB_SW`, `BR`, `CD`, `UBOOT`, `Renesas`, `GUI`, `DbDwnl`, `Gruppo`; plus
`Display`, added by `UpdateDataBase`). On **every boot**, `UpdateDataBase` (`0x0158ce38`)
runs `DELETE FROM versions;` and re-inserts them all as `(ID, Name, Version, Date)`. The stock
seed `versions.sqlite` is empty *(read)*.

**What is shown.** `C_HMI_CONFIG_SystemInformation_M3Z_Z1` lists four items: `TB_SW`, `MGR_BT`,
`DbDwnl` (NAV units only) and **`GUI`**. For the selected item it queries `versions` and shows
*(read)*:

- **field 5000:** that item's `Version` (the DbDwnl item shows its database versions instead);
- **field 6000:** the **`CD`** row's `Version`, on **every** item page. This is the observed
  `cd 26482`;
- **field 7000:** the **`TB_SW`** row's `Date`, on every item page except DbDwnl.

| row | `Version` comes from | `Date` comes from | also used by |
|---|---|---|---|
| `TB_SW` (main software) | an **application-image literal**, `SMEG5.43.A.R2` *(read)* | the image globals `g_MBSW_GENERATION_DAY/MONTH/YEAR` (`0x035e49a5`–`a7`, `19 09 17`), printed `%02x-%02x-%02x` *(read)* | the same globals build the version frame **sent on CAN** (`C_BCM_CAN_MSG_VERSION_BTEL::SendFrame`) *(read)* |
| `CD` | `VER` in the **media partition's** `Data_Base/media.inf`, inside `system.bin` *(read; the `.inf` suffix is inferred)* | – | the diagnostic DID `C_RDBLID_2010_80`, and the CAN version frame *(read)*; very likely the updater's `media.inf` gate *(inferred)* |
| `GUI` | `GUI_VER` in the media partition's `Data_Base/smeg.inf` *(read)* | – | nothing else found *(read)* |

`smeg.inf`'s `VER:` is **not read** by this screen at all. The package-root `media.inf` and the
media partition's `Data_base/media.inf` are byte-identical in stock (`VER:26482`), which is how
the two were confused.

!!! failure "Corrected: where the displayed versions come from"

    This page used to say the main software version comes from `smeg.inf` `VER:`, and that
    the application carries no version strings for display. Both were read off the strings
    in the image and the files in the package, not off the code that builds the screen.
    The code shows the main software version and date come from the **application image**,
    and `cd` from the **media partition's** `media.inf` *(read, #191)*.

### Is `GUI_VER` visible?

By the code, `GUI_VER` is shown in field 5000 of the **GUI** item's page *(read)*. On
2026-09-27 a build set it to `32.01`, and it was not seen, while `cd 26482` was. The likeliest
explanation is that the page looked at was not the GUI item's: `cd` is on every page, and the
item labels are in the undecoded GUI text strings (#62), so which on-screen label is the GUI
item is **not known** *(inferred)*.

!!! failure "Withdrawn: GUI_VER is not shown on the unit"

    That conclusion came from one look at one page. The code puts `GUI_VER` on the GUI item's
    page. What is actually known is narrower: `32.01` was not seen on the page that was
    looked at.

**The cheap car check, with no new build.** On the current stock-`GUI_VER` build, open each
System Information item in turn and note which shows `32.00`, and where `19-09-17` appears.
If `32.00` is on an item page, `GUI_VER` (`media.gui_ver` in a build manifest) already works
as a media-only build marker.

### A candidate marker in the application image (not shipped)

If `GUI_VER` turns out not to be visible, the `TB_SW` date can become the marker. Change only
`Init`'s three loads of the `g_MBSW_*` globals into immediates, so the displayed date shows a
chosen value while the globals, and the CAN frame built from them, stay stock:

| addr | original | replacement |
|---|---|---|
| `0x0158e098` | `888949a5` `lbz r4,0x49a5(r9)` (day) | `388000DD` `li r4,0xDD` |
| `0x0158e090` | `88a949a6` `lbz r5,0x49a6(r9)` (month) | `38a000MM` `li r5,0xMM` |
| `0x0158e0a8` | `88cb49a7` `lbz r6,0x49a7(r11)` (year) | `38c000YY` `li r6,0xYY` |

For example `38800028`, `38a00009`, `38c00026` would show `28-09-26`. The format is `%02x`, so
any two hex digits work. **CANDIDATE**: the replacements were decoded with capstone
*(executed, decoding only)*; nothing was emulated or flashed, and it is not a `patches/*.json`.
Only `Init` and `InitAfterInstance` read these globals *(read, full-image scan)*, and the edit
touches `Init` alone. Residual risk: something the scan missed may read the `versions`
table's `TB_SW` date, and whether field 7000 is on the page you look at is not known; the car
check above settles that too.

### What must not be changed

- **The `SMEG5.43.A.R2` literal or the `g_MBSW_*` globals.** They also reach the CAN version
  frame and `SYSTOOL_SetVersion` (the spy and panic logs) *(read)*.
- **The `CD` value (`media.inf` `VER`).** It is visible, but it also goes to the diagnostic DID
  and the CAN frame *(read)*, and it is very likely what the updater compares a stick's
  `media.inf` against *(inferred)*. Raising it could make a later stock package look like a
  downgrade and be refused, which would block a rollback. See the gates below.

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
  updater applies it — but it changes nothing visible (the screen does not read it) and
  nothing functional (content is whatever was patched).
- An unrecognised series such as `5.43.X.R1` may not parse, landing on the
  "not allows an upgrade" path or, worse, triggering a harmony/BSP re-flash.
- `media.inf` is the one with the hard gate; do not edit it as a marker.

!!! warning "No on-screen build marker is confirmed yet"

    `GUI_VER` is shown on the GUI item's page by the code, but it has not been seen on the
    unit; the car check above settles it. Until then, judge a flash by behaviour: an audible
    replaced ring tone proves the media partition landed, and `preflight.py` or a `SPYTAKE`
    capture proves the patched bytes. See [Hardware verification](VERIFICATION.md).
