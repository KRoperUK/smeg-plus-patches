# Recovery

What to do when an update does not go the way it should.

This page is deliberately thin in places. `FLASHING.md` covers the happy path, and the honest
position is that **several of the failure modes below are not documented anywhere this project
has evidence for** — including by the vendor. Where that is the case it says so rather than
implying a procedure exists. Claims are tagged as in
[Hardware verification](VERIFICATION.md):

- **observed** — seen on hardware
- **read** — decoded from the firmware or the package manifests
- **unknown** — stated neither here nor, as far as this project has found, by anyone

!!! danger "The one rule"

    **Do not remove the stick and do not cut power until the unit reboots.** The update takes
    over 20 minutes and reboots several times on the way. Interrupting it is the way to reach
    the states this page cannot fully answer for.

## Before you start, so you do not need this page

Two things, both cheap, both covered in [Flashing](FLASHING.md):

```sh
python3 tools/verify_package.py --package out/SMEG_PLUS_UPG
python3 tools/prepare_usb.py --package out/SMEG_PLUS_UPG --target /Volumes/USB
```

The first audits every checksum the package carries against the file it describes. The second
copies to the stick and **re-reads every file back off it** to prove the copy is not truncated.
A truncated copy is the failure most likely to be mistaken for a firmware fault.

And keep a rollback: **an untouched copy of the original package, audited too.** A rollback you
have not checked is not a rollback. Copy it with `prepare_usb.py` so the same verification
applies. *(observed — a re-sealed patched package was accepted by a real unit)*

## The unit refused the update and showed an error

**Nothing was written.** This is the good failure: the unit validates before it writes, so a
refusal leaves the unit exactly as it was. *(read — the rejection path in `CheckTrustedSource`;
the refusal itself was not reproduced on the test unit)*

| what you see | what it means |
|---|---|
| **2099**, *"The update file is protected and cannot be copied."* | the package does not match its signed contract. It was modified without being re-sealed. Rebuild with `seal: true`, or run `tools/patch_contract.py`. *(read)* |
| `(UpgradeTask) The version on media.inf not allows an upgrade` | the version field in `media.inf` blocks this upgrade. A wrong value there **blocks** the package rather than warning about it. *(read)* |
| `Upgrade not possible!! value is too high` | as above — the version gate. *(read)* |
| `(GetUBootVersionMedia): field 'VER:' not found!` | the package's version field is missing entirely. *(read)* |
| `Error loading symbol WriteNANDBigQuick, it's an old BSP!!!` / **`BSP Not compatible. Please use the loader button...`** | see below. *(read)* |
| `VerifyNANDBigQuick : CRC of data BigQuick is NOK` | the image failed its CRC check on the way to NAND. *(read)* |

The unit **re-offers** the update when a valid stick is present — the confirmation dialog was
seen a second time after the unit had already updated and come back up. *(observed)*

**What is not known:** whether a refused package triggers any retry loop, and what state the
unit settles into after repeated refusals. The updater does keep a **persisted step counter**,
which implies a re-run resumes rather than restarts — but that is a reading of `upgrade.out`,
not an observed behaviour, and this page will not pretend otherwise. *(read/*unknown*)*

## "BSP Not compatible. Please use the loader button"

The unit's own message, and the most useful one it gives you. It appears when the running BSP
is too old to export the NAND write routine the updater needs — the updater literally reports
`Error loading symbol WriteNANDBigQuick` before it. *(read)*

The fix is to get a **newer BSP** onto the unit, which is what the message is asking for. The
loader is the level below the application, so it can still be reached when the application
cannot.

**What this page will not do is invent a button sequence.** The message names a loader button;
where it is on the fascia, what it does electrically, and the exact procedure to enter the
loader are **not documented in this project and were not decoded from the firmware**. If you are
in this state, that is the question to ask before acting, and anyone answering it confidently
without a source is guessing. *(unknown)*

Related, and slightly better understood: `upgrade_256.out` is the **256-unit relauncher** (its
own string is *"Relaunch For 256"*), sitting beside `upgrade.out` as an entry module. *(read)*

## A unit that will not boot

**There is no documented procedure here.** Nothing in this project describes recovering a unit
that no longer reaches its application, and the vendor strings do not cover it either. The
general risk statement in the repository's `SECURITY.md` is the accurate summary: a bad build
can leave a unit needing recovery or dealer service. *(unknown)*

Two things are worth knowing anyway, because they are the mechanisms a recovery would use, even
though the procedure is not written down:

- the update is **incremental** — an already-current unit reports the boot ROM as done and skips
  the Renesas MCU, and rewrites the application only when its content differs *(read)*;
- the updater carries a **persisted step counter**, so a re-run does not necessarily start from
  the beginning. *(read)*

## Power loss mid-write

**Unknown, and the most consequential unknown on this page.** The repository states the
requirement clearly — engine running, `Keep the engine running.` on screen, no power loss, no
stick removal — and it states that the unit reboots at several points during the update.
*(observed/read)*

What it does **not** state is what a partial write leaves behind, or whether re-flashing
recovers it. There is no claim here that it does. Treat power loss during a write as the case
with the least known recovery path, and act accordingly.

## Wrong-variant stick (256 vs 512)

256 and 512 are the **NAND/board size, not a firmware feature level**. The updater picks a BSP
tree from the hardware type (`SMEG_PLUS_256/` vs `SMEG_PLUS_512/`). A package shipping both has
the variants side by side. *(read)*

Two cross-checks exist and are worth knowing, because they are what would stop a wrong-variant
stick:

- `dbsystem.bin` embeds the matching `vxWorks.bin` CRC32 and a leading byte equal to the top byte
  of the load address (`0x72` for 512, `0x42` for 256). It is a size/CRC/block-count descriptor
  used to cross-check `vxWorks.bin` before flashing — the firmware logs
  `VxWorks.bin parameters in dbsystem are (size: … crc: … Nb blocks = …)`. *(read)*
- `flasher.inf` lists path, load address and CRC per line, with `flasher.crc` the CRC32 of
  `flasher.inf` itself. *(read)*

**What is not known:** whether those checks *actively refuse* a mismatched stick, and how the
unit reads its own hardware type — the selection is `GetHWType`, and it has not been traced.
`dbsystem.bin`'s exact field offsets are also unpinned. So: do not rely on the unit to catch a
wrong-variant stick. Check the variant yourself before you start. *(unknown)*

## See also

- [Flashing](FLASHING.md) — the procedure, and the two checks worth running first
- [Boot & update chain](FLASH_CHAIN.md) — every gate the updater passes, and its strings
- [Media protection](MEDIA_PROTECTION.md) — why 2099 exists and what re-sealing does
- [Hardware verification](VERIFICATION.md) — what has actually been observed
