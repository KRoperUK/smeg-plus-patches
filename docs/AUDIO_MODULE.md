# The audio module (`C_MODULE_AUDIO`)

`C_MODULE_AUDIO` owns the audio DSP and amplifiers. It carries out source changes that
[the scheduler](SCHEDULER.md) decides, holds the AUX input setting, and turns radio events,
including AUX signal changes, into DBUS signals. This page covers the **273 functions** of
the family in the stock NAV `SMEG5.43.A.R2` image.

## How this was read

- Every function was decompiled through the shared Ghidra server; references come from the
  same `bl` / `lis`+`addi` / data-pointer scan as `tools/survey.py`
  ([Firmware map](FIRMWARE_MAP.md)).
- **25 functions are read**: the AUX path, the lifecycle, the event dispatch and the
  mute logic were followed by hand. They are listed [below](#functions-read-closely).
- **248 are inferred**: classified from their names, strings and a machine digest of
  the decompile (calls, fields, `Call_action` ids), not read line by line. They are
  [summarised by purpose](#the-rest-by-purpose), not listed one by one.
- The only executed result is the media app's dispatch of `0xcc` (below), emulated on the stock
  image.

## What matters for AUX

1. **The AUX "status" the media app reacts to is a setting, not a signal.** *Read.* There are
   two AUX quantities:
    - `Get_aux_status` (`0x013b9c8c`) returns `+0x8c`, the stored **AUX input setting**: the
      `audio/Auxiliary_Status` user key, 0..3, set from the media options menu. Confirmed in
      disassembly: it loads `0x8c(r31)` whenever the lifecycle state `+0x74` is non-zero, and
      the only stores to `+0x8c` in the family that write this object are `setAUXGain`
      (`0x013bba28`) and `read_sqlite_AudioUserData` (`0x013caba8`), which loads the key.
    - `Get_AUX_signal_status` (`0x013bc02c`) returns **signal presence** from the radio
      front-end (`C_I2C_SMART_RADIO`).
2. **Two DBUS signals, and the media app listens to the setting one.** *Read.*
   `AUDIO_AUX_INPUT_STATUS_CHANGED` is raised when the setting is written (`setAUXGain`, and the
   diagnostic `Set_diag_aux`). `AUDIO_AUX_SIGNAL_STATUS_CHANGED` is raised on a signal change.
   `C_BCM_HMI_AUDIO_CLIENT` turns the first into HMI message `0xcb` and the second into `0xcc`
   (`li r4,0xcb` at `0x025cdf1c`, `li r4,0xcc` at `0x025cded0`). The media app's AUX handler
   runs on `0xcb`. `C_HMI_MEDIA_APP_BASE::HandleDBUSMessage` has no `0xcc` case: its dispatch
   sends `0xcc` to the default branch *(executed: the dispatch window emulated on the stock
   image, `tests/test_firmware_nav.py`)*. The audio app uses `0xcc` only to refresh its menu
   *(read)*. So **no stock code path activates AUX because a signal appeared.**
3. **Every successful boot re-announces the setting once.** *Read.* `ElabRADIO_READY_FOR_INIT_0`
   ends with `setAUXGain(+0x8c, 1)`, which raises `AUDIO_AUX_INPUT_STATUS_CHANGED`. Whether the
   media app is listening by then is **not known**.
4. **Signal changes before the radio has started are dropped**, and AUX is kept muted while it
   is the current source with no signal (`+0x168`). *Read.*

What this means for the patches is in
[The AUX chain](AUX_CHAIN.md#what-the-handler-actually-reacts-to) and
[Bearing on the AUX patches](#bearing-on-the-aux-patches) below.

## The module

`C_MODULE_AUDIO` is a singleton, object id `0x3c28` in `C_OBJ_PTR_Table`, created by
`Instance()`. It owns the audio DSP and amplifiers, reached through a `Radio` /
`C_I2C_SMART_RADIO` object.

- It runs its own VxWorks task **`tAudTask`**, spawned in `Open` with `Audio_task_handler` ->
  `Module_routine`.
- The task serialises work through a message queue (`+0x64`, depth `0x32`) and a mutex
  (`+0x68`). *Read.*
- Callers outside the task use two paths:
  - the `Cmd_*`/`Get_*`/`Set_*` methods, which take the mutex and run on the caller's thread.
    Almost all are reached only from `C_SRV_AUDIO::bcm_*`, the DBUS server, or from VxWorks
    shell helpers (`do*`);
  - the `Elab_event_*` posts, for radio, VAN and CAN events.

### State fields

| offset | meaning | tier |
|---|---|---|
| `+0x54` | `Radio*` (C_I2C_SMART_RADIO) | read |
| `+0x58` | `C_VAN_BM*` | read |
| `+0x5c` | `UP_MOD*` (user-profile settings) | read |
| `+0x60` | `tAudTask` id | read |
| `+0x64` | message queue | read |
| `+0x68` | module mutex | read |
| `+0x16c` | amplifier-mute mutex | read |
| `+0x70` | radio has started at least once | read |
| `+0x74` | `st_audio`, the lifecycle state: 0 closed, 1 open (set when `Open` spawns `tAudTask`), 2 radio restarted, 9 radio early-started, 10 radio started, `0x28` error. `Get_aux_status` needs it non-zero; `CheckStatus` refuses commands at 0 and `0x28` | read |
| `+0x7c` / `+0x7e` | balance / fader | inferred |
| `+0x87` | AVC enabled | inferred |
| `+0x8a` | diagnostic "AUX fitted" option (AudioCommonData) | read |
| `+0x8c` | **AUX input setting** 0..3 (`audio/Auxiliary_Status`) | read |
| `+0x90` | HiFi mode (AudioConfigData 0..3) | read |
| `+0x94` | Arkamys option | inferred |
| `+0x15c` | system mute flag | read |
| `+0x15d` | user mute flag (applies with `+0x1ac`) | read |
| `+0x15e` | resulting radio mute | read |
| `+0x168` | **AUX no-signal mute** (`m_bAuxSignalMute`, from the log text) | read |
| `+0x169` | timed mute | read |
| `+0x1a4` | current `MGR_SRC_Source_t` | read |
| `+0x1a8` | current `AUDIO_SOURCES_TYPES` (5 = AUX) | read |
| `+0x1b0`..`+0x1c0` | pointers to the current source's volume, bass, treble, loudness and EQ | read |
| `+0x1f8` | touch-sound volume (`audio/Vol_touch_sound`) | read |

### Events in (subscriptions)

| from | event | handler id -> internal event -> handler |
|---|---|---|
| radio | `0x3f` | 5 -> 6 -> `ElabRADIO_READY_FOR_INIT_0` (subscribed in `Open`) |
| radio | `1` | 0 -> 1 -> `ElabRADIO_READY_FOR_INIT_2` (subscribed in `Open`) |
| radio | `3` | 1 -> 2 -> `ElabRADIO_STARTED` |
| radio | `4`, `5` | 2 -> 3 -> `ElabRADIO_RESTART` |
| radio | `0x3c` | 3 -> 4 -> `ElabRADIO_ANTENNA_DIAGNOSIS_CHANGED` |
| radio | **`0x3d`** | **4 -> 5 -> `Elab_AUDIO_AUX_SIGNAL_STATUS_CHANGED`** |
| radio | `0x40` / `0x41` / `0x42` | early started / handover ready / handover completed |
| VAN | `0x1b` | `0xe` -> `ElabBCM_NET_CHANGED_VEHICLE_STATUS` |

All but the first two are subscribed at the top of `Module_routine` (read). The module also
queues its own timer events: mute timers, beep ends, rear volume, amplifier thermal and car speed.

### Actions out (`Call_action` -> C_SRV_AUDIO private message -> DBUS on `com.MM.BCM_Audio`)

| action | message | DBUS signal | raised by (read, from the decompiles) |
|---|---|---|---|
| 0 | 1 | `AUDIO_STARTED` | `ElabRADIO_STARTED` |
| 1 | 2 | `AUDIO_NOT_STARTED` | `Module_routine` |
| 2 | 3 | `AUDIO_SOURCE_SWITCH` | `Cmd_change_source`, `Cmd_end_mix`, both init paths, `ElabRADIO_STARTED` |
| **3** | **4** | **`AUDIO_AUX_INPUT_STATUS_CHANGED`** | **`setAUXGain`** (from `Set_aux_status` and both init paths); `Set_diag_aux` |
| **4** | **5** | **`AUDIO_AUX_SIGNAL_STATUS_CHANGED`** | **`Elab_AUDIO_AUX_SIGNAL_STATUS_CHANGED`** |
| 5 | 6 | `AUDIO_VOLUME_CHANGED` | `Cmd_volume`, `Cmd_volume_limit` |
| 6 | 7 | `AUDIO_PARAM_CHANGED` | tone, fader, balance, loudness, EQ, AVC commands |
| 7 / 8 / 9 | 8 / 9 / 10 | `AUDIO_USER_MUTED` / `_DEMUTING` / `_DEMUTED` | `Cmd_user_mute`, `Cmd_user_demute` |
| `0xb` / `0xc` / `0x13` / `0xe` / `0xf` | `0xb` / `0xc` / `0xd` / `0xe` / `0xf` | diagnosis / Arkamys / distribution / touch-sound / Arkamys-bypass updated | as named |

Actions 10, `0xd`, `0x10`-`0x12` and `0x16` are not subscribed by `SubscribeByAudio`. Whether
anything else subscribes them is not known.

### The AUX path end to end

```
Signal presence (read):
  radio I2C decode -> C_I2C_SMART_RADIO event 0x3d
    -> Audio_event_handler(4) -> Elab_event_AUDIO_AUX_SIGNAL_STATUS_CHANGED (queue 5)
    -> tAudTask: Elab_AUDIO_AUX_SIGNAL_STATUS_CHANGED
         st_audio < 10 -> dropped
         source == AUX -> update +0x168, RadioMuteManager
         Call_action(4) -> msg 5 -> DBUS AUDIO_AUX_SIGNAL_STATUS_CHANGED
    -> C_BCM_AUDIO_CLIENT -> C_BCM_HMI_AUDIO_CLIENT -> HMI message 0xcc
    -> C_HMI_AUDIO_APP_BASE::HandleDBUSMessage: refresh the audio menu if one is on screen
       (C_HMI_MEDIA_APP_BASE::HandleDBUSMessage has no 0xcc case)

AUX input setting (read):
  menu slider (C_HMI_MEDIA_MENU_BT_AUX_Option: 0/1/2 -> status 0/1/3)
    -> C_BCM_HMI_AUDIO_CLIENT::Set_aux_status -> DBUS -> C_SRV_AUDIO::bcm_Set_aux_status
    -> C_MODULE_AUDIO::Set_aux_status -> setAUXGain: radio cmd 0x33, +0x8c = status
    -> Call_action(3) -> msg 4 -> DBUS AUDIO_AUX_INPUT_STATUS_CHANGED
    -> C_BCM_AUDIO_CLIENT (+0x50 listener, Link A) -> C_BCM_HMI_AUDIO_CLIENT -> HMI message 0xcb
    -> C_HMI_MEDIA_APP_BASE::HandleAudioAuxInputStatusChnged
         state = (Get_aux_status != 0); acts only on a change -> ActivateSource(aux, true)
  boot: Open -> readMemFlashInfo -> read_sqlite_AudioUserData loads +0x8c
        ElabRADIO_READY_FOR_INIT_0 -> setAUXGain(+0x8c, 1) -> the same signal, once
```

### Relation to `C_MGR_SRC` and `C_I2C_SMART_RADIO`

- **`C_MGR_SRC` decides and `C_MODULE_AUDIO` executes** (read).
  - The HMI source objects (`C_HMI_SrcAudio::SourceStart`, `SourcePauseEnd`, the TA, nav and BT
    sources) call `C_BCM_HMI_AUDIO_CLIENT::Cmd_change_source(slot, param)` over DBUS.
  - `C_SRV_AUDIO::bcm_Cmd_change_source` looks the slot up in its table
    (`this + slot*0x1c + 0x80..0x90`: MGR source id, audio source type, two flags, parameters)
    and calls `C_MODULE_AUDIO::Cmd_change_source`.
  - The module never calls `C_MGR_SRC`. How the slot table is filled (presumably
    `AllocateSource`) was not read.
- **`C_I2C_SMART_RADIO`** carries every DSP command. `SendCmdRadio` is the single choke point
  (2 070 instructions), and command `0x33` is the AUX gain. It is also the source of all radio
  events, including AUX signal `0x3d`. The module reads signal presence only through
  `Radio::Get_AUX_signal_status` (`0x0131ae40`) -> `C_I2C_SMART_RADIO::Get_AUX_signal_status`.


## Bearing on the AUX patches

Everything in this section is **inferred** from the reading above.

- **A true "switch when a signal appears" needs a new wire.** Stock routes signal changes only to
  a menu refresh. A patch would have to do two things:
  - deliver `0xcc` to the media app's AUX handler;
  - make that handler test `Get_AUX_signal_status`, not `Get_aux_status`.

  Two constraints apply:
  - the signal event is dropped before `st_audio` = 10;
  - AUX is muted while silent (`+0x168`).

  Both matter if AUX is selected with no signal.

  Both changes are `patches/aux-signal-switch.json`: **executed** under emulation, not
  flashed; see [The AUX signal path](AUX_SIGNAL.md#emulation-results). A detection before
  `st_audio` = 10 is still lost, and `aux-sticky` is paired with it so silence does not
  release AUX.
- **Boot to AUX.** The boot-time `AUDIO_AUX_INPUT_STATUS_CHANGED` from
  `ElabRADIO_READY_FOR_INIT_0` means `HandleAudioAuxInputStatusChnged` may also run at boot.
  `aux-boot-restore` clears `PrOnly` both there (`0x02303474`) and in `InitApp`
  (`0x022c0678`). The request the boot restore sees comes from `InitApp`: clearing it there is
  what made AUX match, and the pair with `aux-boot-default` boots to AUX on the car
  *(executed; [Verification](VERIFICATION.md#log))*.


## Functions read closely

Addresses are symbol starts in NAV `5.43.A.R2`.

| address | function | insns | what it does | tier |
|---|---|---:|---|---|
| `013b1a88` | `Set_hifi_mode(TYPE_HIFI_AUDIO_MODE)` | 2 | Writes the HiFi mode `+0x90` | read |
| `013b3c5c` | `RadioMuteManager(bool, short)` | 271 | Computes the radio (DSP) mute: muted unless every mute flag (`+0x15c` system, `+0x15d`/`+0x1ac` user, `+0x168` AUX no-signal, `+0x169` timed) is clear and the source volume is non-zero; arms the radio-mute timer (40 ms for source type 10, else 200 ms) | read |
| `013b4e24` | `Get_ext_audio_src_req(bool&)` | 2 | Stub: returns 0 without writing its out-parameter | read |
| `013b8478` | `Cmd_change_source(MGR_SRC_Source_t, AUDIO_SOURCES_TYPES, bool, bool, u` | 870 | Applies a source change from the server's slot table: bounds and stores per-source vol/bass/treble/loudness/EQ pointers (`+0x1b0`..`+0x1c0`), current MGR source `+0x1a4`, audio source type `+0x1a8`; when the new type is AUX (5) sets the no-signal mute `+0x168` from `Get_AUX_signal_status`; system mute, DSP routing (`CmdSendComAud`), `Call_action(2)` = `AUDIO_SOURCE_SWITCH` | read (partly) |
| `013b9c8c` | `Get_aux_status(TYPE_AUDIO_AUX_STATUS&)` | 69 | Returns the stored AUX input **setting** `+0x8c` (the `audio/Auxiliary_Status` user key, 0..3) - not signal presence; -1 if the module is closed | read |
| `013bb7ec` | `setAUXGain(TYPE_AUDIO_AUX_STATUS, bool)` | 167 | Maps the stored AUX input setting (0..3) to a DSP gain (0,1 -> 0; 2 -> 1; 3 -> 2), sends radio command `0x33`; on success stores the setting at `+0x8c` and calls `Call_action(3)`, i.e. raises DBUS `AUDIO_AUX_INPUT_STATUS_CHANGED` | read |
| `013bba88` | `Set_aux_status(TYPE_AUDIO_AUX_STATUS)` | 86 | DBUS `Set_aux_status` target: under the module mutex (`+0x68`) calls `setAUXGain(status, 0)`; refuses when `CheckStatus` fails | read |
| `013bc02c` | `Get_AUX_signal_status(bool&)` | 70 | Returns raw signal presence from `Radio::Get_AUX_signal_status` (C_I2C_SMART_RADIO); -1 if the module is closed (`st_audio` 0) | read |
| `013c0508` | `Cmd_reset()` | 2 | Stub: returns 0 | read |
| `013c0e00` | `Get_diag_aux(bool&)` | 43 | Returns the diagnostic 'AUX fitted' flag `+0x8a`. No caller found | read |
| `013c1364` | `Set_diag_aux(bool)` | 140 | Diagnostic 'AUX fitted' option: writes `+0x8a` and the UP AudioCommonData, then `Call_action(3)` (raises `AUDIO_AUX_INPUT_STATUS_CHANGED`). No caller found | read |
| `013ca78c` | `read_sqlite_AudioUserData()` | 293 | Loads `audio/Vol_touch_sound` into `+0x1f8` and `audio/Auxiliary_Status` into `+0x8c` (accepted only if < 4) from the UP user keys | read |
| `013cb3f4` | `readMemFlashInfo()` | 421 | Resets defaults (`+0x8c`=0, `+0x8a`=0, beep presets ...) then loads AudioConfigData / AudioCommonData (HiFi mode `+0x90`, 'AUX fitted' `+0x8a`) and the user keys | read (partly) |
| `013cbda0` | `Elab_event_AUDIO_AUX_SIGNAL_STATUS_CHANGED()` | 18 | Queues internal event 5 on the module message queue (`+0x64`); called by `Audio_event_handler` for radio event `0x3d` | read |
| `013cbf08` | `Audio_event_handler(C_MODULE_AUDIO*, AUDIO_MY_EVENT)` | 135 | Maps a subscribed radio/VAN event to one of 16 `Elab_event_*` queue posts (0 init_2 ... 4 AUX signal ... 0xf ext audio src) | read |
| `013cc124` | `Module_routine()` | 1069 | Task loop: subscribes the remaining radio events (3,4,5,`0x3c`,`0x3d`,`0x40`-`0x42`) and VAN event `0x1b`, then receives internal events and dispatches (5 -> `Elab_AUDIO_AUX_SIGNAL_STATUS_CHANGED`, 6 -> init_0, 1 -> init_2, `0x11`.. mute timers, `0x18`/`0x19` rear volume, `0x1d`-`0x21` spy beeps ...) | read (dispatch only) |
| `013ce870` | `Elab_AUDIO_AUX_SIGNAL_STATUS_CHANGED()` | 153 | Handles the internal AUX-signal event: ignored until `st_audio` (`+0x74`) reaches 10; when the current source (`+0x1a8`) is AUX (5), reads `Radio::Get_AUX_signal_status` and sets or clears the no-signal mute flag `+0x168`, re-running `RadioMuteManager`; always ends with `Call_action(4)`, the DBUS `AUDIO_AUX_SIGNAL_STATUS_CHANGED` | read |
| `013cf0fc` | `CheckStatus()` | 99 | Refuses commands while `st_audio` is 0 (closed) or `0x28` (error) | read |
| `013d4514` | `ElabRADIO_RESTART()` | 41 | Radio restart: `st_audio` back to 1, or 2 if the radio had started before (`+0x70`) | read |
| `013d565c` | `ElabRADIO_STARTED()` | 195 | Radio started: `st_audio`=10, `+0x70`=1; if the current source is AUX, refreshes the no-signal mute `+0x168`; raises actions 0, 2, `0xb`, `0xc` | read (partly) |
| `013d5968` | `ElabRADIO_READY_FOR_INIT_2()` | 656 | Alternative init path (radio event 1): Arkamys option, fader/balance, and the same `setAUXGain(+0x8c, 1)` near the end | read (partly) |
| `013d6614` | `ElabRADIO_READY_FOR_INIT_0()` | 651 | Main boot-time audio init after the radio reports ready (event `0x3f`): software level, DSP set-up commands, amplifier diagnosis/start-up, `RadioMuteManager(true)`, beep presets, then **`setAUXGain(+0x8c, 1)`** - so every successful boot raises `AUDIO_AUX_INPUT_STATUS_CHANGED` once | read |
| `013d7040` | `Cmd_emergency_switch(bool)` | 2 | Stub: returns 0 (emergency-call switch not implemented here) | read |
| `013d70a4` | `Call_action(int)` | 46 | Logs, then `C_BASE::Call_action(n)`: runs the subscribers for action n. C_SRV_AUDIO subscribes action n to private message n+1 for n 0..9 (3 -> AUX input, 4 -> AUX signal) | read |
| `013d79a4` | `Open(Radio*, UP_MOD*, C_VAN_BM*)` | 452 | Stores Radio/UP/VAN pointers (`+0x54`/`+0x5c`/`+0x58`), creates message queue `+0x64` and mutexes `+0x68`/`+0x16c`, `readMemFlashInfo`, subscribes radio events `0x3f` and 1, spawns task `tAudTask`, sets `st_audio`=1 | read |

## The rest, by purpose

The remaining 248 functions were classified, not read. Tier: **inferred** for every row.

| purpose | functions |
|---|---:|
| User audio parameters: volume, fader, balance, tone, loudness, EQ, speed-dependent volume (AVC), limits | 50 |
| Beeps (single, cyclical, parking-sensor, early-beep handover) and their volumes/speakers | 43 |
| Mute / amplifier management (system, user, timed, hardware and amplifier mutes; Dirana DSP PLL reset) | 26 |
| Posts an internal event to the module queue (`+0x64`); runs on the radio/VAN/CAN thread that raised it | 23 |
| Diagnostics: amplifier/speaker diagnosis, thermal refresh, diagnostic configuration options | 18 |
| Lifecycle, task and event plumbing | 16 |
| Source routing and mixing (TTS/navigation mix, fast/end mix, source queries) | 13 |
| Internal-event handler run on `tAudTask` by `Module_routine` | 11 |
| Arkamys sound processing option and speaker distribution | 8 |
| Timer callback trampoline: posts the matching internal event | 7 |
| Commands to the radio/DSP through C_I2C_SMART_RADIO | 7 |
| HiFi-over-CAN (external amplifier) volume/mode handling | 7 |
| Spy/diagnostic logging and status dumps | 7 |
| Microphone ADC/DAC gain and phone microphone path | 6 |
| Configuration, persistence and status queries | 4 |
| other single-purpose functions (lifecycle handlers, persistence, early-start) | 2 |

## Not known

- Which radio I2C message sets event `0x3d`, and its debounce (`DecodeMsgXXX`), belongs to the
  `C_I2C_SMART_RADIO` reading.
- Whether the HMI listener (`C_BCM_AUDIO_CLIENT+0x50`, Link A) exists when
  `ElabRADIO_READY_FOR_INIT_0` announces the AUX setting at boot. This needs a spy trace with
  DBUS logging, or emulation of the HMI start-up order.
- The meaning of `TYPE_AUDIO_AUX_STATUS` values 1 and 3 in the vendor UI; the menu offers three
  positions, mapped to 0/1/3.
- Callers of `Set_diag_aux`, `Get_diag_aux` and the other `*_diag_*` setters with "(none found)".
  They are probably reached through a diagnostic table this scan does not model.
