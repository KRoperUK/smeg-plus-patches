#!/usr/bin/env python3

# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///

"""Read the cartography metadata: name pools, the `.inf` sidecars, `SCC` records, `CCT.DAT`.

The cartography is a gzipped tar per country (`MAPPE/<cid>/<cid>.BIN`) whose members are the
map itself, wrapped in three layers of metadata. This tool handles the metadata — the parts
that are *fully* understood — and deliberately does not pretend to handle the tiles, which are
bit-packed and not decoded. See docs/CARTOGRAPHY.md for each claim's evidence.

    names   the NUL-separated string pools (`NAMECITY.DAT`, `%03d_NV.dat`).
            Plain text, round-trips byte for byte. Empty fields are part of the format.
    inf     the `.inf` sidecar: a first line of eight hex digits, then `KEY:VALUE` lines.
            The hex value is NOT a standard CRC or hash of the file it accompanies — the
            algorithm is unidentified, so this tool reads it and does not verify it.
    scc     `%03dSCC.DST`: fixed 92-byte records of `[name area 82][payload 10]`.
            The name is stored twice inside the 82 bytes. The 10-byte payload is bit-packed
            and its field map is not decoded, so it is reported as bytes.
    cct     `CCT.DAT`: 76-byte records, and as a whole a byte-subtraction cipher against a
            896-byte key vector that ships inside the application image itself.

`cct` needs the firmware image because the key lives there, not in the package:

    cartography.py cct decrypt /path/to/CCT.DAT --image app_nav.bin

Only **decryption** is implemented. The transform is a subtraction against a fixed vector and
its inverse is therefore trivial to write, but `CCT.DAT` is how HERE's cartography is licensed
per vehicle, so this tool reads the token rather than sealing one.

No dependencies, so it runs with nothing installed.
"""

import argparse
import sys
from pathlib import Path

# ----------------------------------------------------------------- the string pools

NUL = b"\x00"


def read_pool(path):
    """Every field of a NUL-separated pool, empty ones included.

    Empty fields are load-bearing: `005_NV.DAT` only round-trips when its 78 of them are kept.
    """
    return Path(path).read_bytes().split(NUL)


def write_pool(path, fields):
    Path(path).write_bytes(NUL.join(fields))


def non_empty(fields):
    return [f for f in fields if f]


# ----------------------------------------------------------------- the .inf sidecar


def parse_inf(path):
    """`<8 hex>\\r\\nKEY:VALUE\\r\\n…` -> (checksum_field, {key: value})."""
    lines = Path(path).read_bytes().decode("latin1").replace("\r\n", "\n").split("\n")
    first = lines[0].strip() if lines else ""
    fields = {}
    for line in lines[1:]:
        if ":" in line:
            k, _, v = line.partition(":")
            fields[k.strip()] = v.strip()
    return first, fields


# ----------------------------------------------------------------- SCC records

SCC_RECORD = 92
SCC_NAME_AREA = 82


def parse_scc(data):
    """Yield (offset, primary name, secondary name, 10-byte payload) per 92-byte record."""
    out = []
    for off in range(0, len(data) - SCC_RECORD + 1, SCC_RECORD):
        rec = data[off : off + SCC_RECORD]
        area, payload = rec[:SCC_NAME_AREA], rec[SCC_NAME_AREA:]
        first = area[:41].split(NUL)[0].decode("latin1")
        second = area[41:].split(NUL)[0].decode("latin1")
        out.append((off, first, second, payload))
    return out


# ----------------------------------------------------------------- CCT.DAT

CCT_RECORD = 76
CCT_KEY_OFFSET = 0x035E4CD8  # ChipherCCT_Vect, a data symbol in the application image
CCT_KEY_LEN = 896  # the period the transform cycles with
IMAGE_BASE = 0x01000000  # where the inflated application image is loaded


def key_from_image(image, addr=None):
    """The transform's key vector, read out of the firmware image.

    `addr` defaults to the module constant rather than being bound as a default argument, so
    overriding `CCT_KEY_OFFSET` actually takes effect.
    """
    if addr is None:
        addr = CCT_KEY_OFFSET
    off = addr - IMAGE_BASE
    key = image[off : off + CCT_KEY_LEN]
    if len(key) != CCT_KEY_LEN:
        sys.exit("image too short to contain ChipherCCT_Vect at %#x" % addr)
    return key


