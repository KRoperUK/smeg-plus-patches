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
# The 0x800 bytes before the zlib stream are a table of 32-byte entries. Read against the
# shipped NAV, AUDIO_BT and AUDIO_BT_256 images (tests/test_firmware_nav.py, never in CI) the
# table holds 64 entries and only the first two are used: entries 2..63 are eight `0xdeadbeef`
# words. Entry 0 describes the application image: its first word is the constant `0x00010004`,
# `+0x04` is the size that image inflates to, and `+0x14` the stored span of its stream (the
# `0x08` at 0x800, the compressed bytes, and two trailing bytes). Entry 1 describes a **second**
# segment, not the main stream: its first word is that segment's offset in 2 KiB blocks -
# `(blocks + 1) x 2048` - which lands on a second `0x08` marker followed by a second zlib stream
# that inflates to a second PowerPC image. The main stream is at `0x801`, which entry 1 does
# **not** describe. Which of the remaining words are sizes and which mean something else is not
# established, so they are carried through unparsed. Nothing acts on the parse: `inflate()`
# still finds the main stream by trying offsets, and `patch_smeg.py` copies the header through.
HEADER_TABLE_LEN = 0x800  # the header is one table; 0x800 holds the 0x08 marker
ENTRY_SIZE = 32
ENTRY_COUNT = HEADER_TABLE_LEN // ENTRY_SIZE
HEADER_MAGIC = 0x00010004  # entry 0's first word, on every image anyone has looked at
DEADBEEF = 0xDEADBEEF  # +0x1C of every entry, and the filler of an unused one
DATA_UNIT = 2048  # an entry's first word counts its segment offset in 2 KiB blocks
COMPRESSION_MARKER = 0x08


@dataclass(frozen=True)
class HeaderEntry:
    """One 32-byte table entry, kept as its eight big-endian words.

    Only four word offsets have a reading, so the rest is carried through unparsed rather than
    guessed at: inventing a name for a word nobody has described is how a parse quietly stops
    matching the file it claims to read.
    """

    index: int
    offset: int
    words: tuple

    @property
    def first_word(self):
        """`+0x00` - the magic on entry 0, a segment offset in 2 KiB blocks on later entries."""
        return self.words[0]

    @property
    def inflated_size(self):
        """`+0x04` - the size the entry's segment inflates to. Exact on every shipped image."""
        return self.words[1]

    @property
    def data_size(self):
        """`+0x14` - the stored span of the entry's segment, from its `0x08` marker to its end.

        *(executed)* On the shipped images this is `1 + compressed stream + 2`, the two trailing
        bytes being all that is left over; it is emphatically **not** the inflated size, which is
        `+0x04`.
        """
        return self.words[5]

    @property
    def marker(self):
        """`+0x1C` - `0xdeadbeef`, on every entry whether it is used or not."""
        return self.words[7]

    @property
    def is_unused(self):
        """A table slot the writer never filled: eight `0xdeadbeef` words, or all zeros.

        *(executed)* The shipped images fill entries 2..63 with `0xdeadbeef`; a synthetic header
        of zeros says the same thing, so both count as unused. Treating the filler as a real
        entry would invent sixty-two segments out of one 0x800-byte header.
        """
        return self.words == (DEADBEEF,) * len(self.words) or not any(self.words)


@dataclass(frozen=True)
class ContainerHeader:
    """What `parse_container_header` makes of the 0x800 bytes before the stream.

    `entries` is the used entries in file order - the first two on every shipped image. The
    named fields come from those two: entry 0 carries the magic, the main image's inflated size
    and the stored span of its stream, while entry 1 carries the offset of a **second** segment.
    `blocks`, `data_offset` and `stream_offset` all belong to that second segment and are not the
    main stream at `0x801`; `inflate()` is still what finds the main stream. A field whose entry
    is unused is `None`.

    `magic_ok` is a fact about the file, not a gate: some of the header is a third party's
    description, so a mismatch is reported rather than raised on.
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
    `0x00010004`; a later entry's first word is its segment's offset **in 2 KiB blocks**, so the
    file offset is `(blocks + 1) x 2048`; `+0x04` of an entry is the inflated size, `+0x14` a
    data size and `+0x1C` the marker `0xdeadbeef`.

    Run against the shipped NAV, AUDIO_BT and AUDIO_BT_256 images, that description holds where
    it can be checked and the parse now reports what is there rather than what was expected:

    * `+0x04` and `+0x14` are exactly the inflated size and the stored span of a segment, and
      `0xdeadbeef` is at `+0x1C` - *(executed)*, all three images.
    * Entry 1's first word is **not** 0 on a shipped image, so its `(blocks + 1) x 2048` offset
      is **not** `0x800` and is not where `inflate()` finds the main stream. It is a *second*
      segment: a second `0x08` marker at that offset followed by a second zlib stream that
      inflates to a second PowerPC image. The main image's own stream is at `0x801`, which entry
      1 says nothing about - the third party's "the data's offset" reading is the one thing here
      the real image contradicts, so `data_offset`/`stream_offset` are documented as the second
      segment's and never as the main stream's.
    * Entries 2..63 are eight `0xdeadbeef` words, i.e. unused slots, not segments.

    `inflate()` is deliberately left alone, fallbacks included: this parse must not be the thing
    that decides whether an image unpacks.

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
    blocks = None if second.is_unused else second.first_word
    data_offset = None if blocks is None else (blocks + 1) * DATA_UNIT

    stream_offset = None
    if data_offset is not None and data_offset < len(raw):
        at = raw[data_offset]
        stream_offset = data_offset + 1 if at == COMPRESSION_MARKER else data_offset

    return ContainerHeader(
        entries=tuple(e for e in table if not e.is_unused),
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
