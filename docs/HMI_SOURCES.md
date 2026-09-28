# How HMI apps request sources

How the HMI side asks [the scheduler](SCHEDULER.md) for audio, and every place that asks for
AUX. Everything below comes from the stock NAV `SMEG5.43.A.R2` image, with addresses at base
`0x01000000`. The method was a capstone disassembly of each site, with call targets resolved
through `lis`/`addi` pairs, plus the `tools/survey.py` inventory ([Firmware map](FIRMWARE_MAP.md)). Ghidra was not used; its MCP tools
were not reachable from this session.

Evidence tiers:
- **read**: disassembled and followed by hand;
- **inferred**: reasoned from something read, with the basis given;
- **not known**: not established.

Nothing here was executed.

## Overview

Every HMI audio source (USB, iPod, BT streaming, CDC, AUX, jukebox, tuner, video) is a
`C_HMI_SrcAudio`, which derives from `C_HMI_SrcMgntBase`. The source manager on the other side
(`C_MGR_SRC`) sees only what `C_BCM_HMI_AUDIO_CLIENT::AllocateSource(request)` and
`::ActivateSourceByID(id)` send.

1. **The request is a fixed template.** *(read)*
   - Each source's constructor passes a `t_srv_source_request` held in `.rodata`. The
     `C_HMI_SrcMgntBase` constructor (`0x02738434`) copies `0x2c` bytes of it to `this+0x10`, so
     the `PrOnly` byte (request `+0x28`) lives at `this+0x38`.
   - In **every** media template, `PrOnly` is **0**. The AUX template is at `0x03276f5c`:
     `SrcId 0xe200`, priority 20, type 5, `Sched_Pos` 7, `PrOnly` 0.
   - The constructor's `bool` goes to `this+0x60`. All the media sources pass `false`: AUX does
     so at `0x022c62e8` (`li r6,0`).
2. **`ActivateSource(bool)` (`0x0273a248`) changes `PrOnly` for one call only.** *(read)*
   - It switches on the state word `this+0x58`.
   - In state 1 (IDLE), it sets the state to 2 (REQUESTED), saves `this+0x38`, writes its
     argument there, calls `AllocateSource(this+0x10)`, and then **restores** the saved byte.
   - In state 7 (SUSPENDED), it calls `ActivateSourceByID(this+0x14)`, which carries **no**
     `PrOnly` at all.
   - In any other state, it only logs "m_source_state is not IDLE".
   - So the `bool` reaches `C_MGR_SRC` only on an IDLE→REQUESTED transition.
3. **`HandleSrcMgrEnd` (`0x0273a400`) re-requests with the stored template.** *(read)*
   - When the source manager ends a source whose `this+0x60` is clear, it calls
     `AllocateSource` again with `this+0x10` as it stands, with no argument override.
   - For AUX that means `PrOnly` 0. This path needs no patch.
4. **State numbers.** State 0 is set by the constructor and `Close`, 1 by `Open` and
   `ReleaseSource`, and 2 by `ActivateSource`. *(read)*
   - The names come from the log strings: 0 CLOSED, 1 IDLE, 2 REQUESTED, 7 SUSPENDED.
     `ActivateSourceByID` accepts the bitmask `0x84`, which is states {2, 7}, and its log says
     "REQUESTED or SUSPENDED". *(read)*
   - 3–6 are ACTIVE, MUTED, PAUSED and PAUSED_MUTED in some order. *(inferred: the names appear
     in the log strings, but the order is not pinned)*
5. **AUX is media device type 5.** *(read)* The AUX handler calls `GetMediaDevice(5, …)` at
   `0x023033fc` and `SetMediaDeviceState(5, 2|0)` at `0x02303448` and `0x0230355c`.

## Every `ActivateSource(bool)` call site

The table covers all 17 sites that build the address `0x0273a248`, found by a `lis`/`addi` scan of
the whole image. There are no `bl` callers. The one data pointer to it is the
`C_HMI_SrcMgntBase`/`SrcAudio` vtable. Calls made through that vtable slot would not appear here:
**not known** whether any exist.

