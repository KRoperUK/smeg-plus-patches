# The source scheduler (`C_MGR_SRC`)

`C_MGR_SRC` decides which audio source plays. Every HMI source sends it a request, it picks
a winner per list, and it restores the saved source at boot. This page reads **all 71
functions** in the `C_MGR_SRC` family of the stock NAV `SMEG5.43.A.R2` image: 60
`C_MGR_SRC` methods and 11 `C_MGR_SRC_msg_private` methods, about 7 600 instructions.
The AUX-specific consequences are in [The AUX chain](AUX_CHAIN.md); the HMI side that sends
the requests is in [How HMI apps request sources](HMI_SOURCES.md).

## How this was read

- **Decompilation:** every function was decompiled by the shared Ghidra server (see
  [Toolchain](TOOLCHAIN.md)). The output stays local; it is derived from vendor code.
- **Disassembly:** where the decompiler was unclear, the code was checked with `tools/ppcdis.py`:
  - the literal 1 in `ChangeToNextSchedulerPosition`;
  - the type→list jump table;
  - the `no_source` tail of `ExecuteAllocation`;
  - the unnamed helpers at `0x0169537c` and `0x016953c8`.
- **Field names:** these come from `ShowStatus()`'s own format strings (`m_Mgr_src_…`), which name almost every field.
  - Where a field name is matched to an offset by print order, not by a traced load, it is marked *inferred*.
- **Evidence tiers:**
  - **read** means the decompiled or disassembled code was followed;
  - **executed** means run under `ppcemu` or observed on the car. `AddRequest`,
    `ChangeToNextSchedulerPosition` and the boot restore reach that tier.

