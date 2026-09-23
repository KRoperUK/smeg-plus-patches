"""Tests for the CRC parameter recovery.

The strongest test available here is that the tool recovers *published* parameterisations from
samples it was not told the answer to — so most of these run it against the standard CRC-16
variants. That matters more than usual: a recovery tool that fails silently reports "not a
CRC", and that conclusion is only worth anything if the tool demonstrably recovers real ones.

The search is restricted with `polys=` so the suite does not scan 65536 candidates per case.
"""

import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "tools"))

import crc_recover as cr  # noqa: E402

# eight distinct messages in two lengths, so init and xorout are separately identifiable
MESSAGES = [bytes([(i * 37 + 11 + j) & 0xFF for j in range(24)]) for i in range(5)]
MESSAGES += [bytes([(i * 53 + 7 + j) & 0xFF for j in range(17)]) for i in range(5)]

# the published parameters, against which recovery is checked
VARIANTS = [
    ("CRC-16/MODBUS", 0x8005, 0xFFFF, True, True, 0x0000),
    ("CRC-16/CCITT-FALSE", 0x1021, 0xFFFF, False, False, 0x0000),
    ("CRC-16/XMODEM", 0x1021, 0x0000, False, False, 0x0000),
    ("CRC-16/ARC", 0x8005, 0x0000, True, True, 0x0000),
    ("CRC-16/USB", 0x8005, 0xFFFF, True, True, 0xFFFF),
    ("CRC-16/DNP", 0x3D65, 0x0000, True, True, 0xFFFF),
    ("CRC-16/KERMIT", 0x1021, 0x0000, True, True, 0x0000),
    ("CRC-16/X25", 0x1021, 0xFFFF, True, True, 0xFFFF),
]


def samples_for(poly, init, refin, refout, xorout):
    return [(m, cr.crc(m, poly, 16, refin, refout, init, xorout)) for m in MESSAGES]


@pytest.mark.parametrize("name, poly, init, refin, refout, xorout", VARIANTS)
def test_recovers_every_standard_variant(name, poly, init, refin, refout, xorout):
    got = cr.recover(samples_for(poly, init, refin, refout, xorout), 16, polys=[poly])
    assert got, "%s not recovered" % name
    assert got["name"] == name
    assert (got["poly"], got["refin"], got["refout"]) == (poly, refin, refout)


def test_table_driven_crc_matches_the_reference():
    """The bug that made this tool lie: reflecting in the table but indexing with a raw byte.

    With that bug every reflected variant failed to recover, and the tool reported "not a CRC"
    for all of them — a false negative presented as a finding.
    """
    msg = bytes(range(64))
    for poly in (0x1021, 0x8005, 0x3D65):
        table = cr.table_for(poly, 16)
        for refin in (False, True):
            assert cr.crc0(msg, table, 16, refin) == cr.crc(msg, poly, 16, refin, False, 0, 0)


def test_needs_a_repeated_length():
    """Without two samples of one length nothing is constrained, and it must say so."""
    samples = [(b"a" * (10 + i), 0x1234) for i in range(4)]  # all different lengths
    assert cr.recover(samples, 16, polys=[0x1021]) is None


def test_rejects_a_checksum_that_is_not_a_crc():
    """A plain byte sum must not be mistaken for a CRC."""
    samples = [(m, sum(m) & 0xFFFF) for m in MESSAGES]
    assert cr.recover(samples, 16, polys=[0x1021, 0x8005, 0x3D65]) is None


def test_output_reflection_does_not_break_the_differential():
    """`refout` reverses the final value, and a reversal does not commute with XOR.

    Comparing a reversed differential against an unreversed one made every reflected variant
    unrecoverable, so this pins the property rather than the implementation.
    """
    got = cr.recover(samples_for(0x8005, 0xFFFF, True, True, 0x0000), 16, polys=[0x8005])
    assert got and got["refout"] is True


def test_init_and_xorout_are_not_uniquely_identifiable():
    """The documented degeneracy: a different (init, xorout) reproduces the same CRCs.

    Recorded as a test because a reader could otherwise treat the recovered pair as canonical.
    """
    truth = samples_for(0x8005, 0xFFFF, True, True, 0x0000)
    alt = [(m, cr.crc(m, 0x8005, 16, True, True, 0x7FFC, 0xC001)) for m in MESSAGES]
    assert [c for _, c in truth] == [c for _, c in alt]


def test_full_scan_finds_a_variant_without_being_told_the_polynomial():
    """One end-to-end scan, at width 8 so it is a few hundred candidates rather than 65536."""
    msgs = [bytes([(i * 31 + j) & 0xFF for j in range(12)]) for i in range(4)]
    samples = [(m, cr.crc(m, 0x07, 8, False, False, 0x00, 0x00)) for m in msgs]
    got = cr.recover(samples, 8)
    assert got and got["poly"] == 0x07 and got["width"] == 8
    assert all(cr.crc(m, 0x07, 8, False, False, 0, 0) == w for m, w in samples)
