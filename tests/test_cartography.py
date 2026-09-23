"""Tests for the cartography metadata reader.

The real files are inside vendor packages, so every fixture here is synthesised. The ones that
matter are the mistakes a format invites: the empty fields in a name pool, the name stored
*twice* inside an SCC record, and a CCT record whose fields are positional rather than
labelled.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "tools"))

import cartography as cg  # noqa: E402

# --------------------------------------------------------------- name pools


def test_name_pool_round_trips_byte_for_byte(tmp_path):
    raw = b"ABBEY HEY\\MANCHESTER\x00ARDWICK\\MANCHESTER\x00BL2 6 RADCLIFFE\\MANCHESTER\x00"
    p = tmp_path / "pool.dat"
    p.write_bytes(raw)
    out = tmp_path / "out.dat"
    cg.write_pool(out, cg.read_pool(p))
    assert out.read_bytes() == raw


def test_empty_fields_survive(tmp_path):
    """The real UK pool has 78 of these, and dropping them breaks the round-trip."""
    raw = b"A\\X\x00\x00B\\X\x00\x00\x00"
    p = tmp_path / "pool.dat"
    p.write_bytes(raw)
    fields = cg.read_pool(p)
    assert b"" in fields
    out = tmp_path / "out.dat"
    cg.write_pool(out, fields)
    assert out.read_bytes() == raw
    assert b"\x00".join(f for f in fields if f) + b"\x00" != raw


def test_non_empty_filters(tmp_path):
    p = tmp_path / "pool.dat"
    p.write_bytes(b"ONE\x00\x00TWO\x00")
    assert cg.non_empty(cg.read_pool(p)) == [b"ONE", b"TWO"]


def test_cli_names_round_trip_reports_identical(tmp_path, capsys):
    p = tmp_path / "pool.dat"
    p.write_bytes(b"MEAVER ROAD\x00B3293\x00\x00CHURCHTOWN\x00")
    assert cg.main(["names-round-trip", str(p)]) == 0
    assert "byte-identical" in capsys.readouterr().out


# --------------------------------------------------------------- .inf sidecars


def test_parse_inf_splits_checksum_from_fields(tmp_path):
    p = tmp_path / "thing.inf"
    p.write_bytes(b"4c75a293\r\nVER:0\r\nTYPE:RELOCABLE\r\nSIZE:484\r\nENTRY:NO\r\n")
    first, fields = cg.parse_inf(p)
    assert first == "4c75a293"
    assert fields == {"VER": "0", "TYPE": "RELOCABLE", "SIZE": "484", "ENTRY": "NO"}


def test_parse_inf_tolerates_lf_only(tmp_path):
    p = tmp_path / "thing.inf"
    p.write_bytes(b"3de17348\nVER:M\nSUBVER:2.4.15\n")
    first, fields = cg.parse_inf(p)
    assert first == "3de17348"
    assert fields["SUBVER"] == "2.4.15"


# --------------------------------------------------------------- SCC records


def scc_record(first, second, payload):
    """Build one 92-byte record: two name fields of 41 bytes, then a 10-byte payload."""
    assert len(payload) == 10
    return first.ljust(41, b"\x00") + second.ljust(41, b"\x00") + payload


def test_parse_scc_reads_both_name_fields(tmp_path):
    data = scc_record(b"ST AGNES", b"ST AGNES", bytes(range(10)))
    data += scc_record(b"THE LIZARD", b"THE LIZARD", bytes(range(10, 20)))
    p = tmp_path / "scc.dst"
    p.write_bytes(data)
    recs = cg.parse_scc(p.read_bytes())
    assert len(recs) == 2
    assert recs[0][1] == "ST AGNES" and recs[0][2] == "ST AGNES"
    assert recs[0][3] == bytes(range(10))
    assert recs[1][1] == "THE LIZARD"
    assert recs[1][0] == 92  # the second record starts at the stride


def test_parse_scc_keeps_payload_as_bytes(tmp_path):
    """The payload is bit-packed and not decoded, so it must be reported as bytes."""
    payload = bytes.fromhex("15f4f70104031d019603")
    recs = cg.parse_scc(scc_record(b"X", b"X", payload))
    assert recs[0][3] == payload
    assert isinstance(recs[0][3], bytes)


# --------------------------------------------------------------- CCT.DAT


def cct_record(country, checktype, value, path):
    rec = bytearray(76)
    rec[0:3] = country
    rec[13] = checktype
    rec[14:22] = value
    rec[26 : 26 + len(path)] = path
    return bytes(rec)


def test_cct_decrypt_inverts_the_subtraction():
    key = bytes((i * 7 + 3) & 0xFF for i in range(cg.CCT_KEY_LEN))
    plain = cct_record(b"001", 1, b"4c75a293", b"/MAPPE/001/DESCRI.DAT")
    cipher = bytes((p + key[i % cg.CCT_KEY_LEN]) & 0xFF for i, p in enumerate(plain))
    assert cg.cct_decrypt(cipher, key) == plain


def test_cct_key_cycles_with_period_896():
    """A 900-byte body must wrap the key index, not run off it."""
    key = bytes(range(256)) * 4  # 1024, only the first 896 are used
    data = bytes(900)
    out = cg.cct_decrypt(data, key)
    assert out[0] == (0 - key[0]) & 0xFF
    assert out[896] == (0 - key[0]) & 0xFF


def test_parse_cct_reads_positional_fields():
    plain = cct_record(b"005", 1, b"1b526603", b"/MAPPE/005/DESCRI.DAT")
    plain += cct_record(b"012", 1, b"4deaa03f", b"/MAPPE/012/DESCRI.DAT")
    assert cg.parse_cct(plain) == [
        ("005", 1, "1b526603", "/MAPPE/005/DESCRI.DAT"),
        ("012", 1, "4deaa03f", "/MAPPE/012/DESCRI.DAT"),
    ]


def test_key_from_image_uses_the_symbol_offset(monkeypatch):
    monkeypatch.setattr(cg, "CCT_KEY_OFFSET", cg.IMAGE_BASE + 0x40)
    body = bytes(range(256)) * 4
    image = b"\x00" * 0x40 + body
    assert cg.key_from_image(image) == body[: cg.CCT_KEY_LEN]
    assert len(cg.key_from_image(image)) == 896


def test_key_from_image_rejects_a_short_image(monkeypatch, capsys):
    monkeypatch.setattr(cg, "CCT_KEY_OFFSET", cg.IMAGE_BASE + 0x40)
    try:
        cg.key_from_image(b"\x00" * 0x50)
    except SystemExit as e:
        assert "too short" in str(e)
    else:
        raise AssertionError("a short image should have been refused")
