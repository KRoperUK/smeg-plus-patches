# Hardware verification

The dated record of every test on a real car: what was flashed, and what was observed. This is
the one place the project's history lives; the other pages state the current understanding and
link here for the evidence. Patch-by-patch status is in
[Patch definitions](PATCHES.md#patch-sets-in-this-repository).

**Test unit:** Peugeot 208 (2015), SMEG+ iV1, hardware ID `155`, hardware diversity `NAV`,
running `SMEG5.43.A.R2` (CD 26482, 19-09-17). Every result below is *executed* on that unit
unless marked otherwise. The `AUDIO_BT` and `AUDIO_BT_256` patch sets are verified against
their images but have never been flashed.

## Log

| date | build | observed result |
|---|---|---|
| 2026-09-14 | `aux-autoswitch`, re-sealed | **accepted and flashed**; the re-seal works (no string 2099); AUX no longer greys out and is in the SRC cycle; no automatic switch to AUX. [Details](#2026-09-14-first-flash-the-re-seal) |
| 2026-09-14 | `builds/aux-default-retry.json` (`USER_DATA` payload, `Last_Source = 7`) | flashed; the payload **did not apply** (beacon unchanged); boots to FM. Cause: the payload was copied into an uppercase `SQLITE` directory. [Details](#second-flash-the-user_data-retry-2026-09-14) |
| 2026-09-14 | the case-workaround payload package | flashed; boots to FM; no capture of that run, so the workaround is unproven. [Details](#later-flash-report-the-case-workaround-package) |
| 2026-09-14 | `spy-dump-userdata` | `SPYSTORE` copied the live `/USER_DATA/user_data` tree to the stick. [Details](#2026-09-14-spystore-backs-up-user_data) |
| 2026-09-27 | `aux-autoswitch` + `aux-boot-default` + `spy-dump-userdata-partition`, piano ring tone renamed in the seed database | accepted; the custom tone played; **boots to FM**; the tone kept its stock name; `GUI_VER` 32.01 not seen on the page looked at. [Details](#2026-09-27-aux-boot-default) |
| 2026-09-28 | the same + `aux-boot-restore` with the handler edit only | **boots to FM**, on the 7.5 s init timer. [Details](#2026-09-28-aux-boot-restore-handler-edit-only) |
| 2026-09-28 | the same with the three-edit `aux-boot-restore` (`builds/aux-boot-restore.json`) | **boots to AUX**, three times; `spy-dump-userdata-partition` put no `USER_DATA` tree on the stick. [Details](#2026-09-28-boot-to-aux) |

## 2026-09-14 — first flash: the re-seal

Package built from `NAV` with `aux-autoswitch` (`IsAUXSRCAvailable()` and the
`HandleAudioAuxInputStatusChnged()` `+0x10c` edit), re-sealed with `tools/patch_contract.py`,
application image CRC `0x7c310f0f`.

| check | outcome |
|---|---|
| contract check (string 2099, *"update file is protected and cannot be copied"*) | **not triggered** — the re-sealed package was accepted |
| application image written | **yes** — updater reached `AppBin flashing` |
| media phases ran | **yes** — Phases 0, 3 and 5 observed in this run; Phase 6 in a later one |
| unit rebooted and came back up | **yes** — multiple Peugeot splash screens, then normally working |
| version strings changed | **no, as expected** — re-flashing the same release does not alter them |
| `IsAUXSRCAvailable()` patch | **working** — AUX no longer greys out with no signal |
| AUX in the SRC cycle | **yes** — FM → DAB → AM → USB → AUX |
| automatic switch to AUX | **no** |

!!! success "The re-seal works on hardware"

    String 2099 is the unit's rejection of a package whose media does not match the signed
    contract. It did not appear, and the update proceeded to write the application image. This
    was the blocker for the whole project.

No automatic switch is expected from this build. Its second edit is inert — the branch it
removes is never taken *(executed under emulation; see [Emulating the firmware](EMULATION.md))*
— and the handler it sits in reacts to the saved AUX input setting, not to a signal *(read; see
[The AUX signal path](AUX_SIGNAL.md))*.

### Observed update sequence

Captured from photographs taken during the update, ordered by capture time. Screens marked
*diagnostic* are the blue bootloader/flasher screens with yellow monospace text; the rest are
the normal touchscreen UI.

| time | screen | verbatim text |
|---|---|---|
| 15:34 | update dialog | `UPDATE LEVEL` / `Identification of media...` |
| 15:37 | update dialog | `UPDATE LEVEL` / `Checking compatibility...` |
| 15:37 | update confirm | `Software update.` / `From version:` `CD 26482` / `To version number:` `CD 26482` / `Keep the engine running.` / `The system will restart.` / `Continue?` `Yes` `No` |
| 15:40–15:41 | boot splash ×3 | `PEUGEOT` |
| 15:41 | *diagnostic* | `Renesas Upd...` / `FPComSMEG.N...` |
| 15:41 | *diagnostic* | `AppBin Upgrade...` / `AppBin flashing` / `(Upgrade in progress)` |
| 15:41 | *diagnostic* | `Phase 0` / formatting `/SYSTEM` / `(please wait)` |
| 15:42 | *diagnostic* | `Phase 0` / defragmenting `/USER-DATA/BACKUP` |
| 15:42 | *diagnostic* | `Phase 3` / `Uncompress /SYSTEM` |
| 15:44 | *diagnostic* | `Phase 3` / `Check the result of uncompression of /SYSTEM/` / `Check progression : 6%` |
| 15:44–15:49 | *diagnostic* | `Phase 5` / `Uncompress /SD_DIR` → `Uncompress /SD_DIR_TTS` / `Free space on SD: 2190624 Kbytes` |
| 15:52 | boot splash | `PEUGEOT` |
| 15:52 | source menu | `FM Radio` `DAB Radio` `AM Radio` `USB` `iPod` `Bluetooth` `AUX` |
| 15:53 | update dialog | `UPDATE LEVEL` / `Identification of media...` |
| 15:54 | update confirm | the same `Software update.` confirmation again |
| 15:55 | System Information | `SMEG5.43.A.R2` / `CD: 26482` / `Dated: 19-09-17` |

The update-confirmation dialog appears **twice**, at 15:37 and again at 15:54 — after the unit
had completed the update and come back up. That is the unit offering the update again while the
stick is still in; remove the stick once the normal UI is back. The write itself is the 15:37
pass, since the flasher screens run immediately after it.

A phase number of 1 appears once, in a blurred frame, alongside a word ending in `BACKUP`; it
is not legible enough to record as fact.

#### Phase 6, from a later session the same day

A capture at **17:26** — a separate flash — shows the phase the sequence above never caught:

```
Phase 6
Management of ZA files

(please wait)

The product must reboot in 2 s
```

The run does not end after Phase 5: it goes on to Phase 6 and **reboots itself from there**.
`Management of ZA files` is `C_UPGRADE::ManageZAFiles()` at `0000fd04` in `upgrade.out` — see
[Boot and update chain](FLASH_CHAIN.md#3-the-package-ships-its-own-symbol-tables). The ZA files
are the ones copied from `/SYSTEM_DATA` to `/USER_DATA`, described in
[What is reachable](CAPABILITIES.md).

#### The diagnostic header

The diagnostic screens carry a fixed header that identifies the media being flashed:

```
Media version :        26482
Upgrade version :      5.3.3
BootRom version :      BSP-215.6.PLUSINT May 26 2017, 13:23:13
UBoot version :        06.03 Apr 22 2013 - 15:57:07
Hardware ID :          155
Hardware diversity :   NAV
Renesas version :      05.e3.01
```

These map exactly onto the package contents — `Upgrade version 5.3.3` is `SUBVER` in
`upgrade.out.inf`, `Media version 26482` is `VER` in `media.inf`, and `05.e3.01` is the
`FPComSMEG.mot` version — which confirms the unit was reading **our** package.

#### Reboots, progress and free space

At least four `PEUGEOT` splash screens appear in the series, interleaved with the diagnostic
screens. That matches the `Manage*AndReboot` naming in [Boot and update chain](FLASH_CHAIN.md):
the unit restarts after the BootROM, U-Boot, Renesas and application steps so the new code runs
next.

The only percentage captured is `Check progression : 6%` during the Phase 3 verification pass.
The diagnostic screens otherwise show free space rather than progress, and the figures change
as partitions are rewritten:

| partition | values observed |
|---|---|
| `/SYSTEM` | 107384 → 107776 → 97452 → 73256 Kbytes |
| SD | 2717184 → 2706080 → 2190624 Kbytes |

### Behaviour observed afterwards

- **AUX stays selectable with no signal.** On stock firmware the AUX tile greys out when
  nothing is connected; after the patch it remains available. This is `IsAUXSRCAvailable()`
  returning true.
- **AUX is in the SRC cycle.** Pressing SRC steps FM → DAB → AM → USB → AUX as normal.
- **Long-pressing SRC does not select AUX**, and no patch makes it. It is not a small change
  *(read)*: the source menu's `C_HMI_AUDIO_CHANGE_SOURCE_0X_Menu::HandleVCIKey` reads only
  `GetVKeyReleasedData()` (key codes `0x4f` and `0x20051` call `HandleNextSourceKey`, the SRC
  cycle; `0x51` clicks the focused item), so there is no keep-pressed branch to extend.
  On-screen SRC long-press is bound globally by `C_MENU_STATE::ProcessEscKeyLongPress` to the
  product-code/system-information view, the steering-wheel SRC delivers no keep-pressed event
  to the audio application, and the image carries the string
  `ESC LONG PRESS handling should be done!!!` from `C_MENU_STATE::HandleTouchEvent`.

## Second flash — the `USER_DATA` retry (2026-09-14)

`builds/aux-default-retry.json` was flashed to the same unit the same day, to try
`supervisor.Last_Source = 7` through a `USER_DATA` payload. It carried a **beacon** —
`clock.Time_Zone` moved from `16` to `0` — so that "the payload did not apply" could be told
apart from "the value is wrong".

| check | outcome |
|---|---|
| update ran | **yes** — offered and installed fully |
| application image | **patched** — AUX still does not grey out with no signal |
| `USER_DATA` payload applied | **no** — the time zone did not change |
| the unit's own state | **undisturbed** — paired phones and presets intact |
| boot source | **FM radio**, not AUX |
| `src` behaviour | unchanged; AUX is not offered first (no patch reorders SRC) |

The stick was inspected afterwards: the payload was at exactly the path the updater tests —
`SMEG_PLUS_UPG/NAV/USER_DATA/user_data/sqlite/up_common.sqlite` — with its **build**
timestamp (12:38) intact, so the folder name was not the cause.

What the updater does with the payload *(read from `upgrade.out`)*:

- `UpgradeTask` copies it with `xcopy_blk("/bd0/SMEG_PLUS_UPG/NAV/USER_DATA", "/USER_DATA")`,
  under a bare `IsDirExist` test with no fallback, in the block that continues **Phase 1**. That
  block is reached only when the persisted step (`readStep`, `this+0xc0`) is `0` or `1`.
- `C_UPGRADE::RestoreDataFromUSB()` runs unconditionally just before it and copies from a base
  path held at `this+0x24` into `/USER_DATA` and `/USER_DATA_BACKUP`.
- The updater logs all of this to `/SYSTEM_TMP_DATA/spy/UPG/UPG_log.txt` on the unit
  (`C_UPGRADE::MakeLogArchive` rotates it), and `SPYSTORE` copies that to a stick.

### Root cause, from the updater's own log (2026-09-14)

The log came off the unit with `SPYSTORE` (see [Cheatcodes](CHEATCODES.md)). It shows the copy
**did** run:

```
copying dir  /bd0/SMEG_PLUS_UPG/NAV/USER_DATA/user_data  -> /USER_DATA/user_data
copying dir  .../USER_DATA/user_data/SQLITE             -> /USER_DATA/user_data/SQLITE
copying file .../SQLITE/up_common.sqlite                -> .../SQLITE/up_common.sqlite
(tUpgrade): Copy of /USERDATA from /bd0 to NAND
```

**`SQLITE`, uppercase.** The unit's own dump names the path the application actually uses — in
its open file table and in a database error — as lowercase `sqlite`:

```
/USER_DATA/user_data/sqlite/navigation.sqlite
ERROR: <up_common> [CMMSQLDataBaseImp::BackUp error : disk I/O error
       from </USER_DATA/user_data/sqlite/up_common.sqlite>]
```

FAT hands out uppercase 8.3 short names, and the updater named the destination directory from
what it read off the stick. The payload landed in a sibling directory that differs only by case,
which the application never opens. The unit's settings dump (`CMMUPKeys::ShowStatus`, 271 keys)
confirms it:

```
supervisor.Last_Source.0            <int> : 1
supervisor.Last_Source_Priority.0   <int> : 10
supervisor.Src_Radio_SchedPos.0     <int> : 7
```

`Last_Source` is still the factory `1`, so `7` never reached the live database. Two further
differences in the same log would also have to be fixed:

- The payload shipped **no `.inf` sidecar**, while every database in the live directory has one
  (`up_common.sqlite.inf`).
- `RestoreDataFromUSB` looks for a **per-unit** directory — `/bd0/00FE…0035` style, named after
  the unit itself — not the package path; and `SaveDataOnUSB`, which would create it, never ran
  (zero mentions in the log).

### Later flash report — the case-workaround package

The package staged after identifying the FAT case problem was flashed. The unit still booted to
FM and the SRC button followed its normal cycle. **No new capture was made after that flash**:
the dump discussed here is timestamped 18:29, and the case-workaround payload and its `.inf` on
the stick 19:06, so the dump describes the earlier run. That gives two separate results:

- **The application patches remain installed and do not change either behaviour.**
- **The 18:29 capture shows FM for the earlier run:** `6639::Last_Source : 1 (0x1)`,
  `supervisor.Last_Source.0 <int> : 1`, and `Current_source ... SRC_TUNER`, with the updater log
  naming the copied directory uppercase:

```
copying dir  .../USER_DATA/user_data/SQLITE -> /USER_DATA/user_data/SQLITE
copying file .../SQLITE/up_common.sqlite    -> .../SQLITE/up_common.sqlite
```

So the long-filename workaround is **not demonstrated**: either the FAT entry on the flashed
stick was still exposed as `SQLITE`, or the updater canonicalised it, and the log cannot
distinguish those.

The same log shows what happened to the existing settings before the payload copy: the updater
copied the live lowercase `/USER_DATA/user_data/sqlite` tree to temporary storage, formatted
`/USER_DATA`, and restored the tree — including `up_common.sqlite`, navigation databases and
audio data — before copying the separate uppercase payload directory. That supports
**preservation** of the old data, but does not prove a particular phone pairing survived.

Boot to AUX was later achieved with application patches instead (2026-09-28, below); the payload
route is not pursued.

### 2026-09-14 — SPYSTORE backs up `/USER_DATA`

With `spy-dump-userdata` flashed, `SPYSTORE` with a stick inserted produced a dump
(`SPY/02_.../`) containing the full `/USER_DATA/user_data/` tree — `sqlite/` (14 databases with
their `.inf` CRC sidecars), `Audio/` (`Tuner.dat`/`Radio.dat` presets), and `Nav/`, `TTS/`,
`T2BF/`. `up_common.sqlite`/`up_user.sqlite` are stored **gzip'd** (`1f8b …`), as the unit keeps
them. `connectivity.sqlite`, and so the paired phones, is not in it: it is imported from the
system partition. See [Patch definitions](PATCHES.md#spy-dump-userdata-spystore-also-backs-up-user_data).

The same `SPYSTORE` dump also carried `abs_symbols_base.txt.gz` (98 365 lines) and
`symbols_bsp.txt.gz` (22 497 lines) — the application and BSP symbol tables the analysis tools
resolve names with — and a task/exception capture, which is where the settings listing above
came from.

## 2026-09-27 — `aux-boot-default`

Flashed: `aux-autoswitch` + `aux-boot-default` + `spy-dump-userdata-partition`, a piano ring
tone on ring1 renamed `Piano_riff` in the seed database, and `GUI_VER` 32.01.

- **Accepted and flashed; the custom ring tone played.**
- **Boots to FM**, with audio playing into AUX and AUX visible and selectable. The shipped image
  held `39200007` at `0x0169948c` (pristine `81210008`), inside `C_MGR_SRC::StartUp`
  (`0x016990b8`), so the patch was applied at the right place. AUX's boot request carries
  `PrOnly`, which keeps it out of the restore (see the 2026-09-28 tests).
- **The renamed tone kept its stock name** (`Alien`). The ringtone menu reads its names from the
  application image, not the seed database *(read)*; `media.names` now patches the image — see
  [Ring tones](RINGTONES.md). The image-patched name has not been flashed yet.
- **`GUI_VER` 32.01 was not seen** on the System Information page looked at. The code shows it
  on the GUI item's page *(read)*; which page was looked at was not recorded. See
  [Version strings](VERSION_STRINGS.md).
- This dump has no user spy archive (`SPY/<stamp>/TAR/*-USER.tar.gz`), so there is no
  source-manager trace for this boot.

## 2026-09-28 — `aux-boot-restore`, handler edit only

Flashed: the 2026-09-27 build + `aux-boot-restore` with only its
`HandleAudioAuxInputStatusChnged` edit. **Boots to FM.** A `SPYTAKE` + `SPYSTORE` capture of
the boot (flash at 01:05, collect at 01:07):

```
8847::Last_Source   : 7 (0x7)
10109::AllocateSource  : MsgSrc = 3, SrcId= 0xe200,Type=5, Sched_Pos= 7, ...
10109::SendWAIT [MsgSrc + Source_ID]  : 3, 0xe200
10438::AllocateSource  : MsgSrc = 10, SrcId= 0xbc00,Type=5, Sched_Pos= 1, ...
16347::SendACK [MsgSrc + Source_ID]  : 10, 0xbc00
```

```
Nb|src|id|Status|Norm|NoSr|Lock|Type|sche|Post|Susp|PrOnly|
 3|0x3   |0xe200   |WAITING|  20| 255| 255|   5|   7|   0|   1|   1|  true|
```

- **AUX's boot request still had `PrOnly` set**, and `ScheduledInit` had no position-7 row (USB,
  iPod, BT, CDC and TUNER only). The boot request comes from `InitApp`, not from the handler
  *(read)*, so the handler edit did not reach it.
- **FM was chosen by the init timer:** 8847 ms + 7500 ms = 16347 ms, the exact time of the tuner's
  acknowledgement.
- The `Last_Source` line logs the **saved** value, before `aux-boot-default`'s override *(read)*;
  that session had ended on AUX.

## 2026-09-28 — boot to AUX

Flashed: `builds/aux-boot-restore.json` — `aux-autoswitch` + `aux-boot-default` + the
**three-edit** `aux-boot-restore` (the `InitApp` edit added) + `spy-dump-userdata-partition` and
the piano ring tone. **The unit booted to AUX three times** *(observed)*. The capture of the last
boot, read with `tools/spy_read.py`:

```
 6531 ms  saved Last_Source = 1
10228 ms  request  SrcId 0xe200   pos 7   type 5  PrOnly false   <- AUX
10228 ms  SendACK  SrcId 0xe200
ScheduledInit: POS_TUNER (1, 10), POS_USB (9, 20), POS_IPOD (10, 10), POS_BT (8, 10), POS_CDC (4, 10), POS_AUX (7, 20)
verdict: AUX was acknowledged first, at 10228 ms
```

- **AUX's boot request carries `PrOnly` false**, so it entered `ScheduledInit` as (7, 20).
- **It matched the restore target and was acknowledged in the same millisecond it asked**, with
  no tuner acknowledgement at the 7.5 s mark.
- **The saved `Last_Source` was 1 (FM)**, so `aux-boot-default`'s override (`li r9,7`, written
  after the trace line) is what made the match *(read)*. Why the saved value was 1 after AUX
  boots is *not known*.
- **`spy-dump-userdata-partition` did not work:** the stick's `SPY/<stamp>/` folder holds the
  normal collect and no `USER_DATA` tree.

`aux-boot-default` + `aux-boot-restore` are therefore confirmed as a pair; `builds/aux-boot.json`
is the minimal build with the same boot-to-AUX bytes.

## What these tests do not show

- **An automatic switch to AUX when audio starts.** No flashed build contains a patch for that;
  `aux-signal-switch` is verified under emulation only and is not being pursued. See
  [The AUX signal path](AUX_SIGNAL.md).
- **A visible build marker.** System Information reads `SMEG5.43.A.R2` / `CD 26482` after a
  patched flash: the first is an application-image literal and the second the media partition's
  `media.inf`, neither of which a patch changes. `GUI_VER` has not been seen. Judge a flash by
  behaviour, a replaced ring tone, or a `SPYTAKE` capture.
- **Other builds.** All of the above is `NAV` on one car.

## Reproducing

See [Flashing](FLASHING.md) for preparing the stick and the whole test loop, and
[Media protection](MEDIA_PROTECTION.md) for why the contract must be regenerated.
