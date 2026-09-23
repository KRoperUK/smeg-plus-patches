#!/usr/bin/env python3

# /// script
# requires-python = ">=3.10"
# dependencies = []

"""Recover CRC parameters from (message, checksum) samples.

The cartography's checksums are real CRCs, but not published ones: `DESCRI.DAT` carries a
16-bit CRC per payload and `.inf` sidecars carry a 32-bit value, and neither matches any
standard parameterisation tried. Rather than keep guessing variants, this recovers the
parameters from samples.

**How it works.** A CRC with `init = 0` and `xorout = 0` is linear over the message bits:

    CRC0(a) ^ CRC0(b) == CRC0(a ^ b)          for equal-length a, b

and for two messages of the same length the `init`/`xorout` terms cancel:

    real(a) ^ real(b) == CRC0(a) ^ CRC0(b)

So a single pair of equal-length samples constrains the polynomial without knowing `init` or
`xorout`, and the search only has to range over the polynomial and the input reflection. The
output reflection does not affect it either — bit reversal is linear — so it is settled in the
second phase along with `init` and `xorout`.

**What it needs from you.** At least two samples that are the *same length*. That is the whole
constraint, and it is why the sample groups are reported when recovery fails: a set with no
repeated length cannot constrain anything.

No dependencies, so it runs with nothing installed.

usage:
    # a directory of files plus a `name crc` list
    python3 tools/crc_recover.py --samples samples.txt --root /path/to/package

    # or let it collect the pairs from a package's DESCRI.DAT files
    python3 tools/crc_recover.py --package /path/to/M49RG20-Q0123-2001
"""

import argparse
import collections
import sys
from pathlib import Path

KNOWN = {
    # (width, poly, init, refin, refout, xorout) -> name
    (16, 0x1021, 0xFFFF, False, False, 0x0000): "CRC-16/CCITT-FALSE",
    (16, 0x1021, 0x0000, False, False, 0x0000): "CRC-16/XMODEM",
    (16, 0x8005, 0x0000, True, True, 0x0000): "CRC-16/ARC",
    (16, 0x8005, 0xFFFF, True, True, 0x0000): "CRC-16/MODBUS",
    (16, 0x8005, 0xFFFF, True, True, 0xFFFF): "CRC-16/USB",
    (16, 0x1021, 0x0000, True, True, 0x0000): "CRC-16/KERMIT",
    (16, 0x1021, 0xFFFF, True, True, 0xFFFF): "CRC-16/X25",
    (16, 0x3D65, 0x0000, True, True, 0xFFFF): "CRC-16/DNP",
    (32, 0x04C11DB7, 0xFFFFFFFF, True, True, 0xFFFFFFFF): "CRC-32/ISO-HDLC",
    (32, 0x04C11DB7, 0xFFFFFFFF, True, True, 0x00000000): "CRC-32/JAMCRC",
    (32, 0x04C11DB7, 0xFFFFFFFF, False, False, 0xFFFFFFFF): "CRC-32/BZIP2",
    (32, 0x1EDC6F41, 0xFFFFFFFF, True, True, 0xFFFFFFFF): "CRC-32/ISO-HDLC/Castagnoli",
}


def rev(x, n):
    r = 0
    for i in range(n):
        if x & (1 << i):
            r |= 1 << (n - 1 - i)
    return r


def table_for(poly, width):
    """The standard MSB-first table: `table[i]` is eight steps from `i << (width-8)`.

    Deliberately independent of the reflection settings. Reflection is applied to the *input
    byte* at lookup time instead — building it into the table while indexing with the raw byte
    is not the same thing, and is silently wrong.
    """
    top = 1 << (width - 1)
    mask = (1 << width) - 1
    tbl = []
    for i in range(256):
        c = (i << (width - 8)) & mask
        for _ in range(8):
            c = ((c << 1) ^ poly) & mask if c & top else (c << 1) & mask
        tbl.append(c)
    return tbl


def crc0(data, table, width, refin=False):
    """CRC with init=0, xorout=0, using a prebuilt table."""
    mask = (1 << width) - 1
    shift = width - 8
    c = 0
    for b in data:
        if refin:
            b = rev(b, 8)
        c = ((c << 8) & mask) ^ table[((c >> shift) ^ b) & 0xFF]
    return c


def crc(data, poly, width, refin, refout, init, xorout):
    """A straightforward reference implementation, used to verify a candidate."""
    top = 1 << (width - 1)
    mask = (1 << width) - 1
    c = init
    for b in data:
        if refin:
            b = rev(b, 8)
        c ^= b << (width - 8)
        for _ in range(8):
            c = ((c << 1) ^ poly) & mask if c & top else (c << 1) & mask
    if refout:
        c = rev(c, width)
    return (c ^ xorout) & mask


def groups_by_length(samples):
    g = collections.defaultdict(list)
    for msg, want in samples:
        g[len(msg)].append((msg, want))
    return {L: v for L, v in g.items() if len(v) >= 2}


def _zero_run_basis(poly, width, refin, n):
    """`init` enters the CRC linearly, so the register after `n` zero bytes is linear in it.

    Returning the images of the `width` basis vectors lets the caller get `Z_n(init)` for any
    init with a handful of XORs, instead of running a whole CRC per candidate init — which is
    the difference between a second and three minutes over 65536 candidates.
    """
    zeros = bytes(n)
    return [crc(zeros, poly, width, refin, False, 1 << i, 0) for i in range(width)]


def _apply_basis(basis, init):
    v = 0
    i = 0
    while init:
        if init & 1:
            v ^= basis[i]
        init >>= 1
        i += 1
    return v


