"""Tests for the post-write verification in patch_smeg (issue #18).

The point of these is not that a good patch passes — the existing tests already cover a
successful run. It is that a *broken* one fails. A verification step that cannot fail is
decoration, so every check here is exercised with input designed to trip it.
"""

import json
import os
import subprocess
import sys
import zlib

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
TOOLS = os.path.join(ROOT, "tools")
sys.path.insert(0, HERE)
sys.path.insert(0, TOOLS)

import helpers  # noqa: E402
import patch_smeg  # noqa: E402

BASE = 0x01000000


def run(*args):
    return subprocess.run([sys.executable, *args], capture_output=True, text=True)


@pytest.fixture()
def pkg(tmp_path):
    src = tmp_path / "SMEG_PLUS_UPG"
    src.mkdir()
    info = helpers.build_package(str(src))
    spec = tmp_path / "spec.json"
    spec.write_text(
        json.dumps(helpers.patch_spec(variant=info["variant"], addr=info["patch_addr"]))
    )
    return src, spec, info


# ------------------------------------------------------------------ disassembly


def test_a_clean_instruction_sequence_disassembles():
    site = bytes.fromhex("386000014e800020")  # li r3,1 ; blr
    got = patch_smeg.check_site(site, "NAV", BASE, None)
    assert got == ["li r3, 1", "blr"]


def test_a_patch_that_is_not_instruction_aligned_is_refused():
    """Three bytes cannot be a PowerPC instruction, and the site would decode as garbage."""
    with pytest.raises(SystemExit) as e:
        patch_smeg.check_site(b"\x38\x60\x00", "NAV", BASE, None)
    assert "whole number of PowerPC instructions" in str(e.value)


def test_a_declared_disasm_must_match():
    site = bytes.fromhex("386000014e800020")
    patch_smeg.check_site(site, "NAV", BASE, "li r3, 1 ; blr")

    with pytest.raises(SystemExit) as e:
        patch_smeg.check_site(site, "NAV", BASE, "li r3, 0 ; blr")
    assert "declares" in str(e.value)


def test_the_check_is_skipped_not_faked_when_capstone_is_absent(monkeypatch):
    """patch_smeg declares no dependencies and must keep running without capstone.

    The failure mode to avoid is silently passing. Returning None makes the caller skip the
    check explicitly, rather than the site appearing to have been verified.
    """
    monkeypatch.setitem(sys.modules, "capstone", None)
    assert patch_smeg.disassemble(b"\x4e\x80\x00\x20") is None
    assert patch_smeg.check_site(b"\x4e\x80\x00\x20", "NAV", BASE, None) is None


def test_a_corrupt_bytes_string_is_refused_end_to_end(pkg, tmp_path):
    """A `bytes` field that is the wrong shape must stop the run, not land in the image."""
    src, spec, info = pkg
    bad = json.loads(spec.read_text())
    for name in bad["variants"]:
        bad["variants"][name]["patches"][0]["bytes"] = "386000"  # 3 bytes
    spec.write_text(json.dumps(bad))
    r = run(
        os.path.join(TOOLS, "patch_smeg.py"),
        "--src",
        str(src),
        "--out",
        str(tmp_path / "out"),
        "--patches",
        str(spec),
    )
    assert r.returncode != 0
    assert "PowerPC instructions" in (r.stdout + r.stderr)


# ------------------------------------------------------------ checksum chain


def test_a_wrong_crc_field_is_caught(tmp_path):
    """`.inf` names its file's CRC32 in text; a stale one has to fail the read-back."""
    d = tmp_path / "pkg"
    d.mkdir()
    (d / "f_BigQuick.bin.inf").write_bytes(b"CRC32: 12345\r\nTYPE:RELOCABLE\r\n")
    with pytest.raises(SystemExit) as e:
        patch_smeg.assert_crc_field(str(d), "f_BigQuick.bin.inf", patch_smeg.INF_CRC_RE, 999, "NAV")
    assert "declares CRC32 12345" in str(e.value)


def test_a_missing_crc_field_is_caught(tmp_path):
    d = tmp_path / "pkg"
    d.mkdir()
    (d / "f_BigQuick.bin.inf").write_bytes(b"TYPE:RELOCABLE\r\n")
    with pytest.raises(SystemExit) as e:
        patch_smeg.assert_crc_field(str(d), "f_BigQuick.bin.inf", patch_smeg.INF_CRC_RE, 1, "NAV")
    assert "no CRC field" in str(e.value)


def test_a_ctrl_record_that_lost_its_crc_is_caught(tmp_path):
    """ctrl records hold the CRC as a raw word, so the check looks for the bytes."""
    d = tmp_path / "pkg"
    d.mkdir()
    (d / "NAV_ctrl.bin").write_bytes(b"\x00" * 64)
    with pytest.raises(SystemExit) as e:
        patch_smeg.assert_crc_record(str(d), "NAV_ctrl.bin", 0xDEADBEEF, "NAV")
    assert "does not record CRC" in str(e.value)


def test_a_complete_run_verifies_every_level(pkg, tmp_path):
    """The happy path, asserting the read-back actually reported each level."""
    src, spec, info = pkg
    out = tmp_path / "out"
    r = run(
        os.path.join(TOOLS, "patch_smeg.py"),
        "--src",
        str(src),
        "--out",
        str(out),
        "--patches",
        str(spec),
    )
    assert r.returncode == 0, r.stderr
    assert "verified end to end" in r.stdout
    assert "ctrl.bin" in r.stdout and "verified" in r.stdout

    # and the CRCs it printed are the CRCs of the files it left behind
    bq = (out / info["variant"] / "AppBin" / "f_BigQuick.bin").read_bytes()
    raw = zlib.decompressobj()
    img = raw.decompress(bq[0x801:]) + raw.flush()
    assert patch_smeg.crc32(bq) in [
        int(line.split()[-1], 16) for line in r.stdout.splitlines() if "f_BigQuick.bin " in line
    ]
    assert len(img) > 0
