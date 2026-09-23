"""Tests for the cartography name-pool reader/writer.

The pools are inside a vendor `*.BIN`, so the fixtures here are synthesised. The one that
matters is `test_empty_fields_survive`: the real UK file only round-trips when its 78 empty
fields are kept, and filtering them is the mistake this format invites.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "tools"))

import cartography_names as cn  # noqa: E402


def test_round_trip_is_byte_identical(tmp_path):
    raw = b"ABBEY HEY\\MANCHESTER\x00ARDWICK\\MANCHESTER\x00BL2 6 RADCLIFFE\\MANCHESTER\x00"
    p = tmp_path / "pool.dat"
    p.write_bytes(raw)
    fields = cn.read_pool(p)
    out = tmp_path / "out.dat"
    cn.write_pool(out, fields)
    assert out.read_bytes() == raw


def test_empty_fields_survive(tmp_path):
    """The real file has 78 of these, and dropping them breaks the round-trip."""
    raw = b"A\\X\x00\x00B\\X\x00\x00\x00"
    p = tmp_path / "pool.dat"
    p.write_bytes(raw)
    fields = cn.read_pool(p)
    assert b"" in fields
    out = tmp_path / "out.dat"
    cn.write_pool(out, fields)
    assert out.read_bytes() == raw
    # ...and the naive thing really does lose it
    assert b"\x00".join(f for f in fields if f) + b"\x00" != raw


def test_non_empty_filters(tmp_path):
    p = tmp_path / "pool.dat"
    p.write_bytes(b"ONE\x00\x00TWO\x00")
    assert cn.non_empty(cn.read_pool(p)) == [b"ONE", b"TWO"]


def test_cli_round_trip_reports_identical(tmp_path, capsys):
    p = tmp_path / "pool.dat"
    p.write_bytes(b"MEAVER ROAD\x00B3293\x00\x00CHURCHTOWN\x00")
    assert cn.main(["round-trip", str(p)]) == 0
    assert "byte-identical" in capsys.readouterr().out


def test_cli_emit_writes_the_same_bytes(tmp_path):
    raw = b"VIA ROMA\x00\x00BAR SPORT\x00"
    src = tmp_path / "in.dat"
    src.write_bytes(raw)
    dst = tmp_path / "out.dat"
    cn.main(["emit", str(src), "--out", str(dst)])
    assert dst.read_bytes() == raw
