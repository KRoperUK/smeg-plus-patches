# The AUX auto-switch, gate by gate

This is the single reference for what has to happen, in order, for the unit to select AUX
by itself when a signal appears — the project's goal — and what is known about each step.
Everything with an address was read out of the `NAV` image; everything marked **executed** was run under
[the emulator](EMULATION.md) rather than reasoned about.

If you only read one thing: the chain below does not start from the AUX **signal** at all.
It starts from a change of the saved AUX **input setting**, so stock firmware has no path that
switches to AUX when a signal appears. See
[What the handler actually reacts to](#what-the-handler-actually-reacts-to).

## The chain

```mermaid
flowchart TD
    AS["audio server"] -->|"DBUS AUDIO_AUX_INPUT_STATUS_CHANGED"| CL["C_BCM_HMI_AUDIO_CLIENT"]
    CL --> LA{"LINK A<br/>client-&gt;0x50 == NULL?"}:::unknown
    LA -->|null| STOP["return — no listener"]
    LA -->|set| P203["post message 203 (0xcb)<br/>@ 0x025cdefc"]
    P203 -->|message 203| HDB["C_HMI_MEDIA_APP_BASE::HandleDBUSMessage<br/>@ 0x02309398 · case 0xcb"]
    HDB --> H["HandleAudioAuxInputStatusChnged<br/>@ 0x0230331c"]
    H --> G1{"gate 1 · app NULL?<br/>@ 0x02303358"}
    G1 -->|null| R["shared return path"]
    G1 --> G2{"gate 2 · state unchanged?<br/>@ 0x023033d4"}
    G2 -->|unchanged| R
    G2 --> G3{"gate 3 · GetMediaDevice AUX failed?<br/>@ 0x02303428"}:::never
    G3 -->|failed| R
    G3 --> G4{"gate 4 · source mgr NULL?<br/>@ 0x02303468"}:::never
    G4 -->|null| R
    G4 --> ACT["ActivateSource srcMgr, true<br/>@ 0x02303484"]:::ok

    classDef unknown fill:#fff3cd,stroke:#b8860b,stroke-width:2px;
    classDef never fill:#e3f2fd,stroke:#1565c0;
    classDef ok fill:#e6f4ea,stroke:#2e7d32,stroke-width:2px;
```

Reading the colours: **LINK A** (amber) is the only link that has never been observed — it
depends on runtime state. **Gates 3 and 4** (blue) never fire, proven under
[the emulator](EMULATION.md). The success path (green) is reached once the four gates pass.
The same trace as a call listing:

```
audio server
  --DBUS AUDIO_AUX_INPUT_STATUS_CHANGED-->  C_BCM_HMI_AUDIO_CLIENT
                      if (client->0x50 == NULL) return;        <-- LINK A: no listener
                    post internal message 203 (0xcb)           @ 0x025cdefc
  --message 203-->  C_HMI_MEDIA_APP_BASE::HandleDBUSMessage    @ 0x02309398
                      case 0xcb                                @ 0x02309638 -> 0x02309fbc
  --direct call-->  HandleAudioAuxInputStatusChnged            @ 0x0230331c
                      gate 1  app = this->0x50df4, NULL?       @ 0x02303358
                      gate 2  state unchanged?                 @ 0x023033d4
                      gate 3  GetMediaDevice(AUX) failed?      @ 0x02303428
                      gate 4  source manager NULL?             @ 0x02303468
                    ActivateSource(srcMgr, true)               @ 0x02303484
```

## Link A — the listener

The client only posts message 203 if something registered for it:

```c
void C_BCM_AUDIO_CLIENT::AUDIO_AUX_INPUT_STATUS_CHANGED(client) {   // 0x025c9e78
    if (client->0x50 == NULL) return;       // 0x025c9e9c
    Post203(client->0x50);                  // 0x025cdefc
}
```

An earlier version of this page called `0x025c9e78` `OnAuxSignalStatusChanged`. The symbol map
names it `C_BCM_AUDIO_CLIENT::AUDIO_AUX_INPUT_STATUS_CHANGED`: it is the **input** (setting)
notification, not the signal one. The name had been assumed from what the chain was expected
to do.

`client->0x50` is written by one setter (`0x025c97f0`), called from two places, both of
which look like this:

```c
if (app->0xc == NULL) return;           // no proxy, no registration
SetListener(app->0xc, app);
```

So the listener exists only if `app->0xc` does. **That same `app->0xc` is what the AUX
setting query dereferences** (`0x025cb280`), returning `-1` without touching its out-param
when it is null — and gate 2 discards that return value. One null pointer there would
produce exactly the symptom seen on the car: no switch, no error, nothing in the UI.

`app` itself is `mediaApp->0x50df4`, assigned at `0x022bc4e8` from a DBUS client factory
(`0x025fc3e8`) called as `Create(3, 0xc8, this)`. That factory is a lookup-or-create with
**several paths that return NULL** — it needs a DBUS connection at the moment the media
application initialises. Whether any of them is taken on a real unit is not knowable from
the image; it is the open question.

!!! question "This link has never been observed"

    Everything downstream of it has now been executed. Link A has not, because it depends
    on runtime state (a DBUS connection) that no static reading can settle.

## The four gates in the handler

Recovered by executing the function, not by reading it:

```c
void HandleAudioAuxInputStatusChnged(this) {       // 0x0230331c
    app = this->0x50df4;                           // 0x022ad2c0 — a plain getter
    if (app == NULL) return;                       // gate 1  @ 0x02303358
    ctor(&obj);                                    // 0x02368080 — zeroes obj entirely
    Get_aux_status(app, &setting);                 // 0x025cb258 — RETURN VALUE DISCARDED
    state = (setting != 0);                        // the saved AUX input setting, not a signal
    if (state == this->0x51449) return;            // gate 2  @ 0x023033d4
    this->0x51449 = state;
    if (GetMediaDevice(mgr, AUX, &obj)) return;    // gate 3  @ 0x02303428
    SetMediaDeviceState(mgr, AUX, 2);              // 0x022f388c
    if (obj[0x10] == NULL) return;                 // gate 4  @ 0x02303468
    ActivateSource(obj[0x10], true);               // 0x0273a248
}
```

| gate | tests | status |
|---|---|---|
| 1 | the audio client exists | **unknown** — the only untested link, see above |
| 2 | the saved AUX input setting changed between zero and non-zero | **a real gate** — only acts on a transition |
| 3 | `GetMediaDevice(AUX)` succeeded | **never fires** — executed; see below |
| 4 | the device carries a source manager | **never fires once gate 3 passes** |

**Gate 2 is a change detector, on the AUX input setting.** The value compared is the setting
`Get_aux_status` returns (`C_MODULE_AUDIO+0x8c`, the `audio/Auxiliary_Status` key), not signal
presence; see below. A setting already non-zero when the state is first recorded produces no
activation, because nothing changed. Because the query's return value is thrown away, a
*failed* query reads as "setting 0" and lands here as "no change". A broken link A and an
AUX input switched off in the menu are indistinguishable at this point.

**Gate 3 is what `aux-autoswitch` nops, and it never fires.** The AUX media device is
registered unconditionally at start-up, so `GetMediaDevice(AUX)` succeeds. **Executed:**
running the registration function fills the table with types `{0, 1, 2, 3, 5}`.

**Gate 4 is why nopping gate 3 would not have helped anyway.** `GetMediaDevice` writes
nothing to its out-param when it fails, so the field gate 4 tests is still the zero the
constructor left. See [Emulating the firmware](EMULATION.md) for the full truth table.

!!! danger "Do not nop gate 4"

    `0x0230346c` loads that field straight into `r3` as `ActivateSource`'s `this`. Removing
    the guard calls a C++ method on a null pointer, on the HMI thread.

## What the handler actually reacts to

!!! failure "Correction: the handler follows the AUX setting, not the AUX signal"

    This page, [the archived analysis](ANALYSIS.md), the README and several patch
    descriptions described `HandleAudioAuxInputStatusChnged` as reacting to **an AUX signal
    appearing**. It does not. The claim came from reading the chain by function names and by
    what it was expected to do: the variable gate 2 tests was called `signal` on assumption,
    `0x025c9e78` was named `OnAuxSignalStatusChanged` without checking the map, and the
    emulator runs fed the status query a 1 labelled "the AUX signal appears". Those runs
    established the handler's control flow for a given value. They said nothing about what
    the value means.

What the value is, **read** from the disassembly:

* `C_MODULE_AUDIO::Get_aux_status` (`0x013b9c8c`) returns `lwz r0,0x8c(r31)` whenever the
  module's lifecycle state `+0x74` is non-zero.
* The only writers of that field on the module object are `setAUXGain` (`0x013bba28`,
  `stw r30,0x8c(r29)`, the setting it was given) and `read_sqlite_AudioUserData`
  (`0x013caba8`), which loads the user key `Auxiliary_Status`; the string is in the image.
* So `+0x8c` is the **AUX input setting** from the media options menu, 0..3 — not whether audio
  is arriving. Signal presence is a different call, `Get_AUX_signal_status`, which reads the
  radio front-end.

Which DBUS notification reaches the handler, **read**: `C_BCM_HMI_AUDIO_CLIENT`'s
`AUDIO_AUX_INPUT_STATUS_CHANGED` posts HMI message `0xcb` (`li r4,0xcb` at `0x025cdf1c`), and its
`AUDIO_AUX_SIGNAL_STATUS_CHANGED` posts `0xcc` (`li r4,0xcc` at `0x025cded0`). The media app
dispatches the handler on `0xcb`, above. The close reading of the audio module found no `0xcc`
case in the media app's `HandleDBUSMessage` and the audio app using `0xcc` only to refresh its
menu — *read in that reading, not re-checked independently*.

When the setting notification is raised, **read** (see [The audio module](AUDIO_MODULE.md)):

* when the setting is written from the menu (`Set_aux_status` → `setAUXGain`);
* **once per boot**, at the end of `ElabRADIO_READY_FOR_INIT_0`, which calls
  `setAUXGain(+0x8c, 1)`. Whether the media app is listening by then is **not known**.

What follows:

* **Stock firmware has no path that switches to AUX because a signal appeared.** For the
  media dispatch this is **executed**: the stock window sends `0xcc` to its default case
  ([Emulation results](AUX_SIGNAL.md#emulation-results)). For the whole image it remains
  *inferred* from the routing above, since other paths are not exhaustively excluded. The observed behaviour on the car — AUX greys out and re-enables with
  the signal — is `IsAUXSRCAvailable()` in the audio app, a separate path.
* **`aux-autoswitch`'s premise needs re-examining.** Its second edit nops gate 3, which never
  fires (executed), and even with every gate open the handler would act on a *setting* change.
  Its first edit, `IsAUXSRCAvailable()`, is confirmed on hardware and is unaffected.
* **A real signal-triggered switch would need a new wire.** Now `patches/aux-signal-switch.json`,
  **executed** under emulation (handler and dispatch window), not flashed: route
  `0xcc` into the media app's AUX handler, and make that handler test `Get_AUX_signal_status`
  rather than `Get_aux_status`. Two constraints from the audio module apply: signal events are
  dropped until the radio has started (`+0x74` = 10), and AUX is kept muted while it is the
  current source with no signal (`+0x168`). The whole signal path and the emulation results are
  in [The AUX signal path](AUX_SIGNAL.md).
* **`aux-boot-restore` is unaffected at boot.** Its boot edit is on `InitApp`, which does not go
  through this handler. Its handler edit still covers the boot-time re-announcement and later
  setting changes. What changes is the expected *auto-switch*: see below.

## The media device table

`GetMediaDevice` and its neighbours operate on a fixed array hanging off the media app at
`this+0x50e60`:

```
mgr + 0x00 + n*0x20   device record n, 6 slots
mgr + 0xc0            how many are in use
```

Each 32-byte record holds its type at `+0x00` and its source manager at `+0x10`. Three
functions matter:

| function | address | behaviour |
|---|---|---|
| `FindDevice(mgr, type)` | `0x022f3608` | linear scan of the first `mgr[0xc0]` slots; returns the record or NULL |
| `GetMediaDevice(mgr, type, out)` | `0x022f3750` | `FindDevice`, then field-by-field copy into `out`; returns 0, or **-1 writing nothing** |
| `AddDevice(mgr, src)` | `0x022f3ad0` | append; refuses when `mgr[0xc0] > 5` |

Registration runs once, from media-app init (`0x022bf934` → `0x022b833c`), and is
unconditional — every early-out branch in the caller rejoins before the call. It registers
types 0, 1, 2, 3 and 5 outright, then type 4 only if the byte at `this+0x51450` is set.

### Which type is AUX

Type **5**. Two independent lines of evidence:

- Every `GetMediaDevice`/`SetMediaDeviceState` call site that passes type 5 — `0x02303404`,
  `0x02303450`, `0x02303564` — is **inside the AUX handler**, and no other function uses it.
- Type 4, the only other candidate, is used by unrelated call sites and is gated on a byte
  written in exactly **two places in the whole image, both constructors, both storing 0**.
  Nothing sets it, so type 4 can never be registered at all.

Note the trap: this is not the same enum as the **source** list recovered from the HMI
`OnEventSelect*` handlers. Two namespaces, overlapping numbers. Do not carry a value from
one into the other — and there are more than two.

### Six source numberings, and which one `Last_Source` uses

| numbering | where it comes from | AUX is |
|---|---|---|
| media device type | the table `GetMediaDevice` searches | **5** |
| HMI source | `OnEventSelect*` → `CreateNotificationCommand` | **7** |
| audio module `SRC_*` | the name table at `0x02f9d60c`, printed as `Current_source` | **5** |
| `C_MGR_SRC` scheduler position (`POS_*`) | `AllocateSource`'s `Sched_Pos` field and the SPY dump's switch | **7** |
| `C_MGR_SRC` request `SrcId` | `AllocateSource`'s `SrcId` field | **`0xe200` for AUX** (executed, 2026-09-14 spy archive); observed values are `0xba00`, `0xbc00`, `0xc000`, `0xe200`, `0x17400`, `0x1e200`, `0x1e600` |
| screen position | `GetSourceAtPosition`, 0-based | **4** |

The audio module's table is contiguous from `SRC_NO_SOURCE = 0`:

```
0 SRC_NO_SOURCE   1 SRC_TUNER   2 SRC_CD    3 SRC_MP3      4 SRC_CDC
5 SRC_AUX         6 SRC_PHONE   7 SRC_TTS   8 SRC_TA_PTY   9 SRC_TTS_ON_AUX
10 SRC_AUX_CONVERGENCE  11 SRC_BLUETOOTH  12 SRC_MTB  13 SRC_MLDIPO_RECO_PHONE
```

Two of these put AUX at `7`, but the SPY capture now settles which `C_MGR_SRC` field the
factory `Last_Source = 1` follows. At boot the same module logged:

```
6639::Last_Source : 1 (0x1)
9742::AllocateSource : MsgSrc=10, SrcId=0xbc00, Sched_Pos=1, ...
Current_source ... SRC_TUNER
```

That is **executed runtime evidence**: tuner was active; its request's `SrcId` was `0xbc00`; its
scheduler position was `1`; and `Last_Source` was `1`. Therefore `Last_Source` follows the
`Sched_Pos`/`POS_*` namespace, **not the raw request `SrcId`**. For AUX that namespace says `7`.
This is stronger than the previous inference from object ownership and corrects the section below,
which had labelled request `+0x18` as the value compared directly with `Last_Source`.

`4` and `7` have both been shipped in payloads without the unit starting on AUX, but neither value
reached the live database. The later SPY settings dump still reads
`supervisor.Last_Source.0 <int> : 1`, and the updater log still copied the payload into uppercase
`SQLITE`. So `7` remains untested as a live setting; the observed boot-to-radio result still
settles delivery, not the value.

### The key belongs to `C_MGR_SRC`, and the value must match a live source request

The key is read and written through the generic config loader in the core middleware — read
at `0x01699390`, written at `0x01695e2c` from the field at `+0xb4` of the object. That object
is `C_MGR_SRC`: its `UP_Keys` names (`Last_Source`, `Last_Source_Priority`,
`Src_Radio_SchedPos`, `Src_Media_SchedPos`, `Src_Radio_Priority`, `Src_Media_Priority`) sit
contiguously at `0x0300a578`, immediately ahead of the class's own log strings at
`0x0300a6a4`.

Following `+0xb4` gives the shape of the value. In the NAV build:

| address | what it does |
|---|---|
| `0x01699490` | boot restore: the value read back from `Last_Source` is **stored straight to `+0xb4`** and mirrored to the global `0x035e4cd0`, with no validation at all |
| `0x016995b4` | constructor: `+0xb4` and `0x035e4cd0` are both initialised to `1` — the same value the factory database ships |
| `0x0169c6ac` | reads `0x035e4cd0` and passes it as the scheduler-position argument to `0x016977d0` |
| `0x016977d0` | the position setter — walks the request lists and writes `+0xb4` only on a matching `Sched_Pos`; a miss leaves `+0xb4` alone |
| `0x016957ec` | the scheduler — **selects the source to restore** by matching `node+0x18` (`Sched_Pos`) against `+0xb4` |
| `0x0169815c` | `C_MGR_SRC::AddRequest` — copies `SrcId` to `node+0x04` and `Sched_Pos` to `node+0x18` |
| `0x0169c51c` | the `C_MGR_SRC` message dispatcher (message id `0x62d5`): case 0 → `AddRequest`, case 1 → `RemoveRequest` at `0x01697d60`, case 2 → re-apply `Last_Source` |
| `0x0169bf74` | `C_MGR_SRC::AllocateSource` — the client entry that packages a request and sends it into the dispatcher |
| `0x0169a2e4` | the `MGR_SRC SPY` dump — switches on `Sched_Pos` to name each position (`POS_*`) |

`0x016977d0` walks the first request list, anchored at `this+0xd4` (`next` at `+0x3c`),
comparing its scheduler-position argument against each node's `+0x18` (`Sched_Pos`) field, and
writes `+0xb4` on a match. A position that matches nothing falls straight out to the return path
**without touching `+0xb4`**:

```
016977dc  lwz    r9, 0xd4(r3)     ; head of the first request list
016977e0  cmpwi  cr7, r9, 0
016977e4  bne    cr7, 0x16977f8
016977e8  b      0x1697854        ; empty list -> give up
016977ec  lwz    r9, 0x3c(r9)     ; node = node->next
016977f0  cmpwi  cr7, r9, 0
016977f4  beq    cr7, 0x1697854   ; ran off the end -> give up
016977f8  lwz    r0, 0x18(r9)     ; node->Sched_Pos
016977fc  cmpw   cr7, r4, r0
01697800  bne    cr7, 0x16977ec   ; no match -> keep walking
01697804  ...                     ; matched: commit to +0xb4
```

!!! warning "The setter cannot reject the flashed value"

    Because the miss path leaves `+0xb4` untouched, the setter is not a validator for what the
    database ships. Boot restore has already written `+0xb4` unconditionally, and the
    message-2 path only re-affirms it from `0x035e4cd0`. **A value written into the database
    always takes effect as far as `+0xb4` is concerned** — the question is only whether
    anything downstream does anything with it.

The consumer that gives the value its meaning is the scheduler at `0x016957ec`. It walks the
same lists and, in the mode where the stored source is being restored, picks the node whose
`+0x18` equals `+0xb4`:

```c
iVar7 = DAT_035e4cd0;                                       // the mirrored Last_Source
...
do {
    if (*(int *)(iVar6 + 0x18) == *(int *)(param_1 + 0xb4)) {   // node Sched_Pos == Last_Source
        ... remember this node as the source to restore ...
    }
    iVar6 = *(int *)(iVar6 + 0x3c);
} while (iVar6 != 0);
```

So `Last_Source` must equal the **`Sched_Pos` the source request registered**, or nothing matches
and no source is restored — the unit falls back to its default. The runtime tuner tuple
`Last_Source=1, SrcId=0xbc00, Sched_Pos=1` confirms this interpretation. That is the real gate,
and it is downstream of the value, not a check on it.

#### What a request node is, and who writes `+0x18`

`C_MGR_SRC::AddRequest` (`0x0169815c`) is the registration site this page previously listed as
unfound. It logs under the `C_MGR_SRC` / `AddRequest` strings (`0x0300a6a4` / `0x0300a6b0`)
and is reached from the class's message dispatcher, keyed on **message id `0x62d5`**:

```
source module
  -> send(object, 0x62d5, opcode, flags)      common helper 0x014da78c
  -> C_MGR_SRC dispatch  FUN_0169c51c         (0x62d5 matched at 0x1698e18)
       case 0 -> FUN_0169815c  AddRequest
       case 1 -> FUN_01697d60  RemoveRequest
       case 2 -> FUN_016977d0(this, DAT_035e4cd0, 0, 0)
```

The message body is a 0x6a-byte payload; the request is the 0x2c-byte struct at `+0xc` of it
(`FUN_0169c71c` is a plain `memcpy`). `AddRequest` copies that struct into a freshly allocated
node, links it, and commits:

```c
node = SUB_01695590(this, idx * 4 + this + 0xc4);
if (*(int *)(idx * 4 + this + 0xd4) == 0) *(int *)(idx * 4 + this + 0xd4) = node;
*(short *)(node + 0x00) = req.MsgSrc;
*(int *)  (node + 0x04) = req.SrcId;
*(int *)  (node + 0x14) = req.Type;
*(int *)  (node + 0x18) = req.Sched_Pos;  // <-- the field the setter and scheduler compare
...
FUN_016977d0(this, req.Sched_Pos, 1, 1);
```

??? note "Corrections to an earlier reading of this page"

    * `this+0xd4` is **not a single list of registered sources**. It is the first of four list
      heads in an array (`+0xd4`, `+0xd8`, `+0xdc`, `+0xe0`) selected by a mapping of the request
      `Type`. The nodes are **pending requests**, not a registry.
    * The setter's "must match a node" condition is satisfied trivially here: `AddRequest` inserts
      the node and then immediately calls the setter with the same id. It was never the gate it
      looked like.

The request carries both values: `SrcId` at request `+0x04` (byte `0x10` of the message payload)
and `Sched_Pos` at request `+0x18` (byte `0x24` of the payload). The live dump prints both, which
is what exposed the earlier conflation. AUX's `Sched_Pos` is `7`, and its raw `SrcId` is `0xe200`,
**executed** in the 2026-09-14 spy archive: the one request with `Sched_Pos= 7`, and the source
`ActivateSourceID` switched to when AUX was selected. `0xe200` is not what `Last_Source`
stores.

Requests reach the dispatcher through the client entry `C_MGR_SRC::AllocateSource`
(`0x0169bf74`), which copies the 0x2c-byte request and sends it. `AllocateSource` is reached
from the client wrapper `0x016bc1dc` — not `0x016bc1f0`, which an earlier pass took for the
function start and which is really four instructions inside it — and that wrapper resolves the
service directly with `FUN_0103155c(0x62d4, 0)`.

The ~30 `0x62d5` sites are not that table. Eighteen of them sit at
`0x014dc1a8`–`0x014dd358`, but their common helper `0x014da78c` emits a **0x14-byte** control
body, not the 0x6a-byte request, so they are short notifications that reuse the same message
id rather than source registration.

The client API is a fixed cluster, and it is worth knowing its shape before hunting in it. Eight
wrappers sit at `0x016bbec4`–`0x016bc2ac`, each with exactly one caller; those callers are the
public API at `0x016c09bc`–`0x016c0d3c`; and the public entries are exported through a **service
API table** at `0x0307aedc`–`0x0307af00` (C_MGR_SRC's slots — the table itself runs well beyond
them). Nothing references that table by literal address or by `lis/addi`, because it is reached
through the dynamic service registry (`FUN_0103155c(0x62d4, …)`, `FUN_01001178()`).

That is the wall for static tracing, and it is worth stating plainly: **the per-source callers of
`AllocateSource` cannot be found by xref.** `AllocateSource` has one caller, that caller has
none, and the entry above it is indexed at run time. Finding which module allocates AUX's
request needs the registry resolved, not another xref sweep.

!!! warning "Provenance"

    Everything in this subsection is **read from decompiled code**, not executed — the
    corrected mechanism included. The project's rule applies: reachability is proof, and a
    reading is not. The part corroborated by execution is the setter's own shape, which was
    confirmed by disassembly when this page was first written.

The `Sched_Pos` space is `C_MGR_SRC`'s own **position** enum, readable from the SPY dump at
`0x0169a2e4`, which switches on a per-source field at `+0x370` and names it:

| value | name | value | name |
|---|---|---|---|
| `0` | `POS_NULL` | `6` | `POS_VIDEO` |
| `1` | `POS_TUNER` | `7` | `POS_AUX` |
| `2` | `POS_1CD` | `8` | `POS_BT` |
| `3` | `POS_MP3` | `9` | `POS_USB` |
| `4` | `POS_CDC` | `10` | `POS_IPOD` |
| `5` | `POS_JBX` | `0xff` | `POS_NOT_SCHEDULED` |
|  |  | other | `POS_MGR_SCR_NOT_SCHEDULED` |

**AUX is `7` here, and `5` is the Jukebox** — so the value
[`aux-default-retry.json`](https://github.com/KRoperUK/smeg-plus-patches/blob/main/builds/aux-default-retry.json)
ships has `C_MGR_SRC`'s own naming behind it, not only the HMI numbering's.

Two enums describe sources and they agree at `1` — the factory `Last_Source`, `POS_TUNER`, and
the audio module's `SRC_TUNER` all coincide — but they disagree at AUX: the audio module's
`SRC_*` table has `SRC_AUX = 5`. Since `+0xb4` belongs to `C_MGR_SRC`, its own enum is the one
that should apply, which is a second independent line of evidence for `7` beside the HMI
numbering.

??? note "Why the enum is read from the switch, not the literal order"

    Read the mapping from the switch, not from the string literals. `POS_AUX` sits between
    `POS_MP3` and `POS_BT` in the literal table but is `7` in the enum; an earlier version of
    this page assumed the literals were in value order and concluded `5`. They are not in value
    order.

### The beacon, and what the retry actually answered

Because no `USER_DATA` flash has yet been confirmed to apply, a unit that still starts on
radio is ambiguous — wrong value, or payload skipped again? Ship a **beacon** alongside the
change: a second, unrelated key whose effect is visible and trivially reversible.
`aux-default-retry.json` moves `clock.Time_Zone` from `16` to `0`. After the flash, read the
configured time zone in the settings menu — not the clock face, which a GPS-slaved clock
corrects regardless:

| time zone | source | conclusion |
|---|---|---|
| changed | AUX | the value is right and the mechanism works |
| changed | radio | payload applied and `+0xb4` holds `7`, which the enum says is AUX — so suspect the path (registration or scheduling), not the number |
| unchanged | either | payload was skipped again; the source result means nothing |

The retry answered **`unchanged`**: the time zone did not move, so the payload was skipped once
more and the boot-to-radio result is uninformative. What that points at — a hard-coded source
path that was nonetheless correct on the stick, a step-gated copy, and a save/restore round trip
— is written up under the second flash in [Hardware verification](VERIFICATION.md).

## What to do next

1. **Car test of the three-edit `aux-boot-restore`** (built, on a stick). Does it boot to AUX over
   two restarts? Then `SPYTAKE`/`SPYSTORE`, and check the `25300` buffer for AUX's request with
   `PrOnly` false and a `ScheduledInit` row (7, 20). The procedure is
   [the test loop](FLASHING.md#the-test-loop-end-to-end).
2. **Car test of `builds/aux-signal-switch.json`**, only after test 1 has been read; see
   [What the car test answers](AUX_SIGNAL.md#what-the-car-test-answers).
3. **If test 1 still boots to FM:** look in the capture for an AUX request from
   `HandleMediaStateReady`. The candidate fourth edit is at `0x02306a18`; see
   [How HMI apps request sources](HMI_SOURCES.md).

Earlier routes, now closed or superseded:

- **Observe it through the spy — done.** `C_MGR_SRC`'s dump emits through `C_BCM_SPY::WriteData`,
  not the stubbed log sink, and the user spy collect carries it: the 2026-09-14 and 2026-09-28
  archives answered the questions a log was wanted for. See
  [Cheatcodes](CHEATCODES.md#a-module-dump-reaches-the-spy-not-the-dead-log-sink).
- **Give the firmware a log to write to — superseded.** The handler logs its own name on its
  shared return path (**executed**: every exit reaches the log call), but this build's
  `Log_msg` sink is stubbed. `patches/diagnostic-logsink.json` points it at VxWorks `logMsg`
  (`0x00484a94`); where that output surfaces is issue #94. Until then the diagnostic build is
  buildable but not readable, and the spy capture is the route.

## What the first car test established

The build described above was flashed and observed. Three results, one of them a
falsification.

**`aux-boot-default` is applied, correctly located, and ineffective.** The shipped image holds
`39200007` at `0x0169948c` (pristine holds `81210008`), and that site falls inside
`C_MGR_SRC::StartUp` (`0x016990b8`, 1004 bytes, ending exactly where `C_MGR_SRC::Init` begins at
`0x016994a4`). So the patch does what its description says — `li r9,7` then `stw r9,0xb4(r31)`,
with the value read straight back at `0x01699498` — and the unit still comes up on **FM**, *with
audio playing into the AUX input*. AUX was visible and selectable, so `aux-autoswitch` worked.

That falsifies the obvious explanation. The reading this file previously leaned on — no signal,
so no request node, so FM — does not survive a test with signal present: a node for
`Sched_Pos = 7` is there and does not win.

**Where the match actually happens.** A full scan for readers of `+0xb4` finds `0x01695b90`,
inside `ExecuteAllocationFirstRound` (`0x016957ec`–`0x01695bfc`), near the end of it. It is the
only reader of that field in that function — but not the only access: the same function also
*writes* `+0xb4` at `0x01695b30`, and the class has eleven writers in all. See
[How the boot source is actually chosen](#how-the-boot-source-is-actually-chosen).

**Withdrawn: the ordering hypothesis.** This section previously proposed that the first
allocation pass runs *before* `StartUp` writes `+0xb4`, and that patching the read at
`0x01695b90` to a constant 7 would fix it. Both are withdrawn. `ExecuteAllocationFirstRound` is
reachable only through `ExecuteAllocation`, which only request and scheduler paths call —
`StartUp` never enters allocation — and the match at `0x01695b90` is disabled until a flag that
`StartUp`'s own timer sets. The hypothesis came from reading address order as execution order,
which this section had itself warned against. The section below replaces it.

## A symbol map now exists

The SPYSTORE dump from the same unit carries `abs_symbols_base.txt.gz` and four companions —
**98,365 symbols**. This is the first symbol map this repository has had, and it changes what is
checkable rather than merely making it convenient:

  * `tools/callers.py` works: a scan finds 108,907 `bl` sites and 12,982 in-image targets. Its
    documented limit stands — direct branches only — and `C_MGR_SRC::StartUp` genuinely has **0
    direct callers** because it is virtual. The vtable holds exactly one pointer to it, at
    `0x0307aa74`.
  * **That limit matters more than it sounds.** This firmware mostly calls through a register:
    `lis`/`addi` builds the callee's address, then `mtctr`/`bctrl`. `callers.py` reports 0
    callers for nearly every `C_MGR_SRC` method for that reason, not only the virtual ones. A
    scan for `lis`/`addi` pairs that build the target address finds them — for example
    `ExecuteAllocationFirstRound`'s single caller, `ExecuteAllocation+0x4c`. Treat "0 callers"
    from `callers.py` as "no *direct* callers", never as "unreachable".
  * `ppcdis`, `xref`, `callers` and `symdiff` can now be run against real firmware. Issue
    **#38**, now closed, covered them in CI with synthetic images. For the indirect calls
    `callers.py` misses, use `tools/survey.py` ([Firmware map](FIRMWARE_MAP.md)).

A warning for whoever picks this up: the entry point `InitializeMetaNav` at `0x01000000` also has
0 direct callers, and that is correct — the boot loader jumps to it, nothing in the image branches
to it. Using it as a control for "is the tool working" produces a false negative, as it briefly
did while writing this.

**`traces.bin` is not a source-manager trace.** The dump's `traces.bin` (356 KB) is a VxWorks
exception log: a `FILE DATA` header, then ten `EXCEPTION DATA` records of `0x8e64` bytes each,
from firmware `SMEG5.2.A.R9`, dated 2017–2020. The file itself was last modified in 2020. It holds
task lists and stack dumps from old crashes and nothing from `C_MGR_SRC`. The source manager's
runtime lines are in the **user spy archive** instead: `SPY/<stamp>/TAR/<stamp>-USER.tar.gz`,
under `RAMDISK_SPY/`. That archive is present only in a dump taken after a user spy collect
(`log_error.txt`: *"collect of spy asked by user"*). The 2026-09-14 dump has one; the
2026-09-27 dump does not.

## How the boot source is actually chosen

Read from the NAV image, with the 2026-09-14 user spy archive as runtime evidence. That archive
comes from a boot with `Last_Source = 1`, **not** from a boot of the `aux-boot-default` build.
Each step carries its tier.

**`Init` runs before `StartUp`.** *Inferred from the code.* Both are `C_MGR_SRC` virtuals, at
vtable slots `0x0307aa6c` and `0x0307aa74`. `Init` creates the lock at `+0x80`, and `StartUp`
takes that lock before it restores anything. `Init` also writes `+0xb4 = 1` and
`+0xac = 1` unconditionally (`0x016995b0`–`0x016995b8`), so whatever `StartUp` restores lands on
top of that.

**`StartUp` restores two keys, not one.** *Read.* It reads `Last_Source` into `+0xb4`
(`0x01699490`, the site `aux-boot-default` patches) and `Last_Source_Priority` into `+0xac`
(`0x01699448`). The key names are the strings at `0x0300a578` and `0x0300a584`. It then starts a
7.5 s timer (`0x1d4c` ms). Its callback, `Mgr_src_SCHED_INIT_TIMEOUT`, leads to
`SchedulerInitTimeout` through a private message (`HandlePrivateMessage+0x1bc`).

**Until that timer fires, the first allocation pass does not look at `+0xb4`.** *Read.*
`ExecuteAllocationFirstRound` branches on a mode word at `0x035e4cd4`. `SetCurrentStatus`
(`0x01695424`) sets that word to 1 in the normal case: not locked, and `+0x7c` clear. In mode 1
the `+0xb4` match (`0x01695b84`) runs only when the byte at `this+0x3c0` is non-zero. That byte
is 0 from the constructor and `Init`. `SchedulerInitTimeout` sets it, and four sites in
`AddRequest` set or clear it.

**A saved source is restored only through the `ScheduledInit` path in `AddRequest`.** *Read* —
disassembly, confirmed against Ghidra's decompilation of `AddRequest`. A type-5 or type-6
request is first added to the list at `+0xd4` (jump table at `0x02f4b080`), which is the list the
first pass matches against. Then, **only if the request's byte at `+0x28` is clear**
(`0x0169846c`–`0x01698474`):

| the request's `(Sched_Pos, priority)` pair… | effect |
|---|---|
| is already in the `ScheduledInit` table at `+0x370` (`IsInitialized`) | cancels the init timer, sets the flag, `ForceSchedulerPosition(Sched_Pos)` — a source that asks again after boot is switched to straight away |
| is new | `SetScheduledInit` adds it to the table. If it also equals (`+0xb4`, `+0xac`) — i.e. (`Last_Source`, `Last_Source_Priority`) — the init timer is cancelled and the flag set. Then `ExecuteAllocation` runs, and the first pass matches `+0xb4`: **this is the restore** |

A request with `+0x28` set skips all of that and goes straight to `ExecuteAllocation`. It never
enters the table and can never be restored. Type-4 requests take a separate branch with the same
table-and-compare logic but are never added to a request list.

The request's type is the field at request `+0x14`: the spy line's `Type=`, confirmed from the
format string at `0x0300a63c` and `WriteMgrSrcSpy`'s loads.

**If nothing matches in time, the timer picks FM.** *Read.* `SchedulerInitTimeout` calls
`ChangeToNextSchedulerPosition(0, 0)`. If that function finds an eligible request in the list
at `+0xd4`, it moves the old `+0xb4` into `+0xe4`, stores a literal **1** into `+0xb4`
(`0x01697b44`–`0x01697b48`), and runs allocation. Position 1 is `POS_TUNER`. If it finds none,
the flag is cleared again and a 5 s retry timer is started.

The position it computes before storing 1 is discarded, and it would be the *highest* queued
position, not the next one, so patching the literal does not help. Releasing the current
source already tries the **previous** position first. Both are in
[The source scheduler](SCHEDULER.md#changetonextschedulerposition-in-full).

**AUX's request has `+0x28` set, so AUX never enters the table.** *Executed* — the spy's
request-list dump. The last column, `PrOnly`, is the byte at `+0x28`:

```
Nb|src|id|Status|Norm|NoSr|Lock|Type|sche|Post|Susp|PrOnly|
 1|0xa   |0xbc00   |WAITING|  10| 254| 254|   5|   1|   1|   1|   0|  false|
 2|0x3   |0x17400  |WAITING|  20| 254| 254|   5|   9|   0|   1|   1|  false|
 5|0x3   |0xe200   |ACKNOWL|  20| 255| 255|   5|   7|   0|   1|   1|  true|
```

The rows are the tuner (`0xbc00`, position 1), USB (`0x17400`, position 9) and AUX (`0xe200`,
position 7). AUX's priority (`Norm`) is **20**, and AUX is the only request with `PrOnly` true.
The table dump agrees: every source whose request has `PrOnly` false has a row, and AUX has none.

```
m_Mgr_src_ScheduledInit[0] ->  10 |   1 |POS_TUNER
m_Mgr_src_ScheduledInit[1] ->  20 |   9 |POS_USB
m_Mgr_src_ScheduledInit[2] ->  10 |  10 |POS_IPOD
m_Mgr_src_ScheduledInit[3] ->  10 |   8 |POS_BT
m_Mgr_src_ScheduledInit[4] ->  10 |   4 |POS_CDC
```

The columns are `PNormal | SchedPos`. No row has position 7.

**The boot sequence in that archive.** *Executed* — spy lines, in ms since boot:

```
6511::Last_Source   : 1 (0x1)
9727::AllocateSource  : MsgSrc = 10, SrcId= 0xbc00,Type=5, Sched_Pos= 1, ...
10062::AllocateSource  : MsgSrc = 3, SrcId= 0xe200,Type=5, Sched_Pos= 7, ...
10062::SendWAIT [MsgSrc + Source_ID]  : 3, 0xe200
10221::SendACK [MsgSrc + Source_ID]  : 10, 0xbc00
25789::ActivateSourceID::p_source_ID   : 57856 (0xe200)
```

The tuner was granted at 10221 ms, about 3.7 s after `Last_Source` was read. That is well
inside the 7.5 s window, so the timer did not choose FM on that boot. AUX's request (`SrcId
0xe200`, `Type=5`, `Sched_Pos=7`) was told to wait until AUX was selected by hand at 25789 ms.
The settings dump taken after that selection holds `Last_Source = 7` and
`Last_Source_Priority = 20`, exactly AUX's pair. So **even stock firmware cannot resume AUX**
after you switch off on AUX: the saved values are right, but AUX's request is excluded by
`PrOnly` before the comparison. *Inferred* from the path above and the executed values; not
observed as a separate boot.

**What this means for `aux-boot-default`.** *Inferred.* Writing 7 into `+0xb4` changes the value
compared against, but AUX's request never reaches the comparison. On the patched boot the tuner's
pair (1, 10) does not equal (7, saved priority), so the tuner is not restored either. Nothing sets
the flag, the 7.5 s timer fires, and `ChangeToNextSchedulerPosition` writes 1 → FM. That fits
the car test, but which route chose FM on the patched boot is **not known**: the only spy archive
is from an unpatched boot. A capture from a patched boot, left untouched on FM, would settle it.

**Where `PrOnly` comes from.** *Read* — Ghidra decompilation and disassembly. The HMI's
`C_HMI_SrcMgntBase` keeps its request at `this+0x10`, so the `PrOnly` byte is `this+0x38`.
`ActivateSource(bool)` writes its argument there for the one `AllocateSource` it sends, then puts
the old value back. `C_HMI_MEDIA_APP_BASE::HandleAudioAuxInputStatusChnged` calls
`ActivateSource(aux, true)` (`li r4,1` at `0x02303474`) when the AUX input setting becomes
non-zero (see [What the handler actually reacts to](#what-the-handler-actually-reacts-to)),
and `C_HMI_MEDIA_APP_BASE::InitApp` does the same for the boot-time request (`li r4,1` at
`0x022c0678`). It is the only one of `InitApp`'s six activations that passes `true`; the site is
identified by the label it opens with, `user_HMI.AUX.Equalizer_aux`.
The handler runs only when the AUX input setting changes between zero and non-zero, because it
compares against a cached copy at `this+0x51449`. When the setting goes to zero, it releases the
source. So `PrOnly` means "this source has become available; do not take the audio for it", which is exactly what the boot restore
and the re-request force honour. The video app passes `true` as well (`HandleMediaStateReady`,
`HandleVideoTrackFound`). Inside `C_MGR_SRC`, the byte is read only by `AddRequest`'s restore
gate and by `AllocateSource`'s spy line.

**The candidate fix: `patches/aux-boot-restore.json`.** Three instruction changes, NAV only:

| site | original | candidate | effect |
|---|---|---|---|
| `0x022c0678` in `InitApp` | `li r4,1` | `li r4,0` | AUX's **boot** request is sent with `PrOnly` clear, so it enters the table and meets the restore |
| `0x02303474` in `HandleAudioAuxInputStatusChnged` | `li r4,1` | `li r4,0` | the same for AUX's later requests, when the AUX input setting becomes non-zero (including its once-per-boot re-announcement); no other source changes |
| `0x01699444` in `StartUp` | `lwz r0,8(r1)` | `li r0,20` | the restored `Last_Source_Priority` is always AUX's 20 |

**Emulated** (`tools/ppcemu.py`, the NAV image, `AddRequest` run for real on a synthetic
`C_MGR_SRC` object whose `+0xb4`/`+0xac` hold (7, 20) and whose init timer exists, with only
`memcpy`, the node allocator, `wdCancel`, `ExecuteAllocation` and `ForceSchedulerPosition`
stubbed), fed AUX's request (type 5, position 7, priority 20):

| request | `ScheduledInit` | restore flag `+0x3c0` | init timer cancelled |
|---|---|---|---|
| `PrOnly` set (stock AUX) | empty | 0 | no |
| `PrOnly` clear (what the first edit sends) | `(7, 20)` | **1** | **yes** |
| `PrOnly` clear, but `+0xac` = 10 (second edit absent) | `(7, 20)` | 0 | no |
| `PrOnly` clear, second request with `(7, 20)` already in the table | — | — | `ForceSchedulerPosition` reached |

So `PrOnly` is the only gate between AUX and the restore, and the second edit is needed as
well. An earlier version of this patch removed the gate itself (`nop` at `0x01698474` in
`AddRequest`) and emulated identically. It was replaced because that would also have changed
the video sources, which pass `true`. What is **not** emulated: `StartUp` and the `InitApp` site
(both decoded only), and everything downstream of `ExecuteAllocation`. The handler edit
(`0x02303474`) was executed later, in the `aux-signal-switch` handler runs: with it applied, the
activation passes `PrOnly` 0 ([Emulation results](AUX_SIGNAL.md#emulation-results)).
Whether the unit boots to AUX is **not known** until it is flashed. What to expect beyond boot:

* **Not an auto-switch on signal.** Once AUX is in the table, a *second* AUX request is forced to
  the front: `IsInitialized` → `ForceSchedulerPosition`, emulated above. But the handler sends
  that request only when the AUX input **setting** goes from zero to non-zero, not when a signal
  appears (see [What the handler actually reacts to](#what-the-handler-actually-reacts-to)). An
  earlier version of this page expected a switch "when AUX appears"; that expectation is
  withdrawn. Turning the AUX input on in the menu would now select AUX (*inferred*).
* The first request-list dump from a patched boot should show whether the tuner still wins first.

Changing the literal 1 at `0x01697b44` is **not** a safe shortcut: `ChangeToNextSchedulerPosition`
is also what `C_SRV_AUDIO::bcm_ActivateNextSource` calls, so that edit would change normal source
cycling.

## What the second car test established

On 2026-09-28 `builds/aux-boot-restore.json` was flashed with the **handler-only** version of
`aux-boot-restore`, i.e. without the `InitApp` edit. The unit **always booted to FM**, with
audio on AUX. A `SPYTAKE` + `SPYSTORE` capture of that boot (the update history puts the flash at
01:05 and the collect at 01:07) gives, **executed**:

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

* ~~**`aux-boot-default` works:** `Last_Source` is 7.~~ **Withdrawn:** that trace line logs the
  *saved* value before `aux-boot-default` overrides it (see
  [the third car test](#what-the-third-car-test-established)), so it cannot show the patch
  working. That session had simply ended on AUX.
* **AUX's boot request still had `PrOnly` set,** and `ScheduledInit` still has no position-7 row
  (USB, iPod, BT, CDC and TUNER only). So the handler edit did not reach the boot request.
* **FM was chosen by the init timer:** 8847 ms + 7500 ms = 16347 ms, the exact time of the tuner's
  ACK. That confirms the timer route described above for a patched boot.
* **AUX's request arrived 1.3 s into the 7.5 s window.** Sent without `PrOnly`, it would have been
  in time to match.

The boot request comes from `InitApp`, not from the handler. The order of the requests (USB,
iPod, BT, CDC, AUX) is `InitApp`'s order, and `InitApp`'s AUX activation is the one call that
passes `true` (`0x022c0678`, *read*). The handler runs only on a later *change* of the AUX input setting. The
`InitApp` edit was added to `aux-boot-restore` as a result, and that version is **not yet
flashed**.

## What the third car test established

On 2026-09-28, later the same day, `builds/aux-boot-restore.json` was flashed with the
**three-edit** `aux-boot-restore` (the `InitApp` edit added) plus `aux-boot-default`. The unit
**booted to AUX three times** *(observed)*. The `SPYTAKE` + `SPYSTORE` capture of the last boot,
read with `tools/spy_read.py`, gives *(executed)*:

```
 6531 ms  saved Last_Source = 1
10228 ms  request  SrcId 0xe200   pos 7   type 5  PrOnly false   <- AUX
10228 ms  SendACK  SrcId 0xe200
ScheduledInit: POS_TUNER (1, 10), POS_USB (9, 20), POS_IPOD (10, 10), POS_BT (8, 10), POS_CDC (4, 10), POS_AUX (7, 20)
verdict: AUX was acknowledged first, at 10228 ms
```

* **AUX's boot request now carries `PrOnly` false** (it was true in the second test). The
  `InitApp` edit reached the request the restore sees.
* **AUX is in `ScheduledInit` as (7, 20)** and matched the restore target: it was acknowledged in
  the same millisecond it asked, with no tuner acknowledgement at the 7.5 s mark.
* **`aux-boot-default` is what made it match.** `StartUp` logs `Last_Source` with the *saved*
  value (`lwz r5,8(r1)` passed to `WriteMgrSrcSpy` at `0x01699488`) and only then overwrites it
  with 7 at `0x0169948c` *(read)*. The saved value here was **1** (FM), so without the override
  the restore target would have been the tuner.

Both patch sets are therefore **confirmed on hardware as a pair**: `aux-boot-default` alone
still boots to FM (first test), and the two-edit `aux-boot-restore` did too (second test). Why the
saved value was 1 after three AUX boots is *not known*: when `C_MGR_SRC` saves the source is
described in [the scheduler](SCHEDULER.md).

## Two display findings

!!! failure "Partly withdrawn (#191)"

    The first finding below overreached. By the code, `GUI_VER` *is* shown, on the GUI item's
    page of System Information; what was observed is that `32.01` was not seen on the page
    looked at. The `cd` value comes from the media partition's `Data_base/media.inf`, and the
    main software version from the application image. See
    [Version strings](VERSION_STRINGS.md#is-gui_ver-visible) for the details and the car check.

**The version shown on the unit is not `GUI_VER`.** `GUI_VER` was set to `32.01` for this build,
and it appears nowhere on the unit. The "Display version" screen reads `cd 26482`, which is
`Data_base/media.inf` verbatim — a file this build did not touch. The claim in `AGENTS.md` that
`GUI_VER` is "the only safe visible field" is therefore wrong or at least misleading; do not use
it as an "did it apply" beacon.

**A renamed ringtone keeps its old name.** The custom tone played (so the media partition
applied), but the list still said `Alien`. The build had changed `phone/Ringing_List` in the seed
`up_common.sqlite`. **Corrected (#190):** that key appears nowhere in the application image. The
names are string literals in the image, served by `C_SRV_RING_TOUCH::SetRingFilePath`
*(read)*, so no database edit could change them. The earlier inference that the unit read
its `/USER_DATA` copy was wrong. See [Ring tones](RINGTONES.md#names).

## Status of each claim

| claim | how it is known |
|---|---|
| the chain's addresses and dispatch | read from the image |
| gates 1–4 and their order | **executed** |
| gate 3 never fires; the registered types | **executed** |
| gate 4 blocks a nopped gate 3 | **executed** |
| every exit path logs | **executed** |
| `Log_msg` is gated by a BSS mask | **executed** |
| type 5 is AUX | inferred from call sites, strongly |
| `aux-sticky`'s second edit does what it says | **executed on all three builds** — after being corrected; it shipped unconditional |
| link A's state on a real unit | **not known** — needs the car |
| `HandleAudioAuxInputStatusChnged` reacts to the saved AUX input setting (`C_MODULE_AUDIO+0x8c`, `Auxiliary_Status`), not to signal presence | **read** — `Get_aux_status`, its two writers, and the `0xcb`/`0xcc` posts in disassembly; supersedes the earlier "signal" reading |
| stock firmware has no path that switches to AUX when a signal appears | **executed** for the media dispatch — the stock window sends `0xcc` to its default case; **inferred** for the whole image |
| `InitApp`'s AUX activation passes `PrOnly` true (`0x022c0678`) and is the boot request | **read**; the boot request's `PrOnly` true is **executed** on the 2026-09-28 car trace |
| `aux-signal-switch` routes `0xcc` to the handler and makes it follow the signal | **executed** under emulation (two functions); not flashed |
| the unit measures AUX while another source plays | **not known** — step 1 of the `aux-signal-switch` car test |
| every boot re-announces the AUX setting once (`ElabRADIO_READY_FOR_INIT_0` → `setAUXGain`) | **read** |
| `HandleMediaStateReady` can activate AUX with a computed `PrOnly` (`0x02306a18`), outside `aux-boot-restore` | **read**; whether it runs for AUX is **not known** — see [How HMI apps request sources](HMI_SOURCES.md) |
| `AddRequest` writes `SrcId` to `node+0x04` and `Sched_Pos` to `node+0x18`; the lists at `+0xd4` are requests, not a registry | **read from disassembly/decompiled code** — field names corroborated by the named `SetScheduledInit` call |
| the scheduler matches `node+0x18` (`Sched_Pos`) against `+0xb4` | read statically; **runtime tuner tuple corroborates it** |
| boot restore writes `+0xb4` with no validation | **read from decompiled code** — not executed |
| `POS_AUX = 7`, `POS_JBX = 5`, `POS_TUNER = 1` | read from the SPY switch; **`POS_TUNER=1` executed in the captured `AllocateSource` tuple** |
| `AllocateSource` is the client entry that feeds `AddRequest` | read statically; the function's own runtime lines were captured |
| `Last_Source` uses `Sched_Pos`, not raw `SrcId` | **executed** — tuner had `Last_Source=1`, `SrcId=0xbc00`, `Sched_Pos=1` |
| `7` is the value AUX needs | strongly supported: enum says `POS_AUX=7`; AUX tuple and live setting still not executed |
| `aux-boot-default` applies and is correctly located in `C_MGR_SRC::StartUp` | **executed** — `39200007` verified in the shipped image at `0x0169948c` |
| `aux-boot-default` changes the boot source | **falsified on hardware** — still FM, with audio playing into AUX |
| `ExecuteAllocationFirstRound` reads `+0xb4` at `0x01695b90` | **read from disassembly**, whole-image scan for readers of that field |
| ~~`StartUp` runs before the first allocation pass~~ | **withdrawn** — the question was mis-posed: allocation is reached only through request and scheduler paths, and `StartUp` never enters it |
| `Init` runs before `StartUp` | **inferred** — `StartUp` takes the lock `Init` creates |
| `StartUp` restores `Last_Source` → `+0xb4` and `Last_Source_Priority` → `+0xac`, then starts a 7.5 s init timer | **read from disassembly** |
| the first pass ignores `+0xb4` until the init timer fires or a matching request arrives (`+0x3c0`) | **read from disassembly** |
| restore needs the request's (`Sched_Pos`, priority) to equal (`Last_Source`, `Last_Source_Priority`) as it enters the `ScheduledInit` table; requests with `PrOnly` (`+0x28`) set skip this | **read** — disassembly and Ghidra decompilation of `AddRequest` |
| the timer path writes a literal 1 (`POS_TUNER`) into `+0xb4` | **read from disassembly** — `0x01697b44` |
| AUX's request has `PrOnly` set and has no `ScheduledInit` row; every `PrOnly`-false source has one | **executed** — spy request-list and table dumps, 2026-09-14 |
| on an unpatched boot the tuner won about 3.7 s after the restore, and AUX's request waited | **executed** — spy lines, 2026-09-14 |
| AUX's request priority is 20 | **executed** — `Norm` column of the spy request-list dump |
| stock firmware cannot resume AUX even with `Last_Source`=7 / priority 20 saved | **inferred** — from the path and the executed values; no dedicated boot observed |
| with `aux-boot-restore`, AUX's first request enters the table, sets the restore flag and cancels the init timer | **executed under emulation** — `AddRequest` on the NAV image |
| `PrOnly` is `ActivateSource`'s argument, and the AUX input handler passes `true` (`0x02303474`) | **read** — decompilation and disassembly |
| the handler-only version of `aux-boot-restore` boots to AUX | **falsified on hardware** — 2026-09-28, still FM |
| AUX's boot request comes from `InitApp`, with `PrOnly` true | **executed** (spy trace, 2026-09-28) and **read** (`li r4,1` at `0x022c0678`) |
| on the patched boot, FM was chosen by the 7.5 s init timer | **executed** — tuner ACK at 16347 ms, `Last_Source` read at 8847 ms |
| with the `InitApp` edit added, the unit boots to AUX | **not known** — not flashed |
| which route chose FM on the patched boot | **not known** — needs a spy archive from a patched boot |
| `traces.bin` holds source-manager output | **false** — it is a 2017–2020 exception log |
| the vtable for `C_MGR_SRC` holds exactly one pointer to `StartUp`, at `0x0307aa74` | **read from the image** |
| `callers.py` finds direct `bl` callers | **executed** — 108,907 sites, 12,982 targets; virtual methods return 0 by design |
| most `C_MGR_SRC` calls are `lis`/`addi` + `bctrl`, invisible to `callers.py` | **executed** — an address-materialisation scan finds the callers `callers.py` misses |
| the Display-version screen reads `media.inf`, so `GUI_VER` is not a visible beacon | **partly withdrawn** — `cd 26482` is `media.inf` verbatim (executed on hardware), but the code shows `GUI_VER` on the GUI item's page (read, #191); see [Version strings](VERSION_STRINGS.md#is-gui_ver-visible) |
| a renamed ringtone keeps its old name after a package update | **executed on hardware**; the settings-database reason is **inferred** |
