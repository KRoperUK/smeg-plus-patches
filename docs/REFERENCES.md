# Sources and prior art

This project did not start from nothing. Most of what is known about the SMEG+ platform was
established by others, in public, and this site builds on it. This page records **who
established what**, so a claim can be traced to its origin and so the boundary between "our
measurement" and "someone else's report" is explicit.

!!! warning "We link, we do not copy"

    None of the sources below are redistributed here. Where they are vendor or leaked
    documents we link to a public mirror rather than reproduce them; where they are other
    people's analysis we cite the repository and, where it matters, the file. This is the
    same rule the rest of the site follows for firmware: **we publish our own findings, not
    other people's bytes.** The SMEG+ hardware document is Magneti Marelli property and is
    not included in this repository.

The [evidence tiers](VERIFICATION.md) apply throughout: a fact taken from a third party is
*tier — read, from that source*, and is not promoted to *executed* by our repeating it. Where
this project has since re-derived a claim itself, the destination page says so.

## The unit

- **The SMEG+ Integrated Hardware Technical Specification** (Magneti Marelli, rev 1,
  14/10/13) — the only official hardware document known to exist. Summarised on
  [The hardware](HARDWARE.md). Publicly mirrored by the Brazilian regulator ANATEL
  (`fccid.io/ANATEL/00719-14-05386`). Vendor property; **do not copy it into a repository**.
- **`vidarrt9/smeg-rce` and [its wiki](https://github.com/vidarrt9/smeg-rce/wiki)** — the
  most complete public write-up of the SMEG+I (`5.x`) generation. It is the source of the
  generation framing used in the [glossary](GLOSSARY.md) (SMEG `3.x/4.x`, SMEG+I `5.x`,
  SMEG+Iv2 `6.x`), the
  [Hardware](https://github.com/vidarrt9/smeg-rce/wiki/Hardware) summary, the
  [5.43.A.R2](https://github.com/vidarrt9/smeg-rce/wiki/SMEG+I_5.43.A.R2) package inventory,
  and a walkthrough for physically removing the unit from the car. CC0-licensed.

## The package and its formats

- **`bousqi/SMEG_PLUS`** — reverse-engineering of the `upgrade.out` updater and the
  `vxWorks.bin` kernel. It is the source of: the updater's phase actions and
  `Manage*AndReboot` flow; the `smeg_reverse.txt` format notes (`*ctrl.bin`, `dbsystem.bin`,
  `flasher.inf`, `f_BigQuick.bin`, `BIG_HARMONY.bin`); the TFFS partition dumps
  ([Kernel and partitions](PLATFORM.md)); the VxWorks internal command list; and the
  per-volume file listings this project has not reproduced. It also documents the
  **map activation-key file** (`SMEG_PLUS_UPG/DATA/Licence`) — see
  [Cartography](CARTOGRAPHY.md).
- **`vidarrt9/smeg-plus-analysis`** — the extracted contents of the 5.43.A.R2 upgrade
  package (the version this project targets), plus a Ghidra recipe for loading `vxWorks.bin`
  at `0x200000` and applying a VxWorks symbol-table finder, and symbol maps built from
  recompiled OpenSSL 0.9.8l and zlib 1.2.3. It is the source of the "which `.out`/`.bin`
  files ship, and how big is each" inventory behind
  [Media partition](MEDIA_PARTITION.md).
- **`vidarrt9/vxhunter`** — a VxWorks analysis toolset (plugins for IDA, Ghidra and radare2,
  plus a serial debugger). Not a dependency of this project, but the reference implementation
  for anyone who wants to name kernel functions automatically rather than by hand.

## The car and the key

- **`Mwyann/psakey`** (and `bousqi/smeg-plus_key`) — a Raspberry Pi that pretends over USB to
  be PSA's "connected key", which is why the SMEG+ behaves differently when one is present.
  Relevant because it is a working example of the CDC-EEM gadget class the kernel accepts
  ([Kernel and partitions](PLATFORM.md)).
- **`vidarrt9/usb-intruderer`** — attempts to talk to the SMEG+ over its USB ports by posing
  as supported gadget classes, and a survey of hardware that can do it.
- **`prototux/PSA-CANbus-reverse-engineering`** — the PSA CAN bus itself. Out of scope for
  patching the head unit's software, but it is where the vehicle-side messages are documented.

## Tools referenced

- **`pyghidra-mcp`** — the Ghidra-over-MCP bridge used for [the toolchain](TOOLCHAIN.md).
- **`qresExtract`** — a small utility for extracting Qt `.rcc` resource bundles, which the
  `USERGUIDE/*.rcc` files are ([Media partition](MEDIA_PARTITION.md)).
- **`dust`** — only used by the analysis repo to size the package tree.

## What is *this* project's own work

For contrast, the following are established by this repository rather than taken from the
above, and are where the site's original claims live:

- the AUX boot chain and the three boot-to-AUX patch sets ([The AUX chain](AUX_CHAIN.md));
- the source scheduler and audio-module readings ([Source scheduler](SCHEDULER.md),
  [Audio module](AUDIO_MODULE.md));
- the `contract.dat` format, its re-sealing, and `tools/patch_contract.py`
  ([Media protection](MEDIA_PROTECTION.md));
- the `*_ctrl.bin` / `system_ctrl.bin` record layout and the type-3 CRC-16
  ([Boot and update chain](FLASH_CHAIN.md));
- the `f_BigQuick.bin` container handling and the whole patch/checksum toolchain;
- `tools/ppcemu.py`, `tools/survey.py` and the rest of the analysis tooling.

## Contributing a correction

If a claim here is wrong, or a source is misattributed, the fix belongs on this page and on
whichever destination page carries the claim. Say which tier it was and which it should be;
see [Verification](VERIFICATION.md) for the convention and `CONTRIBUTING.md` for the
mechanics.
