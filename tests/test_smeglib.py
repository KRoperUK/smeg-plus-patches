"""Tests for the shared checksum-chain primitives in `smeglib`.

Two things live here:

* `ctrl_crc16`, the CheckType-3 value in `ctrl` manifests (#197). The algorithm was
  reproduced against every loose type-3 file in the stock package, which cannot ship here,
  so these pin the parts that are easy to get wrong without it: the table is built from the
  REFLECTED polynomial (0xD415; the normal form 0xA82B gives different values), the result
  bytes are swapped, and the 16-bit value is sign-extended.
* the `ctrl` record layout and the `.inf` field helpers (#68). These are the bytes three
  tools used to carry their own private copy of, so a fixture disagreeing with a tool was
  possible; every one now goes through `smeglib`, and these pin the shape it writes.
"""

import os
import struct
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tools"))

import crc_recover  # noqa: E402
import helpers  # noqa: E402
import smeglib  # noqa: E402


def reference(data):
    """A bit-at-a-time implementation, independent of the table."""
    c = 0
    for b in data:
        c ^= b
        for _ in range(8):
            c = (c >> 1) ^ 0xD415 if c & 1 else c >> 1
    v = ((c & 0xFF) << 8) | (c >> 8)
    return v | 0xFFFF0000 if v & 0x8000 else v


def test_the_table_matches_a_bitwise_implementation():
    for data in (b"", b"\x00", b"123456789", bytes(range(256)) * 3):
        assert smeglib.ctrl_crc16(data) == reference(data)


def test_empty_input_is_zero():
    assert smeglib.ctrl_crc16(b"") == 0


def test_a_high_bit_result_is_sign_extended_and_a_low_one_is_not():
    values = {smeglib.ctrl_crc16(bytes([i])) for i in range(256)}
    assert any(v & 0xFFFF0000 == 0xFFFF0000 for v in values)
    assert any(v < 0x8000 for v in values)
    assert all(v < 0x8000 or v >= 0xFFFF8000 for v in values)


def test_the_normal_form_polynomial_gives_different_values():
    """A table built from 0xA82B itself matches none of the stock records; keep it apart."""
    table = smeglib._crc16_table(0xA82B)
    c = 0
    for b in b"123456789":
        c = (c >> 8) ^ table[(c ^ b) & 0xFF]
    assert c != (smeglib.ctrl_crc16(b"123456789") & 0xFFFF)


# ------------------------------------------------------ the shared ctrl layout (#68)

RECORDS = [("/NAV/system.bin", 2, 0x12345678), ("/NAV/system.bin.inf", 1, 0x13CC)]


def test_build_ctrl_writes_the_stock_shape():
    """Header, u32 count at 0x2c, 264-byte records — the shape `has_ctrl_layout` reads."""
    buf = smeglib.build_ctrl(RECORDS)
    assert len(buf) == smeglib.CTRL_HEADER + len(RECORDS) * smeglib.CTRL_RECORD
    assert struct.unpack(">I", buf[smeglib.CTRL_COUNT : smeglib.CTRL_HEADER])[0] == len(RECORDS)
    first = buf[smeglib.CTRL_HEADER : smeglib.CTRL_HEADER + smeglib.CTRL_RECORD]
    assert first[:15] == b"/NAV/system.bin" and first[15] == 0  # NUL-terminated path
    assert struct.unpack_from(">I", first, smeglib.CTRL_TYPE_OFF)[0] == 2
    assert struct.unpack_from(">I", first, smeglib.CTRL_VALUE_OFF)[0] == 0x12345678


def test_a_trailer_is_what_makes_a_ctrl_file_recognisably_stock():
    assert not smeglib.has_ctrl_layout(smeglib.build_ctrl(RECORDS))
    full = smeglib.build_ctrl(RECORDS, trailer=True)
    assert smeglib.has_ctrl_layout(full) and smeglib.has_trailer(full)


