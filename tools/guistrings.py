#!/usr/bin/env python3

# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///

"""Decode and rebuild the GUI string tables (`gui_text_strings_<LANG>.xml.bin`).

The unit shows its user-visible wording from one binary file per language, in the media
partition at `Data_base/boardfs/GUI_STYLE/GUIS_RESSOURCES/gui_texts/`. Despite the name they
are **not XML**:

    0x00  u32  total file size
    0x04  u32  record count
    0x08  u32  offset of the first string (always 0x10 + 12 * count)
    0x0c  u32  zero
    0x10  n * 12-byte records:  u32 id, u32 offset (absolute), u32 length (bytes)
    ...   the string blob: UTF-16BE code units, concatenated, no terminator, no BOM

The directory is sorted by id, the offsets are contiguous, and the blob ends exactly at EOF —
so there is **no internal checksum**; the file's CRC32 lives in `system_ctrl.bin` with the
rest of the partition cascade. A decode followed by a rebuild reproduces the input
byte-for-byte; `probe` checks that on the file you hand it. See docs/GUI_STRINGS.md.

The reader is `C_GUI_StringsManager::LoadStringsFileBinary` and the vendor's own writer is
`C_GUI_StringsManager::buildBinaryStringsFile`, both in the application image; the layout
above is what the disassembly of the two agrees on.

usage:
    # the id -> string table, and what the header says
    python3 tools/guistrings.py dump  media/Data_base/.../gui_texts/gui_text_strings_GB.xml.bin
    python3 tools/guistrings.py info  media/.../gui_text_strings_GB.xml.bin

    # what the format allows, and proof that a rebuild is byte-identical
    python3 tools/guistrings.py probe media/.../gui_text_strings_GB.xml.bin
    python3 tools/guistrings.py probe media/.../gui_texts --lang GB

    # edit a label: dump to JSON, change the value, rebuild (the JSON is the overrides file)
    python3 tools/guistrings.py dump  GB.xml.bin --json > edits.json
    python3 tools/guistrings.py build --base GB.xml.bin --out GB_new.xml.bin --overrides edits.json

    # or in place, keeping every slot the same length so no offset moves
    python3 tools/guistrings.py patch GB.xml.bin --in-place --set 4=CarPlay --pad

    # compare two languages
    python3 tools/guistrings.py diff GB.xml.bin FR.xml.bin
"""

import argparse
import json
import struct
import sys
from dataclasses import dataclass
from pathlib import Path

HEADER_SIZE = 0x10
RECORD_SIZE = 0x0C
# The loader hands the bytes to QString::fromRawData((QChar*)p, length >> 1): 16-bit units,
# big-endian on the e300, counted in bytes and never NUL-terminated.
ENCODING = "utf-16-be"
LANG_PREFIX = "gui_text_strings_"
LANG_SUFFIX = ".xml.bin"


class GuiStringsError(Exception):
    """Not a GUI string table, or an edit that would break the format."""


@dataclass
class Entry:
    """One directory record: an id and the string it names."""

    id: int
    offset: int
    length: int
    text: str


