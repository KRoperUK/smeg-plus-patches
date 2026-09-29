# Patch definitions

Every patch set in `patches/`, what it changes, and what is known about it. Base address for
the inflated application image is `0x01000000`; addresses below are absolute, and the tools
convert with `offset = addr - 0x01000000`. The dated record of every car test is in
[Hardware verification](VERIFICATION.md).

## Patch sets in this repository

The status column is generated from each file's `status` field by `tools/patch_status.py`;
edit the JSON, not this table.

<!-- patch-status:table -->
| file | what it changes | status |
|---|---|---|
| `patches/aux-always-available.json` | `IsAUXSRCAvailable()` true only — AUX stops greying out | **Confirmed**{ .pill .pill-ok } behavioural; no switching |
| `patches/aux-autoswitch.json` | `IsAUXSRCAvailable()` true **and** the inert `GetMediaDevice` bail-out nop | **Confirmed**{ .pill .pill-ok } the first edit on hardware; part of the confirmed boot-to-AUX build (the second edit is inert) |
| `patches/aux-boot-default.json` | forces `C_MGR_SRC::StartUp` to restore AUX (position 7) on every boot, ignoring the saved `Last_Source` | **Confirmed with aux-boot-restore**{ .pill .pill-ok } boots to AUX with aux-boot-restore (2026-09-28, NAV); alone it still boots to FM |
| `patches/aux-boot-restore.json` | lets AUX's `PrOnly` request reach the boot restore, and forces the restored priority to AUX's 20; pair with `aux-boot-default` | **Confirmed with aux-boot-default**{ .pill .pill-ok } booted to AUX three times (2026-09-28, NAV); the spy capture shows AUX restored and acknowledged at request time |
| `patches/aux-signal-switch.json` | the AUX handler reads the **signal** instead of the setting, and the media dispatch sends the signal event (`0xcc`) to it; pair with `aux-boot-restore` and `aux-sticky` | **Never flashed**{ .pill .pill-wip } both functions verified under emulation; not being pursued |
| `patches/aux-sticky.json` | removes the bail-out **and** turns "AUX setting switched off" into a no-op | **Never flashed**{ .pill .pill-wip } control flow verified under emulation; not being pursued |
| `patches/diagnostic-logging.json` | redirects the logging stub to the real logger | **Not for driving**{ .pill .pill-no } diagnostic build; needs the mask patch too |
| `patches/diagnostic-logmask.json` | forces the global trace mask — **necessary but not sufficient**, see below | **Not for driving**{ .pill .pill-no } diagnostic build |
| `patches/diagnostic-logsink.json` | points the stubbed `Log_msg` sink at VxWorks `logMsg`; where its output surfaces is issue #94 | **Not for driving**{ .pill .pill-no } diagnostic build; never flashed |
| `patches/spy-dump-userdata-partition.json` | meant to make `SPYSTORE` copy the whole `USER_DATA` partition root, in place of the calibration and regen files; no copy reached the stick | **Does not work**{ .pill .pill-no } flashed 2026-09-27 and 2026-09-28; SPYSTORE put no USER_DATA tree on the stick (observed 2026-09-28) - use spy-dump-userdata |
| `patches/spy-dump-userdata.json` | makes `SPYSTORE` also copy `/USER_DATA/user_data` out to the stick | **Confirmed**{ .pill .pill-ok } on hardware (2026-09-14, NAV) |
<!-- /patch-status:table -->

