# Cheatcodes and the spy/diagnostics system

## The cheatcode list is data

The codes are not compiled in. They live in the media partition at
`Data_base/sqlite/cheatcodes.sqlite`, table `cheatcodes`:

```sql
CREATE TABLE cheatcodes (
  name VARCHAR(50) PRIMARY KEY,
  is_displayable INT DEFAULT 0,
  is_configurable INT DEFAULT 0,
  max_params_number INT DEFAULT 0,
  is_official INT DEFAULT 0,
  is_synchronous INT DEFAULT 0,
  is_available_in_release INT DEFAULT 1,
  CCOD_PATH TEXT
);
```

!!! danger "Three codes destroy data"

    - **`CATCLN`** resets the media catalogue and picture databases, deletes the picture cache,
      and renames the **jukebox directory** to the firmware's "to remove" directory *(read)*.
      Music copied onto the unit's jukebox is very likely lost *(inferred: the rename target
      is the directory the firmware deletes from; the deletion itself was not followed)*.
    - **`SPYCLN`** deletes the whole spy directory, including any `TAR/*.tar.gz` capture that
      has not yet been copied off with `SPYSTORE`, and clears the exception store *(read)*.
      Run `SPYSTORE` first if a capture matters.
    - **`MSDREFRESH ON`** deletes the `SD_regen*` files from the calibration directory, writes a
      new `SD_regen.inf` and **reboots** *(read)*. What the next boot then does to the map card
      is not known.

    No other code read here writes to the `USER_DATA` settings databases.

Every row below comes from a close reading of the stock NAV `5.43.A.R2` image and of the
libraries in its media partition. The libraries are relocatable PPC ELFs, and their
relocations name every application function they call, so what each code does is **read**,
not guessed from its name. Nothing was run on the car except where a row says so.

