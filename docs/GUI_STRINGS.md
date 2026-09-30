# GUI string tables (`gui_text_strings_<LANG>.xml.bin`)

The unit's **user-visible wording** — every source name, menu entry, message and dialog — ships
in one binary file per language inside the media partition:

```
Data_base/boardfs/GUI_STYLE/GUIS_RESSOURCES/gui_texts/gui_text_strings_<LANG>.xml.bin
```

Despite the name they are **not XML**. They are a flat string table: a 16-byte header, a
12-byte record per string, then the string data. The format is decoded *(executed)*, a decode
followed by a rebuild reproduces the shipped files byte-for-byte *(executed — all 14 of them)*,
and `tools/guistrings.py` edits and rebuilds them so
[`tools/patch_media.py`](../tools/patch_media.py) can swap one into a package.

## The format { #the-format }

All integers are **big-endian**. A "unit" is one UTF-16 code unit — two bytes.

```
0x00  u32   total file size
0x04  u32   record count                     (2379 in every shipped file)
0x08  u32   offset of the first string       (always 0x10 + 12 x count)
0x0c  u32   reserved — zero in every shipped file

0x10  record 0      12 bytes each:
        +0  u32      id
        +4  u32      offset of the string, absolute from the start of the file
        +8  u32      length of the string, in bytes (not characters)
      record 1
      ...

0x10 + 12 x count    the string blob: UTF-16BE code units, back to back,
                     in record order, unaligned, unterminated
```

A two-string file, byte by byte — `1 = "AB"`, `2 = "CD"`:

```
00000030 00000002 00000028 00000000     header: 48 bytes, 2 records, strings at 0x28
00000001 00000028 00000004              id 1, at 0x28, 4 bytes
00000002 0000002c 00000004              id 2, at 0x2c, 4 bytes
00410042 00430044                       "AB" "CD"
```

Facts about the blob that matter when editing it:

* **UTF-16BE, no BOM, no terminator.** The record's length is the only bound on a string;
  there is nothing between one string and the next.
* **The length is a byte count.** `length / 2` is the number of code units; an accented
  character costs two bytes, an astral one (emoji) four. Every length in every shipped file is
  even, which is what `tools/guistrings.py` insists on.
* **Offsets are absolute and contiguous.** The first string sits at the base, and each
  subsequent one starts where the last ended — so `offset = base + sum(previous lengths)`.
  There is no padding and no alignment rule.
* **The records are in ascending id order**, and the id space is sparse: the shipped files use
  2379 ids out of `0..2652`. **The sequence is identical in all 14 languages**, so the ids are
  the unit's own and a translation must not renumber them.
* **The blob ends exactly at EOF**, and `0x10 + 12 x count + sum(lengths)` equals the recorded
  file size exactly. There is **no internal checksum** — see [the CRC](#the-checksum-is-external)
  below.

### How the two readers agree on this { #how-the-two-readers-agree }

The layout above is not inferred from the file's shape alone. It is what the application
image's own loader and the vendor's own writer agree on *(read — disassembly of the NAV
5.43.A.R2 image, `Application/PKG/abs_symbols_base.txt` for the names)*:

| what | where | what it establishes |
|---|---|---|
| `C_GUI_StringsManager::LoadStringsFileBinary(QString const&)` | `0x021f65b4` | reads the whole file into one buffer, takes the count from `0x04`, walks records from **`0x10`**, and for each one does `QString::fromRawData((QChar*)(buffer + offset), length >> 1)` |
| `C_GUI_StringsManager::buildBinaryStringsFile(QString const&)` | `0x021f6b80` | starts the size at `0x10` and adds `0xC` per entry, adds `QString::size() * 2` bytes per string, writes the total at `+0`, the count at `+4`, the base at `+8`, and copies each string with a 16-bit store — which is the layout above, exactly |
| `C_GUI_Manager::LoadLanguage(int)` | `0x0203deb0` | builds `gui_text_strings_<lang>.xml` + `.bin`, calls `LoadStringsFileBinary`, and only if that fails falls back to parsing the plain `.<lang>.xml` as XML |

Four consequences worth knowing:

* The loader **does not check the header.** It never reads the size at `0x00`, the base at
  `0x08` or the reserved word at `0x0c`; it uses the count from `0x04` and the fixed record
  offset `0x10`. `tools/guistrings.py` still writes all four correctly, so the files it
  produces are the same shape the vendor's writer produces *(inferred from the writer's
  disassembly)*.