| call site (`bctrl` target load) | `li r4` at | containing function | source | `PrOnly` passed | tier |
|---|---|---|---|---|---|
| `0x022bf2ec` | computed (`0x022bf2cc` stores 1) | `C_HMI_MEDIA_APP_BASE::EnableJukebox` | JKB | **1** | read |
| `0x022c000c` | `0x022c0004` | `C_HMI_MEDIA_APP_BASE::InitApp` | USB (slot `+0xe2c`) | 0 | read |
| `0x022c01b0` | `0x022c01a8` | `InitApp` | iPod (`+0xe34`) | 0 | read |
| `0x022c0358` | `0x022c0350` | `InitApp` | BT streaming (`+0xe30`) | 0 | read |
| `0x022c0504` | `0x022c04fc` | `InitApp` | CDC (`+0xe38`) | 0 | read |
| `0x022c0680` | **`0x022c0678`** | `InitApp` | **AUX** (`+0xe3c`, `user_HMI.AUX.*` labels) | **1** (patch edit 1 → 0) | read |
| `0x022c0828` | `0x022c0820` | `InitApp` | JKB (`+0xe40`) | 0 | read |
| `0x0230347c` | **`0x02303474`** | `HandleAudioAuxInputStatusChnged` | **AUX** (`GetMediaDevice(5)`) | **1** (patch edit 2 → 0) | read |
| `0x02306a20` | computed: `mr r4,r0` at `0x02306a18`, from the byte at `0x14(r31)` | `HandleMediaStateReady(type, bool)` | the device of `type`, **including AUX if `type` = 5** | 1 for types 0–4 in some branches. For type ≥ 5 it is the caller's `bool` (`HandleDBUSMessage`'s own `bool` parameter) | read (plumbing); **not known** whether type 5 ever arrives |
| `0x0230b6ac` | `0x0230b6a4` | `C_HMI_MEDIA_APP_BASE::HandleSystemMessage`, private message (`0xcc`=6, `0xd0`=`0xbba`) | `GetActiveMediaDevice`: whichever is active, **AUX included** | **1** (after `ReleaseSource`) | read |
| `0x0232b274` | `0x0232b26c` | `C_HMI_MEDIA_POPUP_ERR_DETECT::Close` | `GetActiveMediaDevice`: **AUX included** | **1** (after `ReleaseSource`) | read |
| `0x023c767c` | `0x023c7674` | `C_HMI_TUNER_APP_BASE::InitApp` | tuner (`+0xe10`) | 0 | read |
| `0x0248a3e0` | `0x0248a3d8` | `C_HMI_VIDEO_APP_BASE::InitApp` | video | 0 | read |
| `0x0248d018` | `0x0248d010` | `C_HMI_VIDEO_APP_BASE::HandleMediaStateReady(int)` | video | 1 | read |
| `0x0248d0e8` | `0x0248d0e0` | `C_HMI_VIDEO_APP_BASE::HandleVideoTrackFound(int)` | video | 1 | read |

Two related paths bypass `ActivateSource(bool)`, so they carry no `PrOnly` argument:

- `ActivateSourceByID()` (`0x0273a104`) is called from `C_HMI_MEDIA_APP_BASE::HandleSystemMessage`
  at `0x0230c1fc`. That is switch case 19, where the system message field `0xc8` = 22. The source
  is picked by the message field `0xcc`: 4→device 0, 10→1, 5→3, 6→2, **7→5 (AUX)**, 11→4. It is
  also called from `C_HMI_TUNER_APP_BASE::HandleSystemMessage` at `0x02430520`. *(read)* What
  message 22 is, and what `PrOnly` the server gives an ID-only activation, are **not known**.
- `C_BCM_HMI_AUDIO_CLIENT::AllocateSource` is called directly, with each caller's own request, by:
  - `C_HMI_AUDIO_APP_BASE::AllocateNoSource`;
  - `C_HMI_TUNER_TA_Source::AllocateSource`;
  - `C_HMI_NAV_AUDIO_SOURCE::AllocateSource`;
  - `C_HMI_BT_PHONE_MGR::{AllocateRingMenuSource, AllocateRingSource, AllocatePhoneSource}`.

  None of these is AUX. *(read: caller names only; their requests were not decoded)*

