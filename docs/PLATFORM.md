# Kernel and partitions

The layer between the metal and the application: **U-Boot**, the **VxWorks** kernel, the
address map, and the flash filesystems the unit mounts. This is mostly *read* from
[bousqi/SMEG_PLUS](https://github.com/bousqi/SMEG_PLUS) — which reverse-engineered the
`upgrade.out` updater and the `vxWorks.bin` image — cross-checked against what this project
has measured directly, and noted where it has not. See [Sources and prior art](REFERENCES.md).

!!! note "Two different base addresses"

    Addresses here are **load addresses in the PowerPC address space**, not NAND byte
    offsets. The updater's `flasher.inf` uses flash offsets like `0x720000` for `vxWorks.bin`
    (see [Boot and update chain](FLASH_CHAIN.md)); the kernel then runs at `0x00200000`. Do
    not mix the two.

## Boot

Two stages, both in NAND outside any filesystem:

1. **U-Boot** — the first-stage loader, flashed by the updater's
   `ManageUBootUpdateAndReboot()` and reported in System Information as `UBoot version`
   (ours shows `06.03 Apr 22 2013`). Its variables and the FlashFX/TFFS geometry are not
   documented by this project.
2. **VxWorks 6.7** — the RTOS proper, the image shipped as `BSP/SMEG_PLUS_<256|512>/vxWorks.bin`.

The kernel identifies itself on the console as:

```
VxWorks (for Freescale MPC5121E ADS (Rev 0.1)) version 6.7.
Kernel: WIND version 2.12.
Made on May 26 2017, 13:23:36.
Boot line:
usb(0,0)host:vxWorks h=192.168.10.2 e=192.168.10.1 u=5121 pw=5121 f=0x0 tn=DB600
```

*(read, bousqi/SMEG_PLUS.)* The `usb(0,0)host:…` boot line is the interesting part: the
kernel's default boot device is **USB**, over a host/network device, which is consistent
with the USB device classes below. The `u=`/`pw=` are a built-in login, not a credential of
yours, and `h=192.168.10.2 e=192.168.10.1` is a hard-coded link-local pair.

## Address map

| address | what |
|---|---|
| `0x00010000` | space reserved for loading ELF files |
| `0x00200000` | **`vxWorks.bin`** — the kernel (image base) |
| `0x01000000` | **`f_BigQuick.bin`**'s inflated application image |
| `0x04c00000` | the browser / "Post" image, a separate loadable process |

*(read.)* The first two are bousqi's; the application and browser bases are this project's
own (see [Architecture](ARCHITECTURE.md)). The application and the kernel share **one address
space** — that is what makes a branch from a patch into a kernel function possible at all,
which [`patches/diagnostic-logsink.json`](PATCHES.md) relies on.

## The kernel's own symbol table

`vxWorks.bin` is not an ELF, but it carries a VxWorks symbol table, so kernel functions can
be named even without a linked map. The entries are **20 bytes**:

```
struct s_Symbol {
  int   unk1;
  void *name;     /* pointer into the image's string area */
  void *address;
  int   unk2;
  int   type;     /* 0x100 unk, 0x400 func, 0x800 data, 0x1000 ext */
};
```

The table lives near the end of the image — at `0x00822024` on the analyser's unit, holding
13 853 symbols *(read, bousqi/SMEG_PLUS)*. Read at the `0x00200000` base the name pointers
resolve, which is how this project confirmed the base independently: the application's own
`IsAUXSRCAvailable()` failure path calls `0x0058c248`, and the table names that address
`tickGet` (see [Boot and update chain](FLASH_CHAIN.md)).

Other structures bousqi located in the image, useful starting points for anyone reading the
kernel *(read; addresses are per build, do not assume they match another unit)*:

```
vxSymTbl      0x00822024   the symbol table above
opcodeTbl     0x007a2bf8
registerTbl   0x007a3540
wifiRegionTbl 0x0081CD6C
partTbl       0x00741250
fpRegs        0x007A2524
fpCtrlRegs    0x007A262C
taskRegs      0x007A263C
```

!!! warning "Not the same vxWorks as the WRS public one"

    This is a **Wind River**-built VxWorks 6.7 for a specific Freescale reference board
    (`MPC5121E ADS`). It is not a generic desktop VxWorks, and the symbol table is the only
    map of it this project knows of. `tools/elfsyms.py` cannot read it — it is not ELF.

## Flash partitions

The kernel mounts a FlashFX/TrueFFS flash translation layer as a set of named volumes. The
layout, as seen from a rooted shell *(read, bousqi/SMEG_PLUS — tree dumps in that repo)*:

| TFFS type | device | on | holds |
|---|---|---|---|
| 7 | `/romfs` | internal NAND | debug binaries for audio and `scheduler.bin` |
| 3 | `/ram` | RAM | config files; not readable over telnet |
| 3 | `/sdhc:0` | internal microSD | cartography, cheat-code libraries, TTS |
| 3 | `/sdhc:1` | internal microSD | user guide |
| 3 | `/bd0` | USB mass storage | the stick; this is where `SMEG_PLUS_UPG/` lives |
| 3 | `/SYSTEM` | internal NAND | the media partition, extracted read-only |
| 3 | `/SYSTEM_DATA` | internal NAND | the `system_data.bin` payload |
| 3 | `/SYSTEM_TMP_DATA` | internal NAND | transient update state (e.g. `StartUsb.txt`) |
| 3 | `/USER_DATA` | internal NAND | **live user state the car owns** — settings, phones, destinations |
| 3 | `/USER_DATA_BACKUP` | internal NAND | the backup copy the updater keeps |
| 3 | `/EXTENDED_PARTITION` | — | present in the partition table; contents not documented here |

The ones that matter to patching are `/SYSTEM` (read-only, so edits to the *seed* do not
reach live state — see [What is reachable](CAPABILITIES.md)) and `/USER_DATA` (the live copy
the car owns; overwriting it is destructive and not recoverable by reflashing). Which of
these are NAND-backed versus a card is a distinction the updater's phases act on directly
(see [Boot and update chain](FLASH_CHAIN.md)).

## USB device classes

The kernel's USB stack is not a general one. What it supports, as strings in `vxWorks.bin`
*(read, bousqi/SMEG_PLUS)*:

- **CDC-EEM** (Ethernet Emulation Model) and **CDC-ACM** — the serial/network gadget classes.
  This is why the boot line is `usb(0,0)host:…` and why the community "[psakey]" USB-key work
  is a thing at all.
- **Mass storage**, including several volumes on one device — this is the path the updater
  uses for `SMEG_PLUS_UPG/`.
- USB-to-Ethernet adapters (ADM8511/8513/8515, DM9601 families, and the ASIX/davicom clones
  listed in the kernel) and a few USB 3G modems.
- **Not** RNDIS, ECM or NCM.

[psakey]: https://github.com/Mwyann/psakey

So a host PC cannot simply pretend to be an arbitrary USB device to the unit — it has to
present one of the supported classes. See [the usb-intruderer notes](REFERENCES.md) in
[Sources and prior art](REFERENCES.md) for the prior work of that kind.

## The VxWorks shell

The kernel runs a shell on its serial console (and the CDC-EEM path), where the commands are
**direct symbol lookups**, not a fixed command table — which means *every* public function in
the image is callable by name. Names this project has used or seen used *(read)*:

- `d <addr>` — dump memory as words with an ASCII gutter. Comparing a dump with the file at
  the same offset is how the load base was confirmed.
- `lkup "<name>"` — list symbols matching a name, with their address and type
  (`text` / `data`). Redundant for `vxWorks.bin`, which embeds its own symbols.
- `regsShow`, `memShow`, `ti` / `task`, `devs`, `iosDrvShow`, `ifconfig`, `route`, `ping`.

Reaching that shell needs physical access (UART) or a supported USB gadget; it is not a
remote path and is out of scope here. It is mentioned because it is how several of the
kernel facts above were established, not as a recommended workflow.

## Open questions

- U-Boot: version, variable set, and how its NAND region is laid out. The updater's
  `ManageUBootUpdateAndReboot()` is named but its internals have not been read.
- What lives in `/EXTENDED_PARTITION`.
- Whether the TFFS partition table (`partTbl`) is fixed or shifted between 256 MB and 512 MB
  boards.
- The VxWorks `r2` (TOC) value. bousqi could not pin it down (`0x007A5F80` lands in a
  compressed picture); the shared `EABI` TOC is a candidate but was not confirmed. This
  matters only for someone doing full-kernel decompilation, not for application patching.
