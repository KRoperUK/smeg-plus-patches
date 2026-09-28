"""`smeglib.ctrl_crc16`, the CheckType-3 value in `ctrl` manifests (#197).

The algorithm was reproduced against every loose type-3 file in the stock package, which
cannot ship here. These pin the parts that are easy to get wrong without it: the table is
built from the REFLECTED polynomial (0xD415; the normal form 0xA82B gives different values),
the result bytes are swapped, and the 16-bit value is sign-extended.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tools"))

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