### Is any AUX activation path left uncovered by `aux-boot-restore`?

1. **Boot.** Only the `InitApp` site sends AUX's first request. It is the only IDLE→REQUESTED
   transition at boot, because `Open` sets IDLE at `0x0273aa98` immediately before it. Edit 1
   (`0x022c0678`) covers it. *(read)*
   - If the handler then fires while AUX is REQUESTED, its `ActivateSource` only logs "not IDLE",
     so the handler cannot re-send at boot. *(read)*
   - That agrees with car test 1, where the handler-only patch changed nothing.
2. **AUX re-appearing later.** On removal, the handler always calls `ReleaseSource` (states 3–6
   first make an extra virtual call through `+0xe28`), and `ReleaseSource` returns the state to
   IDLE. *(read, `0x02303534`, `0x0273a008`)* On return, `ActivateSource(true)` therefore goes
   IDLE→REQUESTED, and edit 2 (`0x02303474`) covers it. *(read)*
3. **Uncovered, `PrOnly` still 1:**
   - `HandleSystemMessage` at `0x0230b6a4`, and `POPUP_ERR_DETECT::Close` at `0x0232b26c`.
     Both re-activate *the active media device* after releasing it, so they reach AUX only when
     AUX is already the active source. They cannot decide the boot source, because they run on a
     private message or on closing an error popup. For auto-switch they are a re-activation of
     what is already playing. *(inferred from the guards read above)*
   - `HandleMediaStateReady(5, true)`. This is the one path that could send an AUX request with
     `PrOnly` 1 that the patch does not touch. *Read*, and re-checked in the disassembly: the
     argument is loaded by `mr r4,r0` at `0x02306a18` from a local byte at `0x14(r31)`, which is
     set to 1 when the byte at `0x1a0(r31)` is set, so it is computed rather than a literal.
     It needs the media server to send a StateReady DBUS message for device type 5 with that
     `bool` set. **Not known** whether that ever happens. Neither the 2026-09-14 nor the
     2026-09-28 spy request list has been checked for an AUX request with a caller other than
     `InitApp`, so check the next car dump for it.

     !!! note "A candidate fourth edit, not shipped"

         If a car trace shows an AUX request with `PrOnly` true arriving from this path, the
         matching edit would be `0x02306a18` `mr r4,r0` (`7c 04 03 78`) → `li r4,0`
         (`38 80 00 00`). It is **not** in `patches/aux-boot-restore.json`: nothing yet shows
         the path runs for AUX, and it also carries other device types' activations.
4. **Re-requests after a source end** use the template's `PrOnly` 0. *(read)* No edit is needed.

## `C_HMI_SrcMgntBase`: every function

The addresses are the symbol starts. The reference counts come from the survey: `mat` is
materialised references, `ptr` is data pointers.