The less obvious behaviour (what `+0x7c` is, why "next position" is always 1, when the source
is saved, a missing NULL check) is collected under [Notable behaviour](#notable-behaviour).

## The object (`0x3f4` bytes, one instance)

`Instance()` allocates `0x3f4` bytes. It registers the object in `C_OBJ_PTR_Table` under **`0x62d4` (25300)**.

- That is the same id the spy uses, which is why the unit's dump lands in `RAMDISK_SPY/25300/`.
- The active-object base is created with the name `"MGR_SOURCE"` and version `"5.42"`.

| offset | name (from `ShowStatus`) | written by | read by |
|---|---|---|---|
| `+0x7c` (byte) | `m_Mgr_src_CurrentNoSrcStatus` *(inferred by order)* | set to 0 by the ctor, `Init`, `ForceSchedulerPosition(…, clear=true)` and `ChangeToNextSchedulerPosition(true, …)`. No non-zero store exists in this family. | `SetCurrentStatus`, `ForceSchedulerPositionByType` |
| `+0x80` | mutex (`semMCreate`) | `Init`; deleted by `End` | taken and given around almost every public entry |
| `+0x84` | init watchdog (`m_wd_timeout`) | ctor (`wdCreate`), deleted by the dtor | `StartUp` arms 7.5 s; `AddRequest` cancels; `SchedulerInitTimeout` re-arms 5 s |
| `+0x88` | type watchdog (`m_wd_type_timeout`) | ctor | `StartUp` arms 7.5 s; `SchedulerTypeTimeout`, `AddRequest` and `RemoveRequest` re-arm 5 s |
| `+0x8c`/`+0x8e`/`+0x90` (u16) | `m_Mgr_src_ActiveMMIPerm` / `…TempMixed` / `…TempNotMixed`: the MsgSrc of each active source | `SetSourceContext` | published to context data `0x62d5` |
| `+0x94`, `+0x98`, `+0x9c` | **Radio slot** of `m_Mgr_src_ActiveTypePermSources`: MMI id, priority, SchedPos | `ReadSupervisorData` (the priority and position, from `Src_Radio_*`), `AddRequest` (the id), `UpdateTypePermSource`, `SearchScheduledSourceByType` | `ImmediateSourceSave`, `ForceSchedulerPositionByType`, `GetLastMediaSource` |
| `+0xa0`, `+0xa4`, `+0xa8` | **Media slot**: the same three fields | same, from `Src_Media_*` | same |
| `+0xac` | `m_Mgr_src_CurrentPermSrcPriority` = `Last_Source_Priority` | `StartUp` (restore), `SetSourceContext` (mode 1, from the active request's `+8`) | `AddRequest` (the restore compare), `RemoveRequest`, `ImmediateSourceSave` |
| `+0xb0` | `m_Mgr_src_CurrentPermSrcType` (0 Radio, 1 Media, 2 neither) | ctor/`Init` (2), `UpdateTypePermSource` | `ChangeToNextSchedulerPosition(…, byType=true)` |
| `+0xb4` | `m_Mgr_src_CurrentSchedPosition` = `Last_Source` | `StartUp` (restore), `ForceSchedulerPosition`, `ChangeToNext…` (literal 1), `ChangeToFirst…`, `RemoveRequest`, `ExecuteAllocationFirstRound` (diag mode) | the first pass, `IsRequestAtCurrentPosition`, `ImmediateSourceSave` |
| `+0xb8`/`+0xbc`/`+0xc0` | `m_Mgr_src_SourceContextPerm` / `…TempMixed` / `…TempNotMixed`: the SrcId of each active source | `SetSourceContext` | context data `0x62d8`–`0x62da` |
| `+0xc4`…`+0xd0` | `m_Mgr_src_NewestRequestPtr[4]`: the list **tails** | `AddRequest` (via `SetNextPostion`), `RemoveRequest(node,…)` | the allocation passes (as a "list non-empty" test) |
| `+0xd4`…`+0xe0` | `m_Mgr_src_OldestRequestPtr[4]`: the list **heads**. List 0 is the permanent ("Scheduled") list; lists 1–3 are temporary (Mixed / Mixable / NotMixable, *inferred by print order*) | same | everywhere |
| `+0xe4` | `m_Mgr_src_PreviousSchedPosition` | every function that writes `+0xb4` saves the old value here first | `RemoveRequest` (return to the previous source) |
| `+0xe8` | `m_Mgr_src_RequestCounter`: ACK sequence number | `SendAllocationMessages` | `ExecuteAllocation` (the save threshold) |
| `+0xec` (u16) | `m_Mgr_src_RequestNb`: nodes in use | `SetNextPostion` ++, `RemoveRequest(node,…)` -- | `AddRequest` (refuses at 9) |
| `+0xf0`…`+0x36f` | the request pool: **10 nodes × 0x40** | `SetNextPostion`, `AddRequest`; cleared by `FUN_016953c8` | the lists link into it |
| `+0x370`…`+0x3bf` | `m_Mgr_src_ScheduledInit[10]`: (SchedPos, priority) pairs | `SetScheduledInit`; zeroed by the ctor/`Init` | `IsInitialized` |
| `+0x3c0` (byte) | `m_Mgr_src_SchedulingAllowed` (the first-pass gate) | `AddRequest`, `SchedulerInitTimeout` | `ExecuteAllocationFirstRound` (modes 1 and 3) |
| `+0x3c4`…`+0x3d0` | `m_Mgr_src_SourceActivePtr[4]`: the ACKed node per list | `SendAllocationMessages` | `SetSourceContext`, `UpdateTypePermSource`, `GetCurrentPermanentSource` |
| `+0x3d4`…`+0x3e0` | `m_Mgr_src_SourceAllocatedPtr[4]`: the winner per list for this pass | `ExecuteAllocationFirstRound`; zeroed by `ExecuteAllocation`, `CheckAfterFirstRound` | `SendAllocationMessages`, `ExecuteAllocation` |
| `+0x3e4`/`+0x3e8`/`+0x3ec`/`+0x3f0` | `m_Mgr_src_RequestCounterEnd` / `…Pause` / `…Suspend` / `…Wait` | the `Send*` call sites | spy only |

Globals used alongside the object:

- `0x035e4cd4`: `Mgr_src_CurrentStatus`.
- `m_Mgr_src_CurrentLockedStatus`.
- `m_mgr_src_diag_test_status` and `m_mgr_src_diag_test_source`.
- `m_is_no_source_active`, a byte written in `ExecuteAllocation` via `0x7a16(r29)`.
- `m_Instance`.

### The request node (`MGR_SRC_ReqData_t` + list links)

The first `0x2c` bytes are the request exactly as sent (`GetMsgReqData` copies `0x2c`). The column names come from the spy's request-list header and `WriteMgrSrcSpy(char const*, MGR_SRC_ReqData_t const*)`'s format string.

| offset | field | notes |
|---|---|---|
| `+0x00` (u16) | `MsgSrc` (`src`) | the sender; the key, together with `+4` |
| `+0x04` | `SrcId` (`id`) | `0xe200` AUX, `0xbc00` tuner, `0xba00` = the "no source" source |
| `+0x08` | priority in mode 1 (`Norm`) | lower wins; **≥ `0xfa` (250) is never eligible** |
| `+0x0c` | priority in mode 4 (`NoSr`) | |
| `+0x10` | priority in modes 2 and 3 (`Lock`) | |
| `+0x14` | `Type` | selects the list: see below |
| `+0x18` | `Sched_Pos` (`sche`) | `0xff` = not scheduled; skipped by `ChangeToNext…` |
| `+0x1c` | `Sched_Typ` | 0 Radio slot, 1 Media slot, 2 neither |
| `+0x20` | `PostPone` (`Post`) | on losing: 1 → `WAIT`, else `END` + removed (temporary lists) |
| `+0x24` | `Suspend` (`Susp`) | on losing while active: 1 → `SUSPEND`, else `END` + removed |
| `+0x28` (byte) | `PrOnly` | set → skips the `ScheduledInit` restore ([The AUX chain](AUX_CHAIN.md)) |
| `+0x30` | node state | 0 free, 1 ACKed (active), 2 ended/waiting/suspended, 3 newly added, 4 paused |
| `+0x38` / `+0x3c` | prev / next | |

The **type→list map** is the jump table at `0x02f4b080`, read via `FUN_0169537c`:

| type | goes to |
|---|---|
| 5, 6 | list 0 (permanent) |
| 2 | list 1 |
| 1 | list 2 |
| 3 | list 3 |
| 0, 4 | rejected (-1) |

Type 4 is handled separately in `AddRequest` (below).

## Modes

`SetCurrentStatus` writes `Mgr_src_CurrentStatus`. The mode decides which priority field counts and whether position matters.

| value | name (`ShowStatus`) | when | permanent winner rule |
|---|---|---|---|
| 1 | `MGR_SRC_NORMAL` | not locked, `+0x7c` clear | **only if `+0x3c0` is set**: the lowest `Norm` among requests whose `Sched_Pos == +0xb4` |
| 2 | `MGR_SRC_LOCKED_TEST_OFF` | locked, no diag test | the lowest `Lock` among all requests, position ignored |
| 3 | `MGR_SRC_LOCKED_TEST_ON` | locked, diag test running | `+0xb4 := diag_test_source`; then as mode 1, using `Norm` |
| 4 | `MGR_SRC_NOSRC` | `+0x7c` set | the lowest `NoSr` among all requests, position ignored |

Temporary lists 1–3 always pick their lowest-priority request, using `Norm`, `Lock` or `NoSr` according to the mode. Position is ignored for them. **read**

## The request lifecycle

**1. Sending a request.** A client calls one of two entry points. Both copy the request into a `C_MGR_SRC_msg_private` and post it to the object's own message queue (`C_BASE_ACTIVE::SendMessage`).
- `AllocateSource(req)` posts message kind 0.
- `ReleaseSource(MsgSrc, SrcId, Type)` builds a request and posts kind 1. It sets `Sched_Typ` from `GetLastSourceType(Sched_Pos)`.

**2. Dispatch.** `HandleMessage` (id `0x62d5`) → `HandlePrivateMessage` takes the mutex and switches on the kind:

| kind | action |
|---|---|
| 0 | `AddRequest` |
| 1 | `RemoveRequest` |
| 2 | diag: `ForceSchedulerPosition(diag_test_source, 0, 0)` |
| 3 | `SchedulerInitTimeout` |
| 4 | `SchedulerTypeTimeout` |

The watchdog callbacks `Mgr_src_SCHED_INIT_TIMEOUT` and `Mgr_src_SCHED_TYPE_TIMEOUT` only post kinds 3 and 4, so every timer effect runs on the manager's own task. **read**

**3. `AddRequest`.**
- It **rejects**:
  - a duplicate (MsgSrc, SrcId) on the same list, as "already added !";
  - an invalid type;
  - a full pool (`RequestNb ≥ 9`), which is answered with `END`.
- A valid request is appended to its list's tail.
- A type 5 or 6 request whose (pos, prio) matches the Radio or Media slot has its MsgSrc recorded in that slot.
- The `PrOnly`/`ScheduledInit` logic then runs exactly as [The AUX chain](AUX_CHAIN.md#how-the-boot-source-is-actually-chosen) documents, and every path ends in `ExecuteAllocation`.

**read; executed under emulation** ([The AUX chain](AUX_CHAIN.md))

**4. `ExecuteAllocation`.**
1. Records the old permanent winner's position.
2. Calls `SetCurrentStatus` and clears the four winners.
3. Runs `ExecuteAllocationFirstRound`, which picks per-list winners using the mode rules above.
4. Runs `CheckAfterFirstRound`. This drops the NotMixable winner if it does not beat the Mixable one, and drops the Mixed/Mixable winners if the NotMixable winner outranks them.
5. Runs `SendAllocationMessages`, then `SetSourceContext`.
6. Saves (see below), and flags `no_source` when the winner is `0xba00`.

**read**

**5. `SendAllocationMessages`** turns the winners into verdicts. Each verdict is published as a 16-byte record `{code, SrcId, seq, MsgSrc}` to context data `0x62d4/0x62db`.

| code | verdict |
|---|---|
| 1 | `ACK` |
| 2 | `END` |
| 3 | `SUSPEND` |
| 4 | `WAIT` |
| 5 | `PAUSE` |

- **Permanent list, losers:** a loser that was active gets `SUSPEND`; one that was not gets `WAIT`.
- **Permanent list, winner:** it gets `ACK` only if no temporary source outranks it. Otherwise it gets `PAUSE`: a NotMixable or Mixable winner, or a Mixed winner on a type-6 request.
- **Temporary lists:** the winner gets `ACK`. A loser gets `SUSPEND` or `WAIT` if its `Suspend`/`PostPone` flag allows it; otherwise it gets `END` and is removed.
- A request that receives `ACK` becomes `m_Mgr_src_SourceActivePtr[list]`.

**read**

**6. `RemoveRequest(req)`** unlinks the node.
- **Temporary lists:** if the node was active, allocation re-runs.
- **Permanent list, when the node is the current source** (`+0xb4`/`+0xac` match): if the release's `Sched_Typ` is 0, it jumps to the **Media slot's** position. Otherwise it returns to `+0xe4`, the previous position, or to the first position if that fails.
- **Either way:** the matching Radio/Media slot is cleared, and the type watchdog is re-armed if no replacement is found.

**read**

## The boot restore and the timers

This is the same as [The AUX chain](AUX_CHAIN.md#how-the-boot-source-is-actually-chosen), restated for completeness.

1. **Construction:** the ctor creates both watchdogs. `Init` then:
   - clears the lists, the pool, `ScheduledInit` and `+0x3c0`;
   - sets `+0xb4 = +0xac = 1`;
   - loads the Radio/Media slot positions and priorities from `supervisor.Src_*`. Their defaults are position 1 and priority 250 when a key is missing.
2. **`StartUp`:**
   - sets `+0xb4 = 0`, then restores `Last_Source → +0xb4` (and `+0xe4`) and `Last_Source_Priority → +0xac`;
   - logs the saved `Last_Source` to the spy (`WriteMgrSrcSpy` at `0x01699488`, from `lwz r5,8(r1)`)
     **before** storing it at `0x0169948c`. So the spy's `Last_Source` line always shows the
     saved value, not the one `aux-boot-default` substitutes at `0x0169948c` *(read)*;
   - subscribes to diag event `0x3dbb`;
   - arms **both** watchdogs for **7.5 s** (`0x1d4c`).
3. **Init timer fires:** `SchedulerInitTimeout` sets `+0x3c0` and calls `ChangeToNextSchedulerPosition(false, false)`.
   - On success, that function writes the literal **1** to `+0xb4` and allocates.
   - If no permanent request with `Sched_Pos ≠ 0xff` exists, it fails. The timer is then re-armed for **5 s** and `+0x3c0` is cleared again.
4. **Type timer fires:** `SchedulerTypeTimeout` fills any empty Radio/Media slot from the first permanent request of that `Sched_Typ`. If none exists, it re-arms for 5 s. Then it runs `SetSourceContext`.

**read**

## Notable behaviour

1. **`+0x7c` is the "no source" status, and nothing in this class sets it.**
   - The byte that switches the manager into mode 4 (`MGR_SRC_NOSRC`, priority field `NoSr`) is only ever cleared inside `C_MGR_SRC`. A scan of the family's 71 functions finds five `stb …,0x7c`, all storing 0.
   - So either another class writes it, or mode 4 is unreachable.
   - **Status:** read (the scan). Who sets it is **not known**; this family was the only range scanned.
2. **"Next" always means position 1.**
   - `ChangeToNextSchedulerPosition` walks the permanent list and computes the **highest** `Sched_Pos` above the current one into `r7`. It then discards it and stores `li r0,1` (`0x01697b44`).
   - Its only success condition is that some permanent request has `Sched_Pos ≠ 0xff` (and, with `byType`, the right `Sched_Typ`).
   - **Status:** read (disassembly), then executed under emulation. The full picture, its four callers and why no patch is recommended are in [the section below](#changetonextschedulerposition-in-full).
   - Patching that literal is the wrong lever for boot-to-AUX; see [below](#why-no-patch-is-recommended).
3. **The source is saved only on a change, and never for the first two ACKs after boot.**
   - `ExecuteAllocation` calls `ImmediateSourceSave` only when the permanent winner's position differs from the previous pass *and* `m_Mgr_src_RequestCounter` (`+0xe8`) is above 2. `Init` sets `+0xe8` to 1, and each `ACK` increments it.
   - `ImmediateSourceSave` writes all six `supervisor` keys at once through `UP_MOD::SetCommonKeysImmediate`.
   - **Status:** read. Consequence (**inferred**): a boot that settles on its first or second ACK does not rewrite `Last_Source`, so the saved value can survive a boot where another source won. Why the saved value is sometimes 1 after AUX boots is **not known**.
4. **`ExecuteAllocation` dereferences the NotMixable winner without a NULL check.**
   - When a permanent winner exists, `0x016974ec` loads `+0x3e0` and reads `+0x1c` from it unconditionally. With no NotMixable winner, that is a read from address `0x1c`.
   - **Status:** read (disassembly). Harmless on VxWorks with page 0 mapped (**inferred**). It matters only to anyone emulating `ExecuteAllocation`: map low memory, or the emulator will fault there.
5. **Diag test positions.**
   - `SetCurrentDiagTestSource` maps the diag object's byte as follows: 2 → position 2, 3 → 4, 4 → 9, anything else → 1. It then posts kind 2, which forces that position **without** allocating.
   - **Status:** read. The position names are **not known**. The `POS_*` strings in `ShowStatus` are not in enum order.
6. **`GetLastSourceType` does not follow the Radio/Media naming.** Its result:
   - pos 1 → 1 (Media);
   - pos 2–5, 7–10 → 0 (Radio);
   - anything else → 2.

   Yet `+0x9c` is saved as `Src_Radio_SchedPos`, and the spy shows the tuner at position 1. In practice the value only steers `RemoveRequest`'s "where to go when the current source leaves" choice. Releasing a source at positions 2–10 (AUX included) jumps to the **Media slot's** position.

   **Status:** read. Whether the enum is simply misnamed is **not known**.

`AddRequest` also materialises the string `R_TP_FLAG_CHANGED`, which the decompiled body does not show being used. **Not known.**

## `ChangeToNextSchedulerPosition`, in full

Stock NAV `SMEG5.43.A.R2`. The function was disassembled, every caller found
(4 materialised sites, no `bl`), and the function itself run under `tools/ppcemu.py` with the
lock, unlock and `ExecuteAllocation` stubbed.

**In short**

- **The computed value is never used** *(read, then executed)*. It is not "the next position"
  either: the loop computes the **highest** scheduled position above the current one. The
  stored value is always 1.
- **In normal mode, position 1 means "the tuner, or no permanent source"** *(read)*.
  `ExecuteAllocationFirstRound` picks the permanent winner only among requests whose
  `Sched_Pos` **equals** `+0xb4`; nothing falls through to the next available position.
- **Whether the 1 is deliberate is not known.** The dead computation suggests a vestigial or
  disabled "next" algorithm *(inferred)*. The rest of the class treats position 1 as the
  canonical fallback: `ChangeToFirstSchedulerPosition` forces it, and so does the timer.
- **Returning to the previous source already exists natively** *(read)*. See
  [below](#return-to-the-previous-source).

### What it does (`0x01697a70`, 99 instructions)

`ChangeToNextSchedulerPosition(bool clear, bool byType)`:

1. Locks the mutex at `+0x80`, then walks the permanent list from `+0xd4` (following `+0x3c`),
   with `r5 = r7 = +0xb4` (the current position) and `r6 = 0` *(read)*.
2. **Per node:** `Sched_Pos` (`+0x18`) of `0xff` is skipped. With `byType`, the node counts
   only if `Sched_Typ` (`+0x1c`) equals `+0xb0`. A counting node sets `r6 = 1` ("something
   schedulable exists"), and if its position is above `r7`, `r7` takes it, so `r7` ends as the
   maximum *(read; executed)*.
3. **If `r6 == 0`:** unlocks and returns −1, storing nothing *(executed)*.
4. **Otherwise:** saves the old position to `+0xe4` ("previous"); `li r0,1` at `0x01697b44`
   (`38000001`) then `stw r0,0xb4` sets the current position to **1**; with `clear`, stores 0
   to the no-source byte `+0x7c`; calls `ExecuteAllocation`; unlocks and returns 0
   *(read; executed)*. `r7` is not read after the loop *(read)*.

**Emulation, stock image** *(executed)*. The request nodes are scratch memory holding only
`+0x18`, `+0x1c` and `+0x3c`.

| state | returns | computed `r7` | stored `+0xb4` | `+0xe4` | `+0x7c` |
|---|---|---|---|---|---|
| boot-timer case: current 7; requests 9, 10, 8, 4, 1 | 0 | 10 | **1** | 7 | unchanged |
| current 9; requests 1, 7, 9 | 0 | 9 | **1** | 9 | unchanged |
| current 1; requests 1, 7, 9, 10 | 0 | 10 | **1** | 1 | unchanged |
| only `0xff` requests | −1 | – | 7 (untouched) | – | unchanged |
| empty list | −1 | – | 7 (untouched) | – | unchanged |
| `clear=true`; requests 1, 7 | 0 | 7 | **1** | 1 | **0** |
| `byType`, type 0; requests 1 (type 1), 7 (type 0), 9 (type 0) | 0 | 9 | **1** | 1 | unchanged |
| `byType`, type 0; only a type-1 request | −1 | – | 7 (untouched) | – | unchanged |

`tests/test_firmware_nav.py` carries two of these rows as tests that run against your own
image.

### Every caller *(read)*

| call site | caller | arguments | when | effect of "always 1" |
|---|---|---|---|---|
| `0x01697c0c` | `SchedulerInitTimeout` | `(false, false)` | the 7.5 s init watchdog fires because no boot restore matched | **FM at boot**: the tuner is acknowledged 7500 ms after `Last_Source` is read *(executed on the car; [Verification](VERIFICATION.md#later-car-tests))* |
| `0x01698620` | `AddRequest`, restore-match branch | `(false, false)` | a request matched (`+0xb4`, `+0xac`) and the timer was cancelled, but `IsRequestAtCurrentPosition()` found no permanent request at `+0xb4` | the tuner. Should be rare: the matching request is itself at `+0xb4` unless it is on a temporary list *(inferred)* |
| `0x01697d2c` | `ChangeToFirstSchedulerPosition(clear)` | `(clear, false)` | `ForceSchedulerPosition(1, …)` failed, so nothing is at position 1; it sets `+0xb4 = 1` itself and calls this | stays at 1, so no permanent source *(inferred)* |
| `0x016bc0d4` | `C_SRV_AUDIO::bcm_ActivateNextSource(bool const&)` | `(true, *arg)` | the DBUS `ActivateNextSource`, from the HMI's `SwitchNextSource` → `AllocateNextSource` → `C_BCM_HMI_AUDIO_CLIENT::ActivateNextSource` | "next source" goes to the tuner. `SwitchNextSource` is reached only through a data pointer (`0x03428974`), so **what triggers it is not known**. The SRC key's cycling works on the car, including reaching AUX, so it probably does not use this path *(inferred)* |

### Return to the previous source

`ChangeToFirstSchedulerPosition` has one caller, **`RemoveRequest`** (`0x016980cc`). When the
current permanent source is released, it first calls `ForceSchedulerPosition(+0xe4, 0, 1)`,
which returns to the **previous** position. Only if that fails does it call
`ChangeToFirst…`, and then `ChangeToNext…`, ending at 1 *(read, `0x016980a0`–`0x016980dc`)*.

So returning to the previous source when AUX drops (the request tracked as issue #4) may need
no patch at all: if AUX's release reaches `RemoveRequest` while the previous source's request
is still queued, the manager goes back to `+0xe4` *(read)*. Whether that request is still
queued at that moment is **not known**. A car test of `aux-signal-switch` *without*
`aux-sticky` would settle it.

### Why no patch is recommended

**A. `0x01697b44` `38000001` (`li r0,1`) → `7ce03b78` (`mr r0,r7`).** CANDIDATE, *executed
under emulation for this function only*. It stores the *highest* scheduled position above the
current one (current 7 with requests 8, 9, 10 stores 10), not the next or the previous one.
Per caller *(inferred)*: the boot timer would jump to the highest queued source (iPod or USB),
not FM or AUX; `bcm_ActivateNextSource` would always land on the top position and never wrap;
`ChangeToFirst…` would land on the highest position instead of staying at 1. **Worse than
stock.**

**B. A true "next-higher, wrap to lowest"** would mean rewriting about six words of the loop
at `0x01697ad4`–`0x01697b1c` (initialise `r7` to a sentinel, take a node when
`current < pos < r7`, wrap to the lowest if none). It is expressible in place, but it changes
all four callers at once, and only `bcm_ActivateNextSource`'s callers plausibly want it. **Not
designed further** until what triggers `SwitchNextSource` is known and "next source" is a real
problem on the car.

**For boot-to-AUX, patching this literal is the wrong lever.** `aux-boot-restore` (with
`aux-boot-default`) avoids the timer altogether by making AUX match the restore, which cancels
it; that pair boots to AUX on the car *(executed; [Verification](VERIFICATION.md#later-car-tests))*.

## Every function

Every row below is **read** or better; no function in the family was left unread.

**Reached by** comes from `tools/survey.py` (see [Firmware map](FIRMWARE_MAP.md)):

- `mat×n`: n `lis`/`addi` sites build the address, i.e. called via `bctrl`;
- `ptr×n`: data (vtable) pointers;
- none of these functions has a direct `bl` caller.

| address | function | insns | reached by | what it does | fields | tier |
|---|---|---:|---|---|---|---|
| `01695424` | `SetCurrentStatus()` | 27 | mat×3 | Sets `Mgr_src_CurrentStatus`: locked → 2, or 3 with a diag test; else `+0x7c` → 4, or 1 | `+0x7c`, global mode | read |
| `01695490` | `RemoveRequest(node, head*, tail*)` | 38 | mat×3 | Unlinks a node from a doubly linked list, clears it, decrements `RequestNb` | `+0xec`, node links | read |
| `01695528` | `SearchScheduledSourceByType(t)` | 26 | mat×3 | For t 0/1, fills the Radio/Media slot from the first permanent request with that `Sched_Typ`; -1 if none | `+0x94…+0xa8`, `+0xd4` | read |
| `01695590` | `SetNextPostion(tail*)` | 26 | mat×1 | Takes the first free pool node (state 0), marks it 3, links it after the tail, increments `RequestNb` | `+0xf0` pool, `+0xec` | read |
| `016955f8` | `IsInitialized(pos, prio)` | 15 | mat×1 | Is (pos, prio) in `ScheduledInit[10]` | `+0x370` | read |
| `01695634` | `IsRequestAtCurrentPosition()` | 18 | mat×1 | Does any permanent request have `Sched_Pos == +0xb4` | `+0xd4`, `+0xb4` | read |
| `0169567c` | `SetScheduledInit(pos, prio)` | 19 | mat×1 | Adds (pos, prio) to the first empty `ScheduledInit` slot unless it is present | `+0x370` | read |
| `016956c8` | `UpdateTypePermSource()` | 27 | mat×1 | Copies the active permanent request into the Radio or Media slot by its `Sched_Typ`; sets `+0xb0` | `+0x3c4`, `+0x94…+0xb0` | read |
| `01695734` | `CheckAfterFirstRound()` | 46 | mat×1 | Arbitrates between the temporary winners: drops the NotMixable winner unless it beats Mixable, else drops Mixed/Mixable | `+0x3d8…+0x3e0` | read |
| `016957ec` | `ExecuteAllocationFirstRound()` | 260 | mat×1 | Picks the winner per list by the mode rules; priority ≥ 250 ineligible; the permanent list is position-gated in modes 1/3 | `+0xd4…`, `+0x3c0`, `+0xb4`, `+0x3d4…` | read |
| `01695bfc` | `GetLastSourceType(pos)` | 13 | mat×1 | pos 1 → 1; pos 2–5, 7–10 → 0; else 2 ([notable behaviour](#notable-behaviour), item 6) | — | read |
| `01695c30` | `WriteMgrSrcSpy(CMMString const&)` | 44 | mat×2 | Writes a string to the spy channel `0x62d4` via `C_BCM_SPY::WriteData` | — | read |
| `01695ce0` | `WriteMgrSrcSpy(char const*)` | 34 | mat×4 | Wraps a C string and calls the above | — | read |
| `01695d68` | `ImmediateSourceSave()` | 199 | mat×1 | Writes `supervisor.{Last_Source, Last_Source_Priority, Src_Radio/Media_SchedPos, Src_Radio/Media_Priority}` now | reads `+0xb4 +0xac +0x9c +0xa8 +0x98 +0xa4` | read |
| `01696084` | `WriteMgrSrcSpy(char const*, ulong, long)` | 96 | mat×9 | Formats `"%lu::%s : %d, 0x%x"` with a timestamp and writes it to the spy | — | read |
| `01696204` | `WriteMgrSrcSpy(char const*, ReqData const*)` | 84 | mat×1 | Formats a whole request (`MsgSrc, SrcId, Type, Sched_Pos, Sched_Typ, PostPone, Suspend`) | — | read |
| `01696354` | `RemoveSpy()` | 30 | mat×1 | Unsubscribes `CallUserSpy`, removes spy configuration `0x62d4` | — | read |
| `016963cc` | `CreateSpy()` | 43 | mat×1 | Registers spy channel `0x62d4` (a `0x19000`-byte buffer) and subscribes `CallUserSpy` | — | read |
| `01696478` | `GetCurrentPermanentSource(&src)` | 34 | mat×3 | Under the mutex, returns the allocated permanent winner's SrcId, or -1 | `+0x3d4` | read |
| `01696500` | `GetLastMediaSource(&src)` | 46 | mat×2 | If the Radio slot has an id, returns the SrcId of the permanent request at the Radio slot's position | `+0x94`, `+0x9c` | read |
| `016965b8` | `SetSourceContext()` | 96 | mat×4 | Publishes the active MsgSrc/SrcId per class to context data `0x62d5…0x62da`; in mode 1 also sets `+0xac` and updates the slots | `+0x8c…+0xc0`, `+0xac` | read |
| `01696738` | `SchedulerTypeTimeout()` | 101 | mat×1 | Fills empty Radio/Media slots, re-arming the 5 s type timer if none are found; `SetSourceContext` | `+0x94…`, `+0x88` | read |
| `016968cc` | `SendPAUSE(req, seq)` | 61 | mat×1 | Publishes verdict 5 | — | read |
| `016969c0` | `SendWAIT(req, seq)` | 61 | mat×1 | Publishes verdict 4 | — | read |
| `01696ab4` | `SendSUSPEND(req, seq)` | 61 | mat×1 | Publishes verdict 3 | — | read |
| `01696ba8` | `SendEND(req, seq)` | 61 | mat×3 | Publishes verdict 2 | — | read |
| `01696c9c` | `SendACK(req, seq)` | 61 | mat×1 | Publishes verdict 1 | — | read |
| `01696d90` | `SendAllocationMessages()` | 415 | mat×1 | Turns winners into ACK/PAUSE/SUSPEND/WAIT/END, removes ended temporaries, records active pointers | `+0x3c4…+0x3e0`, counters | read |
| `0169740c` | `ExecuteAllocation()` | 103 | mat×5 | The allocation pipeline; saves when the position changes and more than 2 ACKs have been sent; `no_source` on `0xba00` | `+0x3d4…`, `+0xe8` | read |
| `016975a8` | `EmptyTempSourceQueues()` | 138 | mat×1 | ENDs and removes every temporary request (skips list 3 while `no_source` is active; stops at SrcId `0x1d600`), then allocates | lists 1–3 | read |
| `016977d0` | `ForceSchedulerPosition(pos, clearNoSrc, alloc)` | 39 | mat×6 | If a permanent request has that position: `+0xe4 := +0xb4`, `+0xb4 := pos`, optionally clears `+0x7c` and allocates | `+0xb4 +0xe4 +0x7c` | read |
| `0169786c` | `ForceSchedulerPositionByType(t, clear)` | 59 | mat×2 | Forces the Radio (0) or Media (1) slot's position unless it is already current | `+0x94…`, `+0xb4` | read |
| `01697958` | `ActivateSourceID(src)` | 70 | mat×1 | Finds the permanent request with that SrcId and forces its position (clear `+0x7c`, allocate) | `+0xd4` | read |
| `01697a70` | `ChangeToNextSchedulerPosition(clear, byType)` | 99 | mat×4 | Succeeds if any schedulable permanent request exists, then **always** sets position 1 and allocates ([in full](#changetonextschedulerposition-in-full)) | `+0xb4 +0xe4 +0x7c` | read; executed (emulation) |
| `01697bfc` | `SchedulerInitTimeout()` | 53 | mat×1 | Sets `+0x3c0`, calls the above; on failure re-arms 5 s and clears `+0x3c0` | `+0x3c0`, `+0x84` | read |
| `01697cd0` | `ChangeToFirstSchedulerPosition(clear)` | 36 | mat×1 | Forces position 1; if nothing is there, sets it anyway and calls `ChangeToNext…` | `+0xb4 +0xe4` | read |
| `01697d60` | `RemoveRequest(req)` | 255 | mat×1 | Release by (MsgSrc, SrcId, Type); re-selects the permanent source if it was current; clears slots | see lifecycle 6 | read |
| `0169815c` | `AddRequest(req)` | 463 | mat×1 | Validation, insertion, slot recording, the `PrOnly`/`ScheduledInit` restore, and the type-4 announce branch | see lifecycle 3 | read; executed (emulation) |
| `01698898` | `ReleaseSource(MsgSrc, SrcId, Type)` | 129 | mat×1 | Builds a release with `Sched_Typ = GetLastSourceType(pos)` and posts kind 1 | — | read |
| `01698a9c` | `ReadSupervisorData()` | 220 | mat×1 | Loads the `Src_Radio/Media_{SchedPos,Priority}` keys (defaults 1 / 250) | `+0x98 +0x9c +0xa4 +0xa8` | read |
| `01698e0c` | `HandleMessage(…)` | 25 | ptr×1 | Routes message id `0x62d5` to `HandlePrivateMessage` | — | read |
| `01698e70` | `End(int)` | 146 | ptr×1 | Resets the VAN source-order counter, removes the spy, cancels the timers, deletes the mutex and the context data, unsubscribes | `+0x80…+0x88` | read |
| `016990b8` | `StartUp()` | 251 | ptr×1 | Restores `Last_Source`/`Last_Source_Priority` (logging the saved value first), subscribes to diag, arms both timers for 7.5 s | `+0xb4 +0xac +0xe4` | read; the restore executed on the car ([Verification](VERIFICATION.md#later-car-tests)) |
| `016994a4` | `Init()` | 193 | ptr×1 | Creates the mutex and spy; resets all state; reads supervisor data; creates the context-data entries | nearly all | read |
| `016997a8` | `~C_MGR_SRC()` (D1) | 97 | ptr×1 | Deletes both watchdogs, clears `m_Instance`, then runs the base dtor | `+0x84 +0x88` | read |
| `0169992c` | `~C_MGR_SRC()` (D0) | 102 | ptr×1 | Same, and frees | — | read |
| `01699ac4` | `~C_MGR_SRC()` (D2) | 102 | none found | Same body as D0 | — | read |
| `01699c5c` | `C_MGR_SRC()` (C1) | 163 | mat×1 | Base `C_BASE_ACTIVE("MGR_SOURCE", "5.42", …)`, zeroes state, creates two watchdogs | — | read |
| `01699ee8` | `C_MGR_SRC()` (C2) | 163 | none found | Identical to C1 | — | read |
| `0169a174` | `Instance()` | 50 | mat×3 | Singleton: allocates `0x3f4`, registers as object `0x62d4` | `m_Instance` | read |
| `0169a2b8` | `CallUserSpy()` | 11 | mat×2 | Calls `MGR_SRC_ShowStatus()` | — | read |
| `0169a2e4` | `ShowStatus()` | 1828 | ptr×1 | Dumps every field, the slot table, both list-pointer sets, the counters, `ScheduledInit` and the request queue to the spy | read-only | read (format strings and structure; individual loads not traced) |
| `0169bf74` | `AllocateSource(req*)` | 108 | mat×1 | Copies the request and posts kind 0 | — | read |
| `0169c124` | `Mgr_src_SCHED_TYPE_TIMEOUT()` | 43 | mat×2 | Watchdog callback: posts kind 4 | — | read |
| `0169c1d0` | `Mgr_src_SCHED_INIT_TIMEOUT()` | 43 | mat×3 | Watchdog callback: posts kind 3 | — | read |
| `0169c27c` | `SetCurrentDiagTestStatus()` | 63 | mat×1 | Reads diag status from context `0x3dbb`; if set, posts kind 2 | diag globals | read |
| `0169c378` | `SetCurrentDiagTestSource()` | 73 | mat×2 | Event `0x3dbb` handler: maps the diag byte to a position ([notable behaviour](#notable-behaviour), item 5) | `m_mgr_src_diag_test_source` | read |
| `0169c49c` | `UnSubscribeByMGRSRC()` | 15 | mat×2 | Unsubscribes from event `0x3dbb` | — | read |
| `0169c4d8` | `SubscribeByMGRSRC()` | 17 | mat×1 | Subscribes to event `0x3dbb` | — | read |
| `0169c51c` | `HandlePrivateMessage(msg)` | 124 | mat×1 | Takes the mutex and dispatches kinds 0–4 | — | read |
| `0169c70c` | `msg_private::GetData(int&)` | 4 | ptr×1 | Returns the payload pointer, size `0x2c` | — | read |
| `0169c71c` | `msg_private::GetMsgReqData()` | 17 | mat×1 | Copies the `0x2c`-byte request out | — | read |
| `0169c760` | `msg_private::SetData(p, n)` | 30 | ptr×1 | Copies `0x2c` bytes in; rejects n < `0x2c` | — | read |
| `0169c7d8` | `msg_private(kind, req)` (C1) | 30 | mat×2 | `C_ActiveMessage(0x62d5, 0x62d4, kind)` + request copy | — | read |
| `0169c850` | `msg_private(kind, req)` (C2) | 30 | none found | Identical | — | read |
| `0169c8c8` | `msg_private(kind)` (C1) | 27 | mat×3 | Same, with a zeroed request | — | read |
| `0169c934` | `msg_private(kind)` (C2) | 27 | none found | Identical | — | read |
| `0169c9a0` | `msg_private()` (C1) | 27 | mat×1 | Default kind | — | read (the default kind value is not checked) |
| `0169ca0c` | `msg_private()` (C2) | 27 | none found | Identical | — | read |
| `0195baf8` | `~msg_private()` (D0) | 22 | ptr×1 | Base dtor, then free | — | read |
| `0195bb50` | `~msg_private()` (D1) | 14 | ptr×1 | Base dtor | — | read |

Two helpers without symbols sit just before the class and are used throughout: `FUN_0169537c` (the type→list map) and `FUN_016953c8` (clear a pool node: SrcId -1, `Sched_Typ` 2, the rest 0). Both were **read** from disassembly.

The vxWorks calls reached through `0x0058xxxx` stubs are named here from their error strings: `semTake`/`semGive`/`semDelete`/`semMCreate` and `wdCreate`/`wdStart`/`wdCancel`/`wdDelete`. That naming is **inferred**; the stubs themselves were not read.
