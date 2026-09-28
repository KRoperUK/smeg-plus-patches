#!/usr/bin/env python3

# /// script
# requires-python = ">=3.10"
# dependencies = []

"""Inventory every function in a SMEG+ application image: where it sits, what reaches it.

One pass over the whole image produces, for each code symbol in the map:

  * its family (subsystem, from the class-name prefix) and size in instructions,
  * direct callers (`bl`),
  * address-materialisation sites (`lis rX,hi` + `addi`/`ori rX,rX,lo`) that produce its
    address - how this firmware makes most of its calls, via `mtctr`/`bctrl`, and what
    `callers.py` cannot see,
  * pointers to it stored in data (vtables, callback tables), and
  * the strings it materialises the address of - usually trace or log text naming what the
    function does.

The output is local analysis, written under `--out` and never into this repository: it is
derived from the vendor's symbol map, which AGENTS.md keeps out of the tree.

  functions.tsv   one row per function
  families.tsv    one row per family: count, instructions, share of the image
  unreached.tsv   functions with no caller, reference or pointer found - dead code, or
                  reached some way this scan does not model (computed branch tables)

The reference counts are lower bounds. An address built with `addis`+`lwz`, or computed at
run time, is not counted. A function with no references found is not proved unreachable.

usage:
    python3 tools/survey.py NAV.img abs_symbols_base.txt --out ~/smeg-survey
    python3 tools/survey.py NAV/AppBin/f_BigQuick.bin abs_symbols_base.txt --out ~/smeg-survey
"""

import argparse
import bisect
import collections
import os
import re
import shutil
import struct
import subprocess
import sys
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from appimage import DEFAULT_BASE, inflate  # noqa: E402
from symbols import load_typed_symbols  # noqa: E402

CODE_TYPES = {"T", "t", "W", "w"}
# how far back an `addi`/`ori` may look for its `lis`; the compiler schedules them apart
LIS_WINDOW = 30
# prefixes whose names identify a library; labels are inferred from the names alone
THIRD_PARTY = {
    "Qt": "Qt",
    "std": "C++ standard library",
    "V3D": "3D map renderer",
    "TagLib": "TagLib (media tags)",
    "sqlite": "SQLite",
    "png": "libpng",
    "FT": "FreeType",
    "FTC": "FreeType",
    "TT": "FreeType",
    "jinit": "libjpeg",
    "jpeg": "libjpeg",
    "XML": "expat",
    "Xml": "expat",
    "HB": "HarfBuzz",
    "mxml": "Mini-XML",
    "SDP": "Bluetooth stack",
    "HCI": "Bluetooth stack",
    "RFCOMM": "Bluetooth stack",
    "L2CAP": "Bluetooth stack",
    "Arkamys": "Arkamys audio processing",
    "FLACDec": "FLAC decoder",
    "WMA": "WMA decoder",
}


def load_image(path):
    """The inflated image, from either an `f_BigQuick.bin` container or a raw image."""
    raw = Path(path).read_bytes()
    if len(raw) > 0x801 and raw[0x800] == 0x08:
        try:
            return inflate(raw)[1]
        except SystemExit:
            pass
    return raw


def demangle(names):
    """Demangled names via `c++filt` when it is on PATH; the mangled names otherwise."""
    tool = shutil.which("c++filt") or shutil.which("llvm-cxxfilt")
    if not tool:
        return list(names)
    r = subprocess.run([tool], input="\n".join(names), capture_output=True, text=True, check=True)
    out = r.stdout.splitlines()
    return out if len(out) == len(names) else list(names)


def family(name):
    """Subsystem label from a demangled name: the class prefix, or a free function's stem."""
    name = re.sub(r"^((non-)?virtual thunk to |guard variable for )", "", name)
    head = name.split("(")[0]
    if "::" in head:
        cls = re.sub(r"<.*", "", head.split("::")[0]).split()[-1]
        m = re.match(r"(C_[A-Z0-9]+_[A-Za-z0-9]+)", cls)
        if m:
            return m.group(1)
        if cls.startswith("com_MM_"):
            return "com_MM"
        if re.match(r"Q[A-Z]", cls):
            return "Qt"
        return cls
    m = re.match(r"_*([A-Za-z]+)", head.split()[-1] if head.split() else head)
    stem = m.group(1) if m else head
    if stem.startswith(("qt", "Q")):
        return "Qt"
    return stem if stem in THIRD_PARTY else "(free functions)"


def c_string(img, off, limit=120):
    """The printable NUL-terminated string at `off`, or None."""
    end = img.find(b"\x00", off, off + limit)
    if end - off < 4:
        return None
    s = img[off:end]
    if all(32 <= b < 127 or b in (9, 10) for b in s):
        return s.decode("ascii")
    return None