def recover(samples, width=16, polys=None):
    """Return a dict of parameters, or None. Needs at least one repeated message length.

    `polys` restricts the polynomial search, which exists so tests can exercise the whole
    path in milliseconds rather than scanning 65536 candidates. Left as None it scans them all.
    """
    groups = groups_by_length(samples)
    if not groups:
        return None
    mask = (1 << width) - 1
    # Every pair *within* a group, not just one per group. One pair only pins the polynomial
    # up to divisors — the differential `CRC0(a^b) == c1^c2` is satisfied by any divisor of
    # (a^b)·x^w + c1^c2 — so a single probe per length lets spurious polynomials through and
    # the search then reports whichever of them happens to fit.
    probes = []
    for v in groups.values():
        m0, c0 = v[0]
        for m, c in v[1:]:
            probes.append(((m0, c0), (m, c)))

    candidates = []
    for poly in range(1, mask + 1) if polys is None else polys:
        table = table_for(poly, width)
        for refin in (False, True):
            ok = True
            for (m1, c1), (m2, c2) in probes:
                want = c1 ^ c2
                got = crc0(m1, table, width, refin) ^ crc0(m2, table, width, refin)
                # Output reflection is a bit reversal of the final value, and a reversal does
                # NOT commute with the XOR differential — so the reversed differential has to
                # be accepted too. Refinement of *which* one applies is phase two's job.
                if got != want and rev(got, width) != want:
                    ok = False
                    break
            if ok:
                candidates.append((poly, refin))
    if not candidates:
        return None

    # phase two: settle refout, init and xorout against every sample
    for poly, refin in candidates:
        lengths = sorted({len(m) for m, _ in samples})
        cores = [(m, want, len(m), crc(m, poly, width, refin, False, 0, 0)) for m, want in samples]
        zero_basis = {n: _zero_run_basis(poly, width, refin, n) for n in lengths}
        for refout in (False, True):
            for init in range(mask + 1):
                xorout = None
                ok = True
                for _, want, n, core in cores:
                    z = _apply_basis(zero_basis[n], init)
                    if refout:
                        v = rev(core, width) ^ rev(z, width)
                    else:
                        v = core ^ z
                    if xorout is None:
                        xorout = v ^ want
                    elif (v ^ want) != xorout:
                        ok = False
                        break
                if ok:
                    return {
                        "width": width,
                        "poly": poly,
                        "init": init,
                        "refin": refin,
                        "refout": refout,
                        "xorout": xorout,
                        "name": canonical_name(samples, width, poly, refin, refout)
                        or "non-standard",
                    }
    return None


def canonical_name(samples, width, poly, refin, refout):
    """The published name for this polynomial/reflection, if the canonical form also fits.

    `init` and `xorout` are NOT uniquely recoverable: a CRC admits a family of equivalent
    parameterisations that agree at every message length. `CRC-16/MODBUS` is recovered as
    `init=0x7ffc, xorout=0xc001`, which is exactly equivalent to its published
    `init=0xffff, xorout=0x0000` — so it is worth checking whether the published values
    reproduce the samples before calling a result non-standard. The polynomial, input
    reflection and output reflection *are* uniquely determined.
    """
    for (w, p, i, ri, ro, x), name in KNOWN.items():
        if (w, p, ri, ro) != (width, poly, refin, refout):
            continue
        if all(crc(m, p, w, ri, ro, i, x) == want for m, want in samples):
            return name
    return None


# ---------------------------------------------------------------- sample collection


def samples_from_package(root):
    """Every `(file bytes, crc)` pair a package's DESCRI.DAT files declare."""
    out = []
    root = Path(root)
    for descri in sorted(root.glob("MAPPE/*/DESCRI.DAT")):
        for line in descri.read_text(encoding="latin1").splitlines():
            f = line.split(",")
            if len(f) >= 5 and f[3].upper() == "CRC":
                rel = f[2].replace("\\", "/").lstrip("/")
                p = root / rel
                if p.exists():
                    out.append((p.read_bytes(), int(f[4], 16)))
    return out


def samples_from_list(path, root):
    out = []
    root = Path(root)
    for line in Path(path).read_text().splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        name, _, hexval = line.rpartition(" ")
        p = root / name
        if p.exists():
            out.append((p.read_bytes(), int(hexval, 16)))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--package", help="a map package root; collects from its DESCRI.DAT files")
    ap.add_argument("--samples", help="a file of '<path> <hex>' lines")
    ap.add_argument("--root", default=".", help="base for the paths in --samples")
    ap.add_argument("--width", type=int, default=16)
    args = ap.parse_args(argv)

    if args.package:
        samples = samples_from_package(args.package)
    elif args.samples:
        samples = samples_from_list(args.samples, args.root)
    else:
        ap.error("give --package or --samples")

    lens = collections.Counter(len(m) for m, _ in samples)
    repeated = {L: n for L, n in lens.items() if n >= 2}
    print(
        "%d samples, %d distinct lengths, %d lengths with >=2"
        % (len(samples), len(lens), len(repeated))
    )
    if not repeated:
        sys.exit("no length occurs twice, so nothing can be constrained — add more samples")

    got = recover(samples, args.width)
    if not got:
        sys.exit("no parameterisation reproduces the samples")
    print("  width  %d" % got["width"])
    print("  poly   %#06x" % got["poly"])
    print("  init   %#06x" % got["init"])
    print("  refin  %s" % got["refin"])
    print("  refout %s" % got["refout"])
    print("  xorout %#06x" % got["xorout"])
    print("  -> %s" % got["name"])
    bad = [
        (len(m), hex(w))
        for m, w in samples
        if crc(
            m, got["poly"], got["width"], got["refin"], got["refout"], got["init"], got["xorout"]
        )
        != w
    ]
    print("  verified against all %d samples: %s" % (len(samples), "yes" if not bad else bad[:5]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
