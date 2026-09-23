#!/usr/bin/env python3

# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///

"""Read and write the cartography name pools.

`NAMECITY.DAT` and `%03d_NV.dat` inside a country's `*.BIN` are the one part of the map
format that is fully understood: **plain NUL-separated strings**, no header, no footer, no
compression. `NAMECITY.DAT` holds `NAME\\TOWN` entries, some with a postcode district
(`BL2 6 RADCLIFFE\\MANCHESTER`); `%03d_NV.dat` holds street names and road numbers.

The one thing that is easy to get wrong: **empty fields are part of the format.** Reading and
writing `005_NV.DAT` reproduces it byte for byte only when they are preserved — 78 of them in
the UK file — so they are not padding to be filtered. `round-trip` is the check that proves a
reader still agrees with the vendor's own file, and it is the reason this tool exists rather
than a one-line `split`.

It is also the only layer a proof-of-concept can drive end to end today: it carries names, not
geometry, so it puts nothing on a screen. See [Cartography](../docs/CARTOGRAPHY.md).

No dependencies, so it runs with nothing installed.

usage:
    python3 tools/cartography_names.py dump FILE [--limit N]     # inspect a pool
    python3 tools/cartography_names.py round-trip FILE           # read+write, byte compare
    python3 tools/cartography_names.py emit FILE --out NEW       # rewrite, normalised
"""

import argparse
import sys
from pathlib import Path

SEPARATOR = b"\x00"


def read_pool(path):
    """Return every field, empty ones included."""
    return Path(path).read_bytes().split(SEPARATOR)


def write_pool(path, fields):
    Path(path).write_bytes(SEPARATOR.join(fields))


def non_empty(fields):
    return [f for f in fields if f]


def cmd_dump(args):
    fields = read_pool(args.file)
    text = non_empty(fields)
    print("%s: %d fields (%d non-empty, %d empty)"
          % (args.file, len(fields), len(text), len(fields) - len(text)))
    for f in text[: args.limit]:
        print("  %r" % f.decode("latin1"))


def cmd_round_trip(args):
    fields = read_pool(args.file)
    out = Path(args.file + ".roundtrip")
    write_pool(out, fields)
    same = out.read_bytes() == Path(args.file).read_bytes()
    out.unlink()
    print("%s: %d fields -> %s" % (args.file, len(fields), "byte-identical" if same else "DIFFERENT"))
    return 0 if same else 1


def cmd_emit(args):
    fields = read_pool(args.file)
    write_pool(args.out, fields)
    print("wrote %s (%d fields)" % (args.out, len(fields)))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("dump", help="show the fields of a pool")
    p.add_argument("file")
    p.add_argument("--limit", type=int, default=20)
    p.set_defaults(fn=cmd_dump)

    p = sub.add_parser("round-trip", help="read and write back, then compare bytes")
    p.add_argument("file")
    p.set_defaults(fn=cmd_round_trip)

    p = sub.add_parser("emit", help="write a pool out again")
    p.add_argument("file")
    p.add_argument("--out", required=True)
    p.set_defaults(fn=cmd_emit)

    args = ap.parse_args(argv)
    return args.fn(args) or 0


if __name__ == "__main__":
    sys.exit(main())