class StringsFile:
    """A parsed `gui_text_strings_<LANG>.xml.bin`."""

    def __init__(self, size_field, count_field, base_field, reserved, entries, file_length):
        self.size_field = size_field
        self.count_field = count_field
        self.base_field = base_field
        self.reserved = reserved
        self.entries = entries
        self.file_length = file_length

    @classmethod
    def parse(cls, data):
        if len(data) < HEADER_SIZE:
            raise GuiStringsError("shorter than a %d-byte header" % HEADER_SIZE)
        size_field, count_field, base_field, reserved = struct.unpack_from(">IIII", data, 0)
        end = HEADER_SIZE + count_field * RECORD_SIZE
        if end > len(data):
            raise GuiStringsError(
                "the directory says %d records, which runs to 0x%x past the %d-byte file"
                % (count_field, end, len(data))
            )
        entries = []
        for i in range(count_field):
            sid, off, length = struct.unpack_from(">III", data, HEADER_SIZE + i * RECORD_SIZE)
            if length % 2:
                raise GuiStringsError(
                    "record %d (id %d) is %d bytes: an odd length cannot be UTF-16"
                    % (i, sid, length)
                )
            if off + length > len(data):
                raise GuiStringsError(
                    "record %d (id %d) runs to 0x%x past the %d-byte file"
                    % (i, sid, off + length, len(data))
                )
            # surrogatepass so that any 16-bit unit round-trips, including a lone surrogate
            # no real text produces.
            entries.append(
                Entry(sid, off, length, data[off : off + length].decode(ENCODING, "surrogatepass"))
            )
        return cls(size_field, count_field, base_field, reserved, entries, len(data))

    @classmethod
    def load(cls, path):
        return cls.parse(Path(path).read_bytes())

    def to_bytes(self, entries=None):
        """Rebuild the file. Offsets and lengths are recomputed, never copied.

        With the file's own entries this is byte-identical to the input, which is what
        `probe` asserts and `tests/test_guistrings.py` locks down.
        """
        entries = self.entries if entries is None else entries
        base = HEADER_SIZE + RECORD_SIZE * len(entries)
        records = bytearray()
        blob = bytearray()
        for e in entries:
            raw = e.text.encode(ENCODING, "surrogatepass")
            records += struct.pack(">III", e.id, base + len(blob), len(raw))
            blob += raw
        total = base + len(blob)
        # The reserved word at 0x0c stays zero: the vendor's writer memsets the buffer and
        # never touches it, and the loader never reads it.
        header = struct.pack(">IIII", total, len(entries), base, 0)
        return header + bytes(records) + bytes(blob)

    def issues(self):
        """Structural checks, as (description, ok) pairs — the shipped files pass all of them."""
        out = [
            ("size field (0x00) equals the file length", self.size_field == self.file_length),
            (
                "strings base (0x08) equals 0x10 + 12 * count",
                self.base_field == HEADER_SIZE + RECORD_SIZE * self.count_field,
            ),
            ("reserved word (0x0c) is zero", self.reserved == 0),
            (
                "count field (0x04) equals the number of records",
                self.count_field == len(self.entries),
            ),
            ("ids are unique", len({e.id for e in self.entries}) == len(self.entries)),
            (
                "records are in ascending id order",
                [e.id for e in self.entries] == sorted(e.id for e in self.entries),
            ),
            (
                "each string ends where the next begins",
                all(
                    self.entries[i].offset + self.entries[i].length == self.entries[i + 1].offset
                    for i in range(len(self.entries) - 1)
                ),
            ),
            (
                "offsets are absolute, as the loader uses them",
                not self.entries or self.entries[0].offset == self.base_field,
            ),
            (
                "nothing follows the last string",
                not self.entries
                or self.entries[-1].offset + self.entries[-1].length == self.file_length,
            ),
            (
                "every length is even (UTF-16 code units)",
                all(e.length % 2 == 0 for e in self.entries),
            ),
            (
                "no string carries a NUL inside its length",
                all("\x00" not in e.text for e in self.entries),
            ),
        ]
        return out


def language_of(path):
    """`gui_text_strings_GB.xml.bin` -> `GB`, or None for any other name."""
    name = Path(path).name
    if name.startswith(LANG_PREFIX) and name.endswith(LANG_SUFFIX):
        return name[len(LANG_PREFIX) : -len(LANG_SUFFIX)]
    return None


def resolve_inputs(paths, lang=None):
    """Expand files and directories into a list of string tables, newest name order."""
    found = []
    for raw in paths:
        p = Path(raw)
        if p.is_dir():
            found += sorted(p.glob(LANG_PREFIX + "*" + LANG_SUFFIX))
        elif p.exists():
            found.append(p)
        else:
            raise GuiStringsError("no such file or directory: %s" % p)
    if lang:
        want = lang.upper()
        found = [f for f in found if (language_of(f) or "").upper() == want]
        if not found:
            raise GuiStringsError(
                "no %s*%s file for language %s" % (LANG_PREFIX, LANG_SUFFIX, lang)
            )
    if not found:
        raise GuiStringsError("nothing to read")
    return found


def escape(text):
    """Make a string safe to show one-entry-per-line; `--raw` prints the real thing."""
    out = []
    for ch in text:
        if ch == "\\":
            out.append("\\\\")
        elif ch == "\n":
            out.append("\\n")
        elif ch == "\r":
            out.append("\\r")
        elif ch == "\t":
            out.append("\\t")
        elif ord(ch) < 0x20 or 0xD800 <= ord(ch) <= 0xDFFF:
            out.append("\\u%04x" % ord(ch))
        else:
            out.append(ch)
    return "".join(out)


