# Patch definitions

Base address for the inflated application image is `0x01000000`. Offsets below are
absolute addresses in that image; the tool converts to a file offset with
`offset = addr - 0x01000000`.

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

    **The `expect` bytes are not a sufficient guard**, which is worth knowing because they look
    like one. Two entries in this repository match at the same address on the `5.42.B.R4` NAV
    image — `diagnostic-logging` and `diagnostic-logsink`, both at `0x010346d0` — because a
    short instruction sequence recurs across versions. On that image the expect check passes and
    the edit lands 152 bytes off.

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

## Which build is this? `tools/fingerprint.py`

The version check above covers *which firmware*. The *build* — `AUDIO_BT`, `AUDIO_BT_256`,
`NAV` — used to be picked by hand, and that choice is easy to get wrong: **`AUDIO_BT` and
`AUDIO_BT_256` declare identical patch addresses and identical `expect` bytes**, so nothing in
the patch data separates them.

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

**It refuses rather than guesses, and that is the design.** On the firmware in this repository
the `AUDIO_BT` and `AUDIO_BT_256` variants are genuinely indistinguishable from the recorded
addresses, so a tool that picked one would be worse than the manual step it replaced — it would
make the same mistake, silently. Verified by hand against the `5.43.A.R2` NAV image, where it
identifies `NAV` and rejects every `AUDIO_BT` variant.

`patch_smeg.py` calls the same identification before patching. It stays quiet when an image
matches nothing, because the firmware-token check and the per-patch `expect` check already
report that precisely — a third message would pre-empt the more specific one. What it adds is
the wrong-*build* case, which otherwise surfaces as a confusing byte mismatch:

```
NAV: this image is not the NAV build - refusing to patch.
  It matches: AUDIO_BT. Addresses are per build, so patching it with these addresses
  would write to the wrong locations. Run tools/fingerprint.py for a verdict.
```