**What works on hardware** (NAV, 5.43.A.R2): a re-sealed package flashes; AUX stays available
with no signal (`IsAUXSRCAvailable()`); the unit **boots to AUX** with
[`builds/aux-boot.json`](#boot-to-aux-aux-boot-default-aux-boot-restore); and `SPYSTORE` can
back up `/USER_DATA/user_data`. The unit does not switch to AUX by itself when audio starts:
no shipped patch does that, and the handler most AUX patches touch reacts to the saved AUX
input *setting*, not to a signal (see [The AUX signal path](AUX_SIGNAL.md)).

## The application image

Every patch here edits `<module>/AppBin/f_BigQuick.bin`:

```
0x0000..0x0800    header (version, sizes, segment descriptors, 0xdeadbeef markers)
0x0800            0x08 (compression marker)
0x0801..          a zlib stream
```

Inflating the stream yields the application image (about 32 MB for `AUDIO_BT`, about 40 MB for
`NAV`), a raw PowerPC image loaded at `0x01000000`. It is not encrypted. The header holds the
inflated size at offset `0x04` and no compressed size. The symbol map `SPYSTORE` copies off the
unit (`abs_symbols_base.txt.gz`) lines up exactly with the inflated image — every function
symbol lands on a PowerPC prologue (`stwu r1,-N(r1) ; mflr r0`) — which is what makes
symbol-level patching possible. `tools/unpack.py` inflates it; `patch_smeg.py` re-packs it and
walks the checksum cascade (`f_BigQuick.bin` → `.inf` → `smeg.inf` → `<module>_ctrl.bin` →
`ctrl.bin`, see [Boot and update chain](FLASH_CHAIN.md)).

## Addresses are per firmware version, not only per build

Every address on this page was read out of the **`SMEG_5.43.A.R2`** NAV image. `AGENTS.md`
already warns that addresses differ between the `AUDIO_BT`, `AUDIO_BT_256` and `NAV` builds.
They also differ between firmware *versions*, and by more than a few bytes.

Comparing the NAV application images from `SMEG_5.42.B.R4` (Nov 2016) and `SMEG_5.43.A.R2`
(Sep 2017):

| what | `5.43.A.R2` | `5.42.B.R4` | shift |
|---|---|---|---|
| `IsAUXSRCAvailable()` | `0x02247858` | `0x022477c0` | −152 |
| `C_MGR_SRC` setter (`Last_Source`) | `0x016977d0` | `0x01697738` | −152 |
| `C_MGR_SRC` SPY dump | `0x0169a2e4` | `0x0169a24c` | −152 |
| `C_MGR_SRC` class strings | `0x0300a6a4` | `0x0300a624` | −152 |
| `Time_Zone` string | `0x02fcc5f4` | `0x02fcc574` | −152 |

The two images are the same code **displaced by a constant 152 bytes**. That is why a naive
byte-for-byte comparison calls ~80% of the image different: it is mostly the shift, not new
code. Not everything is displacement though — the AUX handler region does not match verbatim
at any offset, so there are real changes there as well.

!!! warning "If your unit is not on 5.43.A.R2"

    The addresses in `patches/*.json` will be wrong for it, and writing to them would corrupt
    the image.

    **The `expect` bytes are not a sufficient guard.** Two entries in this repository match at
    the same address on the `5.42.B.R4` NAV image — `diagnostic-logging` and
    `diagnostic-logsink`, both at `0x010346d0` — because a short instruction sequence recurs
    across versions. On that image the expect check passes and the edit lands 152 bytes off.

    So every variant declares the version it was derived from:

    ```json
    "firmware": "5.43.A.R2"
    ```

    `patch_smeg.py` refuses unless the inflated image carries that token, which the vendor's own
    build path supplies (`E:/ccm_wa71/04_HMI_DEV-5.43.A.R2/...`). It reports the version it did
    find, so a mismatch explains itself:

    ```
    NAV: this image is not 5.43.A.R2 - refusing to patch.
      Addresses are per firmware version, and the expect-byte check is not a
      reliable substitute: short instruction sequences recur across versions.
      Build tokens found in this image: 5.42.B.R4.1
    ```

    Porting is mostly mechanical *for unchanged code* (subtract 152 here), but the AUX handler
    changed, so a 5.42 port needs that address re-derived from a 5.42 symbol table rather than
    shifted. Addresses must be re-derived per firmware version, not copied.

### `tools/symdiff.py` — find out which of that is mechanical

The tool works out the shift and separates the two cases that matter — moved-and-unchanged,
where the address follows from the displacement alone, from moved-and-changed, where it does
not:

```sh
python3 tools/symdiff.py --a old.bin old_symbols.txt --b new.bin new_symbols.txt
python3 tools/symdiff.py --a old.bin old_symbols.txt --b new.bin new_symbols.txt \
    --patch-addr 0x02247858
```

```
  shift        +152  (agreed by 3 of 3 moved symbols)
    identical  1184   a patch here moves by the shift alone
    changed    61     address carries over, bytes need re-deriving
```

It reads a symbol map in the same `<addr> <type> <name>` form `ppcdis`/`xref` do, because a
map one tool accepts and another rejects would be a trap.

**A derived address is a candidate, not a patch.** The tool prints that itself, and it is the
rule from `AGENTS.md`: an address without the `expect` bytes to back it is not safe to apply,
and `patch_smeg.py` refuses one that does not match anyway. Use this to know *where to look*,
then re-derive the `expect` bytes from the target image.

## Which build is this? `tools/fingerprint.py`

The version check above covers *which firmware*. The *build* — `AUDIO_BT`, `AUDIO_BT_256`,
`NAV` — is easy to get wrong by hand: **`AUDIO_BT` and `AUDIO_BT_256` declare identical patch
addresses and identical `expect` bytes**, so nothing in the patch data separates them.

`tools/fingerprint.py` reads the image and answers from the bytes:

```sh
python3 tools/fingerprint.py --image app_nav.bin
```

```
    image          39863376 bytes, already inflated
    build tokens   5.43.A.R2
    aux-autoswitch/AUDIO_BT     0/2 probes   firmware=5.43.A.R2
    aux-autoswitch/AUDIO_BT_256 0/2 probes   firmware=5.43.A.R2
    aux-autoswitch/NAV          2/2 probes   firmware=5.43.A.R2  <- match
    ...
    verdict: NAV
```

It exits non-zero when it cannot name a single build. Three outcomes, and only one is success:

| verdict | meaning |
|---|---|
| a build name | exactly one build's probes all match — exit `0` |
| `AMBIGUOUS` | several builds match, so the probes cannot choose between them — exit `1` |
| `UNKNOWN` | nothing matches; the build tokens actually present are printed — exit `1` |

**It refuses rather than guesses, by design.** On the firmware in this repository the
`AUDIO_BT` and `AUDIO_BT_256` variants are indistinguishable from the recorded addresses, so a
tool that picked one would make the same mistake a person would, silently. Verified by hand
against the `5.43.A.R2` NAV image, where it identifies `NAV` and rejects every `AUDIO_BT`
variant.

`patch_smeg.py` calls the same identification before patching. It stays quiet when an image
matches nothing, because the firmware-token check and the per-patch `expect` check already
report that precisely. What it adds is the wrong-*build* case, which otherwise surfaces as a
confusing byte mismatch:

```
NAV: this image is not the NAV build - refusing to patch.
  It matches: AUDIO_BT. Addresses are per build, so patching it with these addresses
  would write to the wrong locations. Run tools/fingerprint.py for a verdict.
```

The probes are the recorded `expect` bytes themselves, so a build only fingerprints as well as
the patch data for it is accurate. A build with no patch set here is still **named** from the
vendor build path inside its image (`build_tokens` in `fingerprint.py`'s output), but no patch
set can be selected for it: its addresses have to be derived first (see `tools/symdiff.py`
above).

## AUX availability: `aux-always-available`, `aux-autoswitch`

### `C_HMI_AUDIO_APP_BASE::IsAUXSRCAvailable()` — force available

Replaces the function prologue with `li r3,1 ; blr`, so AUX is reported available
regardless of vehicle config or signal. The AUX source stays selectable, no longer greys out
when there is no signal, and is always in the SRC cycle *(confirmed on hardware)*. It does not
make the unit switch by itself.

| build | address | original | patched |
|---|---|---|---|
| `AUDIO_BT`, `AUDIO_BT_256` | `0x02247718` | `94 21 ff a0` (`stwu r1,-0x60(r1)`) | `38 60 00 01 4e 80 00 20` (`li r3,1 ; blr`) |
| `NAV` | `0x02247858` | `94 21 ff a0` | `38 60 00 01 4e 80 00 20` |

```
li   r3, 1        # 0x38600001
blr               # 0x4e800020
```

`aux-always-available` is this edit alone. `aux-autoswitch` is this edit plus the one below.

### `HandleAudioAuxInputStatusChnged()` `+0x10c` — the inert second edit of `aux-autoswitch`

At `handler + 0x10c` the function returns early when `GetMediaDevice(AUX)` fails, before it
reaches `ActivateSource()`. This edit replaces that conditional branch with `nop`.

| build | handler | branch address | original | patched |
|---|---|---|---|---|
| `AUDIO_BT`, `AUDIO_BT_256` | `0x023031dc` | `0x023032e8` | `41 9e 01 4c` (`beq cr7,+0x14c`) | `60 00 00 00` (`nop`) |
| `NAV` | `0x0230331c` | `0x02303428` | `41 9e 01 4c` | `60 00 00 00` (`nop`) |

**It has no effect** *(executed)*. The branch is never taken: the AUX media device is
registered unconditionally at start-up, so `GetMediaDevice(AUX)` succeeds and the `beq` falls
through with or without the patch. Forcing the failure case does not help either —
`GetMediaDevice` writes nothing to its out-param when it fails, so the source-manager guard at
`0x02303468` returns one call later. The runs are in [Emulating the firmware](EMULATION.md).

The edit is kept in `aux-autoswitch` because that is the exact set flashed in the confirmed
boot-to-AUX build. The handler itself runs when the saved AUX input *setting* changes
(`Auxiliary_Status`, message `0xcb`), not when a signal appears *(read)*; see
[The AUX chain](AUX_CHAIN.md).

## Boot to AUX: `aux-boot-default` + `aux-boot-restore`

**Confirmed on hardware** (NAV, 2026-09-28): with both sets, plus `aux-autoswitch`, the unit
booted to AUX three times, and the spy capture of the last boot shows why
*(executed; see [Hardware verification](VERIFICATION.md))*. Each set alone still boots to FM,
as does `aux-boot-restore` without its `InitApp` edit *(executed on the car)*.
[`builds/aux-boot.json`](https://github.com/KRoperUK/smeg-plus-patches/blob/main/builds/aux-boot.json)
is the minimal build: exactly those three sets.

How the unit picks its boot source *(read, and `AddRequest` executed under emulation)*:

1. `C_MGR_SRC::StartUp` restores the saved `Last_Source` (a scheduler position) and
   `Last_Source_Priority` into `this+0xb4` and `this+0xac`, and starts a 7.5 s init timer.
2. As each source app starts, it requests its source. `C_MGR_SRC::AddRequest` adds a request's
   (`Sched_Pos`, priority) to the `ScheduledInit` table and compares it with the restored pair —
   **only if the request's `PrOnly` byte (`+0x28`) is clear**.
3. A match cancels the timer and selects that source. If nothing matches in 7.5 s, the timer
   falls back to position 1, the tuner.

On stock firmware AUX loses on two counts: its boot request carries `PrOnly` true, so it never
enters the table, and the saved `Last_Source` is whatever the unit last played. The two sets fix
one each.

### `aux-boot-default` — make the restore target AUX

`Last_Source` is not a fixed preference. `C_MGR_SRC::ImmediateSourceSave` (`0x01695d68`) writes
the active source back to it whenever the source changes, so a settings-database seed lasts only
until the next source change. This patch changes the restore instead of the saved value.

Inside `C_MGR_SRC::StartUp` the restore reads `Last_Source` and stores it, unvalidated, into the
field the scheduler later matches on:

```
0169948c  lwz  r9, 8(r1)        ; r9 = saved Last_Source
01699490  stw  r9, 0xb4(r31)    ; this+0xb4  (matched against each node's Sched_Pos)
01699494  stw  r9, 0x4cd0(r25)  ; global 0x035e4cd0 (mirror)
0169949c  stw  r9, 0xe4(r31)
```

Replacing the load with a constant pins the restore to position **7 (`POS_AUX`)**:

| build | address | original | patched |
|---|---|---|---|
| `NAV` | `0x0169948c` | `81 21 00 08` (`lwz r9,8(r1)`) | `39 20 00 07` (`li r9,7`) |
| `AUDIO_BT`, `AUDIO_BT_256` | `0x01699334` | `81 21 00 08` (`lwz r9,8(r1)`) | `39 20 00 07` (`li r9,7`) |

Emulated on the NAV image, with the saved value set to `1` (radio) *(executed)*:

| build | `this+0xb4` | global `0x035e4cd0` | `this+0xe4` |
|---|---|---|---|
| stock | 1 | 1 | 1 |
| patched | 7 | 7 | 7 |

The `Last_Source` line in the `C_MGR_SRC` spy trace is written just before this store
(`WriteMgrSrcSpy` at `0x01699488`), so it shows the **saved** value, not the patched one
*(read)*. The `AUDIO_BT` variants are the same instruction at the same offset in `StartUp`,
located with each build's own symbol map *(read)*; they have never been flashed.

### `aux-boot-restore` — let AUX's request take part in the restore

`PrOnly` is the `bool` argument of `C_HMI_SrcMgntBase::ActivateSource`. Two places pass `true`
for AUX: `C_HMI_MEDIA_APP_BASE::InitApp`, whose request is the one the boot restore sees, and
`HandleAudioAuxInputStatusChnged`, which re-requests AUX when the AUX input setting changes.
This set makes both pass `false`, and forces the restored priority to AUX's 20 so that AUX's
pair (7, 20) matches:

| build | address | original | patched |
|---|---|---|---|
| `NAV` | `0x022c0678` | `38 80 00 01` (`li r4,1`: the boot-time `ActivateSource(aux, true)` in `InitApp`) | `38 80 00 00` (`li r4,0`) |
| `NAV` | `0x02303474` | `38 80 00 01` (`li r4,1`: `ActivateSource(aux, true)` in `HandleAudioAuxInputStatusChnged`) | `38 80 00 00` (`li r4,0`) |
| `NAV` | `0x01699444` | `80 01 00 08` (`lwz r0,8(r1)`, the saved `Last_Source_Priority`) | `38 00 00 14` (`li r0,20`) |
| `AUDIO_BT`, `AUDIO_BT_256` | `0x022c0538` | `38 80 00 01` (`InitApp`) | `38 80 00 00` |
| `AUDIO_BT`, `AUDIO_BT_256` | `0x02303334` | `38 80 00 01` (the handler) | `38 80 00 00` |
| `AUDIO_BT`, `AUDIO_BT_256` | `0x016992ec` | `80 01 00 08` (`StartUp`) | `38 00 00 14` |

The `InitApp` site is the only one of `InitApp`'s six activations that passes `true`, so no
other source changes. Under emulation, `AddRequest` with `PrOnly` clear fills `ScheduledInit`
with (7, 20), sets the restore flag (`+0x3c0`) and cancels the init timer, and does none of that
with `PrOnly` set *(executed; `tests/test_firmware_nav.py`)*.

The `AUDIO_BT` addresses are not the NAV ones moved by the image-wide shift (−344): the media
app's functions sit at −320, so each site is the same offset in the same function, found with
the build's own symbol map. `InitApp` has the same six activations with only the fifth passing
`true`. On both `AUDIO_BT` images the same `AddRequest` runs give the same results, and the
patched handler passes `PrOnly` 0 where stock passes 1 *(executed;
`tests/test_firmware_audio_bt.py`)*. Neither variant has been flashed.

On the car, the capture of a boot with both sets shows AUX's request with `PrOnly` false,
`POS_AUX` (7, 20) in `ScheduledInit`, and AUX acknowledged in the same millisecond it asked,
while the saved `Last_Source` was 1 — so `aux-boot-default`'s override made the match
*(executed)*.

After boot, a second AUX request is forced to the front (`ForceSchedulerPosition`). The handler
sends one only when the AUX input setting goes from zero to non-zero, so this does not switch
to AUX when audio starts. One more AUX activation path exists outside this set:
`HandleMediaStateReady`, with a computed `PrOnly` at `0x02306a18`. Whether it ever runs for AUX
is *not known*; boot to AUX works without touching it. See
[How HMI apps request sources](HMI_SOURCES.md).

## Not pursued: `aux-sticky`, `aux-signal-switch`

Both are **candidates, verified under emulation only and never flashed**. The owner is happy
with boot to AUX and is not pursuing a switch to AUX when audio starts.

### `aux-sticky`

Two edits in `HandleAudioAuxInputStatusChnged()`:

| offset | original | patched | effect |
|---|---|---|---|
| `+0x10c` (AUDIO_BT `0x023032e8`, NAV `0x02303428`) | `beq` | `nop` | the inert edit above, kept so the set is a superset of `aux-autoswitch` |
| `+0x118` (AUDIO_BT `0x023032f4`, NAV `0x02303434`) | `beq cr7,+0x58` | `beq cr7,+0x140` | when the AUX input setting is zero, branch to the shared return path instead of the release branch |

The second edit means that once AUX has been activated it stays selected until the user
changes source. It follows the saved AUX input setting, so on its own it does not address
intermittent audio on the AUX input *(inferred)*. The condition is kept and only the target
changes; an unconditional `b +0x140` would make the activate path below unreachable.
`tests/test_patch_definitions.py` refuses any edit that turns a conditional branch into an
unconditional one unless `why` says so.

Emulated on all three images (`NAV`, `AUDIO_BT`, `AUDIO_BT_256`), with the call targets decoded
from each build's own `lis`/`addi` pairs *(executed)*:

| bytes at the branch | setting becomes non-zero | setting becomes zero |
|---|---|---|
| `419e0058` stock | activates | releases |
| `419e0140` patched | activates | does not release |

The handler lives at `0x0230331c` on `NAV` and `0x023031dc` on both `AUDIO_BT` variants, and the
offsets within it (`+0x10c`, `+0x118`, `+0x258`) are the same in all three.

### `aux-signal-switch` — switch to AUX when its signal appears

Stock firmware has no switch-on-signal path. The AUX handler runs on the *setting* event
(`0xcb`) and tests the setting, and the media app drops the *signal* event (`0xcc`)
*(read)*. This set changes both:

| build | edits | what |
|---|---|---|
| `NAV` | `0x02303378`, `0x0230338c`, `0x02303398`, `0x0230342c` | `HandleAudioAuxInputStatusChnged` calls `Get_AUX_signal_status` instead of `Get_aux_status`, and reads its `bool` result |
| `NAV` | `0x02309628`–`0x02309648` (8 words) | `HandleDBUSMessage` gains a `0xcc` case going to the same handler; every other id is routed as before |

The exact bytes are in [The AUX signal path](AUX_SIGNAL.md). Under `tools/ppcemu.py` on the
NAV image *(executed)*: the patched handler activates AUX when the signal appears and releases
it when the signal is lost; with `aux-boot-restore` the activation passes `PrOnly` 0; with
`aux-sticky` the release is suppressed; the dispatch sends `0xcc` to the handler and every
other id where stock sends it. Whether the unit measures AUX while another source plays is
*not known*; if it does not, this cannot switch away from FM.
`builds/aux-signal-switch.json` is the car build.

## `SPYSTORE` backups: `spy-dump-userdata`, `spy-dump-userdata-partition`

### `spy-dump-userdata` — SPYSTORE also backs up `/USER_DATA`

**Confirmed on hardware** (NAV, 5.43.A.R2, 2026-09-14): with this patch flashed, `SPYSTORE`
with a stick inserted produced a dump (`SPY/02_.../`) containing the full
`/USER_DATA/user_data/` tree — `sqlite/` (14 databases with their `.inf` CRC sidecars),
`Audio/` (`Tuner.dat`/`Radio.dat` presets), and `Nav/`, `TTS/`, `T2BF/`. The files are the
live copies: `nav_dest.sqlite` is a valid SQLite file, and `up_common.sqlite`/`up_user.sqlite`
are stored **gzip'd** (`1f8b …`), which is how the unit keeps them on disk (the boot log's
`gzUnixRead`).

`connectivity.sqlite` is **not** captured: it is not a file under
`/USER_DATA/user_data/sqlite/` — the boot log shows it is imported from the system partition
(`connectivity imported from system`) — so **paired phones are out of scope** of this backup.
Navigation destinations (`nav_dest.sqlite`), radio presets (`Audio/*.dat`) and general
settings (`up_common`) *are* captured.

`C_BCM_SPY::CallBackCopy` (NAV `0x01273734`) is the routine `SPYSTORE` runs to copy the spy
directory out to a stick. It is a sequence of `Get<X>Dir` source getters each followed by
`C_FS_STORAGE_CTRL_IO::Xcopy(source, dest)` into a timestamped folder on the stick
(`<stick>/SPY/<timestamp>`); see [Cheatcodes](CHEATCODES.md). None of those sources is the
live settings partition, so a stock collect never captures the user's databases.

The firmware already exports the primitive that fixes this:
`C_FS_STORAGE_CTRL_PATH::GetUserDataDir` (`0x0105ae44`) points an entity at
`/USER_DATA/user_data/`. So the added copy is one more block of exactly the existing shape:

```
GetUserDataDir(r29)     ; r29 = /USER_DATA/user_data/  (source)
Xcopy(r29, r31)         ; r31 = <stick>/SPY/<timestamp> (dest)
```

`CallBackCopy` has no spare space, and there is **no usable code cave inside `.text`** (see
the note below). So the patch is **cave-free**: it overwrites the last of the two
calibration-copy blocks — the `*regen*` one — in place. That 48-byte block is more than the
nine instructions the replacement needs.

| build | address | original (`*regen*` copy) | patched |
|---|---|---|---|
| `NAV` | `0x01273a1c` | `GetCalibrationDataDir ; AddName "*regen*" ; Xcopy` (12 instr) | `GetUserDataDir(r29) ; Xcopy(r29,r31) ; nop×3` |

```
lis   r9, 0x106          # 3d200106
addi  r9, r9, -0x51bc    # 3929ae44   -> r9 = GetUserDataDir (0x0105ae44)
mtctr r9                 # 7d2903a6
mr    r3, r29            # 7fa3eb78   -> source entity
bctrl                    # 4e800421   -> GetUserDataDir(r29)
mr    r3, r29            # 7fa3eb78   -> source
mr    r4, r31            # 7fe4fb78   -> dest (stick SPY/<timestamp>)
mtctr r26                # 7f4903a6   -> r26 still holds Xcopy (0x010554f4)
bctrl                    # 4e800421   -> Xcopy(r29, r31)
nop ; nop ; nop          # 60000000 ×3
```

Why this is safe to write in place:

- `r29` (the source entity) and `r31` (the destination) are callee-saved registers and are
  live here — the original block uses both at this exact point.
- `r26` already holds `Xcopy` (`0x010554f4`): the very block being replaced does `mtctr r26`
  for its own `Xcopy`, so the value is guaranteed valid, and the replacement does not reload it.
- The trailing `nop`s keep `Xcopy`'s return in `r3` intact for the `cmpwi r3,-1` at
  `0x01273a4c` that follows, so the function's existing success/error handling is unchanged.

Verified by round-tripping the bytes through `capstone` and by `tests/test_spy_dump_userdata.py`,
which decodes the `lis`/`addi` pair to confirm the callee is `GetUserDataDir` and applies the
shipped definition end-to-end through `patch_smeg.py`.

!!! note "Trade-offs"

    - **The dump loses the `*regen*` calibration files** in exchange for the `/USER_DATA`
      backup. That is the cost of staying cave-free.
    - **NAV only.** `AUDIO_BT`/`AUDIO_BT_256` have a different `CallBackCopy` address; derive
      it from each build's own image before adding those variants.
    - This reads `/USER_DATA` but does not write it, so it cannot damage the user partition —
      unlike a `USER_DATA` *payload* build.

!!! note "Why a trampoline is out of reach, and what would change that"

    Every run of 32 bytes or more of nops/zeros in the image lies in `.rodata` —
    `CMMStrBufEncodedUTF8`'s table, `sqlite3_version`, `utf8proc_sequences` and friends — so it
    is live data, not padding. Text ends at `0x02def4c0`.

    A trampoline would therefore have to live **past the end of the image**, and that is
    mechanically expressible rather than impossible: the container header carries the
    **inflated size at offset `0x04`** (`0x02604450` on this NAV image, verified) and **no**
    compressed size, because the zlib stream is self-delimiting. The image can be grown and
    that field updated. Whether the loader maps the appended region **executable** is
    *not known*, so a trampoline is theoretical.

### `spy-dump-userdata-partition` — the whole partition (does not work)

**Flashed, and the copy did not land** *(observed)*. This set was in the 2026-09-27 and
2026-09-28 car builds and `SPYSTORE` was run after each. The stick's `SPY/<stamp>/` folder from
the 2026-09-28 run, checked in full, holds the normal collect and no `USER_DATA` tree; the
calibration `*.log` and `*regen*` files are gone, as the edit removes them. Why `Xcopy` of the
device root copied nothing is *not known*. Use `spy-dump-userdata` for a settings backup.

The idea: `spy-dump-userdata` captures `/USER_DATA/user_data`, and its **siblings** are
separate directories on the same storage device:

```
/user_data          <- what spy-dump-userdata gets: settings, nav destinations, presets
/address_book       /internet_user   /welcome_screen
/picture_cache      /catalog         /TurboBoot
```

The path-fragment table at `0x02f08418` shows each `C_FS_STORAGE_CTRL_PATH::Get*Dir` is only
`SetDevice(<device>) + SetPartition(n) + AddName("<fragment>")` *(read)*, so device + partition
with no name should be that device's root. `GetUserDataDir` is `USER_DATA`, partition 4,
`/user_data`; `GetAddressBookDir` is the same device and partition with `/address_book`.

So this patch rebuilds the source entity as the root — fresh constructor,
`C_FS_STORAGE_DEVICE_USER_DATA::Instance()`, `SetDevice`, `SetPartition(4)`, deliberately no
`AddName` — and copies that:

```asm
mr    r3, r29            # source entity
mtctr r23                # r23 = C_FS_STORAGE_ENTITY::C1 (0x01068d24), already loaded
bctrl                    # fresh entity: no names, so it is the device root
lis   r9, 0x0106
addi  r9, r9, 0x702c     # -> USER_DATA::Instance() (0x0106702c)
mtctr r9
bctrl
mr    r4, r3
mr    r3, r29
lis   r9, 0x0107
addi  r9, r9, -0x773c    # -> SetDevice (0x010688c4)
mtctr r9
bctrl
lis   r9, 0x0107
addi  r9, r9, -0x76d4    # -> SetPartition (0x0106892c)
mtctr r9
li    r4, 4
mr    r3, r29
bctrl
mr    r3, r29
mr    r4, r31
mtctr r26                # r26 still holds Xcopy (0x010554f4)
bctrl
nop ×7                   # pads the reclaimed 120 bytes
```

| build | address | replace | patched |
|---|---|---|---|
| `NAV` | `0x012739dc` | 120 bytes — the calibration `*.log` block **and** the `*regen*` block, ending just before the `SYSTOOL_PlayBeep_Spy` setup at `0x01273a54` | the routine above |

Its call sequence was executed under `tools/ppcemu.py`, with every callee stubbed
*(executed)*:

| | call sequence through the copy blocks |
|---|---|
| stock | `… GetApplicationDir, Xcopy, GetCalibrationDataDir, Xcopy, GetCalibrationDataDir, Xcopy` |
| patched | `… GetApplicationDir, Xcopy, USER_DATA::Instance, SetDevice, SetPartition, Xcopy` |

That proves the control flow and the call targets, not what `Xcopy` does with a device root on
the unit — which, on the evidence above, is nothing that reaches the stick.

It overwrites the same `0x01273a1c` block as `spy-dump-userdata`, so the two cannot both be
applied: the `expect` check refuses the second. NAV only.

## Diagnostic logging: `diagnostic-logmask`, `diagnostic-logsink`, `diagnostic-logging`

!!! danger "Not for driving"

    These are diagnostic builds. With logging enabled the firmware formats a message on every
    path it takes. **Do not drive on them**, and flash a normal build afterwards. Never flash
    `diagnostic-logging` together with `diagnostic-logmask` (below).

The application's logging has **no output path** in this build *(read and executed)*:

- `Log_msg` (`0x02742558`) returns at a gate unless `(GetLogMask() & level) != 0`.
  `GetLogMask` (`0x02742530`) reads one global at `0x036d42a8`, which is past the end of the
  image (`0x03604450`) — BSS, so zero at boot. Exactly one instruction writes it, reachable
  only through ten `SetTrace` wrappers that are vtable entries, so nothing in the ordinary
  start-up path turns logging on.
- Past the gate, `Log_msg` makes one more call: to `0x010346d0`, the **sink**, which the vendor
  shipped as `li r3,0 ; blr`. The ~6700 call sites that call `dummyLogMsg` directly end at the
  same no-op, because `dummyLogMsg` *is* `0x010346d0`.

So a working diagnostic needs **both** the mask forced and the sink pointed at something that
writes: `builds/diagnostic-logging.json` is `diagnostic-logmask` + `diagnostic-logsink`. Where
`logMsg` output surfaces on the unit — serial, telnet, a file, or nowhere reachable — is
*not known* (issue #94); none of these three has been flashed.

The reason it would be worth having: `HandleAudioAuxInputStatusChnged` logs its own name at
level 1 on its **shared return path**, which every one of its exits and its success path reach
*(executed)*:

```
0230331c  HandleAudioAuxInputStatusChnged()
  …
  02303574  li  r3, 1                 ; level
  0230357c  addi r4, r9, -0x2948      ; "HandleAudioAuxInputStatusChnged() -\n"
  02303590  bctrl Log_msg
```

With logging readable, that line would show whether the handler ran on a given event.

### `diagnostic-logmask` — force the trace mask

| build | address | original | patched |
|---|---|---|---|
| `NAV` | `0x02742530` | `94 21 ff f0 93 e1 00 0c` (prologue) | `38 60 ff ff 4e 80 00 20` (`li r3,-1 ; blr`) |

`GetLogMask` returns all ones, so the ~5900 call sites that go through `Log_msg` run to
completion instead of returning at the gate. Same idiom as the `IsAUXSRCAvailable()` patch —
overwrite a prologue with a constant return, no code cave, trivially reversible. Emulating
`Log_msg`: with the mask at 0 it bails after 47 instructions; forced, it runs 271 and calls its
sink *(executed)*. On its own it produces no output, because the sink is the no-op.

### `diagnostic-logsink` — point the sink at VxWorks `logMsg`

The caller passes a format string in `r3` and up to six arguments in `r4`–`r9`, which is
exactly VxWorks `logMsg(fmt, a1…a6)`.

**`logMsg` is at `0x00484a94`.** `BSP/SMEG_PLUS_512/vxWorks.bin` is a raw PowerPC image that
begins with a function prologue at offset 0 and carries a **VxWorks symbol table**: 20-byte
entries holding a pointer to the name and then the address. Read at a load base of
`0x00200000` the table is self-consistent, and the base is confirmed independently — the
application's own call into the kernel at `0x0058c248`, the one `IsAUXSRCAvailable()` makes on
its failure path, is named `tickGet` by that table at exactly that address.

| build | sink | original | patched |
|---|---|---|---|
| `NAV` | `0x010346d0` | `38 60 00 00` (`li r3,0`) | `4b 45 03 c4` (`b 0x00484a94`) |
| `AUDIO_BT`, `AUDIO_BT_256` | `0x01034578` | `38 60 00 00` | `4b 45 05 1c` (`b 0x00484a94`) |

The displacement is about −11.7 MB, inside the 24-bit branch range, so no code cave is needed.
The `blr` after the patched instruction becomes unreachable, which is harmless: `logMsg`
returns to `Log_msg`'s caller itself. Emulated, the patched sink jumps to `0x00484a94` and the
emulator reports an unmapped fetch — expected, since that address is in the kernel rather than
the application image. That confirms the branch target and nothing more *(executed)*.

### `diagnostic-logging` — point the sink at `Log_msg` (do not use with the mask)

`dummyLogMsg` at `0x010346d0` is literally:

```
010346d0  li  r3, 0
010346d4  blr
```

This patch replaces that instruction with a branch to the real logger:

| build | address | original | patched |
|---|---|---|---|
| `NAV` | `0x010346d0` | `38 60 00 00` (`li r3,0`) | `49 70 de 88` (`b 0x02742558`) |

`Log_msg` wants `r3` = level and `r4` = format, and the caller has already set both, so the
branch passes them straight through. The two functions are 24 174 216 bytes apart, inside the
24-bit branch range.

On its own it emits nothing: every redirected site lands in `Log_msg` and returns at the mask
gate. **With `diagnostic-logmask` it is worse**: `0x010346d0` is the sink `Log_msg` itself
calls, so `Log_msg` calls the sink, the sink re-enters `Log_msg`, and so on, on every log call
in the firmware. Emulated, one call re-enters `Log_msg` three times before unwinding
*(executed)*. Use `diagnostic-logsink` for the sink instead.

## Adding your own patches

`patches/*.json` is data-driven:

```json
{
  "name": "my-patch",
  "description": "what it does, why, and what has been verified",
  "summary": "one line of Markdown for the status table",
  "status": {"state": "never-flashed", "label": "Never flashed", "note": "decoded only"},
  "variants": {
    "NAV": {
      "app_image": "NAV/AppBin/f_BigQuick.bin",
      "inf": "NAV/AppBin/f_BigQuick.bin.inf",
      "smeg_inf": "NAV/smeg.inf",
      "ctrl": "NAV_ctrl.bin",
      "base": "0x01000000",
      "patches": [
        {
          "addr": "0x02247858",
          "expect": "9421ffa0",
          "bytes": "386000014e800020",
          "why": "...",
          "disasm": "li r3, 1 ; blr"
        }
      ]
    }
  }
}
```

`expect` is checked before writing, so a mismatched firmware build fails loudly instead of
being corrupted.

`status.state` is one of `confirmed`, `flashed`, `never-flashed`, `falsified` or `diagnostic`.
After adding a set, or when a car test changes its status, run `python3 tools/patch_status.py`
to regenerate the table above and the landing-page panel; a test fails while they are stale.

### `data` — an edit that is not code

Every edit is checked to decode as whole PowerPC instructions. An edit to a string or a table,
such as the ring tone names `media.names` generates, sets `"data": true` to skip that check;
`expect` is still verified first.

### `disasm` — pin the instructions, not just the bytes

`disasm` is optional and asserts what the patched site must decode to. Without it the tool
still disassembles every patched site and prints it, and still asserts the bytes decode to
whole, valid PowerPC instructions — so a `bytes` string that is corrupt or truncated is
caught. `disasm` goes further and pins the exact intent, which matters because the hex is
unreadable at a glance and `why` is prose a machine cannot check:

```
    NAV            0x02247858  9421ffa0 -> 386000014e800020
                     li r3, 1 ; blr
```

Anything that does not match stops the run.

Disassembly needs [`capstone`](https://www.capstone-engine.org/), which is in the `dev`
extra. **The check is skipped, not faked, when it is absent** — this tool declares no
dependencies and has to keep running on a machine with nothing but the standard library, so
it returns nothing rather than passing silently.

## The run verifies what it wrote

`patch_smeg.py` does not trust its own output. After writing, it **re-reads every file from
disk** and closes the loop:

- re-inflates the packed `f_BigQuick.bin` and confirms each patched site holds the new bytes,
- recomputes the CRC32 of each file and checks the `.inf` sidecars declare it,
- checks the module `ctrl` records those CRCs, and that `ctrl.bin` records the module's,

then prints the whole chain:

```
    crc chain      verified end to end
      f_BigQuick.bin      0x7ce25274
      f_BigQuick.bin.inf  0x0fd24c96
      smeg.inf            0xcce0fb84
      NAV_ctrl.bin        0xd3a50ee5
    ctrl.bin       name=verified (1)
```

In-memory checks alone would miss a write that did not land, or landed twice.

## Resulting file checksums

Because the compressed stream is rebuilt, the resulting `f_BigQuick.bin` CRCs depend on
the zlib implementation/level and are not stable values to match against. Recompute them
with the tooling and propagate through the cascade (the tool does this automatically).
