# The AUX signal path

How the unit detects that audio is arriving on the AUX input, and where that knowledge goes.
This is the groundwork for a real switch-on-signal patch.
[What the handler actually reacts to](AUX_CHAIN.md#what-the-handler-actually-reacts-to)
explains why the existing AUX handler cannot do this job: it follows the saved AUX input
*setting*, not the signal.

This is a close reading of the stock **NAV `SMEG5.43.A.R2`** image, at base `0x01000000`,
through Ghidra decompiles and `tools/ppcdis.py`. Evidence tiers are as in
[Verification](VERIFICATION.md).

!!! warning "Emulated, not flashed"

    The detection and routing below are **read**. The two patch designs at the end ship as
    `patches/aux-signal-switch.json`. Each was **executed** under `tools/ppcemu.py`, on its own
    function, with its callees stubbed. Neither has been flashed.

## In short

- **The signal is measured all the time, from boot** *(read)*. No check of the current source
  gates the polling or the event.
- **Its change event already reaches the media app, which drops it** *(read)*. The media
  app's DBUS dispatch has a case for the setting event (`0xcb`) and none for the signal
  event (`0xcc`).
- **A switch-on-signal patch therefore looks feasible** *(inferred)*: route `0xcc` into the
  existing AUX handler, and make that handler read the signal instead of the setting.
- **Not known:** whether the detector measures the AUX input while another source is
  playing. There is a cheap car check for this, [below](#is-the-signal-measured-while-another-source-plays).

## 1. Detection *(read)*

```
boot: Reset_audio_base_at_startup
        -> Configure_Analogic_input (0x0132f714)
          -> SetCfgAuxPrimary (0x0132f5bc)
               DSP writes: AUX input configuration, and a quasi-peak detector set-up
               arms watchdog 0x0362d8fc: 0xfa ticks -> CheckAuxiliaryInput
CheckAuxiliaryInput (0x01324ea8): posts message 0x47 to the Audio_task queue
Audio_task (0x01334900): message 0x47 -> CheckAuxiliaryDetection
CheckAuxiliaryDetection (0x01324a80):
    Dspread(0xd00e5, ...)                   # the detector's level
    compare with the threshold at 0x035da75c (0x2000 in .data)
    state 0x0362d8f0:
      0 idle     -> 1 when level > threshold
      1 rising   -> counts to 10 while above, then -> 2; back to 0 if it drops
      2 present  -> 3 when level < threshold
      3 falling  -> counts while below; after 20 -> 0; back to 2 if it rises again
    entering 2:          byte 0x0362d8ec = 1, "Launch Event For AUX Detection ON !!!",
                         CallBackDirana(0x12)
    reaching 0 from on:  byte = 0, "...OFF !!!", CallBackDirana(0x12)
    re-arms the watchdog: 5 ticks while rising, 0xfa ticks otherwise
```

- **Signal presence is the global byte `0x0362d8ec`.** Its only writer is
  `CheckAuxiliaryDetection`, and `Get_Current_Aux_STATUS` (`0x01320064`) returns it *(read)*.
- **The threshold defaults to `0x2000`.** `ChangeAux_Min_Input_value` can change it
  *(read)*. Whether anything calls that at run time is not known.
- **Timing** *(inferred)*. Detection takes 11 consecutive samples above the threshold, 5 ticks
  apart. Loss takes 20 samples below it, 250 ticks apart. The tick rate was not read, so
  wall-clock times are **not known**. At 100 Hz that would be about 2.5 s to detect and about
  50 s of silence to drop; at 1 kHz, about 0.3 s and 5 s.
- **The loop never stops in normal running** *(read)*. The watchdog is cancelled only when
  `Audio_task` exits.

## 2. From the detector to DBUS *(read)*

```
CallBackDirana(0x12)
  -> C_I2C_SMART_RADIO::AddDiranaEvent -> ManageEvent (0x0135de2c), case 0x12
  -> i2c message 0x77 -> i2c_MainTunerTask -> Call_action_do(0x3d)
  -> C_MODULE_AUDIO::Elab_AUDIO_AUX_SIGNAL_STATUS_CHANGED (0x013ce870)
       drops the event while the module's state +0x74 is below 10 (radio not started)
       if the current source is AUX (type 5): update the no-signal mute (+0x168)
       Call_action(4) - whatever the current source
  -> C_SRV_AUDIO: action 4 -> DBUS AUDIO_AUX_SIGNAL_STATUS_CHANGED
```

- A second raiser of `0x3d`, in `DecodeMsgXXX`, was not mapped *(not known)*.
- **Early boot.** A detection that completes before the radio has started is dropped. It
  is not re-sent while the signal stays present *(read)*.

## 3. From DBUS to the apps *(read)*

- `com_MM_BCM_Audio_proxy::connect_all_signals` connects both
  `AUDIO_AUX_INPUT_STATUS_CHANGED` and `AUDIO_AUX_SIGNAL_STATUS_CHANGED`.
- `C_BCM_AUDIO_CLIENT::AUDIO_AUX_SIGNAL_STATUS_CHANGED` (`0x025c9e1c`) forwards the signal to
  `C_BCM_HMI_AUDIO_CLIENT`, which posts HMI message **`0xcc`** to the app that owns it. The
  setting event takes the same route and posts **`0xcb`**.
- So an app that receives `0xcb` through its audio client also receives `0xcc`
  *(inferred from the shared client and connection)*.

| app dispatcher | `0xcb` (setting) | `0xcc` (signal) |
|---|---|---|
| `C_HMI_MEDIA_APP_BASE::HandleDBUSMessage` (`0x02309398`) | calls `HandleAudioAuxInputStatusChnged` | **no case**; falls through to return |
| `C_HMI_AUDIO_APP_BASE` (`0x02270f60`) | none | refreshes the audio menu |
| every other app | none | none |

The media dispatch at `0x02309628`–`0x0230964c` reloads the message id, compares it with
`0xcb` (branching to the handler at `0x02309fbc`), then with `0xd7`, and otherwise returns.
Both the original bytes and the disassembly were checked.

## Is the signal measured while another source plays?

**Not known from the code.**

- **What points to yes** *(inferred, fairly strong)*:
  - Nothing gates the polling or the event on the current source; only the mute update is
    gated *(read)*.
  - Stock `IsAUXSRCAvailable()` lets AUX be selected only when the setting is non-zero *and*
    `Get_AUX_signal_status` reports a signal *(read)*. For AUX ever to have been selectable
    from another source, the detector must have seen the signal while that source played.
- **What is not known:** whether the detector at `0xd00e5` taps the AUX input directly or
  the routed audio path. A dedicated detector is set up once in `SetCfgAuxPrimary`, rather
  than on each source switch, which suggests a direct tap *(inferred)*.

**The cheap car check.** You need a build **without** the `IsAUXSRCAvailable` edit (stock,
or one without `aux-autoswitch` / `aux-always-available`), because that edit forces the AUX
tile available.

1. Stay on FM.
2. Start playback into AUX.
3. See whether the AUX tile ungreys. If it does, detection runs while AUX is not the current
   source.

## Candidate designs: `aux-signal-switch` *(emulated, not flashed)*

Every **original** word below was read from the stock image and re-checked against it while
writing this page, for both A and B. Replacements were assembled with `llvm-mc` or encoded by
hand for the branches. Each replacement was then decoded with capstone at its own address,
and it decodes to the instruction in the table *(executed)*. Being well-formed says nothing
about whether the patched code behaves correctly.

### A. The handler reads the signal instead of the setting

In `C_HMI_MEDIA_APP_BASE::HandleAudioAuxInputStatusChnged`:

| addr | original | replacement | why |
|---|---|---|---|
| `0x02303378` | `981f0008` `stb r0,8(r31)` | `981f0010` `stb r0,0x10(r31)` | zero the result byte before the query |
| `0x0230338c` | `3929b258` `addi r9,r9,-0x4da8` | `3929cbe4` `addi r9,r9,-0x341c` | call `C_BCM_HMI_AUDIO_CLIENT::Get_AUX_signal_status` (`0x025ccbe4`) instead of `::Get_aux_status` (`0x025cb258`); both take `(this, T&)` |
| `0x02303398` | `801f0010` `lwz r0,0x10(r31)` | `881f0010` `lbz r0,0x10(r31)` | the signal query writes a `bool`, not a `long` |
| `0x0230342c` | `801f0010` `lwz r0,0x10(r31)` | `881f0010` `lbz r0,0x10(r31)` | the same, at the activate/release decision |

!!! note "The dropped store to `+8` is dead *(read)*"

    The first edit replaces the stock zeroing of `8(r31)`. `r31` is the frame pointer here, so
    `+8` is a stack local: the handler's "state" byte. Both branches after the query overwrite
    it, at `0x023033a8` (`0`) and `0x023033b4` (`1`), before its only read at `0x023033c8`.
    The result byte at `+0x10` is also a stack local, the query's out-parameter.

With A applied, the handler's cached state follows the signal *(executed; see
[Emulation results](#emulation-results))*:

- **Signal appears:** it activates AUX. `aux-boot-restore`'s `0x02303474` edit already makes
  that request's `PrOnly` 0.
- **Signal is lost:** it releases AUX if AUX is active.

The saved AUX menu setting would then no longer drive this handler.

### B. The media dispatch also sends `0xcc` to the handler

In `C_HMI_MEDIA_APP_BASE::HandleDBUSMessage`. This drops the redundant reloads of
`0x220(r31)`, which frees two slots for a `0xcc` case. `0xcb` and `0xd7` behave as before.

| addr | original | replacement |
|---|---|---|
| `0x02309628` | `801f0220` `lwz r0,0x220(r31)` | `2b8000d9` `cmplwi cr7,r0,0xd9` |
| `0x0230962c` | `2b8000d9` `cmplwi cr7,r0,0xd9` | `419d0024` `bgt cr7,0x02309650` |
| `0x02309630` | `419d0020` `bgt cr7,0x02309650` | `2f8000cb` `cmpwi cr7,r0,0xcb` |
| `0x02309634` | `801f0220` `lwz r0,0x220(r31)` | `419e0988` `beq cr7,0x02309fbc` |
| `0x02309638` | `2f8000cb` `cmpwi cr7,r0,0xcb` | `2f8000cc` `cmpwi cr7,r0,0xcc` |
| `0x0230963c` | `419e0980` `beq cr7,0x02309fbc` | unchanged |
| `0x02309640` | `801f0220` `lwz r0,0x220(r31)` | `2f8000d7` `cmpwi cr7,r0,0xd7` |
| `0x02309644` | `2f8000d7` `cmpwi cr7,r0,0xd7` | `419e0b4c` `beq cr7,0x0230a190` |
| `0x02309648` | `419e0b48` `beq cr7,0x0230a190` | `4800101c` `b 0x0230a664` |

- `r0` still holds the message id loaded at `0x0230961c`; nothing in between writes it
  *(read)*.
- The only branch in the function that lands inside this window is the `bgt` being moved
  *(read, by a scan of every relative branch in the function)*.
- `0x0230964c` (`b 0x0230a664`) becomes unreachable and is left alone.

### Risks *(inferred unless marked)*

- **Silence drops AUX.** After the loss count, the handler releases AUX. The scheduler's
  "next" position is then a literal 1, the tuner ([The source scheduler](SCHEDULER.md)), so
  pausing the phone for longer than the loss time would switch to FM. `aux-sticky`'s edit
  at `0x02303434` redirects exactly that release branch, and combining the two would keep AUX
  selected. Neither design overlaps it.
- **Early boot.** A detection dropped before the radio has started is not re-sent while the
  signal stays present. The once-per-boot setting event (`0xcb`) would still run the patched
  handler, which then reads the signal. Whether detection has finished by then is not known.
- **A failed DBUS query** leaves the byte at 0, which reads as "no signal". Stock code has
  the same weakness with the setting.
- **No address overlap** with `aux-autoswitch` (`0x02303428`), `aux-sticky` (`0x02303434`) or
  `aux-boot-restore` (`0x02303474`, `0x022c0678`, `0x01699444`) *(read)*.

### Emulation results

**Handler** (`0x0230331c`), run on the stock NAV image with A applied. Every callee is
stubbed: the audio client pointer, both queries (each writing the value under test),
`GetMediaDevice` (returning 0 with a fake source), `SetMediaDeviceState`, `ActivateSource`
and `ReleaseSource`. `this+0x51449` is the cached state *(executed)*.

| image | setting | signal | cached | query called | outcome |
|---|---|---|---|---|---|
| stock | 1 | 0 | 0 | setting | `ActivateSource(aux, 1)`; cache → 1 |
| stock | 0 | 1 | 0 | setting | nothing: the stock handler cannot see the signal |
| A | 0 | 1 | 0 | signal | `ActivateSource(aux, 1)`, device state 2; cache → 1 |
| A + `aux-boot-restore` | 0 | 1 | 0 | signal | `ActivateSource(aux, 0)`: `PrOnly` clear |
| A | 1 | 0 | 0 | signal | nothing: a setting change alone no longer activates |
| A | 1 | 1 | 1 | signal | nothing: no change |
| A | 1 | 0 | 1 | signal | `ReleaseSource`, device state 0; cache → 0 (for every stubbed source state 0–8) |
| A + `aux-sticky` | – | 0 | 1 | signal | no release; cache → 0 |
| A + `aux-sticky` | – | 1 | 0 | signal | `ActivateSource`; cache → 1 |

**Dispatch window** (`0x0230961c`–`0x02309650`), run from the message-id load to the first
address outside the window *(executed)*:

| message id | stock goes to | with B goes to |
|---|---|---|
| `0xcb` | AUX handler case (`0x02309fbc`) | same |
| `0xcc` | default (`0x0230a664`) | **AUX handler case** |
| `0xd7`, `0xd9` | `0x0230a190` | same |
| `0xca`, `0xd8`, `0x10` | default | same |
| `0xda`, `0x385` | the `> 0xd9` chain (`0x02309650`) | same |

`tests/test_aux_signal_switch.py` replays the dispatch window on a synthetic image, so CI
checks it without firmware. Breaking the `0xcc` compare fails the test.

**Not executed:** anything outside those two functions, the DBUS round trip of
`Get_AUX_signal_status`, and the car.

### What the car test answers

`builds/aux-signal-switch.json` combines this with the boot-restore build: `aux-always-available`,
`aux-sticky`, `aux-boot-default`, `aux-boot-restore`, `aux-signal-switch` and
`spy-dump-userdata-partition`. Flash it only after the `aux-boot-restore` test has been read.

1. **On FM, start playback into AUX.** If the unit switches to AUX, the detector runs while
   AUX is not selected. This also answers the open question
   [above](#is-the-signal-measured-while-another-source-plays).
2. **Pause the phone for a minute.** With `aux-sticky`, AUX should stay selected.
3. **Change source manually, then restart playback.** Nothing should switch: the handler
   acts on a *change* of signal, and the signal did not change.
4. **Take a `SPYTAKE`, then `SPYSTORE`.** The `06301` buffer (the media app) and the
   `25300` buffer (`C_MGR_SRC`) show whether `0xcc` arrived and what was requested.