def cct_decrypt(data, key):
    """`plain[i] = (cipher[i] - key[i % 896]) & 0xFF`.

    Kept separate from the key lookup so it can be tested without a firmware image: the
    transform is arithmetic, and only the key location is about the image.
    """
    return bytes((c - key[i % CCT_KEY_LEN]) & 0xFF for i, c in enumerate(data))


def parse_cct(plain):
    """Yield (country, checktype, value, path) per 76-byte record."""
    out = []
    for off in range(0, len(plain) - CCT_RECORD + 1, CCT_RECORD):
        rec = plain[off : off + CCT_RECORD]
        country = rec[0:3].decode("latin1")
        checktype = rec[13]
        value = rec[14:22].decode("latin1")
        path = rec[26:].split(NUL)[0].decode("latin1")
        out.append((country, checktype, value, path))
    return out


# ----------------------------------------------------------------- commands


def cmd_names(args):
    fields = read_pool(args.file)
    if args.out:
        write_pool(args.out, fields)
        print("wrote %s (%d fields)" % (args.out, len(fields)))
        return 0
    text = non_empty(fields)
    print(
        "%s: %d fields (%d non-empty, %d empty)"
        % (args.file, len(fields), len(text), len(fields) - len(text))
    )
    for f in text[: args.limit]:
        print("  %r" % f.decode("latin1"))
    return 0


def cmd_round_trip(args):
    fields = read_pool(args.file)
    out = Path(str(args.file) + ".roundtrip")
    write_pool(out, fields)
    same = out.read_bytes() == Path(args.file).read_bytes()
    out.unlink()
    print(
        "%s: %d fields -> %s" % (args.file, len(fields), "byte-identical" if same else "DIFFERENT")
    )
    return 0 if same else 1


def cmd_inf(args):
    first, fields = parse_inf(args.file)
    print("%s: checksum field %r" % (args.file, first))
    for k, v in fields.items():
        print("  %-12s %s" % (k, v))
    return 0


def cmd_scc(args):
    recs = parse_scc(Path(args.file).read_bytes())
    print("%s: %d records of %d bytes" % (args.file, len(recs), SCC_RECORD))
    for off, first, second, payload in recs[: args.limit]:
        print("  @%06x  %-34r %-22r  %s" % (off, first, second, payload.hex(" ")))
    return 0


def cmd_cct(args):
    key = key_from_image(Path(args.image).read_bytes())
    plain = cct_decrypt(Path(args.file).read_bytes(), key)
    if args.out:
        Path(args.out).write_bytes(plain)
        print("wrote %s (%d bytes)" % (args.out, len(plain)))
        return 0
    recs = parse_cct(plain)
    print("%s: %d records of %d bytes, decrypted" % (args.file, len(recs), CCT_RECORD))
    print("  %-6s %-6s %-12s %s" % ("ctry", "check", "value", "path"))
    for country, checktype, value, path in recs:
        print("  %-6s %-6d %-12s %s" % (country, checktype, value, path))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("names", help="inspect or rewrite a NUL-separated name pool")
    p.add_argument("file")
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--out", help="write the pool out again instead of listing it")
    p.set_defaults(fn=cmd_names)
    p = sub.add_parser("names-round-trip", help="read and write a pool, then compare bytes")
    p.add_argument("file")
    p.set_defaults(fn=cmd_round_trip)

    p = sub.add_parser("inf", help="show a .inf sidecar")
    p.add_argument("file")
    p.set_defaults(fn=cmd_inf)

    p = sub.add_parser("scc", help="list the records of a %%03dSCC.DST")
    p.add_argument("file")
    p.add_argument("--limit", type=int, default=10)
    p.set_defaults(fn=cmd_scc)

    p = sub.add_parser("cct", help="decrypt and show CCT.DAT (needs the firmware image)")
    p.add_argument("file")
    p.add_argument("--image", required=True, help="the inflated application image")
    p.add_argument("--out", help="write the decrypted table instead of listing it")
    p.set_defaults(fn=cmd_cct)

    args = ap.parse_args(argv)
    return args.fn(args) or 0


if __name__ == "__main__":
    sys.exit(main())
