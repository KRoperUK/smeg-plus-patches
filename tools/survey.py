#!/usr/bin/env python3

# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///

"""Inventory every function in a SMEG+ application image: where it sits, what reaches it.

One pass over the whole image produces, for each code symbol in the map:

  * its family (subsystem, from the class-name prefix) and size in instructions,
  * direct callers (`bl`),
  * address-materialisation sites (`lis rX,hi` + `addi`/`ori rX,rX,lo`) that produce its
    address - how this firmware makes most of its calls, via `mtctr`/`bctrl`, and what
    `callers.py` cannot see,
  * pointers to it stored in data (vtables, callback tables), and
  * the strings it materialises the address of - usually trace or log text naming what the
    function does,
  * the vtable slots it occupies, and
  * the globals it reads and writes (`lis rX,hi` + a load or store at `lo(rX)`).

The output is local analysis, written under `--out` and never into this repository: it is
derived from the vendor's symbol map, which AGENTS.md keeps out of the tree.

  functions.tsv   one row per function
  families.tsv    one row per family: count, instructions, share of the image
  unreached.tsv   functions with no caller, reference or pointer found - dead code, or
                  reached some way this scan does not model (computed branch tables)
  vtables.tsv     one row per vtable slot: class, slot offset, function
  virtual_calls.tsv  call sites of the form `lwz vptr,0(obj); lwz rZ,off(vptr); mtctr rZ;
                  bctrl`, with the slot offset they call. The receiver's class is not inferred,
                  so a site is not attributed to one function
  globals.tsv     data symbols with the functions that read and write them

The reference counts are lower bounds. An address built with `addis`+`lwz`, or computed at
run time, is not counted. A function with no references found is not proved unreachable.

usage:
    python3 tools/survey.py NAV.img abs_symbols_base.txt.gz --out ~/smeg-survey
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
VTABLE_PREFIX = "_ZTV"
VTABLE_HEADER = 8  # offset-to-top and typeinfo (0: no RTTI) before the first slot
LOAD_OPS = {32, 33, 34, 35, 40, 41, 42, 43}  # lwz lwzu lbz lbzu lhz lhzu lha lhau
STORE_OPS = {36, 37, 38, 39, 44, 45}  # stw stwu stb stbu sth sthu
MTCTR_MASK, MTCTR = 0xFC1FFFFF, 0x7C0903A6
BCTRL = 0x4E800421
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


# volatile registers under the PowerPC EABI: a call may leave anything in them
VOLATILE = (0, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12)
# D-form opcodes whose result lands in bits 21-25 (loads, mulli, subfic, addic, addis)
WRITES_RT = {7, 8, 12, 13, 15, 32, 33, 34, 35, 40, 41, 42, 43, 46}
# D/M-form opcodes whose result lands in bits 16-20 (logical immediates, rotates)
WRITES_RA = {20, 21, 23, 25, 26, 27, 28, 29}


def clobber_volatile(lis):
    for r in VOLATILE:
        lis.pop(r, None)


def written(w, op):
    """GPRs an instruction may overwrite, erring towards too many.

    Forgetting a `lis` too early only loses a reference; keeping one past an overwrite
    invents a reference that is not there, which is the worse error for an inventory.
    Opcode 31 is not decoded further, so both of its register fields count as written.
    """
    if op in WRITES_RT:
        return [(w >> 21) & 31]
    if op in WRITES_RA:
        return [(w >> 16) & 31]
    if op == 31:
        return [(w >> 21) & 31, (w >> 16) & 31]
    return []


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

    callers = collections.defaultdict(set)
    materialised = collections.defaultdict(set)
    pointers = collections.defaultdict(int)
    callees = collections.defaultdict(set)
    strings = collections.defaultdict(list)
    readers = collections.defaultdict(set)
    writers = collections.defaultdict(set)
    virtual_calls = []  # (caller, site, slot offset)
    # globals include BSS, which lies past the end of the image and is not in the file
    all_data = sorted(a for a in typed if a >= base and typed[a][0] not in CODE_TYPES)
    data_ends = {
        a: all_data[i + 1] if i + 1 < len(all_data) else a + 4 for i, a in enumerate(all_data)
    }
    data_top = data_ends[all_data[-1]] if all_data else top

    def data_symbol(addr):
        k = bisect.bisect_right(all_data, addr) - 1
        if k >= 0 and addr < data_ends[all_data[k]]:
            return all_data[k]
        return None

    code = []
    for f in funcs:
        code.append(((f - base) // 4, (ends[f] - base) // 4, f))
    in_code = bytearray(n)
    for lo, hi, _ in code:
        in_code[lo:hi] = b"\x01" * (hi - lo)

    for lo, hi, f in code:
        lis = {}
        vptr = set()  # registers holding an object's vtable pointer
        slot = {}  # register -> slot offset loaded through a vtable pointer
        ctr_slot = None
        for i in range(lo, hi):
            w = words[i]
            op = w >> 26
            if w == BCTRL and ctr_slot is not None:
                virtual_calls.append((f, base + i * 4, ctr_slot))
            if w & MTCTR_MASK == MTCTR:
                ctr_slot = slot.get((w >> 21) & 31)
            elif op == 19 and w & 1:
                ctr_slot = None
            if op in LOAD_OPS or op in STORE_OPS:
                rd, ra, d = (w >> 21) & 31, (w >> 16) & 31, w & 0xFFFF
                # decided before any register state changes: `lwz r9,4(r9)` reads the vtable
                # pointer in r9 and overwrites it with the slot in the same instruction
                is_vptr = op == 32 and d == 0
                is_slot = op == 32 and ra in vptr and not d & 0x8000 and not is_vptr
                hit = lis.get(ra)
                if hit and ra and i - hit[1] <= LIS_WINDOW:
                    addr = ((hit[0] << 16) + (d - 0x10000 if d & 0x8000 else d)) & 0xFFFFFFFF
                    g = data_symbol(addr) if base <= addr < data_top else None
                    if g is not None:
                        (readers if op in LOAD_OPS else writers)[g].add(f)
                if op & 1:  # the update forms (lwzu, stwu, ...) also write the base register
                    lis.pop(ra, None)
                    vptr.discard(ra)
                    slot.pop(ra, None)
                if op in LOAD_OPS:
                    lis.pop(rd, None)
                    vptr.discard(rd)
                    slot.pop(rd, None)
                    if is_vptr:
                        vptr.add(rd)
                    elif is_slot:
                        slot[rd] = d
                continue
            if op == 18 and w & 3 == 1:  # bl
                off = w & 0x03FFFFFC
                if off & 0x02000000:
                    off -= 0x04000000
                t = base + i * 4 + off
                if t in fset:
                    callers[t].add(f)
                    callees[f].add(t)
                clobber_volatile(lis)
            elif op == 19 and w & 1:  # bctrl / blrl
                clobber_volatile(lis)
                vptr.clear()
                slot.clear()
            elif op == 15 and (w >> 16) & 31 == 0:  # lis rD,hi
                lis[(w >> 21) & 31] = (w & 0xFFFF, i)
            elif op in (14, 24):  # addi rD,rA,lo / ori rA,rS,lo
                src, dst = (
                    ((w >> 16) & 31, (w >> 21) & 31)
                    if op == 14
                    else ((w >> 21) & 31, (w >> 16) & 31)
                )
                hit = lis.get(src)
                lis.pop(dst, None)
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
            else:
                for r in written(w, op):
                    lis.pop(r, None)
                    vptr.discard(r)
                    slot.pop(r, None)

    # vtables: the slots after the header, for as long as they point at functions
    vtables = []
    vslots = collections.Counter()
    for a in addrs:
        if not typed[a][1].startswith(VTABLE_PREFIX) or typed[a][0] in CODE_TYPES:
            continue
        k = (a + VTABLE_HEADER - base) // 4
        stop = (ends[a] - base) // 4
        while k < stop and words[k] in fset:
            vtables.append((a, base + k * 4 - a - VTABLE_HEADER, words[k]))
            vslots[words[k]] += 1
            k += 1

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
                "vslots": vslots[f],
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
    extras = {
        "vtables": [(a, typed[a][1], off, fn, typed[fn][1]) for a, off, fn in vtables],
        "virtual_calls": [(c, site, off, typed[c][1]) for c, site, off in virtual_calls],
        "globals": [
            (
                g,
                typed[g][1],
                sorted(typed[f][1] for f in readers[g]),
                sorted(typed[f][1] for f in writers[g]),
            )
            for g in sorted(set(readers) | set(writers))
        ],
    }
    return rows, fams, extras


def clean(s):
    return s.replace("\t", " ").replace("\n", "\\n")


def write(out, rows, fams, extras=None):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "functions.tsv", "w") as fh:
        fh.write(
            "addr\tinsns\tfamily\tcallers\tmaterialised\tpointers\tcallees\tname\tstrings\tvslots\n"
        )
        for r in rows:
            fh.write(
                "%08x\t%d\t%s\t%d\t%d\t%d\t%d\t%s\t%s\t%d\n"
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
                    r["vslots"],
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
    if extras is None:
        return
    with open(out / "vtables.tsv", "w") as fh:
        fh.write("vtable\tclass_symbol\tslot_offset\tfunction\tname\n")
        for vt, vname, off, fn, fname in extras["vtables"]:
            fh.write("%08x\t%s\t%d\t%08x\t%s\n" % (vt, vname, off, fn, fname))
    with open(out / "virtual_calls.tsv", "w") as fh:
        fh.write("site\tslot_offset\tcaller\n")
        for caller, site, off, cname in extras["virtual_calls"]:
            fh.write("%08x\t%d\t%s\n" % (site, off, cname))
    with open(out / "globals.tsv", "w") as fh:
        fh.write("addr\tsymbol\treaders\twriters\treader_names\twriter_names\n")
        for g, gname, rd, wr in extras["globals"]:
            fh.write(
                "%08x\t%s\t%d\t%d\t%s\t%s\n"
                % (g, gname, len(rd), len(wr), " ".join(rd[:10]), " ".join(wr[:10]))
            )


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("image", help="f_BigQuick.bin or an already-inflated image")
    ap.add_argument("symbols", help="abs_symbols_base.txt, or the .gz as SPYSTORE copies it")
    ap.add_argument("--out", required=True, help="directory for the TSV files")
    ap.add_argument("--base", default="0x01000000")
    args = ap.parse_args()

    img = load_image(args.image)
    typed = load_typed_symbols(args.symbols)
    rows, fams, extras = survey(img, typed, int(args.base, 16))
    if not rows:
        sys.exit("no code symbols fall inside the image - wrong map or --base?")
    write(args.out, rows, fams, extras)

    insns = sum(r["insns"] for r in rows)
    reached = sum(1 for r in rows if r["callers"] or r["materialised"] or r["pointers"])
    print("%d functions, %d instructions, %d families" % (len(rows), insns, len(fams)))
    print(
        "%d with at least one caller, reference or pointer; %d with none found"
        % (reached, len(rows) - reached)
    )
    print(
        "%d vtable slots, %d virtual call sites, %d globals referenced"
        % (len(extras["vtables"]), len(extras["virtual_calls"]), len(extras["globals"]))
    )
    for f in fams[:15]:
        print(
            "  %-24s %6d fn %9d insns %5.1f%%  %s"
            % (f["family"], f["functions"], f["insns"], 100 * f["share"], f["third_party"])
        )
    print("written to %s" % args.out)


if __name__ == "__main__":
    main()
