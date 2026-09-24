"""The boring, load-bearing parts of a package's checksum chain, in one place.

These are shared because the tools disagreeing about the same bytes is the failure mode
this module exists to prevent, not because sharing them is tidy. Three tools once carried
their own copy of the `ctrl.bin` record layout and the CRC swap, and a patch applied
through one and verified through another would have agreed only by luck.

Stdlib only, deliberately: `patch_smeg` runs with no dependencies, and this is the kind of
code that must not drag one in.
"""

import re
import struct
import zlib


def crc32(b):
    """The CRC32 of a package member, as the `.inf` files record it."""
    return zlib.crc32(b) & 0xFFFFFFFF


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


def read_inf_field(text, field="CRC32"):
    """Read one numeric field out of an `.inf`, or None when it is absent."""
    m = re.search((field + r": (-?\d+)").encode(), text)
    return None if m is None else int(m.group(1)) & 0xFFFFFFFF


def rewrite_inf_field(blob, field, value, where, signed=True):
    """Rewrite one `FIELD: <int>` in place, refusing when it is not there exactly once.

    `signed` is not cosmetic and is not inferred. The CRC32 fields are written in the
    signed-decimal form the .inf files use, so a value above 0x7fffffff goes out negative;
    the SIZE fields are plain unsigned counts. Collapsing the two would write a negative
    size for a partition above 2 GiB, which no test here would notice.
    """
    out, n = re.subn(
        (field + r": -?\d+" if signed else field + r": \d+").encode(),
        ("%s: %d" % (field, s32(value) if signed else value)).encode(),
        blob,
        count=1,
    )
    if n != 1:
        raise SystemExit("no '%s:' field found in %s" % (field, where))
    return out