def test_the_fixtures_emit_the_stock_count_field(tmp_path):
    """The fixture once wrote the record count as one byte; stock has a u32 at 0x2c (#68)."""
    path = tmp_path / "ctrl.bin"
    helpers.write_ctrl(str(path), [(1, 0xDEADBEEF, "/NAV/x.bin")])
    buf = path.read_bytes()
    assert struct.unpack(">I", buf[smeglib.CTRL_COUNT : smeglib.CTRL_HEADER])[0] == 1
    assert len(buf) == smeglib.CTRL_HEADER + smeglib.CTRL_RECORD  # no trailer, as designed


def test_patch_ctrl_record_rewrites_only_the_matching_record():
    buf = bytearray(smeglib.build_ctrl(RECORDS))
    smeglib.patch_ctrl_record(buf, "/NAV/system.bin", 0x12345678, 0xCAFEBABE, where="ctrl")
    out = bytes(buf)
    first = smeglib.CTRL_HEADER + smeglib.CTRL_VALUE_OFF
    assert struct.unpack_from(">I", out, first)[0] == 0xCAFEBABE
    # the record that was not named still holds its own value
    second = smeglib.CTRL_HEADER + smeglib.CTRL_RECORD + smeglib.CTRL_VALUE_OFF
    assert struct.unpack_from(">I", out, second)[0] == 0x13CC


def test_patch_ctrl_record_refuses_a_wrong_old_crc():
    buf = bytearray(smeglib.build_ctrl(RECORDS))
    with pytest.raises(SystemExit) as e:
        smeglib.patch_ctrl_record(buf, "/NAV/system.bin", 0x1, 0x2)
    assert "expected" in str(e.value)


def test_patch_ctrl_record_refuses_a_missing_or_duplicated_record():
    with pytest.raises(SystemExit) as e:
        smeglib.patch_ctrl_record(bytearray(smeglib.build_ctrl(RECORDS)), "/NAV/nope.bin", 0x1, 0x2)
    assert "no record" in str(e.value)

    dup = bytearray(smeglib.build_ctrl(RECORDS + RECORDS))
    with pytest.raises(SystemExit) as e:
        smeglib.patch_ctrl_record(dup, "/NAV/system.bin", 0x12345678, 0x2)
    assert "more than one" in str(e.value)


# ------------------------------------------------------------- the .inf helpers (#68)


def test_inf_fields_read_and_rewrite_round_trip():
    blob = b"CRC32: -258767625\r\nSIZE: 10\r\nSIZE_1: 4096\r\n"
    assert smeglib.read_inf_field(blob, "CRC32") == 0xF09384F7
    assert smeglib.read_inf_fields(blob, ("SIZE", "SIZE_1", "SIZE_32")) == {
        "SIZE": 10,
        "SIZE_1": 4096,
    }
    # rewritten signed, as every stock .inf writes a CRC above 0x7fffffff
    assert b"CRC32: -268435456\r\n" in smeglib.rewrite_inf_field(blob, "CRC32", 0xF0000000)


def test_rewrite_inf_field_refuses_a_missing_field():
    with pytest.raises(SystemExit) as e:
        smeglib.rewrite_inf_field(b"SIZE: 1\r\n", "CRC32", 1)
    assert "no 'CRC32:' field" in str(e.value)


def test_roundup_matches_the_size_block_formula():
    assert smeglib.roundup(0, 1024) == 0
    assert smeglib.roundup(1, 1024) == 1024
    assert smeglib.roundup(1024, 1024) == 1024
    assert smeglib.roundup(1025, 1024) == 2048


def test_crc_recover_agrees_with_the_shared_crc32_on_iso_hdlc():
    """`crc_recover` recovers unknown CRCs, so its generic CRC is its own — but where the
    parameters *are* CRC-32/ISO-HDLC it must be the same CRC-32 `smeglib` hands out, so the
    two cannot quietly drift apart."""
    iso_hdlc = (0x04C11DB7, 32, True, True, 0xFFFFFFFF, 0xFFFFFFFF)
    for data in (b"", b"123456789", bytes(range(256))):
        assert crc_recover.crc(data, *iso_hdlc) == smeglib.crc32(data)
