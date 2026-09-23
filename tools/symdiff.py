#!/usr/bin/env python3

# /// script
# requires-python = ">=3.10"
# dependencies = []

"""Diff two firmware releases by symbol, so a patch set can be carried across.

Extending the patches to another SMEG release currently means redoing the analysis by hand.
Most of it does not need redoing. The 5.43 and 5.42 NAV images are the same code *displaced by
a constant 152 bytes*, which a naive byte comparison reports as ~80% different — the shift,
not new code. This separates the three cases that matter:

  * **moved, same bytes** — the patch address is mechanical: add the displacement
  * **moved, different bytes** — the address carries over but the patch needs re-deriving
  * **gone or renamed** — nothing to carry

and it reports the displacement rather than making you find it. Point `--patch-addr` at a
site in A and it says whether that site survives into B, and where.

It heeds the rule in `AGENTS.md` either way: a derived address is a *candidate*. Nothing here
patches anything, and a candidate address without the `expect` bytes to back it is not safe to
apply.

usage:
    python3 tools/symdiff.py --a old.bin old_symbols.txt --b new.bin new_symbols.txt
    python3 tools/symdiff.py --a old.bin old_symbols.txt --b new.bin new_symbols.txt \\
        --patch-addr 0x02247858
"""

import argparse
import collections
import json
import sys
from pathlib import Path


def load_symbols(path):
    """`<hex addr> <type> <name>`, tolerating header and section lines.

    Same parsing as ppcdis/xref/callers, deliberately: a symbol map that one tool accepts and
    another does not would be a trap.
    """
    syms = {}
    with open(path, "r", errors="replace") as fh:
        for line in fh:
            p = line.split()
            if len(p) >= 3:
                try:
                    syms.setdefault(int(p[0], 16), p[2])
                except ValueError:
                    continue
    return syms


def extents(syms, image_len, base):
    """name -> (start, size), where size is up to the next symbol in address order.

    Symbol maps do not carry sizes, so the next address is the only available estimate. It
    over-states the last symbol in a run, which is why nothing here depends on an exact size.
    """
    out = {}
    addrs = sorted(syms)
    for i, addr in enumerate(addrs):
        nxt = addrs[i + 1] if i + 1 < len(addrs) else image_len + base
        out[syms[addr]] = (addr, max(0, nxt - addr))
    return out


def slice_at(image, base, addr, size):
    off = addr - base
    if off < 0 or off >= len(image):
        return None
    return image[off : off + size]


def diff(img_a, syms_a, base_a, img_b, syms_b, base_b, patch_addr=None):
    """The comparison, returning a dict. Pure, so the tests need no real firmware."""
    ext_a = extents(syms_a, len(img_a), base_a)
    ext_b = extents(syms_b, len(img_b), base_b)

    only_a = sorted(set(ext_a) - set(ext_b))
    only_b = sorted(set(ext_b) - set(ext_a))
    common = sorted(set(ext_a) & set(ext_b))

    moved = []
    same_bytes = []
    changed = []
    for name in common:
        a_addr, a_size = ext_a[name]
        b_addr, b_size = ext_b[name]
        a_bytes = slice_at(img_a, base_a, a_addr, a_size)
        b_bytes = slice_at(img_b, base_b, b_addr, b_size)
        rec = {
            "name": name,
            "a_addr": a_addr,
            "b_addr": b_addr,
            "delta": b_addr - a_addr,
            "a_size": a_size,
            "b_size": b_size,
        }
        if a_addr != b_addr:
            moved.append(rec)
        if a_bytes is not None and b_bytes is not None and a_bytes == b_bytes:
            same_bytes.append(rec)
        else:
            changed.append(rec)

    # the modal displacement: if the images are one image shifted, this is it, and every
    # patch address follows from it without any re-analysis
    shifts = collections.Counter(r["delta"] for r in moved)
    top = shifts.most_common(1)
    shift = top[0][0] if top else 0
    agreeing = top[0][1] if top else 0

    out = {
        "a": {"symbols": len(ext_a), "image": len(img_a)},
        "b": {"symbols": len(ext_b), "image": len(img_b)},
        "only_in_a": only_a,
        "only_in_b": only_b,
        "moved": len(moved),
        "same_bytes": len(same_bytes),
        "changed": len(changed),
        "shift": shift,
        "shift_agreement": agreeing,
        "moved_total": len(moved),
        "reusable": [
            {"name": r["name"], "b_addr": r["b_addr"], "delta": r["delta"]} for r in same_bytes
        ],
        "changed_names": sorted(r["name"] for r in changed),
    }

    if patch_addr is not None:
        out["patch"] = locate_patch(ext_a, ext_b, img_a, img_b, base_a, base_b, patch_addr, shift)
    return out