| address | function | what it does | tier |
|---|---|---|---|
| `0x02738434` | ctor (request, ctx, bool, display, audio client, UP client) | vtable. Stores the clients at `+4`/`+8`. Copies the request (0x2c bytes) to `+0x10` and the ctx (0x1c bytes) to `+0x3c`. State `+0x58` = 0, `+0x5c` = 0, bool → `+0x60`, display → `+0x68` | read |
| `0x0273855c` | ctor (second ABI copy) | same signature; no references found | read (name/size only) |
| `0x027397ac`, `0x02739894` | default ctors | not followed | not known |
| `0x02738684` | `GetStatus(state&)` | `*out = this+0x58`; returns 0 | read |
| `0x027386c0` | `ActivateDisplay` | not followed | not known |
| `0x02738740` | `ReleaseDisplay` | called from `ReleaseSource` and `HandleSrcMgrEnd` | read (calls only) |
| `0x027387c0` | `RemoveContextualMenus` | 10 data pointers: overridden per subclass | read (survey) |
| `0x027387e8`, `0x027388f0` | `Demute`, `Mute` | state switch; logs "Unknown m_source_state" | read (strings only) |
| `0x02738a1c` | `HandleSrcMgrPause` | source-manager PAUSE reply; PAUSED/PAUSED_MUTED | read (strings only) |
| `0x02738c68` | `HandleSrcMgrSuspend` | SUSPEND reply; distinguishes REQUESTED, SUSPENDED, CLOSED/IDLE | read (strings only) |
| `0x02738e10` | `HandleSrcMgrAck(id)` | ACK reply; ACTIVE/MUTED, SOURCE_SUSPENDED | read (strings only) |
| `0x02739160`, `0x0273997c` | `LoadProfile`, `SaveProfile` | per-source volume/bass/treble/loudness/EQ through the UP client, keyed by `t_src_up_labels` (for example `user_HMI.AUX.Vol_aux`) | read (strings + `InitApp` labels) |
| `0x02739f30` | `ReleaseSource` | from states {2, 7}, and the playing states: `ReleaseDisplay`, state → 1 (IDLE), `C_BCM_HMI_AUDIO_CLIENT::ReleaseSource`. Logs "CLOSED or IDLE" otherwise | read (partial) |
| `0x0273a104` | `ActivateSourceByID` | states {2, 7}: `ActivateSourceByID(this+0x14)` (the `SrcId`). Otherwise logs | read |
| `0x0273a248` | `ActivateSource(bool)` | see the overview. State 1: →2, then `AllocateSource` with `PrOnly` = arg for that call only. State 7: `ActivateSourceByID`. Otherwise logs | read |
| `0x0273a400` | `HandleSrcMgrEnd` | states {2, 7}: if `+0x60` is clear → state 2 and **re-`AllocateSource`** with the stored request, else → 1. States 3–6: vtable `+0x10` call, `ReleaseDisplay`, and the same re-request rule | read |
| `0x0273a644` | `HandleSrcMgrMess(msg, app, src)` | dispatcher for source-manager replies; checks the application and source ids | read (strings only) |
| `0x0273a8f0` | `Close` | if state is not 0/1… `Cmd_delete_audio_context`; state → 0 | read (partial) |
| `0x0273a98c` | `Open(labels)` | state → 1, `LoadProfile(labels)`, `Cmd_create_audio_context` | read |
| `0x0273aa70` | `Open()` | state → 1, `Cmd_create_audio_context` (used by video) | read |
| `0x0273ab08`, `0x0273ab9c`, `0x0273ac30` | destructors | not followed | not known |

## Consistency with `docs/AUX_CHAIN.md`

- **Consistent:**
  - `PrOnly` at `this+0x38`, set only for the one `AllocateSource` call and then restored;
  - AUX's boot request comes from `InitApp` with `li r4,1`;
  - the video app passes `true` from `HandleMediaStateReady` and `HandleVideoTrackFound`;
  - the 2026-09-14 dump showing AUX as the only `PrOnly`-true request matches `InitApp`, where
    AUX is the only source given 1.
- **Refinement, not in `AUX_CHAIN`:**
  - the video app's own `InitApp` passes 0;
  - `ActivateSource` does nothing unless the source is IDLE or SUSPENDED;
  - SUSPENDED goes through `ActivateSourceByID`, which carries no `PrOnly` argument.

  An AUX source that was never released (state 7) and is reactivated takes the ID path, not the
  `AllocateSource` path. *(read)* How `C_MGR_SRC` handles that is **not known** from this pass.
- **Possible explanation for BT (`0x1e600`) re-requesting with `PrOnly` true at 15 266 ms:** it
  cannot come from `InitApp`, which passes 0 for BT streaming. The remaining candidates are
  `HandleMediaStateReady` with `bool` true, or the "active device" re-activations at
  `0x0230b6a4` and `0x0232b26c`. *(inferred; not checked against the trace)*

## A survey artefact this reading exposed

While this page was written, `tools/survey.py` attributed bogus strings to some functions
(for example "SendGroupMessage: SendMessage returned Error" on the `C_HMI_SrcMgntBase`
constructor). Its register tracking kept a `lis` value after the register was overwritten.
That was fixed in #153; the counts on [Firmware map](FIRMWARE_MAP.md) are from the fixed scan.