def load_overrides(path, sets=None):
    """Edits from a JSON file, plus any `--set id=text`. Ids may be ints or decimal strings."""
    raw = {}
    if path:
        try:
            doc = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise GuiStringsError("could not read overrides from %s: %s" % (path, exc)) from exc
        if isinstance(doc, dict) and isinstance(doc.get("strings"), dict):
            doc = doc["strings"]
        if not isinstance(doc, dict):
            raise GuiStringsError("%s must hold an object of id -> string" % path)
        raw.update(doc)
    for item in sets or []:
        if "=" not in item:
            raise GuiStringsError("--set wants id=text, got %r" % item)
        key, _, value = item.partition("=")
        raw[key.strip()] = value
    overrides = {}
    for key, value in raw.items():
        if not isinstance(value, str):
            raise GuiStringsError(
                "override for id %r is %s, not a string" % (key, type(value).__name__)
            )
        try:
            overrides[int(str(key).strip())] = value
        except ValueError:
            raise GuiStringsError("id %r is not a number" % key) from None
    return overrides


def apply_overrides(entries, overrides, pad=False, truncate=False, allow_new_id=False):
    """Return (new entries, notes).

    With `pad`, a replacement keeps its original slot: it is NUL-padded up to the old byte
    length, so the file's size and every offset in it are unchanged. That is the conservative
    edit — see docs/GUI_STRINGS.md on what the padding costs.
    """
    known = {e.id for e in entries}
    unknown = sorted(set(overrides) - known)
    if unknown and not allow_new_id:
        raise GuiStringsError(
            "no such string id: %s (--allow-new-id adds it; the entry count then changes)"
            % ", ".join(str(i) for i in unknown)
        )
    notes = []
    out = []
    for e in entries:
        if e.id not in overrides:
            out.append(Entry(e.id, e.offset, e.length, e.text))
            continue
        text = overrides[e.id]
        raw = text.encode(ENCODING, "surrogatepass")
        if not pad:
            out.append(Entry(e.id, e.offset, len(raw), text))
            continue
        if len(raw) > e.length:
            if not truncate:
                raise GuiStringsError(
                    "id %d: the replacement is %d bytes and the slot is %d; shorten it, or "
                    "pass --pad --truncate to clip it" % (e.id, len(raw), e.length)
                )
            raw = raw[: e.length]
            text = raw.decode(ENCODING, "surrogatepass")
            notes.append("id %d: clipped to the original %d bytes" % (e.id, e.length))
        units = e.length - len(raw)
        if units:
            text += "\x00" * (units // 2)
        out.append(Entry(e.id, e.offset, e.length, text))
    for sid in unknown:
        # Appended, not inserted: the loader walks the directory into a hash, so the order it
        # arrives in does not matter, and appending leaves every existing offset alone.
        out.append(Entry(sid, 0, 0, overrides[sid]))
    return out, notes


# ---------------------------------------------------------------- commands


def cmd_info(args):
    for path in resolve_inputs(args.files, args.lang):
        data = Path(path).read_bytes()
        f = StringsFile.parse(data)
        lang = language_of(path) or "(unrecognised name)"
        checks = f.issues()
        if args.json:
            print(
                json.dumps(
                    {
                        "file": str(path),
                        "language": lang,
                        "size": len(data),
                        "header": {
                            "size": f.size_field,
                            "count": f.count_field,
                            "strings_base": f.base_field,
                            "reserved": f.reserved,
                        },
                        "records": len(f.entries),
                        "directory_bytes": len(f.entries) * RECORD_SIZE,
                        "string_bytes": sum(e.length for e in f.entries),
                        "id_min": min((e.id for e in f.entries), default=None),
                        "id_max": max((e.id for e in f.entries), default=None),
                        "missing_ids": max((e.id for e in f.entries), default=-1)
                        + 1
                        - len(f.entries),
                        "checks": {d: ok for d, ok in checks},
                    },
                    indent=2,
                    ensure_ascii=False,
                )
            )
            continue
        print("%s" % path)
        print("  language    %s" % lang)
        print("  size        %d bytes (header says %d)" % (len(data), f.size_field))
        print(
            "  header      size=%d count=%d strings_base=%d (0x%x) reserved=%d"
            % (f.size_field, f.count_field, f.base_field, f.base_field, f.reserved)
        )
        print(
            "  directory   %d records of %d bytes, 0x%x..0x%x"
            % (len(f.entries), RECORD_SIZE, HEADER_SIZE, HEADER_SIZE + len(f.entries) * RECORD_SIZE)
        )
        blob = sum(e.length for e in f.entries)
        print("  strings     %d bytes of UTF-16BE (%d code units)" % (blob, blob // 2))
        ids = [e.id for e in f.entries]
        print(
            "  ids         %s, %d records, %d id(s) absent from the space"
            % (
                "%d..%d" % (min(ids), max(ids)) if ids else "(none)",
                len(f.entries),
                max(ids) + 1 - len(f.entries) if ids else 0,
            )
        )
        print("  checks")
        for desc, ok in checks:
            print("    %-54s %s" % (desc, "yes" if ok else "NO"))
        print("  checksum    none of its own: the CRC32 of this file is a type-2 record in")
        print("              system_ctrl.bin, with the rest of the partition cascade")
        print()
    return 0


def cmd_dump(args):
    paths = resolve_inputs(args.files, args.lang)
    if args.ids:
        wanted = set(args.ids)
    else:
        wanted = None
    if args.json:
        if len(paths) == 1:
            f = StringsFile.load(paths[0])
            out = {str(e.id): e.text for e in f.entries if wanted is None or e.id in wanted}
        else:
            out = {}
            for path in paths:
                f = StringsFile.load(path)
                out[str(path)] = {
                    str(e.id): e.text for e in f.entries if wanted is None or e.id in wanted
                }
        print(json.dumps(out, indent=2, ensure_ascii=False))
        return 0
    for path in paths:
        f = StringsFile.load(path)
        lang = language_of(path) or "?"
        ids = [e.id for e in f.entries]
        print(
            "# %s [%s] — %d strings, UTF-16BE, ids %s"
            % (path, lang, len(f.entries), "%d..%d" % (min(ids), max(ids)) if ids else "(none)")
        )
        for e in f.entries:
            if wanted is not None and e.id not in wanted:
                continue
            print("%d\t%s" % (e.id, e.text if args.raw else escape(e.text)))
    return 0


def cmd_probe(args):
    ok = True
    reports = []
    for path in resolve_inputs(args.files, args.lang):
        data = Path(path).read_bytes()
        f = StringsFile.parse(data)
        rebuilt = f.to_bytes()
        same = rebuilt == data
        longest = max(f.entries, key=lambda e: e.length, default=None)
        empty_ids = [e.id for e in f.entries if e.length == 0]
        report = {
            "file": str(path),
            "size": len(data),
            "checks": {d: v for d, v in f.issues()},
            "encoding": {
                "utf16_be_strict_decode": _strict_ok(f),
                "nul_terminated": False,
                "bom": False,
                "strings_with_an_internal_nul": sum(1 for e in f.entries if "\x00" in e.text),
            },
            "limits": {
                "records": len(f.entries),
                "largest_id": max((e.id for e in f.entries), default=None),
                "longest_string_bytes": longest.length if longest else None,
                "longest_string_id": longest.id if longest else None,
                "longest_string_units": longest.length // 2 if longest else None,
                "empty_strings": len(empty_ids),
                "length_field_width": "u32 — the format itself sets no ceiling",
            },
            "internal_checksum": "none found",
            "round_trip": "byte-identical (%d bytes)" % len(rebuilt) if same else "DIFFERS",
        }
        if not same:
            ok = False
            report["round_trip_first_difference"] = _first_difference(data, rebuilt)
        reports.append(report)
        if args.json:
            continue
        _print_probe(report)
    if args.json:
        print(json.dumps(reports if len(reports) > 1 else reports[0], indent=2, ensure_ascii=False))
    return 0 if ok else 1


def _strict_ok(f):
    try:
        for e in f.entries:
            e.text.encode(ENCODING)
        return True
    except UnicodeEncodeError:
        return False


def _first_difference(a, b):
    for i in range(min(len(a), len(b))):
        if a[i] != b[i]:
            return "at 0x%x (input %02x, rebuilt %02x)" % (i, a[i], b[i])
    return "at 0x%x (length %d vs %d)" % (min(len(a), len(b)), len(a), len(b))


def _print_probe(r):
    print("%s" % r["file"])
    print("  structure")
    for desc, good in r["checks"].items():
        print("    %-54s %s" % (desc, "yes" if good else "NO"))
    enc = r["encoding"]
    print("  encoding")
    print(
        "    %-54s %s"
        % (
            "UTF-16BE, every string decodes strictly",
            "yes" if enc["utf16_be_strict_decode"] else "no",
        )
    )
    print(
        "    %-54s %s"
        % (
            "NUL-terminated",
            "no — the directory length is the only bound" if not enc["nul_terminated"] else "yes",
        )
    )
    print("    %-54s %s" % ("byte-order mark", "none" if not enc["bom"] else "present"))
    print(
        "    %-54s %d"
        % ("strings with a NUL inside their length", enc["strings_with_an_internal_nul"])
    )
    lim = r["limits"]
    print("  limits")
    print("    %-54s %d" % ("records", lim["records"]))
    print("    %-54s %s" % ("largest id", lim["largest_id"]))
    print(
        "    %-54s %d bytes / %d units (id %s)"
        % (
            "longest string",
            lim["longest_string_bytes"] or 0,
            lim["longest_string_units"] or 0,
            lim["longest_string_id"],
        )
    )
    print("    %-54s %d" % ("empty strings", lim["empty_strings"]))
    print("    %-54s %s" % ("length field", lim["length_field_width"]))
    print("  checksum")
    print("    %-54s %s" % ("internal checksum", r["internal_checksum"]))
    print("  round trip")
    print("    %-54s %s" % ("decode -> rebuild", r["round_trip"]))
    if "round_trip_first_difference" in r:
        print("    %-54s %s" % ("first difference", r["round_trip_first_difference"]))
    print()


def _build(args, base, out):
    f = StringsFile.load(base)
    overrides = load_overrides(args.overrides, args.set)
    if not overrides:
        # Still a rebuild: this is the no-edit round trip, and the byte comparison is the point.
        pass
    entries, notes = apply_overrides(
        f.entries,
        overrides,
        pad=args.pad,
        truncate=args.truncate,
        allow_new_id=args.allow_new_id,
    )
    data = f.to_bytes(entries)
    Path(out).write_bytes(data)
    changed = [e.id for e in entries if e.id in overrides]
    print(
        "%s -> %s: %d string(s) edited, %d -> %d bytes%s"
        % (
            base,
            out,
            len(changed),
            Path(base).stat().st_size,
            len(data),
            ", padded" if args.pad else "",
        )
    )
    for note in notes:
        print("  note: %s" % note)
    return 0


def cmd_build(args):
    return _build(args, args.base, args.out)


def cmd_patch(args):
    if args.in_place and args.out:
        raise GuiStringsError("--in-place and --out are alternatives")
    out = args.out or (args.file if args.in_place else None)
    if out is None:
        raise GuiStringsError("give --out FILE, or --in-place to rewrite the file you read")
    if Path(out) == Path(args.file) and not args.in_place:
        raise GuiStringsError("refusing to overwrite %s without --in-place" % args.file)
    return _build(args, args.file, out)


def cmd_diff(args):
    a = StringsFile.load(args.old)
    b = StringsFile.load(args.new)
    left = {e.id: e.text for e in a.entries}
    right = {e.id: e.text for e in b.entries}
    only_a = sorted(set(left) - set(right))
    only_b = sorted(set(right) - set(left))
    changed = sorted(i for i in set(left) & set(right) if left[i] != right[i])
    if args.json:
        print(
            json.dumps(
                {
                    "old": str(args.old),
                    "new": str(args.new),
                    "size": [Path(args.old).stat().st_size, Path(args.new).stat().st_size],
                    "count": [len(a.entries), len(b.entries)],
                    "only_in_old": only_a,
                    "only_in_new": only_b,
                    "changed": {str(i): {"old": left[i], "new": right[i]} for i in changed},
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0
    print("%s -> %s" % (args.old, args.new))
    print(
        "  size   %d -> %d (%+d)"
        % (
            Path(args.old).stat().st_size,
            Path(args.new).stat().st_size,
            Path(args.new).stat().st_size - Path(args.old).stat().st_size,
        )
    )
    print("  count  %d -> %d" % (len(a.entries), len(b.entries)))
    print(
        "  only in old: %d%s"
        % (len(only_a), " " + ", ".join(map(str, only_a[:20])) if only_a else "")
    )
    print(
        "  only in new: %d%s"
        % (len(only_b), " " + ", ".join(map(str, only_b[:20])) if only_b else "")
    )
    print("  changed:     %d" % len(changed))
    shown = changed if args.limit is None else changed[: args.limit]
    for i in shown:
        print("    id %d: %s -> %s" % (i, escape(left[i]), escape(right[i])))
    if len(shown) < len(changed):
        print("    ... %d more (--limit 0 for all)" % (len(changed) - len(shown)))
    return 0


def _add_edit_args(p):
    p.add_argument("--overrides", help="a JSON object of id -> string, as `dump --json` writes")
    p.add_argument(
        "--set",
        action="append",
        metavar="ID=TEXT",
        help="one override on the command line; repeatable",
    )
    p.add_argument(
        "--pad",
        action="store_true",
        help="keep each edited string's original byte length (NUL-padded), so no offset moves",
    )
    p.add_argument(
        "--truncate",
        action="store_true",
        help="with --pad, clip a replacement that is longer than the slot instead of refusing",
    )
    p.add_argument(
        "--allow-new-id",
        action="store_true",
        help="accept an id that is not in the file; it is appended and the count changes",
    )


def main(argv=None):
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("info", help="the header fields and a structural check")
    p.add_argument("files", nargs="+", help="a .xml.bin string table, or a gui_texts directory")
    p.add_argument("--lang", help="with a directory, only this language code (GB, FR, ...)")
    p.add_argument("--json", action="store_true", help="machine-readable output")
    p.set_defaults(fn=cmd_info)

    p = sub.add_parser("dump", help="print the id -> string table")
    p.add_argument("files", nargs="+", help="a .xml.bin string table, or a gui_texts directory")
    p.add_argument("--lang", help="with a directory, only this language code (GB, FR, ...)")
    p.add_argument(
        "--json", action="store_true", help="JSON object of id -> string, usable as --overrides"
    )
    p.add_argument("--ids", type=int, nargs="+", help="only these ids")
    p.add_argument("--raw", action="store_true", help="do not escape control characters")
    p.set_defaults(fn=cmd_dump)

    p = sub.add_parser("probe", help="show the format's own limits and prove the round trip")
    p.add_argument("files", nargs="+", help="a .xml.bin string table, or a gui_texts directory")
    p.add_argument("--lang", help="with a directory, only this language code (GB, FR, ...)")
    p.add_argument("--json", action="store_true", help="machine-readable output")
    p.set_defaults(fn=cmd_probe)

    p = sub.add_parser(
        "build", help="rebuild a file from a base plus edits (no edits = a byte-for-byte copy)"
    )
    p.add_argument("--base", required=True, help="the file to rebuild from")
    p.add_argument("--out", required=True, help="where to write the rebuilt file")
    _add_edit_args(p)
    p.set_defaults(fn=cmd_build)

    p = sub.add_parser("patch", help="apply edits to a file (build with the base filled in)")
    p.add_argument("file", help="the .xml.bin file to patch")
    p.add_argument("--out", help="where to write the result")
    p.add_argument("--in-place", action="store_true", help="rewrite the input file")
    _add_edit_args(p)
    p.set_defaults(fn=cmd_patch)

    p = sub.add_parser("diff", help="compare two string tables")
    p.add_argument("old")
    p.add_argument("new")
    p.add_argument("--json", action="store_true", help="machine-readable output")
    p.add_argument(
        "--limit", type=int, default=20, help="how many changed entries to show (0 for all)"
    )
    p.set_defaults(fn=cmd_diff)

    args = ap.parse_args(argv)
    if getattr(args, "limit", None) == 0:
        args.limit = None
    try:
        return args.fn(args)
    except GuiStringsError as exc:
        print("guistrings: %s" % exc, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
