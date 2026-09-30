"""The boring, load-bearing parts of a package's checksum chain, in one place.

These are shared because the tools disagreeing about the same bytes is the failure mode
this module exists to prevent, not because sharing them is tidy. Three tools once carried
their own copy of the `ctrl.bin` record layout and the CRC swap, and a patch applied
through one and verified through another would have agreed only by luck.

So this is the one home for the `ctrl` record layout, the `.inf` field read/rewrite and the
CRC helpers (#68): a `ctrl` file is a fixed header, a u32 record count at `0x2c`, 264-byte
records and an optional trailing CRC32, and every tool that touches that chain reads the
shape from here rather than restating it.

Stdlib only, deliberately: `patch_smeg` runs with no dependencies, and this is the kind of
code that must not drag one in.
"""

import os
import re
import struct
import zlib


def die(msg):
    """Stop with a message on stderr, the same way from every tool."""
    raise SystemExit(msg)


def crc32(b):
    """The CRC32 of a package member, as the `.inf` files record it."""
    return zlib.crc32(b) & 0xFFFFFFFF


def _crc16_table(poly=0xD415):
    table = []
    for i in range(256):
        c = i
        for _ in range(8):
            c = (c >> 1) ^ poly if c & 1 else c >> 1
        table.append(c)
    return table


_CRC16 = _crc16_table()


def ctrl_crc16(data):
    """The value a CheckType-3 `ctrl` record holds for a file (docs/FLASH_CHAIN.md, #197).

    A reflected CRC-16, table polynomial 0xD415 (0xA82B in normal form), init 0, no final XOR;
    the two result bytes are stored swapped and the 16-bit value sign-extended to 32 bits.
    Built from the polynomial alone. Reproduced for every type-3 record whose file is loose in
    the stock 5.43.A.R2 package (executed). The unit's `CheckCRCFile` may also compare a
    sidecar value and take an offset; that part is not known.
    """
    c = 0
    for b in data:
        c = (c >> 8) ^ _CRC16[(c ^ b) & 0xFF]
    v = ((c & 0xFF) << 8) | (c >> 8)
    return v | 0xFFFF0000 if v & 0x8000 else v


def s32(v):
    """The signed-decimal form the `.inf` files use for CRC32.

    Unsigned values above 0x7fffffff are written negative, which is why every reader has to
    go through this rather than `int()`.
    """
    return struct.unpack(">i", struct.pack(">I", v))[0]


def roundup(v, b):
    """Round `v` up to a multiple of `b` — the `SIZE_n` per-file block rounding.

    `SIZE_n` is the sum of the file sizes each rounded up to an `n` KiB block
    (docs/MEDIA_PARTITION.md), so the patcher and the fixtures that test it round alike.
    """
    return (v + b - 1) // b * b


def swap_crc(buf, old, new, what, where="the control file"):
    """Replace exactly one 4-byte big-endian CRC, or refuse.

    The count check is the point. A control file that carries the value zero, twice, or not
    at all means the patch was applied to something other than what the manifest describes,
    and replacing it anyway would write a wrong CRC rather than fail.
    """
    pat = struct.pack(">I", old)
    n = buf.count(pat)
    if n != 1:
        raise SystemExit(
            "expected exactly one occurrence of %s CRC %#010x in %s, found %d"
            % (what, old, where, n)
        )
    return buf.replace(pat, struct.pack(">I", new))


def has_trailer(buf):
    """Whether a `ctrl` file ends in a CRC32 of everything before it.

    Every stock `ctrl.bin`, `<MODULE>_ctrl.bin` and `system_ctrl.bin` does. The synthetic
    packages the tests build do not, so this is checked rather than assumed.
    """
    return len(buf) >= 8 and crc32(buf[:-4]) == struct.unpack(">I", bytes(buf[-4:]))[0]


def refresh_trailer(old, new):
    """Recompute `new`'s trailing CRC32 when `old` carried a valid one.

    `swap_crc` rewrites the records but not the trailer, so without this every patched
    `ctrl` file ends in the stock file's CRC. Units have accepted packages like that, which
    suggests the trailer is not checked, but that is inferred; a stock-shaped file is not.
    Call it on the finished file, before taking its CRC for the manifest above it.
    """
    if not has_trailer(old):
        return bytes(new)
    body = bytes(new[:-4])
    return body + struct.pack(">I", crc32(body))


# ---------------------------------------------------------------- ctrl layout

CTRL_HEADER = 0x30  # date/version string to 0x2c, then the u32 record count
CTRL_COUNT = 0x2C  # the u32 record count, at the end of that string
CTRL_RECORD = 264  # path[256], CheckType u32, value u32
CTRL_TYPE_OFF = 256  # CheckType within a record
CTRL_VALUE_OFF = 260  # the value within a record: CRC32, size, or the CRC-16
CTRL_HEADER_MSG = b"19/09/2017  2.1.0.0"  # generation date + manifest version


