"""Tests for the shared application-image container reader.

No firmware is involved: `tests/helpers.pack_bigquick` builds the container. That is the point
here more than usual — the header layout `parse_container_header` implements is a third
party's description, not a measurement of this repository's, so the only thing these tests can
pin is that the parse matches the description and that it changed nothing about `inflate()`.
"""

import os
import struct
import sys
import zlib

import pytest

import helpers

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "tools"))

import appimage  # noqa: E402


def pack_bigquick_with_fields(img, blocks=0, data_size=0):
    """`helpers.pack_bigquick` plus the two header words the container reader also names.

    The shared builder fills in what unpacking needs - entry 0's magic, its inflated size and
    the `0xdeadbeef` markers - but not entry 0's `+0x14` or entry 1's first word, so those are
    written here rather than in `helpers.py`, which another change is already editing.
    """
    bq = bytearray(helpers.pack_bigquick(img))
    struct.pack_into(">I", bq, 0x14, data_size)  # entry 0, +0x14
    struct.pack_into(">I", bq, 0x20, blocks)  # entry 1, +0x00
    return bytes(bq)


def moved_container(img, blocks):
    """A container whose data really does start where the header says it does.

    `pack_bigquick` always puts the stream at `0x801`. This one pads to the block the header
    claims first, so the header's own offset is the only thing that can be right about it.
    """
    bq = pack_bigquick_with_fields(img, blocks=blocks)
    at = (blocks + 1) * 2048
    return bq[:0x800] + bytes(at - 0x800) + b"\x08" + bq[0x801:]


def test_the_header_parses_into_named_fields():
    img = helpers.make_image()
    h = appimage.parse_container_header(pack_bigquick_with_fields(img, blocks=0, data_size=0x1234))

    assert h.magic == 0x00010004
    assert h.magic_ok
    assert h.inflated_size == len(img)
    assert h.data_size == 0x1234
    assert h.blocks == 0
    assert h.data_offset == 0x800
    assert h.stream_offset == 0x801


def test_the_two_live_entries_are_the_ones_carrying_the_markers():
    """The table holds 64 entries; only 0 and 1 say anything, and both end in `0xdeadbeef`."""
    h = appimage.parse_container_header(pack_bigquick_with_fields(helpers.make_image()))
    assert [(e.index, e.marker) for e in h.entries] == [
        (0, 0xDEADBEEF),
        (1, 0xDEADBEEF),
    ]


def test_the_parsed_stream_offset_is_where_inflate_starts():
    """The reconciliation, on the shipped layout.

    `blocks` 0 puts the data at `0x800`, which holds the `0x08` compression marker, so the
    stream begins at `0x801` - the first offset `inflate()` tries. The parse describes the
    stream; it does not decide where it is.
    """
    img = helpers.make_image()
    bq = pack_bigquick_with_fields(img, blocks=0)

    start, out = appimage.inflate(bq)

    assert (start, appimage.parse_container_header(bq).stream_offset) == (0x801, 0x801)
    assert out == img


def test_a_nonzero_block_count_moves_the_data_offset():
    """Entry 1's first word in 2 KiB blocks: `(blocks + 1) x 2048` *(read, bousqi/SMEG_PLUS)*."""
    h = appimage.parse_container_header(moved_container(helpers.make_image(), blocks=3))
    assert h.data_offset == 4 * 2048
    assert h.stream_offset == 4 * 2048 + 1


def test_inflate_still_only_handles_the_shipped_layout():
    """`inflate()` was not generalised, and this is the test that says so.

    It tries `0x801` and `0x800` and nothing else, so a container whose header moves the data
    elsewhere does not unpack. Leaving that alone is the requirement: the new parse describes
    the header, it does not get a say in whether an image works.
    """
    with pytest.raises(SystemExit):
        appimage.inflate(moved_container(helpers.make_image(), blocks=3))


def test_inflate_keeps_its_0x800_fallback():
    """A container with no `0x08` marker still unpacks at `0x800`, as it always did."""
    img = helpers.make_image()
    raw = bytes(0x800) + zlib.compress(img, 6)
    assert appimage.inflate(raw) == (0x800, img)


def test_without_the_marker_the_stream_is_taken_to_start_at_the_data():
    bq = bytearray(pack_bigquick_with_fields(helpers.make_image(), blocks=0))
    bq[0x800] = 0x00
    assert appimage.parse_container_header(bytes(bq)).stream_offset == 0x800


def test_a_foreign_magic_is_reported_rather_than_raised_on():
    """Some of the header is not confirmed here, so a mismatch is a fact about the file."""
    bq = bytearray(pack_bigquick_with_fields(helpers.make_image()))
    struct.pack_into(">I", bq, 0x00, 0xDEADBEEF)
    h = appimage.parse_container_header(bytes(bq))
    assert (h.magic, h.magic_ok) == (0xDEADBEEF, False)


def test_a_blank_entry_one_leaves_the_offset_unknown():
    """Nothing to read is reported as nothing, not as block 0 - which is a real offset."""
    bq = bytearray(pack_bigquick_with_fields(helpers.make_image(), blocks=0))
    bq[0x3C:0x40] = b"\x00" * 4  # entry 1's marker is the only word it had
    h = appimage.parse_container_header(bytes(bq))
    assert (h.blocks, h.data_offset, h.stream_offset) == (None, None, None)


def test_an_all_zero_header_has_no_entries():
    h = appimage.parse_container_header(bytes(0x800))
    assert h.entries == ()
    assert (h.magic, h.magic_ok) == (0, False)
    assert h.blocks is None


def test_a_short_buffer_is_refused():
    """A header half-read off a truncated file would be worse than an error."""
    with pytest.raises(ValueError):
        appimage.parse_container_header(bytes(0x7FF))
