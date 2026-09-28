# Firmware map

Where the application image's code goes, and how much of it has been looked at. The
[Architecture](ARCHITECTURE.md) page describes how the pieces talk. This page accounts for
the whole image, one function at a time, and tracks which parts have been read closely.

All figures on this page come from `tools/survey.py`, run on the owner's own stock **NAV
`SMEG5.43.A.R2`** image and the symbol map `SPYSTORE` copies off the unit. Figures for the
AUDIO_BT build will differ.

## Scale

| | NAV 5.43.A.R2 |
|---|---|
| code symbols (`T`/`W` in `abs_symbols_base`) inside the image | **89 351** |
| instructions spanned by those symbols | **≈ 7.99 million** (31.9 MB) |
| families (class prefix, or library for free functions) | 1 030 |
| functions with at least one `bl` caller, materialised reference or data pointer found | 79 462 |
| functions with none found | 9 889 (≈ 625 000 instructions) |

Reading every instruction by hand is not feasible, so the working unit is the **function**.
Every function gets a row in the survey. Each subsystem that matters to a patch then gets a
close reading, recorded in the [coverage ledger](#coverage-ledger) below.

!!! warning "What the instruction counts over-state"

    A symbol map carries no sizes. A function's extent runs to the next symbol, so any
    unlabelled constant data after a function is counted as its code. That is why a few
    single functions show hundreds of kilobytes (`fnmatch`, `mxmlSetElement`). Treat
    per-function sizes as upper bounds, and family totals as close but inflated.

## Where the code goes

About **35%** of the instructions belong to families whose names identify a third-party
library. That labelling is *inferred from names* (`sqlite3_*`, `png_*`, `FT_*`, `Q*`); no
library version has been checked against its upstream source.

| layer | functions | instructions | share | what it is |
|---|---:|---:|---:|---|
| Qt | 20 736 | 1 437 421 | 18.0% | Qt middleware (widgets, QWS, graphics) |
| `C_HMI_*` | 9 957 | 1 292 224 | 16.2% | HMI applications: one family per app (tuner, BT, media, nav, drive, config, upgrade, climate…) |
| free functions (unlabelled) | 8 159 | 1 064 426 | 13.3% | C code with no class; includes vendor C modules and unrecognised libraries |
| `C_BCM_*` | 12 202 | 894 919 | 11.2% | Business components, the logic behind each HMI app, and their DBUS server/client pairs |
| C++ standard library | 9 638 | 579 088 | 7.3% | template instantiations |
| `C_GUI_*` | 2 979 | 362 951 | 4.5% | the vendor widget toolkit over Qt (lists, coverflow, bezier, …) |
| `V3D` | 2 684 | 285 849 | 3.6% | the 3D map renderer |
| `C_I2C_SMART_RADIO` | 299 | 139 247 | 1.7% | the radio/audio front-end over I2C |
| TagLib | 1 994 | 137 794 | 1.7% | media tag parsing |
| SQLite | 184 | 127 099 | 1.6% | the database engine |
| `com_MM_*` | 2 583 | 119 826 | 1.5% | generated DBUS proxies (`com/MM/...` interfaces) |
| `C_MODULE_*` | 672 | 97 969 | 1.2% | hardware owners: `C_MODULE_TUNER`, `C_MODULE_AUDIO`, the multi-tuner variants |
| `C_NAV_*`, `TCartogr`, `Map`, `M_MAP_MNG` | 2 006 | 184 435 | 2.3% | navigation server, cartography and map management |
| `C_SRV_*` | 1 210 | 65 136 | 0.8% | services (`C_SRV_AUDIO_SERVER`, media, tuner) |
| `C_MGR_*` | 112 | 10 170 | 0.1% | `C_MGR_SRC` (the source scheduler) and `C_MGR_BT` |
| everything else | | ≈ 1.2 M | ≈ 15% | FreeType, libpng, libjpeg, HarfBuzz, expat, a Bluetooth stack, codecs, and ~900 small vendor families |

The layer that decides behaviour is small. `C_MGR_SRC` is **71 functions and ≈ 7 600
instructions** out of eight million. Every AUX patch so far edits `C_MGR_SRC`,
`C_MODULE_AUDIO` or the `C_HMI_MEDIA` app.

## Producing the inventory

`tools/survey.py` makes one pass over the image. For every code symbol it records:

- its family and size;
- its direct `bl` callers;
- its **materialised references**: `lis`+`addi`/`ori` pairs that build its address. This is
  how most of this firmware's calls are made (through `mtctr`/`bctrl`), and it is exactly
  what `tools/callers.py` cannot see. `C_MGR_SRC::ExecuteAllocationFirstRound` has 0 `bl`
  callers and 1 materialised reference, from `ExecuteAllocation`;
- pointers to it held in data (vtables, callback tables). `C_HMI_MEDIA_APP_BASE::InitApp`
  and `C_MGR_SRC::StartUp` are reached this way only;
- the strings whose address it builds, usually its trace text.

```sh
uv run tools/survey.py ~/Downloads/SMEG_PLUS_UPG/NAV/AppBin/f_BigQuick.bin \
    abs_symbols_base.txt --out ~/smeg-survey
```

It takes `f_BigQuick.bin` or an inflated image, and an unpacked `abs_symbols_base.txt.gz`
from a `SPYSTORE` dump. The run takes a few seconds. It writes `functions.tsv`,
`families.tsv` and `unreached.tsv` under `--out`. That output is derived from the vendor's
symbol map, so it stays on your machine. Do not commit it; see `AGENTS.md`.

!!! note "Reference counts are lower bounds"

    An address built with `addis`+`lwz`, taken from a register computed at run time, or
    reached through a branch table is not counted. A function in `unreached.tsv` has no
    reference *this scan recognises*; that does not prove it is dead. 4 100 of the 9 889
    are Qt, where unused library code is expected.

## Coverage ledger

How closely each part has been examined, using the evidence tiers from
[Verification](VERIFICATION.md). **Read** means disassembled or decompiled and followed.
**Executed** means run under [the emulator](EMULATION.md) or observed on the car.

| area | depth | where |
|---|---|---|
| `C_MGR_SRC` boot restore: `StartUp`, `AddRequest`, `SetScheduledInit`, `SchedulerInitTimeout`, `ExecuteAllocation` | read. `AddRequest` executed under emulation. The boot-to-FM outcome was observed on the car. | [The AUX chain](AUX_CHAIN.md) |
| `C_MODULE_AUDIO::IsAUXSRCAvailable` and the AUX gates | read. The patched gate was confirmed on hardware. | [The AUX chain](AUX_CHAIN.md), [Patches](PATCHES.md) |
| `C_HMI_MEDIA_APP_BASE::InitApp` and `HandleAudioAuxInputStatusChnged` (`ActivateSource` call sites) | read | [The AUX chain](AUX_CHAIN.md) |
| `C_BCM_SPY` (`SPYTAKE`/`SPYSTORE` collection) | read, and executed on the car | [Cheatcodes & spy](CHEATCODES.md) |
| the upgrade container, manifests and `contract.dat` checks | read, and executed on the car (packages flash) | [Boot & update chain](FLASH_CHAIN.md), [Media protection](MEDIA_PROTECTION.md) |
| `C_MGR_SRC`, the source scheduler: all 71 functions | read, every function; `AddRequest` also executed under emulation | [The source scheduler](SCHEDULER.md) |
| `C_MODULE_AUDIO`, the audio module: 273 functions | 25 read closely (the AUX path, lifecycle, event dispatch, mute); 248 inferred from names, strings and a decompile digest | [The audio module](AUDIO_MODULE.md) |
| `C_HMI_SrcMgntBase` and every `ActivateSource(bool)` call site (17) | read | [How HMI apps request sources](HMI_SOURCES.md) |
| HMI framework: messages, event handler, menus | named from symbols, partly read | [Architecture](ARCHITECTURE.md) |
| everything else | inventoried by the survey only | this page |

When a subsystem is read closely, add a row here with its depth and the page it is written
on. Keep the tier honest: a function that is named, or that has a caller, has not been read.