The probes are the recorded `expect` bytes themselves, so a build only fingerprints as well as
the patch data for it is accurate. A build with no patch set here cannot be identified at all —
that is issue [#16](https://github.com/KRoperUK/smeg-plus-patches/issues/16).

## 1. `C_HMI_AUDIO_APP_BASE::IsAUXSRCAvailable()` — force available

Replaces the function prologue with `li r3,1 ; blr`, so AUX is reported available
regardless of vehicle config / signal. Consequence: the AUX source stays selectable and
no longer greys out when there is no signal.

| build | address | original | patched |
|---|---|---|---|
| `AUDIO_BT`, `AUDIO_BT_256` | `0x02247718` | `94 21 ff a0` (`stwu r1,-0x60(r1)`) | `38 60 00 01 4e 80 00 20` (`li r3,1 ; blr`) |
| `NAV` | `0x02247858` | `94 21 ff a0` | `38 60 00 01 4e 80 00 20` |

```
li   r3, 1        # 0x38600001
blr               # 0x4e800020
```

## 2. `C_HMI_MEDIA_APP_BASE::HandleAudioAuxInputStatusChnged()` — remove early exit

At `handler + 0x10c` the function bails out when `GetMediaDevice(AUX)` fails, before it
reaches `ActivateSource()`. Replace the conditional branch with `nop` so execution
continues into the `SetMediaDeviceState` / `ActivateSource` path.

!!! failure "This edit is inert — keep it for reference, do not expect it to do anything"

    Emulating the function showed the branch is **never taken**: the AUX media device is
    registered unconditionally at start-up, so `GetMediaDevice(AUX)` returns success and
    the `beq` falls through with or without the patch. Forcing the failure case does not
    help either — `GetMediaDevice` writes nothing to its out-param when it fails, so the
    source-manager guard at `0x02303468` returns instead, one call later. The full
    reasoning, and the runs behind it, are in
    [Emulating the firmware](EMULATION.md).

| build | handler | branch address | original | patched |
|---|---|---|---|---|
| `AUDIO_BT`, `AUDIO_BT_256` | `0x023031dc` | `0x023032e8` | `41 9e 01 4c` (`beq cr7,+0x14c`) | `60 00 00 00` (`nop`) |
| `NAV` | `0x0230331c` | `0x02303428` | `41 9e 01 4c` | `60 00 00 00` (`nop`) |

The branch target (`handler + 0x258`) is the shared return path for the "nothing to do"
cases; the patched fall-through runs:

```
SetMediaDeviceState(AUX, state = 2)
if (this->srcMgr) C_HMI_SrcMgntBase::ActivateSource(true)
```

## Resulting file checksums

Because the compressed stream is rebuilt, the resulting `f_BigQuick.bin` CRCs depend on
the zlib implementation/level and are not stable values to match against. Recompute them
with the tooling and propagate through the cascade (the tool does this automatically).

## Adding your own patches

`patches/*.json` is data-driven:

```json
{
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

The earlier checks all run in memory, so a write that did not land — or landed twice — was
invisible to them. That is the gap this closes.

## Patch sets in this repository

| file | what it changes | status |
|---|---|---|
| `patches/aux-autoswitch.json` | `IsAUXSRCAvailable()` true **and** removes the `GetMediaDevice` bail-out | **Flashed**{ .pill .pill-ok } the combined build — accepted by the contract check; first edit confirmed on hardware |
| `patches/aux-always-available.json` | `IsAUXSRCAvailable()` true only — AUX stops greying out | **Confirmed**{ .pill .pill-ok } behavioural; no switching |
| `patches/aux-sticky.json` | removes the bail-out **and** turns "signal absent" into a no-op | **Never flashed**{ .pill .pill-wip } control flow verified under emulation |
| `patches/aux-boot-default.json` | forces `C_MGR_SRC::StartUp` to restore AUX (position 7) on every boot, ignoring the saved `Last_Source` | **Never flashed**{ .pill .pill-wip } restore effect verified under emulation |
| `patches/diagnostic-logmask.json` | forces the global trace mask — **necessary but not sufficient**, see below | **Not for driving**{ .pill .pill-no } diagnostic build |
| `patches/diagnostic-logging.json` | redirects the logging stub to the real logger | **Not for driving**{ .pill .pill-no } diagnostic build; needs the mask patch too |
| `patches/spy-dump-userdata.json` | makes `SPYSTORE` also copy `/USER_DATA/user_data` out to the stick | **Confirmed**{ .pill .pill-ok } on hardware (2026-09-14, NAV) |

!!! note "Hardware status"

    The combined build has been flashed to a real unit and accepted by the media contract
    check. The `IsAUXSRCAvailable()` change is confirmed working: AUX no longer greys out
    and is back in the SRC cycle. The **auto-switch has not been observed working yet** —
    see [Hardware verification](VERIFICATION.md).

### `diagnostic-logmask` — half of what a diagnostic build needs

`Log_msg` at `0x02742558` does not write anything until it has cleared a gate:

```c
mask = GetLogMask();                 // 0x02742530 — reads one global
if ((mask & level) == 0) return;     // 0x027425e4
```

That global lives at `0x036d42a8`, which is **past the end of the image** (`0x03604450`) —
it is BSS, so it is zero when the unit boots. Exactly one instruction in the whole image
writes it, and it is reachable only through ten thin `SetTrace` wrappers that are vtable
entries, so nothing in the ordinary start-up path is known to turn logging on.

Replacing `GetLogMask` with a constant makes every level pass:

| build | address | original | patched |
|---|---|---|---|
| `NAV` | `0x02742530` | `94 21 ff f0 93 e1 00 0c` (prologue) | `38 60 ff ff 4e 80 00 20` (`li r3,-1 ; blr`) |

Same idiom as the `IsAUXSRCAvailable()` patch — overwrite a prologue with a constant
return, no code cave, trivially reversible.

This lets the **~5900 call sites that call `Log_msg` directly** run to completion instead
of returning at the gate. One of them is the reason this patch exists:

```
0230331c  HandleAudioAuxInputStatusChnged()
  …
  02303574  li  r3, 1                 ; level
  0230357c  addi r4, r9, -0x2948      ; "HandleAudioAuxInputStatusChnged() -\n"
  02303590  bctrl Log_msg
```

The handler logs its own name at level 1 on its **shared return path**. Every one of its
four exit paths reaches that call, and so does the success path — checked by executing all
five. So the line appearing at all means the message arrived and the handler ran; its
absence means the event never got there. That is the standing question in
[Hardware verification](VERIFICATION.md) and [The AUX chain](AUX_CHAIN.md), answered while
changing no behaviour whatsoever. Verified in emulation: stock, the line is suppressed at
the mask test; patched, it is emitted. See [Emulating the firmware](EMULATION.md).

!!! failure "On its own this produces no output"

    Forcing the mask is necessary but not sufficient, and the reason matters for anyone
    building a diagnostic.

    `Log_msg` makes exactly **two** calls. The first is `GetLogMask`. The second, after it
    has cleared the gate and marshalled up to six varargs, is to `0x010346d0` — and
    `0x010346d0` is `li r3,0 ; blr`.

    That address is the one `diagnostic-logging` patches. It is **the sink `Log_msg`
    itself calls**, and the vendor shipped it stubbed out. Both halves of the firmware's
    logging — the ~6700 sites that call the sink directly and the ~5900 that go through
    `Log_msg` — end at the same no-op.

    So in this build the application's logging has **no output path at all**. Forcing the
    mask makes `Log_msg` format the message and hand it to a function that throws it away.

!!! danger "And do not flash both diagnostic patches together"

    `diagnostic-logging` repoints `0x010346d0` at `Log_msg`. With the mask also forced,
    `Log_msg` calls the sink, the sink re-enters `Log_msg`, which calls the sink again —
    self-referential, on every log call in the firmware. Emulated, one call re-enters
    `Log_msg` three times before unwinding; on the unit it burns stack and time on a path
    that runs constantly.

### `diagnostic-logsink` — the other half

The missing piece is a **sink**: `0x010346d0` pointed at something that really writes. The
signature is in its favour — the caller passes a format string in `r3` and up to six
arguments in `r4`–`r9`, which is exactly VxWorks `logMsg(fmt, a1…a6)`.

**`logMsg` is at `0x00484a94`.** `BSP/SMEG_PLUS_512/vxWorks.bin` is a raw PowerPC image
that begins with a function prologue at offset 0 and carries a **VxWorks symbol table**:
20-byte entries holding a pointer to the name and then the address. Read at a load base of
`0x00200000` the table is self-consistent, and the base is confirmed independently — the
application's own call into the kernel at `0x0058c248`, the one `IsAUXSRCAvailable()` makes
on its failure path, is named `tickGet` by that table at exactly that address.

| build | sink | original | patched |
|---|---|---|---|
| `NAV` | `0x010346d0` | `38 60 00 00` (`li r3,0`) | `4b 45 03 c4` (`b 0x00484a94`) |
| `AUDIO_BT`, `AUDIO_BT_256` | `0x01034578` | `38 60 00 00` | `4b 45 05 1c` (`b 0x00484a94`) |

The displacement is about −11.7 MB, inside the 24-bit branch range, so no code cave is
needed. The `blr` after the patched instruction becomes unreachable, which is harmless:
`logMsg` returns to `Log_msg`'s caller itself.

**Flash it with `diagnostic-logmask`, never with `diagnostic-logging`.** The mask patch is
what lets `Log_msg` reach the sink at all, so neither half is any use alone;
`diagnostic-logging` repoints the same sink and the two edits fight.
`builds/diagnostic-logging.json` pairs the right two.

!!! warning "Verified in emulation, not on a car"

    Emulated, the patched sink jumps to `0x00484a94` — which the emulator reports as an
    unmapped fetch, because that address is in the kernel rather than the application
    image. That confirms the branch target and nothing more. **Where `logMsg` output
    physically surfaces on this unit — serial, telnet, a file, or nowhere reachable — is
    still unknown**, and is the open part. See issue #94.

### `diagnostic-logging` — the other half, and not the useful half alone

The application has a **second** logging mechanism: ~6700 call sites that are compiled out,
calling `dummyLogMsg` instead of `Log_msg`. `dummyLogMsg` at `0x010346d0` is literally:

```
010346d0  li  r3, 0
010346d4  blr
```

So replacing that one instruction with a branch to the real logger:

| build | address | original | patched |
|---|---|---|---|
| `NAV` | `0x010346d0` | `38 60 00 00` (`li r3,0`) | `49 70 de 88` (`b 0x02742558`) |

makes those stubbed call sites live. `Log_msg` (`0x02742558`) wants `r3` = level and `r4` =
format, and the caller has already set both before calling the stub, so the branch passes
them straight through. The two functions are 24 174 216 bytes apart, inside the 24-bit branch
range, so no code cave is needed.

!!! failure "On its own this emits nothing — and with the mask patch it is worse"

    The redirected sites land in `Log_msg`, which tests the trace mask described above and
    returns. Nothing comes out.

    Flashing it *with* `diagnostic-logmask` does not fix that, it creates a loop:
    `0x010346d0` is the sink `Log_msg` calls, so repointing it at `Log_msg` makes the two
    call each other. Neither patch, alone or together, gives the firmware an output path —
    see the correction above.

**Use it to find out whether something is reaching the app** — for example whether DBUS
message `0xcb` (203), the AUX status trigger, arrives at the media app at all. Turn it on, and
expect a lot of output: **do not drive on this build**, and reflash a normal one afterwards.

Open question: `Log_msg` is the debug channel, so where its output actually lands — serial,
the spy ring buffer, or a file — decides whether this is readable without hardware attached.
Settle that before flashing it.


### `aux-always-available`

`li r3,1 ; blr` at the top of `C_HMI_AUDIO_APP_BASE::IsAUXSRCAvailable()`. AUX stays
selectable with no signal, so it is always in the SRC cycle. It does **not** cause the
unit to switch by itself.

### `aux-sticky`

Two edits in `HandleAudioAuxInputStatusChnged()`:

| offset | original | patched | effect |
|---|---|---|---|
| `+0x10c` (AUDIO_BT `0x023032e8`, NAV `0x02303428`) | `beq` | `nop` | drop the `GetMediaDevice` early exit — **inert**, see [Emulating the firmware](EMULATION.md) |
| `+0x118` (AUDIO_BT `0x023032f4`, NAV `0x02303434`) | `beq cr7,+0x58` | `beq cr7,+0x140` | when the AUX signal is absent, branch to the return path instead of the release branch |

The second edit means that once AUX has been activated it **stays** selected until the
user changes source — for intermittent CarPlay audio that otherwise flaps between AUX
and radio. It is a deliberate trade: AUX will no longer hand back to radio on its own.

Both offsets were verified against all three images (`AUDIO_BT`, `AUDIO_BT_256`, `NAV`).

!!! bug "This patch was wrong until it was executed"

    It shipped as `b +0x140` — **unconditional**. The displacement was right and the
    condition was gone, so the branch was taken whatever the signal was doing, the activate
    path below it became unreachable, and the handler could never select AUX at all. Worse
    than stock, in a patch whose whole purpose is to select AUX.

    Emulated on **all three images**, with the call targets decoded from each build's own
    `lis`/`addi` pairs rather than hard-coded, so the same run covers `NAV`,
    `AUDIO_BT` and `AUDIO_BT_256`:

    | bytes at the branch | signal appears | signal vanishes |
    |---|---|---|
    | `419e0058` stock | activates | releases |
    | `48000140` as shipped | **nothing** | nothing |
    | `419e0140` fixed | activates | does not release |

    Identical on every build. The handler lives at `0x0230331c` on `NAV` and `0x023031dc`
    on both `AUDIO_BT` variants, and the offsets within it (`+0x10c`, `+0x118`, `+0x258`)
    are the same in all three.

    `tests/test_patch_definitions.py` now refuses any edit that turns a conditional branch
    into an unconditional one unless `why` says so in as many words.


### `aux-boot-default` — resume AUX on every boot

`Last_Source` is the source the unit restores at start-up — but it is **not** a fixed
preference. `C_MGR_SRC::ImmediateSourceSave` (`0x01695d68`) writes the active source back to
it whenever the source changes, so seeding it in the settings database only lasts until the
next time you select something else. To make boot-to-AUX *stick*, patch the restore rather
than the saved value.

Inside `C_MGR_SRC::StartUp` the restore reads `Last_Source` and stores it, unvalidated, into
the field the scheduler later matches on:

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

Emulated on the NAV image (`tools/ppcemu.py`), with the saved value set to `1` (radio):

| build | `this+0xb4` | global `0x035e4cd0` | `this+0xe4` |
|---|---|---|---|
| stock | 1 | 1 | 1 |
| patched | 7 | 7 | 7 |

So the restore now targets AUX no matter what `ImmediateSourceSave` persisted. Pair it with
`aux-always-available` so AUX is a valid source — `builds/aux-boot.json` does both.

!!! warning "Sets the target, does not force the switch"

    `+0xb4 = 7` is the value `ExecuteAllocationFirstRound` (`0x016957ec`) matches against each
    request node's `Sched_Pos`. It only *selects* AUX if an AUX request node (`Sched_Pos 7`)
    is registered at start-up — the same downstream condition tracked in
    [The AUX chain](AUX_CHAIN.md). If nothing is scheduled there, the restore finds no match
    and falls back to the default. That is the thing to confirm before a car trip.

    NAV only — the `StartUp` address differs on the `AUDIO_BT` builds and must be re-derived.

### `spy-dump-userdata` — SPYSTORE also backs up `/USER_DATA`

`C_BCM_SPY::CallBackCopy` (NAV `0x01273734`) is the routine `SPYSTORE` runs to copy the spy
directory out to a stick. It is a sequence of `Get<X>Dir` source getters each followed by
`C_FS_STORAGE_CTRL_IO::Xcopy(source, dest)` into a timestamped folder on the stick
(`<stick>/SPY/<timestamp>`); see [Cheatcodes](CHEATCODES.md). None of those sources is the
live settings partition, so a stock collect never captures the user's databases.

The firmware already exports the primitive that fixes this:
`C_FS_STORAGE_CTRL_PATH::GetUserDataDir` (`0x0105ae44`) points an entity at
`/USER_DATA/user_data/` — the tree holding `sqlite/up_common.sqlite`,
`sqlite/connectivity.sqlite`, `sqlite/nav_dest.sqlite`, `Audio/Tuner.dat` and the rest. So
the added copy is one more block of exactly the existing shape:

```
GetUserDataDir(r29)     ; r29 = /USER_DATA/user_data/  (source)
Xcopy(r29, r31)         ; r31 = <stick>/SPY/<timestamp> (dest)
```

`CallBackCopy` has no spare space, and there is **no usable code cave inside `.text`** (the
functions are packed; the only large zero-runs sit past the last function at `0x02def4c0`,
in data, which is unsafe to execute). So rather than a trampoline this patch is **cave-free**:
it overwrites the last of the two calibration-copy blocks — the `*regen*` one — in place. That
48-byte block is more than the nine instructions the replacement needs.

!!! note "Why a trampoline is still out of reach, and what would change that"

    The cave search was redone from scratch and the conclusion holds: **every** run of 32
    bytes or more of nops/zeros in the image lies in `.rodata` — `CMMStrBufEncodedUTF8`'s
    table, `sqlite3_version`, `utf8proc_sequences` and friends — so it is live data, not
    padding. Text ends at `0x02def4c0`.

    A trampoline would therefore have to live **past the end of the image**, and that is
    mechanically expressible rather than impossible: the container header carries the
    **inflated size at offset `0x04`** (`0x02604450` on this NAV image, verified) and **no**
    compressed size, because the zlib stream is self-delimiting. The image can be grown and
    that field updated.

    What is **unverified** is whether the loader maps the appended region **executable**.
    Until a hardware test settles that, a trampoline is theoretical — do not rely on one.

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

!!! success "Confirmed on hardware — 2026-09-14 (NAV, 5.43.A.R2)"

    Flashed to a real unit; running `SPYSTORE` with a stick inserted produced a dump
    (`SPY/02_.../`) containing the full `/USER_DATA/user_data/` tree — `sqlite/` (14 databases
    with their `.inf` CRC sidecars), `Audio/` (`Tuner.dat`/`Radio.dat` presets), and
    `Nav/`, `TTS/`, `T2BF/`. The files are the genuine live copies: `nav_dest.sqlite` is a
    valid SQLite file, and `up_common.sqlite`/`up_user.sqlite` are stored **gzip'd**
    (`1f8b …`), which is how the unit keeps them on disk — the boot log's `gzUnixRead`. So
    `SPYSTORE` is now a working way to pull a settings backup off the unit.

    - **`connectivity.sqlite` is not captured.** Despite being named in the source path, it
      is not a file under `/USER_DATA/user_data/sqlite/` — the boot log shows it is imported
      from the system partition (`connectivity imported from system`), so **paired phones are
      out of scope** of this backup. Navigation destinations (`nav_dest.sqlite`), radio
      presets (`Audio/*.dat`) and general settings (`up_common`) *are* captured.

!!! note "Trade-offs"

    - **The dump loses the `*regen*` calibration files** in exchange for the `/USER_DATA`
      backup. That is the cost of staying cave-free.
    - **NAV only.** `AUDIO_BT`/`AUDIO_BT_256` have a different `CallBackCopy` address; derive
      it from each build's own image before adding those variants.
    - This reads `/USER_DATA` but does not write it, so it cannot damage the user partition —
      unlike a `USER_DATA` *payload* build.

### `spy-dump-userdata-partition` — the whole partition, not just the settings tree

`spy-dump-userdata` captures `/USER_DATA/user_data`. Its **siblings** are not captured, and
they are separate directories on the same storage device:

```
/user_data          <- what spy-dump-userdata gets: settings, nav destinations, presets
/address_book       /internet_user   /welcome_screen
/picture_cache      /catalog         /TurboBoot
```

That is measured, not inferred. The path-fragment table at `0x02f08418` shows each
`C_FS_STORAGE_CTRL_PATH::Get*Dir` is only `SetDevice(<device>) + SetPartition(n) +
AddName("<fragment>")` — so device + partition with **no** name is that device's root.
`GetUserDataDir` is `USER_DATA`, partition 4, `/user_data`; `GetAddressBookDir` is the *same*
device and partition with `/address_book`.

So this patch rebuilds the source entity as the root — fresh constructor,
`C_FS_STORAGE_DEVICE_USER_DATA::Instance()`, `SetDevice`, `SetPartition(4)`, deliberately no
`AddName` — and copies that, so one `Xcopy` takes every sibling.

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

**It supersedes `spy-dump-userdata`.** Both write `0x01273a1c`, so applying both fails the
`expect` check — pick one.

!!! warning "Not flashed"

    Static verification only. Its call sequence was executed under `tools/ppcemu.py`, with
    every callee stubbed so the sequence itself is the evidence:

    | | call sequence through the copy blocks |
    |---|---|
    | stock | `… GetApplicationDir, Xcopy, GetCalibrationDataDir, Xcopy, GetCalibrationDataDir, Xcopy` |
    | patched | `… GetApplicationDir, Xcopy, USER_DATA::Instance, SetDevice, SetPartition, Xcopy` |

    Both calibration blocks are gone and replaced by exactly the intended four calls. That
    proves the control flow and the targets; it does not prove what `Xcopy` does with a
    device root on real hardware.

!!! note "Trade-offs"

    - It consumes **two** blocks, so the dump loses the calibration `*.log` files as well as
      `*regen*`.
    - **NAV only**, for the same reason as `spy-dump-userdata`: the address is per build.
    - `CallBackCopy` only runs when `SPYSTORE` is invoked, so a fault here costs a dump, not
      a boot.
    - It reads `/USER_DATA` and does not write it, so it cannot damage the user partition.