def locate_patch(ext_a, ext_b, img_a, img_b, base_a, base_b, addr, shift):
    """Whether a site in A survives into B, and where. The practical question."""
    owner = None
    for name, (start, size) in ext_a.items():
        if start <= addr < start + size:
            if owner is None or start > ext_a[owner][0]:
                owner = name
    want = slice_at(img_a, base_a, addr, 16)
    res = {
        "addr": addr,
        "function": owner,
        "b_addr_by_shift": addr + shift,
        "same_bytes_at_shift": None,
        "same_bytes_in_function": None,
        "b_function_addr": ext_b[owner][0] if owner in ext_b else None,
    }
    if want:
        at = slice_at(img_b, base_b, addr + shift, len(want))
        res["same_bytes_at_shift"] = bool(at == want)
    if owner and owner in ext_b:
        a_off = addr - ext_a[owner][0]
        b_start = ext_b[owner][0]
        res["b_function_addr"] = b_start
        res["b_site"] = b_start + a_off
        res["same_bytes_in_function"] = _fn_equal(
            ext_a[owner], ext_b[owner], img_a, img_b, base_a, base_b
        )
    return res


def _fn_equal(a_ext, b_ext, img_a, img_b, base_a, base_b):
    size = min(a_ext[1], b_ext[1])
    if size <= 0:
        return None
    x = slice_at(img_a, base_a, a_ext[0], size)
    y = slice_at(img_b, base_b, b_ext[0], size)
    return None if x is None or y is None else x == y


def report(d, as_json):
    if as_json:
        print(json.dumps(d, indent=2))
        return
    print("A: %d symbols, %d bytes" % (d["a"]["symbols"], d["a"]["image"]))
    print("B: %d symbols, %d bytes" % (d["b"]["symbols"], d["b"]["image"]))
    print()
    print(
        "  shift        %+d  (agreed by %d of %d moved symbols)"
        % (d["shift"], d["shift_agreement"], d["moved_total"])
    )
    print("  shared       %d" % (d["same_bytes"] + d["changed"]))
    print("    identical  %d   a patch here moves by the shift alone" % d["same_bytes"])
    print("    changed    %d   address carries over, bytes need re-deriving" % d["changed"])
    print("  only in A    %d" % len(d["only_in_a"]))
    print("  only in B    %d" % len(d["only_in_b"]))
    if d["changed_names"][:8]:
        print("  changed e.g. %s" % ", ".join(d["changed_names"][:8]))
    p = d.get("patch")
    if p:
        print()
        print("  patch site   %#x  in %s" % (p["addr"], p["function"] or "<no symbol>"))
        print("    candidate B address   %#x  (A %+d)" % (p["b_addr_by_shift"], d["shift"]))
        if p.get("b_site") is not None:
            print("    same offset in B fn   %#x" % p["b_site"])
        print("    identical bytes there %s" % p["same_bytes_at_shift"])
        print("    whole function equal  %s" % p["same_bytes_in_function"])
        print()
        print("  A candidate is not a patch. Confirm the expect bytes before applying.")


def main(argv=None):
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument(
        "--a", nargs=2, required=True, metavar=("IMAGE", "SYMBOLS"), help="older release"
    )
    ap.add_argument(
        "--b", nargs=2, required=True, metavar=("IMAGE", "SYMBOLS"), help="newer release"
    )
    ap.add_argument("--base", default="0x01000000", help="load address of the images")
    ap.add_argument("--patch-addr", default=None, help="a patch site in A to locate in B")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    base = int(args.base, 16)
    img_a = Path(args.a[0]).read_bytes()
    img_b = Path(args.b[0]).read_bytes()
    syms_a = load_symbols(args.a[1])
    syms_b = load_symbols(args.b[1])
    if not syms_a or not syms_b:
        raise SystemExit("one of the symbol maps is empty or unreadable")

    addr = int(args.patch_addr, 16) if args.patch_addr else None
    report(diff(img_a, syms_a, base, img_b, syms_b, base, addr), args.json)
    return 0


if __name__ == "__main__":
    sys.exit(main())