* A **duplicate id** is ignored with a `qWarning(...) << "Duplicate Id" ...` *(read)*.
* An **id that is not in the file** yields an **empty** string — `GetString(id)` constructs its
  result from an empty literal when the lookup misses *(read, `0x021f7248`)*.
* The strings are read with `QString::fromRawData`, which does **not copy**: they alias the
  buffer the loader allocated, which is why the loader holds the whole file for as long as the
  strings are live rather than deallocating after parsing *(read)*.

### The checksum is external { #the-checksum-is-external }

The file carries no checksum of its own *(executed)*. There is nowhere for one: the recorded
size equals the header plus the directory plus the sum of the string lengths, to the byte, in
all 14 shipped files, and the reserved word at `0x0c` is zero in all 14.

What protects it is the partition's cascade — a **type-2 (`CheckType = 2`) CRC32 of the file's
contents** in `system_ctrl.bin`, then `system.bin` / `system.bin.inf`, then the module and root
manifests. `tools/patch_media.py` recomputes all of it, and its `SIZE:` / `SIZE_n` handling
absorbs a changed file size by applying the delta. See
[Media partition](MEDIA_PARTITION.md#system-ctrl-bin).

## Limits

| what | limit | evidence |
|---|---|---|
| longest string | **the format sets none** — the length is a `u32`; the shipped maximum is **404 bytes / 202 units** (FR, id 2644, a multi-line navigation message) | executed |
| shortest string | **0** — empty strings are shipped and are legal (17 per file) | executed |
| number of records | not fixed by the format; **2379** in every shipped file | executed |
| id space | `0..2652` shipped, sparse; nothing in the format forbids another id | executed |
| languages | **16** are listed in `GUI_STYLE/gui_languages.xml`; **14** files ship (`SC` and `US`, the two Chinese entries, are absent) | executed |
| encoding | UTF-16BE only; there is no code-page field and no BOM | read + executed |
| how long a label may be | **not known** — the UI widget that displays a given id is outside this format, so no bound can be read off the file | not known |

That last row is the honest one. The file format has no ceiling, but a label the skin's
widget cannot fit might clip or overflow, and nothing here tells you which ids are safe to
lengthen. The conservative edit is `--pad`, which keeps a replaced string in its original
slot; the file grows only when you choose to let it.

## Editing one

`tools/guistrings.py` is the whole toolchain. Nothing is written in place unless you ask:

```sh
# what is in a file, and whether it is structurally sane
python3 tools/guistrings.py info  media/.../gui_texts/gui_text_strings_GB.xml.bin

# the id -> string table. --json is a valid overrides file, so this is the edit loop:
python3 tools/guistrings.py dump  media/.../gui_texts/gui_text_strings_GB.xml.bin --json > edits.json
#   ... change "9": "AUX" to "9": "CarPlay" ...
python3 tools/guistrings.py build --base media/.../gui_text_strings_GB.xml.bin \
                                  --out  media/.../gui_text_strings_GB.xml.bin.new \
                                  --overrides edits.json

# or in place, keeping every slot the same length so that no offset moves
python3 tools/guistrings.py patch media/.../gui_text_strings_GB.xml.bin --in-place --set 9=CarPlay
```

`patch` and `build` are the same operation; `patch` takes the file as a positional argument and
`build` takes it as `--base`. With no edits at all, a rebuild is a byte-for-byte copy of the
input — that is the round-trip bar, and `probe` checks it on whatever you hand it:

```sh
python3 tools/guistrings.py probe media/Data_base/boardfs/GUI_STYLE/GUIS_RESSOURCES/gui_texts
```

The options that matter:

| option | what it does |
|---|---|
| `--set ID=TEXT` | one override on the command line; repeatable |
| `--overrides FILE` | a JSON object of `id -> string`, which is exactly what `dump --json` writes |
| `--pad` | keep each edited string's original byte length, NUL-padding it, so the file size and **every** offset in it are unchanged. Refuses a replacement that would not fit |
| `--pad --truncate` | clip an over-long replacement to the slot instead of refusing |
| `--allow-new-id` | accept an id the file does not have; it is appended and the record count changes |

!!! warning "NUL padding is untested on the unit"

    `--pad` pads a shortened label with `U+0000` inside its recorded length. That is
    self-consistent — the offset arithmetic stays valid and no shipped string contains a NUL —
    but **no shipped string is padded like that**, so whether the widget stops drawing at the
    first NUL or renders it as a gap is **not known**. If you lengthen a label, do not use
    `--pad`: let the file grow. `tools/patch_media.py` handles the size change.

## Which id is which label { #which-id-is-which-label }

The ids are not named anywhere in the partition, so two things are true and one is not yet
settled:

* The **first ~37 ids are the source names**: `DAB Radio`, `AM Radio`, `USB`, `CD`, `Jukebox`,
  `Copy…`, `iPod`, `Bluetooth`, `AUX`, `Video`, then the same ten again in a different order,
  and again a third time. **`AUX` appears at six ids** (9, 19, 30, 36, 1329 and 1804 in the
  British file) *(executed)*.
* Which of those a given tile shows is decided by the **skin's template**, and the template is
  not in this partition: `gui_templates.xml` is referenced by the application but delivered by
  the **HARMONY** module, whose `.bin` skin archives are a separate format
  ([What is reachable](CAPABILITIES.md)). So map id to on-screen label **by changing one and
  looking**, not by guessing from the order alone *(inferred)*.
* Languages repeat the same id for the same label, so an override has to be applied to every
  language you care about — the unit only loads the file for the language it is set to.

## The flash-through path

Editing a label is a **media-partition change**, not a code patch, so it reuses the existing,
working path end to end *(executed offline; not yet flashed)*:

```
gui_text_strings_GB.xml.bin   rebuilt by tools/guistrings.py
  -> system_ctrl.bin          type-2 record: CRC32 of the file's contents   (recomputed)
  -> system.bin               the tar and its gzip                          (rebuilt)
  -> system.bin.inf           CRC32 + the SIZE / SIZE_n fields              (delta applied)
  -> NAV_ctrl.bin             CRC32 per packaged file
  -> ctrl.bin                 the root manifest
  -> contract.dat             re-sealed last — see Media protection
```

Worked example, on an extracted partition (1 file changed, `AUX` → `CarPlay` at id 9, which
lengthens the file by 8 bytes):

```sh
python3 tools/guistrings.py patch media/Data_base/.../gui_text_strings_GB.xml.bin \
        --in-place --set 9=CarPlay
python3 tools/patch_media.py apply --package SMEG_PLUS_UPG --module NAV \
        --tree media --out SMEG_PLUS_UPG_mod
```

```
changes (1):
   Data_base/boardfs/GUI_STYLE/GUIS_RESSOURCES/gui_texts/gui_text_strings_GB.xml.bin  119794 -> 119802

wrote:
   NAV/system.bin, NAV/system.bin.inf, NAV/system_ctrl.bin, NAV_ctrl.bin, ctrl.bin
```

Re-extracting that `system.bin` gives the edited file back byte for byte, the type-2 record in
`system_ctrl.bin` matches its CRC32, `SIZE:` moves by exactly `+8`, and the `SIZE_1`..`SIZE_32`
fields do not move at all (8 bytes is inside every KiB rounding) *(executed)*. Build the
package with `tools/build_package.py` and re-seal it before it goes near a car — a modified
package that is not re-sealed is rejected with string 2099
([Media protection](MEDIA_PROTECTION.md)).

## What is not established { #what-is-not-established }

* **Nothing here has been flashed.** Every claim above is a static read of the file, the
  loader or the vendor's writer, plus an offline rebuild of a real package.
* **Which id the source tile shows**, and therefore whether renaming `AUX` to `CarPlay` puts
  the word where the user reads it. See [above](#which-id-is-which-label).
* **Whether an over-long label clips** rather than overflowing its widget.
* **What reads `gui_text_strings.inf`** — the small sidecar beside the tables
  (`TEXT_MAJOR:24.5`, `TEXT_MINOR:1`, `SMEG:4;5`, `XML_EDITOR:30_4`). No caller has been
  identified; it looks like the text-team tooling's own manifest, not something the unit reads
  *(inferred)*.
* **What id 0 is for.** Every language has id 0 = `"DY"`, which is not a label anyone would
  show. The loader treats it like any other record *(read)*; nothing looks it up as far as this
  analysis went.

## Provenance

Established on **your own** extracted partition, never from a committed file: the round trip is
re-run by `tests/test_firmware_gui_strings.py` against the tree
`tools/patch_media.py extract` writes, gated on `SMEG_MEDIA_DIR` and skipped in CI:

```sh
SMEG_MEDIA_DIR=media .venv/bin/python -m pytest -m firmware -q
```

The synthetic half — the layout, the offsets, the padding rules and the CLI — is
`tests/test_guistrings.py`, which builds its own tables and needs no firmware at all.
