"""Tests for the release-to-release symbol diff.

The fixture models the real case rather than a convenient one: release B is release A
displaced by a constant, with one function genuinely changed. That is what 5.43 and 5.42 are,
and a diff that cannot tell the displacement from the real edit would report ~80% of the image
as different, which is exactly the mistake this tool exists to avoid.
"""

import json
import os
import struct
import subprocess
import sys


HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
TOOLS = os.path.join(ROOT, "tools")
sys.path.insert(0, TOOLS)

import symdiff  # noqa: E402

BASE = 0x01000000
SHIFT = 152


def make_release():
    """Three functions; B is A displaced by SHIFT with one byte changed in `gamma`."""
    a = bytearray(b"\x00" * 0x400)
    for off, words in (
        (0x000, [0x3D800100, 0x398C0040, 0x7D8903A6, 0x4E800020]),
        (0x100, [0x38600001, 0x4E800020]),
        (0x200, [0x38600000, 0x4E800020]),
    ):
        for i, w in enumerate(words):
            a[off + 4 * i : off + 4 * i + 4] = struct.pack(">I", w)

    b = bytearray(b"\xbb" * SHIFT) + bytes(a)
    b[SHIFT + 0x200 + 4] = 0x01  # gamma differs

    syms_a = {BASE: "alpha", BASE + 0x100: "beta", BASE + 0x200: "gamma"}
    syms_b = {
        BASE + SHIFT: "alpha",
        BASE + 0x100 + SHIFT: "beta",
        BASE + 0x200 + SHIFT: "gamma",
        BASE + 0x300 + SHIFT: "only_new_here",
    }
    return bytes(a), syms_a, bytes(b), syms_b


def test_the_displacement_is_derived_not_assumed():
    a, sa, b, sb = make_release()
    d = symdiff.diff(a, sa, BASE, b, sb, BASE)
    assert d["shift"] == SHIFT
    assert d["shift_agreement"] == d["moved_total"] == 3


def test_a_changed_function_is_not_called_identical():
    a, sa, b, sb = make_release()
    d = symdiff.diff(a, sa, BASE, b, sb, BASE)
    assert d["changed_names"] == ["gamma"]
    assert d["same_bytes"] == 2


def test_symbols_present_in_only_one_release_are_reported():
    a, sa, b, sb = make_release()
    d = symdiff.diff(a, sa, BASE, b, sb, BASE)
    assert d["only_in_b"] == ["only_new_here"]
    assert d["only_in_a"] == []


def test_a_patch_site_is_located_and_cleared_for_carrying():
    a, sa, b, sb = make_release()
    d = symdiff.diff(a, sa, BASE, b, sb, BASE, patch_addr=BASE + 0x100)
    p = d["patch"]
    assert p["function"] == "beta"
    assert p["b_addr_by_shift"] == BASE + 0x100 + SHIFT
    assert p["same_bytes_at_shift"] is True
    assert p["same_bytes_in_function"] is True


def test_a_patch_in_a_changed_function_is_not_cleared():
    """The answer has to be 'no' when the function moved *and* changed - that is the one
    worth re-deriving by hand."""
    a, sa, b, sb = make_release()
    d = symdiff.diff(a, sa, BASE, b, sb, BASE, patch_addr=BASE + 0x200)
    p = d["patch"]
    assert p["function"] == "gamma"
    assert p["same_bytes_at_shift"] is False
    assert p["same_bytes_in_function"] is False


def test_a_patch_address_with_no_symbol_is_handled():
    """Past the end of the image there is no containing symbol, and that must not crash.

    Note the asymmetry: symbol maps carry no sizes, so the *last* symbol in a run is given the
    rest of the image and an address like BASE+0x3F0 does resolve to it. That over-statement is
    documented; an address past the image is the case with genuinely no owner.
    """
    a, sa, b, sb = make_release()
    d = symdiff.diff(a, sa, BASE, b, sb, BASE, patch_addr=BASE + 0x1000)
    assert d["patch"]["function"] is None


def test_load_symbols_tolerates_header_lines(tmp_path):
    """Real symbol maps carry section headers and blank lines; they must not become symbols."""
    p = tmp_path / "symbols.txt"
    p.write_text(
        "Symbol table for f_BigQuick.bin\n"
        "\n"
        "01000000 T alpha\n"
        "01000100 T beta\n"
        "not-a-hex T ignored\n"
    )
    syms = symdiff.load_symbols(str(p))
    assert syms == {BASE: "alpha", BASE + 0x100: "beta"}


def test_the_cli_reports_and_exits_zero(tmp_path):
    a, sa, b, sb = make_release()
    (tmp_path / "a.bin").write_bytes(a)
    (tmp_path / "b.bin").write_bytes(b)
    (tmp_path / "sa.txt").write_text("".join("%08x T %s\n" % (k, v) for k, v in sa.items()))
    (tmp_path / "sb.txt").write_text("".join("%08x T %s\n" % (k, v) for k, v in sb.items()))
    r = subprocess.run(
        [
            sys.executable,
            os.path.join(TOOLS, "symdiff.py"),
            "--a",
            str(tmp_path / "a.bin"),
            str(tmp_path / "sa.txt"),
            "--b",
            str(tmp_path / "b.bin"),
            str(tmp_path / "sb.txt"),
        ],
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, r.stderr
    assert "shift        +152" in r.stdout


def test_the_cli_json_is_parseable(tmp_path):
    a, sa, b, sb = make_release()
    (tmp_path / "a.bin").write_bytes(a)
    (tmp_path / "b.bin").write_bytes(b)
    (tmp_path / "sa.txt").write_text("".join("%08x T %s\n" % (k, v) for k, v in sa.items()))
    (tmp_path / "sb.txt").write_text("".join("%08x T %s\n" % (k, v) for k, v in sb.items()))
    r = subprocess.run(
        [
            sys.executable,
            os.path.join(TOOLS, "symdiff.py"),
            "--a",
            str(tmp_path / "a.bin"),
            str(tmp_path / "sa.txt"),
            "--b",
            str(tmp_path / "b.bin"),
            str(tmp_path / "sb.txt"),
            "--json",
        ],
        capture_output=True,
        text=True,
    )
    doc = json.loads(r.stdout)
    assert doc["shift"] == SHIFT and doc["changed_names"] == ["gamma"]