def build_ctrl(records, trailer=False):
    """Build a `ctrl` file: header, u32 count, 264-byte records, and optionally the trailer.

    `records` is an iterable of `(path, check_type, value)`. The trailing CRC32 is optional
    because the synthetic test fixtures carry none — `has_ctrl_layout` is what calls a file
    with one stock, and `refresh_trailer` is what adds it back after an edit. Writing the
    count as a u32 at `0x2c` rather than a single byte is the shape `has_ctrl_layout` reads.
    """
    records = list(records)
    body = bytearray(CTRL_HEADER_MSG.ljust(CTRL_COUNT, b"\x00"))
    body += struct.pack(">I", len(records))
    for path, check_type, value in records:
        name = path.encode() if isinstance(path, str) else bytes(path)
        if len(name) >= CTRL_TYPE_OFF:
            raise SystemExit("ctrl record path is too long: %r" % path)
        rec = bytearray(CTRL_RECORD)
        rec[0 : len(name)] = name  # the byte after it stays NUL, terminating the path
        struct.pack_into(">I", rec, CTRL_TYPE_OFF, check_type)
        struct.pack_into(">I", rec, CTRL_VALUE_OFF, value & 0xFFFFFFFF)
        body += rec
    out = bytes(body)
    return out + struct.pack(">I", crc32(out)) if trailer else out


def has_ctrl_layout(buf):
    """Whether `buf` is sized exactly as a stock `ctrl` file: header, records, trailer.

    All 16 `*ctrl.bin` files in the stock 5.43.A.R2 package match this (docs/FLASH_CHAIN.md).
    The synthetic test packages do not, which is how a check can tell a file that should
    carry a trailer from one that never had one.
    """
    if len(buf) < CTRL_HEADER + 4:
        return False
    count = struct.unpack(">I", bytes(buf[CTRL_COUNT:CTRL_HEADER]))[0]
    return len(buf) == CTRL_HEADER + count * CTRL_RECORD + 4


def patch_ctrl_record(buf, member_path, old, new, where="the control file", name=None):
    """Rewrite the value of the one stock `ctrl` record whose path is `member_path`.

    The record-aware companion to `swap_crc`: that finds a CRC by value in a
    `<MODULE>_ctrl.bin`, this finds a record by path in a `system_ctrl.bin`, where the path
    is what identifies the record. The NUL terminator is required, because without it
    "x.pkg" also matches an "x.pkg.inf" record and looks like a duplicate.
    """
    label = member_path if name is None else name
    needle = member_path.encode() + b"\x00"
    off = buf.find(needle)
    if off < 0:
        raise SystemExit("%s has no record for %s — cannot replace it" % (where, label))
    if buf.find(needle, off + 1) >= 0:
        raise SystemExit("%s has more than one record for %s" % (where, label))
    pos = off + CTRL_VALUE_OFF
    have = struct.unpack_from(">I", buf, pos)[0]
    if have != old:
        raise SystemExit(
            "%s record for %s holds %#010x, expected %#010x" % (where, label, have, old)
        )
    struct.pack_into(">I", buf, pos, new)
    return buf


def stale_trailers(root):
    """Package-relative paths of stock-layout `ctrl` files whose trailing CRC32 is wrong.

    Packages built before #159 carry three of these. Units have accepted them, which suggests
    the trailer is not checked (inferred), so callers report this as a warning.
    """
    stale = []
    for dirpath, _, names in os.walk(root):
        for name in sorted(names):
            if not name.endswith("ctrl.bin"):
                continue
            path = os.path.join(dirpath, name)
            with open(path, "rb") as fh:
                buf = fh.read()
            if has_ctrl_layout(buf) and not has_trailer(buf):
                stale.append(os.path.relpath(path, root))
    return sorted(stale)


# ------------------------------------------------------------------ .inf fields


def read_inf_field(text, field="CRC32"):
    """Read one numeric field out of an `.inf`, or None when it is absent."""
    m = re.search((field + r": (-?\d+)").encode(), text)
    return None if m is None else int(m.group(1)) & 0xFFFFFFFF


def read_inf_fields(text, fields):
    """Read several named `FIELD: <int>` values at once; absent fields are left out."""
    return {f: v for f in fields if (v := read_inf_field(text, f)) is not None}


def rewrite_inf_field(blob, field, value):
    """Rewrite one `FIELD: <int>` in place, refusing when it is not there exactly once."""
    out, n = re.subn(
        (field + r": -?\d+").encode(), ("%s: %d" % (field, s32(value))).encode(), blob, count=1
    )
    if n != 1:
        raise SystemExit("no '%s:' field found in the .inf" % field)
    return out


def sqlite_inf(data):
    """The `<database>.sqlite.inf` sidecar that belongs beside a live SQLite file.

    One signed-decimal `CRC32:` line with a CRLF — the same form `rewrite_inf_field` writes
    and `read_inf_field` reads. The updater's `ManageSQLiteFiles` generates one beside every
    live database, so a shipped `USER_DATA` payload has to carry a matching sidecar or the
    payload is incomplete. `build_package` writes it and `preflight` checks it against the
    database, and both must agree byte for byte, which is why it lives here rather than twice.
    """
    return ("CRC32: %d\r\n" % s32(crc32(data))).encode()
