# Running the firmware without a car

Patch addresses in this project are found by reading disassembly. `tools/ppcemu.py` checks
what a patch *does* by executing the shipped image. It does not boot the unit — there is no
VxWorks, no display, no DBUS. It calls **one function at a time** on an emulated PowerPC core,
with a stack, a scratch region and stubs for whatever that function calls. That answers the
question a patch raises: *does control reach the code I think it reaches, and under what
conditions?*

## Why this is possible at all

The SoC is a **Freescale MPC5121e** — an e300 core, which is plain 32-bit big-endian PowerPC.
Unicorn's PowerPC backend runs it directly. There is no custom silicon to model because nothing
that touches the peripherals is executed: a function that would talk to hardware is stubbed at
its call site.

The application image is not encrypted (see [Patch definitions](PATCHES.md#the-application-image)), so
`tools/unpack.py` produces exactly the bytes the CPU would fetch, based at `0x01000000`.

```sh
uv run tools/unpack.py SMEG_PLUS_UPG/NAV/AppBin/f_BigQuick.bin app_nav.bin
uv run tools/ppcemu.py app_nav.bin --call 0x02247858 --arg 0x60000000 \
    --patches patches/aux-autoswitch.json --module NAV --trace
```

A whole comparison — six runs of a 39 MB image, stock against patched — takes well under a
second, so this belongs in the edit loop, not in a special session.

## What it can and cannot tell you

**Reachability is proof.** If the emulator shows a branch is taken, that branch is taken for
those register and memory values; the CPU has no opinion about where the values came from.

**Behaviour is not.** A stub returning `0` is an assumption written down, not something observed
on a car. The emulator makes assumptions *explicit and executable*, but it cannot tell you
whether the unit's real state matches them. Where a finding below depends on a stub, it says so.
Reaching past a gate is also not the same as producing its output: execution reaching the log
call does not mean anything was logged (finding 5).

Unmapped memory is recorded rather than fatal: the emulator maps a zero page and notes the
access, so the list of "state this function expected to exist" falls out of a run.

## What it found

### 1. The `IsAUXSRCAvailable()` patch does what it claims

Stock, with a zeroed object, the function finds a null pointer at `this+0x50dfc` and takes the
failure path into the kernel. Patched, it returns `1` in two instructions. This matches the
hardware result (see [Hardware verification](VERIFICATION.md)).

### 2. The `+0x10c` early-exit edit in `aux-autoswitch` is inert

Two independent reasons, either of which is sufficient.

**It patches a branch that is never taken.** The early exit fires when
`GetMediaDevice(mgr, AUX, &obj)` returns non-zero, and that call fails only when the AUX media
device is not registered. Registration was executed, not read:

```
C_HMI_MEDIA_APP_BASE init  @ 0x022bf934
  -> register devices      @ 0x022b833c        (unconditional; every early-out
                                                 branch in init rejoins before it)
       AddDevice(type 0) …(type 1)…(type 2)…(type 3)…(type 5)
       if (this->0x51450)  AddDevice(type 4)   <- the only conditional
```

Running that function fills the table with **types {0, 1, 2, 3, 5}** — AUX (type 5) among them,
unconditionally, with its source manager taken from `this+0x50e3c`, which is allocated and
stored unconditionally at `0x022bcac8`. So `GetMediaDevice(AUX)` succeeds, the status is `0`,
and the `beq` at `+0x10c` falls through with or without the patch.

**And if it were taken, the patch still would not help.** `GetMediaDevice` writes nothing to its
out-param on the failure path:

```c
int GetMediaDevice(mgr, type, out) {       // 0x022f3750
    status = -1;
    dev = FindDevice(mgr, type);           // 0x022f3608 — linear scan, count at mgr+0xc0
    if (dev == NULL) return status;        // -1, and *out is left exactly as it was
    out[0x00] = dev[0x00]; … out[0x10] = dev[0x10]; …
    return 0;
}
```

`out` is the local object the handler just zero-initialised, and `out[0x10]` is the source
manager the handler needs. Nopping the early exit lets execution continue with that field still
null — straight into the guard at `0x02303468`, which returns. The patch buys exactly one extra
call, `SetMediaDeviceState(AUX, 2)`, and then exits at the same place:

| AUX media device | stock | patched |
|---|---|---|
| absent | returns at `+0x10c` | returns at `+0x14c`, having called `SetMediaDeviceState` |
| present | reaches `ActivateSource` | reaches `ActivateSource` — identical |

There is no configuration in which the patch reaches `ActivateSource` and stock does not.

!!! danger "Do not nop the source-manager guard as well"

    Also removing the `beq` at `0x02303468` calls `ActivateSource` with a **null `this`**:
    `0x0230346c` loads that field straight into `r3`, on the HMI thread. Leave it alone.

### 3. The handler's gates, in order

```c
void HandleAudioAuxInputStatusChnged(this) {       // 0x0230331c
    app = this->0x50df4;                           // 0x022ad2c0, a plain getter
    if (app == NULL) return;                       // gate 1  @ 0x02303358
    ctor(&obj);                                    // zeroes obj, obj[0x10] included
    GetAuxStatus(app, &setting);                   // 0x025cb258 — the saved AUX input
                                                   // setting; return value IGNORED
    state = (setting != 0);
    if (state == this->0x51449) return;            // gate 2  @ 0x023033d4  (change detector)
    this->0x51449 = state;
    if (GetMediaDevice(mgr, AUX, &obj)) return;    // gate 3  @ 0x02303428  (never taken)
    SetMediaDeviceState(mgr, AUX, 2);
    if (obj[0x10] == NULL) return;                 // gate 4  @ 0x02303468  (never taken
    ActivateSource(obj[0x10], true);               //          once gate 3 passes)
}
```

The value gate 2 tests is the saved AUX input **setting** (`C_MODULE_AUDIO+0x8c`,
`Auxiliary_Status`), not a signal *(read; see [The audio module](AUDIO_MODULE.md))*. Two things
matter beyond the patch:

**Gate 2 means the handler only acts on a transition.** A setting that is already non-zero when
the state is first recorded produces no activation, because nothing changed.

**`GetAuxStatus`'s return value is discarded.** It returns `-1` without touching the out-param if
its proxy (`obj->0xc`) is null — and the handler reads the untouched local as "setting 0". A
failed query is indistinguishable from AUX being switched off, and lands in gate 2 as "no
change".

### 4. `aux-sticky`'s branch must stay conditional

`aux-sticky`'s second edit retargets the "AUX setting zero" branch at `0x02303434` to the shared
return path, so an activated AUX is not released when the setting drops. The condition has to
be kept: an unconditional `b +0x140`, with the same correct displacement, is taken whatever the
setting, and the activate path immediately below it becomes unreachable.

| bytes at `0x02303434` | setting becomes non-zero | setting becomes zero |
|---|---|---|
| `419e0058` (stock, `beq +0x58`) | activates | releases |
| `48000140` (`b +0x140`) | **does nothing** | does nothing |
| `419e0140` (`aux-sticky`, `beq +0x140`) | activates | does not release |

Reading the bytes does not show the difference — the displacement is correct and `+0x140` really
is the return path. Running it does. `tests/test_patch_definitions.py` refuses any edit that turns
a conditional branch into an unconditional one unless its `why` says so.

### 5. The logging is gated by one global, and its sink is a no-op

`Log_msg` begins `if ((GetLogMask() & level) == 0) return;`. `GetLogMask` reads a single global
at `0x036d42a8` — past the end of the image, so BSS, so **zero at boot** — and exactly one
instruction anywhere in the image writes it, through ten `SetTrace` wrappers that are vtable
entries only.

Emulating `Log_msg` directly: with the mask at 0, it bails after 47 instructions and never
reaches the formatting code; with the mask forced, it runs 271 and calls its sink.

**The sink is stubbed.** `Log_msg` makes exactly two calls — `GetLogMask`, and then
`0x010346d0`, which is `li r3,0 ; blr`. That is the same address `diagnostic-logging` redirects:
`0x010346d0` is **the sink `Log_msg` itself calls**. Both halves of the firmware's logging end at
the same no-op, so forcing the mask only buys the formatting before the message is discarded.
The handler's own log line (finding 3's shared return path) is therefore reached, but not
emitted.

Consequences for the diagnostic patch sets (see [Patch definitions](PATCHES.md)):

- `diagnostic-logging`, which redirects the ~6700 compiled-out call sites to `Log_msg`, **emits
  nothing on its own**: every redirected site lands in `Log_msg` and hits the gate.
- With the mask also forced it is worse: `diagnostic-logging` repoints the sink at `Log_msg`, so
  the two call each other. One call re-enters `Log_msg` three times before unwinding in
  emulation; on the unit that would run on every log call in the firmware.
- `diagnostic-logsink` points `0x010346d0` at VxWorks `logMsg` (`0x00484a94`). Emulated, the
  patched sink jumps to that address and the emulator reports an unmapped fetch — expected,
  since the kernel is not part of the application image — which confirms the branch target.
  Where that output surfaces on the unit is *not known* (issue #94).

### 6. One device type is unreachable firmware-wide

Device **type 4** is registered only when the byte at `this+0x51450` is non-zero. That byte is
written in exactly **two places in the entire 39 MB image** — both constructors, both storing
`0`. Nothing anywhere sets it. Whatever type 4 is (the surrounding evidence points at Jukebox),
the firmware as shipped can never register it. So a device type being absent from the table is
not evidence about AUX: at least one type is absent by construction.

### 7. The boot restore: `AddRequest` with and without `PrOnly`

`C_MGR_SRC::AddRequest` (`0x0169815c`) was run on the NAV image with AUX's request (`SrcId
0xe200`, type 5, `Sched_Pos` 7, priority 20) and `Last_Source`/`Last_Source_Priority` set to
(7, 20). Stubs: `memcpy` (`0x002cb648`) performs a real copy; the list-insert helper
(`0x01695590`) returns a scratch node; the watchdog cancel, `ExecuteAllocation` and
`ForceSchedulerPosition` return 0. *(executed)*

| request | `ScheduledInit` table | restore flag (`+0x3c0`) | init timer |
|---|---|---|---|
| `PrOnly` set (stock AUX) | empty | 0 | left running → FM after 7.5 s |
| `PrOnly` clear | (7, 20) | 1 | cancelled |
| `PrOnly` clear, saved priority (`+0xac`) 10 instead of 20 | (7, 20) | 0 — no match against (7, 10) | not cancelled |
| a second AUX request, table already (7, 20) | — | — | reaches `ForceSchedulerPosition` |

This is why `aux-boot-restore` clears `PrOnly` and forces the restored priority to 20, and it is
what the car showed on 2026-09-28 (see [Hardware verification](VERIFICATION.md)).

### 8. `aux-signal-switch`: the handler, and a window of the dispatch

The handler was run with every callee stubbed — both status queries write the value under
test, `GetMediaDevice` returns 0 with a fake source — and the cached state at `this+0x51449`
set by hand. With the patch it queries the signal, activates AUX when the signal appears,
releases it when the signal is lost, and ignores a setting-only change. With `aux-boot-restore`
also applied the activation passes `PrOnly` 0; with `aux-sticky`, the release is suppressed.
*(executed)*

The dispatch change sits in the middle of `C_HMI_MEDIA_APP_BASE::HandleDBUSMessage`, so the
whole function was not run. Instead, a **window** was: execution starts at the message-id load
(`0x0230961c`) with `r31` pointing at a scratch frame, and a code hook stops at the first address
outside `[0x0230961c, 0x02309650)`. That exit address is the case the message goes to. Stock
sends `0xcc` to the default case; patched, to the AUX handler; every other id tested goes where
stock sends it. `tests/test_aux_signal_switch.py` replays this window on a synthetic image, so CI
checks it. Full tables: [The AUX signal path](AUX_SIGNAL.md).

## Reproducing this

The tests in `tests/test_ppcemu.py` cover the emulator itself against assembled-in-test images,
so they run without any firmware.

### Firmware-in-the-loop tests (your own image, never CI)

`tests/test_firmware_nav.py` runs the behavioural claims against **your own** stock NAV
5.43.A.R2 image. Point `SMEG_NAV_IMAGE` at `f_BigQuick.bin` (or an inflated image):

```sh
SMEG_NAV_IMAGE=~/Downloads/SMEG_PLUS_UPG/NAV/AppBin/f_BigQuick.bin \
    .venv/bin/python -m pytest -m firmware -q
```

Without the variable the tests are skipped, which is what happens in CI. They check:

- every `expect` in every `patches/*.json` NAV set derived from 5.43.A.R2, against the real image;
- `C_MGR_SRC::AddRequest`: PrOnly keeps AUX out of the boot restore, PrOnly 0 matches (7, 20),
  sets the flag and cancels the timer, and a second request is forced;
- the AUX handler: stock follows the setting, `aux-signal-switch` follows the signal,
  `aux-boot-restore` makes the activation's PrOnly 0, and `aux-sticky` suppresses the release;
- the media dispatch window: stock drops `0xcc`, and `aux-signal-switch` routes only `0xcc`
  differently;
- `C_MGR_SRC::ChangeToNextSchedulerPosition` (see [The source scheduler](SCHEDULER.md)).

Each test's docstring says what it stubs. A broken patch fails them: changing the `0xcc` compare
in `aux-signal-switch` fails 8.

### By hand

The findings above can also be reproduced one command at a time:

```sh
uv run tools/unpack.py SMEG_PLUS_UPG/NAV/AppBin/f_BigQuick.bin app_nav.bin

# 1. the IsAUXSRCAvailable patch, stock vs patched
uv run tools/ppcemu.py app_nav.bin --call 0x02247858 --arg 0x60000000
uv run tools/ppcemu.py app_nav.bin --call 0x02247858 --arg 0x60000000 \
    --patches patches/aux-autoswitch.json --module NAV

# 2. the device table — types registered, with the type-4 flag clear
uv run tools/ppcemu.py app_nav.bin --call 0x022b833c --arg 0x60000000
```

The handler comparison needs two stubs, so it is a short script rather than a command:

```python
import struct, sys

sys.path.insert(0, "tools")
from ppcemu import Emulator, SCRATCH
from unicorn.ppc_const import UC_PPC_REG_4

IMG = open("app_nav.bin", "rb").read()
DEV = SCRATCH + 0x9000
REAL = {0x022F3750, 0x02368080, 0x022F3608}  # GetMediaDevice, ctor, FindDevice


def run(patched, device_found):
    e = Emulator(IMG)
    if patched:
        e.apply_patch_file("patches/aux-autoswitch.json", "NAV")
    e.stub_all, e.stub_default, e.run_for_real = True, 0x60002000, REAL
    e.stub(
        0x025CB258,
        lambda uc: uc.mem_write(  # the AUX setting query returns non-zero
            uc.reg_read(UC_PPC_REG_4), struct.pack(">I", 1)
        ),
    )
    e.stub(0x022F3608, DEV if device_found else 0)  # FindDevice
    e.write(DEV, b"\x00" * 0x20)
    e.write_u32(DEV + 0x10, 0xC0FFEE00)  # the device's source manager
    e.call(0x0230331C, [SCRATCH])
    return e.reached(0x0273A248), e.call_sequence()  # ActivateSource?


for patched in (False, True):
    for found in (False, True):
        print(patched, found, run(patched, found)[0])
```
