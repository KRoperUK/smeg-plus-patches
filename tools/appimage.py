#!/usr/bin/env python3

# /// script
# requires-python = ">=3.10"
# dependencies = []

"""The application image container, shared by every tool that reads it.

`AppBin/f_BigQuick.bin` is a `0x800`-byte header, a `0x08` marker at `0x800`, then a **zlib
stream** from `0x801`, inflating to a raw PowerPC image loaded at `0x01000000`.

This lives on its own because two tools need it and one used to import the other to get at
it, which is an import cycle: `patch_smeg` reached into `fingerprint` for the build check,
and `fingerprint` reached back into `patch_smeg` for the container. CodeQL flagged it as
`py/cyclic-import`. Pulling the shared part down to a leaf module is the fix — a deferred
import inside the function would have hidden the cycle rather than removed it, and the
container is not really either tool's business anyway.
"""

import re
import zlib

# addresses in the inflated image are absolute; file offsets are addr - DEFAULT_BASE
DEFAULT_BASE = 0x01000000
HEADER_SIZE = 0x801

# the vendor's own build path, which is how an image names the firmware it came from
BUILD_PATH_RE = re.compile(rb"04_HMI_DEV-([^/\x00]{1,32})/")


def crc32_file(path):
    """CRC32 of a file, read in chunks so a large image does not land in memory."""
    c = 0
    with open(path, "rb") as fh:
        while True:
            b = fh.read(1 << 20)
            if not b:
                break
            c = zlib.crc32(b, c)
    return c & 0xFFFFFFFF


def inflate(raw):
    """Unwrap the container, returning (stream offset, inflated image).

    The stream position is tried at a few plausible offsets rather than trusting one: the
    shipped images start it at `0x801`, and being wrong about that is indistinguishable from
    a corrupt image until you look.
    """
    for start in (HEADER_SIZE, HEADER_SIZE - 1, 0x800):
        try:
            d = zlib.decompressobj()
            out = d.decompress(raw[start:])
            out += d.flush()
        except zlib.error:
            continue
        if len(out) > 0x100000:
            return start, out
    raise SystemExit("could not inflate application image")


def firmware_hints(img):
    """Build-version tokens the vendor's own build paths leave in the image."""
    return sorted({m.group(1).decode("latin1") for m in BUILD_PATH_RE.finditer(bytes(img))})
