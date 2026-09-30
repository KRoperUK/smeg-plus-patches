#!/usr/bin/env python3

# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///

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
import struct
import zlib
from dataclasses import dataclass

# addresses in the inflated image are absolute; file offsets are addr - DEFAULT_BASE
DEFAULT_BASE = 0x01000000
HEADER_SIZE = 0x801

# the vendor's own build path, which is how an image names the firmware it came from
BUILD_PATH_RE = re.compile(rb"04_HMI_DEV-([^/\x00]{1,32})/")

# --- the 0x800-byte container header ---------------------------------------
#
# Everything below describes the table of 32-byte entries that fills the 0x800 bytes before
# the zlib stream. Two field meanings are this repository's own (the inflated size at +0x04
# and the 0xdeadbeef markers, both recorded in docs/PATCHES.md); the *entry structure* is
# bousqi/SMEG_PLUS's description (`smeg_reverse.txt`, "f_BigQuick.bin") and is **read, not
# executed** — no vendor image has been checked against it here. Nothing acts on the parse:
# `inflate()` still finds the stream by trying offsets, exactly as before, and `patch_smeg.py`
# still copies the header through untouched.
HEADER_TABLE_LEN = 0x800  # the header is one table; 0x800 holds the 0x08 marker
ENTRY_SIZE = 32
ENTRY_COUNT = HEADER_TABLE_LEN // ENTRY_SIZE
HEADER_MAGIC = 0x00010004  # entry 0's first word, on every image anyone has looked at
DEADBEEF = 0xDEADBEEF  # +0x1C of an entry
DATA_UNIT = 2048  # entry 1 counts the data offset in 2 KiB blocks
COMPRESSION_MARKER = 0x08


@dataclass(frozen=True)
class HeaderEntry:
    """One 32-byte table entry, kept as its eight big-endian words.

    Only three word offsets have a published meaning, so the rest is carried through
    unparsed rather than guessed at: inventing a name for a word nobody has described is how
    a parse quietly stops matching the file it claims to read.
    """

    index: int
    offset: int
    words: tuple

    @property
    def first_word(self):
        """`+0x00` — the magic on entry 0, the data offset in 2 KiB blocks on entry 1."""
        return self.words[0]

    @property
    def inflated_size(self):
        """`+0x04` — the size the image inflates to."""
        return self.words[1]

    @property
    def data_size(self):
        """`+0x14` — a data size *(read, bousqi/SMEG_PLUS; unconfirmed here)*."""
        return self.words[5]

    @property
    def marker(self):
        """`+0x1C` — `0xdeadbeef`."""
        return self.words[7]

    @property
    def is_blank(self):
        """An all-zero entry. The table holds 64 and only the first two are populated."""
        return not any(self.words)


@dataclass(frozen=True)
class ContainerHeader:
    """What `parse_container_header` makes of the 0x800 bytes before the stream.

    `entries` is the non-blank entries in file order. The named fields come from the two
    entries that carry meaning: entry 0 holds the magic, the inflated size and the data size,
    entry 1 the data's offset in 2 KiB blocks. A field whose entry is blank is `None`.
    """

    entries: tuple
    magic: int | None
    inflated_size: int | None
    data_size: int | None
    blocks: int | None
    data_offset: int | None
    stream_offset: int | None

    @property
    def magic_ok(self):
        """Whether entry 0 carries the `0x00010004` every image is expected to start with."""
        return self.magic == HEADER_MAGIC


def parse_container_header(raw):
    """Parse the 0x800-byte `f_BigQuick.bin` container header into named fields.

    The layout, as described by bousqi/SMEG_PLUS (`smeg_reverse.txt`, "f_BigQuick.bin"): the
    header is a **table of 32-byte entries**; entry 0's first word is the constant
    `0x00010004`; entry 1's first word is the data's offset **in 2 KiB blocks**, so the file
    offset is `(blocks + 1) x 2048`; `+0x04` of an entry is the inflated size, `+0x14` a data
    size and `+0x1C` the marker `0xdeadbeef`.

    That entry structure is **read, not executed** — this repository has not checked it
    against a vendor image, and nothing here acts on the result. Two of its field meanings are
    already this repo's own: `+0x04` is the inflated size (docs/PATCHES.md, "The application
    image", and the trampoline note in AGENTS.md that would have to rewrite it), and the
    `0xdeadbeef` markers at `+0x1C`.

    Where it meets `inflate()`: on the shipped layout `blocks` is 0, so `data_offset` is
    `0x800` — the byte the `0x08` compression marker sits in — and `stream_offset` is `0x801`,
    which is the first offset `inflate()` tries. The two are reported separately because they
    only coincide when the marker is where the header says the data begins. `inflate()` is
    deliberately left alone, fallbacks included: this parse must not be the thing that decides
    whether an image unpacks.

    Raises `ValueError` if there are not 0x800 bytes to read, rather than returning a header
    half-filled from a short buffer.
    """
    if len(raw) < HEADER_TABLE_LEN:
        raise ValueError("container header needs %#x bytes, got %#x" % (HEADER_TABLE_LEN, len(raw)))

    table = tuple(
        HeaderEntry(i, i * ENTRY_SIZE, struct.unpack_from(">8I", raw, i * ENTRY_SIZE))
        for i in range(ENTRY_COUNT)
    )

    first, second = table[0], table[1]
    blocks = None if second.is_blank else second.first_word
    data_offset = None if blocks is None else (blocks + 1) * DATA_UNIT

    stream_offset = None
    if data_offset is not None and data_offset < len(raw):
        at = raw[data_offset]
        stream_offset = data_offset + 1 if at == COMPRESSION_MARKER else data_offset

    return ContainerHeader(
        entries=tuple(e for e in table if not e.is_blank),
        magic=first.first_word,
        inflated_size=first.inflated_size,
        data_size=first.data_size,
        blocks=blocks,
        data_offset=data_offset,
        stream_offset=stream_offset,
    )


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
