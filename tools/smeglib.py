"""The boring, load-bearing parts of a package's checksum chain, in one place.

These are shared because the tools disagreeing about the same bytes is the failure mode
this module exists to prevent, not because sharing them is tidy. Three tools once carried
their own copy of the `ctrl.bin` record layout and the CRC swap, and a patch applied
through one and verified through another would have agreed only by luck.

Stdlib only, deliberately: `patch_smeg` runs with no dependencies, and this is the kind of
code that must not drag one in.
"""

import os
import re
import struct
import zlib


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


CTRL_HEADER = 0x30  # date/version string to 0x2c, then the u32 record count
CTRL_RECORD = 264  # path[256], CheckType u32, value u32


def has_ctrl_layout(buf):
    """Whether `buf` is sized exactly as a stock `ctrl` file: header, records, trailer.

    All 16 `*ctrl.bin` files in the stock 5.43.A.R2 package match this (docs/FLASH_CHAIN.md).
    The synthetic test packages do not, which is how a check can tell a file that should
    carry a trailer from one that never had one.
    """
    if len(buf) < CTRL_HEADER + 4:
        return False
    count = struct.unpack(">I", bytes(buf[0x2C:0x30]))[0]
    return len(buf) == CTRL_HEADER + count * CTRL_RECORD + 4


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


def read_inf_field(text, field="CRC32"):
    """Read one numeric field out of an `.inf`, or None when it is absent."""
    m = re.search((field + r": (-?\d+)").encode(), text)
    return None if m is None else int(m.group(1)) & 0xFFFFFFFF


def rewrite_inf_field(blob, field, value):
    """Rewrite one `FIELD: <int>` in place, refusing when it is not there exactly once."""
    out, n = re.subn(
        (field + r": -?\d+").encode(), ("%s: %d" % (field, s32(value))).encode(), blob, count=1
    )
    if n != 1:
        raise SystemExit("no '%s:' field found in the .inf" % field)
    return out