def survey(img, typed, base=DEFAULT_BASE):
    """Scan the image once; return (functions, families) as lists of dicts."""
    top = base + len(img)
    addrs = sorted(a for a in typed if base <= a < top)
    funcs = [a for a in addrs if typed[a][0] in CODE_TYPES]
    fset = set(funcs)
    ends = {a: (addrs[i + 1] if i + 1 < len(addrs) else top) for i, a in enumerate(addrs)}

    n = len(img) // 4
    words = struct.unpack(">%dI" % n, img[: n * 4])

    owner_idx = [(f - base) // 4 for f in funcs]

    def owner(i):
        k = bisect.bisect_right(owner_idx, i) - 1
        return funcs[k] if k >= 0 and i < (ends[funcs[k]] - base) // 4 else None

    callers = collections.defaultdict(set)
    materialised = collections.defaultdict(set)
    pointers = collections.defaultdict(int)
    callees = collections.defaultdict(set)
    strings = collections.defaultdict(list)

    code = []
    for f in funcs:
        code.append(((f - base) // 4, (ends[f] - base) // 4, f))
    in_code = bytearray(n)
    for lo, hi, _ in code:
        in_code[lo:hi] = b"\x01" * (hi - lo)

    for lo, hi, f in code:
        lis = {}
        for i in range(lo, hi):
            w = words[i]
            op = w >> 26
            if op == 18 and w & 3 == 1:  # bl
                off = w & 0x03FFFFFC
                if off & 0x02000000:
                    off -= 0x04000000
                t = base + i * 4 + off
                if t in fset:
                    callers[t].add(f)
                    callees[f].add(t)
            elif op == 15 and (w >> 16) & 31 == 0:  # lis rD,hi
                lis[(w >> 21) & 31] = (w & 0xFFFF, i)
            elif op in (14, 24):  # addi / ori rD,rA,lo
                ra = (w >> 16) & 31
                hit = lis.get(ra)
                if hit and i - hit[1] <= LIS_WINDOW:
                    hi16 = hit[0] << 16
                    lo16 = w & 0xFFFF
                    if op == 14 and lo16 & 0x8000:
                        val = (hi16 + lo16 - 0x10000) & 0xFFFFFFFF
                    else:
                        val = (hi16 | lo16) if op == 24 else (hi16 + lo16) & 0xFFFFFFFF
                    if val in fset:
                        materialised[val].add(f)
                        callees[f].add(val)
                    elif base <= val < top and not in_code[(val - base) // 4]:
                        s = c_string(img, val - base)
                        if s and s not in strings[f]:
                            strings[f].append(s)

    for i in range(n):
        if not in_code[i]:
            w = words[i]
            if w in fset:
                pointers[w] += 1

    raw_names = [typed[f][1] for f in funcs]
    names = demangle(raw_names)
    rows = []
    fam_count = collections.Counter()
    fam_insns = collections.Counter()
    for f, raw, name in zip(funcs, raw_names, names):
        fam = family(name)
        insns = (ends[f] - f) // 4
        fam_count[fam] += 1
        fam_insns[fam] += insns
        rows.append(
            {
                "addr": f,
                "insns": insns,
                "family": fam,
                "name": name,
                "mangled": raw,
                "callers": len(callers[f]),
                "materialised": len(materialised[f]),
                "pointers": pointers[f],
                "callees": len(callees[f]),
                "strings": strings[f],
            }
        )
    total = sum(fam_insns.values()) or 1
    fams = [
        {
            "family": k,
            "functions": fam_count[k],
            "insns": v,
            "share": v / total,
            "third_party": THIRD_PARTY.get(k, ""),
        }
        for k, v in fam_insns.most_common()
    ]
    return rows, fams


def clean(s):
    return s.replace("\t", " ").replace("\n", "\\n")


def write(out, rows, fams):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "functions.tsv", "w") as fh:
        fh.write("addr\tinsns\tfamily\tcallers\tmaterialised\tpointers\tcallees\tname\tstrings\n")
        for r in rows:
            fh.write(
                "%08x\t%d\t%s\t%d\t%d\t%d\t%d\t%s\t%s\n"
                % (
                    r["addr"],
                    r["insns"],
                    r["family"],
                    r["callers"],
                    r["materialised"],
                    r["pointers"],
                    r["callees"],
                    clean(r["name"]),
                    " | ".join(clean(s) for s in r["strings"][:5]),
                )
            )
    with open(out / "families.tsv", "w") as fh:
        fh.write("family\tfunctions\tinsns\tshare\tthird_party\n")
        for f in fams:
            fh.write(
                "%s\t%d\t%d\t%.4f\t%s\n"
                % (f["family"], f["functions"], f["insns"], f["share"], f["third_party"])
            )
    with open(out / "unreached.tsv", "w") as fh:
        fh.write("addr\tinsns\tfamily\tname\n")
        for r in rows:
            if not (r["callers"] or r["materialised"] or r["pointers"]):
                fh.write(
                    "%08x\t%d\t%s\t%s\n" % (r["addr"], r["insns"], r["family"], clean(r["name"]))
                )


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("image", help="f_BigQuick.bin or an already-inflated image")
    ap.add_argument("symbols", help="abs_symbols_base.txt (or the .gz, unpacked)")
    ap.add_argument("--out", required=True, help="directory for the TSV files")
    ap.add_argument("--base", default="0x01000000")
    args = ap.parse_args()

    img = load_image(args.image)
    typed = load_typed_symbols(args.symbols)
    rows, fams = survey(img, typed, int(args.base, 16))
    if not rows:
        sys.exit("no code symbols fall inside the image - wrong map or --base?")
    write(args.out, rows, fams)

    insns = sum(r["insns"] for r in rows)
    reached = sum(1 for r in rows if r["callers"] or r["materialised"] or r["pointers"])
    print("%d functions, %d instructions, %d families" % (len(rows), insns, len(fams)))
    print(
        "%d with at least one caller, reference or pointer; %d with none found"
        % (reached, len(rows) - reached)
    )
    for f in fams[:15]:
        print(
            "  %-24s %6d fn %9d insns %5.1f%%  %s"
            % (f["family"], f["functions"], f["insns"], 100 * f["share"], f["third_party"])
        )
    print("written to %s" % args.out)


if __name__ == "__main__":
    main()