| code | params | what it does | reboots? | writes | tier |
|---|---|---|---|---|---|
| `SPYTAKE` | 0 | the full **user spy collect** (see [below](#what-a-collect-captures)) | **yes** | spy dir `TAR/<stamp>-USER.tar.gz` | read; the reboot is also observed on the car |
| `SPYSTORE` | 0 | `C_BCM_SPY::DirectCallCopy("/bd0")` → `CallBackCopy`: copies the traces, spy dir, symbol maps and calibration logs to `<stick>/SPY/<stamp>` | no | the USB stick only | read; observed on the car |
| `SPYCLN` | 0 | deletes and recreates the spy dir, then `mmf_exc_clean()` | no | **deletes spy captures** | read |
| `REBOOT` | 0 | stops any micro-SD refresh, closes storage, reboots (`EmergencyReboot()` as fallback) | **yes** | none found | read |
| `CATCLN` | 0 | `RestoreDataBase`/`SaveDataBase` on `media_catalog`, `media_cdc_catalog`, `media_jkb_catalog`, `Pictures`; deletes the picture cache; moves the jukebox dir aside | no | **media databases, picture cache, jukebox** | read; the music loss is inferred |
| `MSDREFRESH` | 1 | `STOP` stops a refresh; `ON` deletes `SD_regen*`, writes `SD_regen.inf` and reboots; anything else reports progress | **yes**, for `ON` | calibration dir | read |
| `HWINFO` | 0 | hardware info and memory-partition statistics | no | none | read |
| `SWINFO` | 0 | software release, GUI version, symbol-table lookups | no | none | read (calls) |
| `ZAINFO` | 0 | `SYSTOOL_GetEOLInfo()`, formatted | no | none | read |
| `AUDIOINFO` | 0 | `C_MODULE_AUDIO::Get_audio_info` and the Arkamys configuration | no | none | read |
| `TUNERINFO` | 0 | radio debug data, band, DAB quality and service info | no | none | read |
| `BTINFO` | 0 | Bluetooth RSSI, SNR, and connected and media device info | no | none | read |
| `NETINFO` | 1 | connectivity `netinfoCheatCode` | no | none found | read |
| `PING` | 1 | connectivity `pingCheatCode(host, n, out)` | no | none found | read |
| `SYSMON` | 0 | boot-monitor averages (CPU, RAM, GPU RAM, NAND, USB, SD) written to a spy file | no | spy dir | read (calls) |
| `MMIMON` | 0 | MMI CPU-load monitor: start, stop, read | no | none found | read |
| `FPS` | 0 | frame-rate overlay; can log to `/tgtsvr/FPSPLogs.txt` | no | a host path only | read (calls, strings) |
| `MIRE` | 1 | display test pattern | no | none found | read (calls) |
| `AFTT` | 0 | `C_MODULE_TUNER::Cmd_cheat_code_AFTT_triggered()`, the AF tracking tool | no | not followed | read (call only) |
| `ARKBYP` | 0 | `C_MODULE_AUDIO::Cmd_cheat_code_Arkamys_Bypass()` | no | not followed | read (call only) |
| `BT0DB` | 0 | `C_BCM_T2BF::CmdSetTestChannelPower0(39)`, a Bluetooth RF test | no | not known | read (call only) |
| `BTSTARTER` | 1 | `"1"` → `C_BCM_T2BF::CmdSetTestMode(true)`, else `false` | no | not known | read |
| `BT` | 2 | **stub**: `li r3,0; blr` | no | nothing | read |
| `BTADC` | 2 | **stub**: `li r3,-1; blr` | no | nothing | read |
| `ECSAVE` | 1 | **stub**: `li r3,-1; blr` | no | nothing | read |
| `GPSINFO`, `SIMSPEED`, `MAPSPEED`, `GUIDBG` | — | **no library on NAND**, and none in the `M49RG20` map update | — | — | read (absence) |

`BT0DB` and `BTSTARTER` put the Bluetooth chip into RF test modes. Expect them to disrupt
phone connections until a reboot *(inferred from the names of the functions they call)*.

### How a code is found and run *(read)*

1. **Lookup.** `C_BCM_Cheat_Code::Activate` (`0x01604154`) looks the name up with
   `... FROM cheatcodes WHERE name='%ws' AND is_available_in_release=1`.
2. **Location.** **`CCOD_PATH` is never read.** It is not in the query, and the string does
   not occur anywhere in the image. `StartCheatCode` (`0x01603ac8`) finds
   `libcheatcode_<NAME>.out` through `GetCheatcodesPathList` (`0x0105c724`), which searches
   `<ApplicationDir>/CCOD/` and then `<NavigationApplicationDir>/CCOD/`. It loads the library
   with `MMdlopen` and calls its `Activate`. The database's `CCOD_PATH` values (`NAND` for most codes,
   `MICRO_SD` for `GPSINFO`, `SIMSPEED` and `MAPSPEED`) are therefore metadata only; the four missing codes would load only if the navigation directory held
   them *(not known)*.
3. **Parameters.** `CheckConfiguration` (`0x016040a4`) requires the parameter string to be
   **40 characters or fewer**. When `max_params_number` is non-zero, the string must hold
   **exactly** that many `;`-separated fields.
4. **Running.** A synchronous code is run inline, and its text is shown if `is_displayable`.
   Any other code runs on a task, `ThCheatCode`, and reports back over DBUS. Only one code
   runs at a time. `is_displayable = 0` only means the code is not listed on the entry
   screen; it can still be typed.

Each library ships beside a `.out.inf` and a `.out.txt.gz` symbol map. A loader string,
"Symbols file of CCCOD [%s] is not aligned with application", suggests the map is checked
against the application *(inferred from the string; not followed)*.

!!! failure "Corrections to this page"

    - **`SPYTAKE`** was described as an "audio long-event spy hook". It is the full user
      collect followed by a reboot. The old description came from the name of its entry
      function, `DirectCallAudioLongEvent`, not from following the call.
    - **`CCOD_PATH`** was presented as where each library lives. The application never reads
      it. The column was taken to be meaningful because it exists in the schema.
    - **All 29 codes** were listed as usable. Only 25 libraries ship, and three of those are
      empty stubs.

## How you get to the entry screen

- The screen is `C_HMI_CONFIG_EngineModeCheatCode_VKB_Z1` (a virtual keyboard) plus
  `C_HMI_CONFIG_CheatcodeFormat_MNU_Z1`.
- The Config app registers it at runtime:
  `C_HMI_CONFIG_EngineModeCheatCode_VKB_Z1::C1(...)` then
  `C_HMI_MENU_MGR::RegisterScreen(0x5601, state)` — `0x5601` = screen id **22017**.
- The menu tree (`desktopServices.sqlite` -> `current_menu`) has item **22017
  'Cheat Code'**, but it is a *root* item (`parent_item_ID = 65535`) with
  `key_event_keycode = 0`, and it is **not** a child of **22000 'Config Sec View'**
  (what the carrousel "Config" entry opens). So it never appears in Settings, and it
  has no shortcut key.
- The only hard-coded trigger is `C_HMI_CONFIG_APP_BASE::HandleKeyboardMessage`, which
  calls `StartCheatCodeSession()` on virtual key **`0x54`** while the Config app has
  focus. That constant is firmware-only; it maps to no DB entry.
- Launch path: `CheckCheatCode()` -> `C_BCM_HMI_CHEAT_CODE_CLIENT::exists()` /
  `is_displayable()` -> `LaunchCheatCode()` -> `activate()`, over DBUS
  `com/MM/BCM_CHEAT_CODE` (`BCM_cheatcode_SERVER`).

!!! success "There is a way in — observed on a car, 2026-09-14"

    **Holding the RADIO / MEDIA button opens the entry screen.** This section previously
    concluded there was no user-facing route, and that was wrong. The hard-coded trigger is
    virtual key `0x54` while the Config app has focus, so the RADIO/MEDIA long-press is very
    likely what that key is — which is direct evidence for issue **#23**, and means the codes
    are reachable today without the #22 menu work.

    Practical consequence: `SPYSTORE` can be run without patching anything, and it copies the
    spy directory out to removable storage. What lands there is more than logs:

    - the updater's `/SYSTEM_TMP_DATA/spy/UPG/UPG_log.txt` (rotated) — see
      [Hardware verification](VERIFICATION.md)
    - **`abs_symbols_base.txt.gz`** (98 365 lines) and **`symbols_bsp.txt.gz`** (22 497) — the
      application and BSP symbol tables that `tools/ppcdis.py`, `xref.py` and `callers.py`
      resolve names from. They are what `AGENTS.md` means by "patch by symbol, not by pattern",
      and `SPYSTORE` is a way to obtain them.
    - a task/exception capture from the last boot, which is how the unit's own settings
      (`CMMUPKeys::ShowStatus`, 271 keys) can be read without the UI.

Net: the entry screen is reachable by holding **RADIO / MEDIA**; the menu path is still
absent, so see issue **#22** if that should be fixed properly, and **#23** for confirming that
virtual key `0x54` is this button.

## The spy system

`C_BCM_SPY` / `C_BCM_SPY_List` / `C_BCM_SPY_Elem` implement per-module ring buffers of
text lines, registered at runtime:

```
C_BCM_SPY::SetConfiguration(id, name, t_SpyBufferType, size, n, m, enable)
C_BCM_SPY::WriteData(id, ptr, len)
```

Compiled flags: `__HIFI_SPY_TO_DISK__ = YES`, `__HIFI_SPY_MEMORIZED_ENABLED__ = NO`,
`__HIFI_SPY_NEW_SETCONF_API__ = NO`.

Spy output lives on the unit under `/SYSTEM_TMP_DATA/SPY/` — e.g.
`spyAudio_%lu.bin.gz`, tuner-DAB dumps (`DmpEvn_*.dat`, `DmpFic_*.dat`,
`EPG_*.bin`), `log_error.txt`.

What `SPYSTORE` actually does:

```
libcheatcode_SPYSTORE.out : Activate()
  -> C_BCM_SPY::DirectCallCopy(std::string const&)     # "/bd0" (see note below)
     -> C_BCM_SPY::CallBackCopy(std::string const&)    # NAV 0x01273734
        -> C_FS_STORAGE_CTRL_PATH::GetUnknownDir()      # removable media target
        -> Mkdir + GetSpyFolderName                     # dest = <stick>/SPY/<timestamp>
        -> Copy (GetTracesFile)                         # traces.bin
        -> Xcopy (GetSpyDir)                            # /SYSTEM_TMP_DATA/SPY ring buffers
        -> Xcopy (GetApplicationDir + "/PKG/*.*")       # the abs_symbols_*.gz maps
        -> Xcopy (GetCalibrationDataDir + "*.log")      # calibration logs
        -> Xcopy (GetCalibrationDataDir + "*regen*")    # SD-regen files
```

`C_BCM_SPY::CopyTraces(t_bcm_spy_files)` is the sibling entry point. Each copy step is the
same shape — a `Get<X>Dir` source getter, an optional `AddName` glob, then
`C_FS_STORAGE_CTRL_IO::Xcopy(source, dest)` (`0x010554f4`) into the timestamped stick
folder. Verified by disassembly (`tools/ppcdis.py`) against the 5.43.A.R2 NAV image.

The argument used to be given here as "an empty string in practice". The close reading of
the `SPYSTORE` library found it passing `"/bd0"` *(read)*. The destination comes from
`GetUnknownDir()` either way, so the copy behaves as described.

### What a collect captures

`SPYTAKE` is the way to get a module's runtime trace. How to get a capture off the unit and
read it is [the test loop](FLASHING.md#the-test-loop-end-to-end); a capture holds the VIN and
personal data, so keep it private. It runs the **user collect** *(read)*:

1. **Trigger.** `SPYTAKE` → `DirectCallAudioLongEvent` → `CallBackUserSpyEvent` raises event
   `0x52d1`. `C_BCM_SPY::HandlePrivateMessage` (`0x01279010`) then runs case 2,
   `CommonCollectSpy("-USER")` (`0x01277634`). Front-panel key event **`0x40a`** in
   `C_BCM_KIM::HandleKbdEvent_NotDiag_NotEC_15` (`0x014dcc58`) raises the same event. Which
   physical key that is, is not known.
2. **Build a RAM disk.** `/RAMDISK_SPY` is sized at 2 × the total buffer size + `0x277000`
   bytes, capped at 10 MB.
3. **Write the snapshots.** Into the RAM disk go: a beep, a task report, a screenshot, and
   every enabled module buffer as `RAMDISK_SPY/<id %05d>/<stamp>.bin`. Then the `EXC` and
   `REBOOT` trace copies, `FS_STORAGE_CTRL`, task tracebacks, `MONITOR/WakeUp` and
   `MONITOR/RunTime`, and `FILES/SQLITE/diag_zi.sqlite`, which is a copy.
4. **Archive it** to `<SpyDir>/TAR/<stamp>-USER.tar.gz`.
5. **Reboot.** It sets context `0x52d3` to 1, and
   `C_BCM_FAILSOFT::EvtHandlerRebootReqSpy` (`0x015a833c`) reboots.

`SPYSTORE` then copies the spy dir, `TAR` included, to the stick. **No trace switch is
needed.** Every buffer registration found passes `enable = 1`, and almost all set the
starter bit a user collect uses *(read)*. `traces.bin` is the exception log from
`GetTracesFile`, not a module trace.

The other collectors are also *read*:

| suffix | trigger | reboots? |
|---|---|---|
| `-USER` | `SPYTAKE`, key event `0x40a` | yes |
| `-AUTO` | event `0x52d2`; nothing that raises it was found | no |
| `-FRZ` | the freeze hook registered in `StartUp`; what calls it is not known | no |
| `-EXC` | the exception hook; on `0xDEADBEEF` it also writes `<SpyDir>/SSM/<stamp>.txt` | no |
| `-DEAD` | the dead-task hook | no |
| `SELF/<id>` | `SpyMemorize(id)`, one buffer | no |

**What a real capture holds** *(executed: the `-USER` archive from the car, 2026-09-28)*: 71
buffer directories under `RAMDISK_SPY/`, plus `EXC`, `REBOOT`, `FILES`, `MONITOR`, `TASKS`,
`FS_STORAGE_CTRL` and a screenshot. The ones that matter for the AUX work:

| id | module | tier of the identification |
|---|---|---|
| `25300` | `C_MGR_SRC`, the [source scheduler](SCHEDULER.md) | read (registration call site) |
| `06301` | `C_HMI_MEDIA_APP_BASE`, the media app | read (registration call site `0x022b1468`) |
| `06500`, `06501` | `C_HMI_AUDIO_APP_BASE` | read |
| `15400` | `C_MODULE_AUDIO`, the [audio module](AUDIO_MODULE.md) | inferred, from its object-table id |
| `17900` | `C_MODULE_TUNER` | inferred, from its object-table id |

Other ids registered at identifiable call sites *(read)*:

- HMI: `6000`/`6001` event handler, `6003` window manager, `6004` asserts, `6100`/`6101` nav,
  `6600` BT, `6900` upgrade, `7000`–`7002` tuner, `7100` picture, `8200` config,
  `31500`/`31501` desktop;
- `15600` CDC audio, `17800` sound;
- `C_BCM_*`: `18000` upgrade, `21600` jukebox, `22300` USB, `22400` FMT, `24100` DAB,
  `24400` BT audio, `25200` TS, `25600` BT connection, `26300` antitheft, `26700` picture,
  `26800` OOM;
- `30000` `C_SRV_MEDIA`.

`6004`, `21600` and `26800` were missing from the car's archive; why is not known.

### Adding /USER_DATA to the dump (`spy-dump-userdata`)

The one thing the collect does **not** capture is the live settings partition. There is no
removable card to image, and the ring buffers above are not the settings databases — so a
stock `SPYSTORE` cannot back up your paired phones, navigation destinations or presets.

`patches/spy-dump-userdata.json` adds that. The firmware already ships the exact primitive:
`C_FS_STORAGE_CTRL_PATH::GetUserDataDir` (`0x0105ae44`) resolves to `/USER_DATA/user_data/`
— the tree holding `sqlite/up_common.sqlite`, `sqlite/connectivity.sqlite`,
`sqlite/nav_dest.sqlite`, `Audio/Tuner.dat` and the rest. `CallBackCopy` has no spare room
and there is no usable code cave inside `.text`, so the patch is **cave-free**: it
overwrites the least-valuable existing copy block — the `*regen*` calibration copy — with

```
GetUserDataDir(entity)     ; source = /USER_DATA/user_data/
Xcopy(entity, dest)        ; dest = <stick>/SPY/<timestamp>, Xcopy addr reused from r26
```

Trade-off: the dump no longer contains the `*regen*` calibration files. Exact addresses
and bytes are in [Patch reference](PATCHES.md).

!!! success "Confirmed on hardware (NAV, 2026-09-14)"

    A real unit produced a dump containing the whole `/USER_DATA/user_data/` tree — nav
    destinations, radio presets and general settings — so `SPYSTORE` is now a working way to
    pull a settings backup off the unit. Paired phones (`connectivity.sqlite`) are out of
    scope, as that database is imported from the system partition. The full result, caveats
    and trade-offs live with the patch itself — see
    [Patch reference](PATCHES.md#spy-dump-userdata-spystore-also-backs-up-user_data).

**Do not confuse this with** `C_BCM_SPY_System_Shot::SpyFiles()`. Despite the name, it copies
`diag_zi.sqlite` from `USER_DATA` into a collect; it does not copy the debug spy logs, and it
writes nothing back to `USER_DATA` *(read)*. It was ruled out as a hook.

### A module dump reaches the spy, not the dead log sink

A module's SPY dump is a live caller of this system, and it is worth knowing that it does **not**
go through `Log_msg`'s stubbed sink (see [Patch reference](PATCHES.md) and issue **#94**).
`C_MGR_SRC`'s dump at `0x0169a2e4` builds its lines with the string-buffer helpers and then
emits them through a service, not the logger:

```
0x0169a2e4   MGR_SRC SPY dump  (one block per scheduled slot)
  -> 0x01695c30
       -> FUN_0103155c(0x52d0, 0)   look up service 0x52d0
       -> 0x012753c0                C_BCM_SPY::WriteData(id = 0x62d4, ptr, len)
```

`0x012753c0` is `C_BCM_SPY::WriteData`: it logs under the `BCM_SPY` / `WriteData` strings, and
the only stubbed sink it touches, `0x010346d0`, is reached on its **error** path
(`m_pListSpy isn't init`). Spy data therefore has its own route to `/SYSTEM_TMP_DATA/SPY/`, and
observing a module dump does not depend on the log sink being given a destination.

That dump now exists. The `25300` buffer in a `SPYTAKE` capture is exactly this output, and it
is what settled how the boot source is chosen (see [The AUX chain](AUX_CHAIN.md#how-the-boot-source-is-actually-chosen)).
The same capture carries the media app's buffer (`06301`), which shows whether
`HandleAudioAuxInputStatusChnged()` ran. It follows the saved AUX input setting, not the AUX
signal; see [The AUX signal path](AUX_SIGNAL.md).
