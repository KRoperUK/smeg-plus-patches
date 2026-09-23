"""Tests for the USB stick preparation.

The copy and verification logic is deliberately separated from the OS probing, so all of it
is testable with ordinary temp directories — no removable media, and nothing to unplug.

The two failures this exists to catch are a **truncated copy** (a stick pulled mid-write) and
**AppleDouble litter**, so both have tests that make them happen rather than asserting the
happy path works.
"""

import os
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
TOOLS = os.path.join(ROOT, "tools")
sys.path.insert(0, HERE)
sys.path.insert(0, TOOLS)

import helpers  # noqa: E402
import prepare_usb  # noqa: E402


def run(*args):
    return subprocess.run([sys.executable, *args], capture_output=True, text=True)


def make_package(root, variant="NAV", contract=True):
    os.makedirs(root, exist_ok=True)
    info = helpers.build_package(root, variant=variant)
    if contract:
        with open(os.path.join(root, "contract.dat"), "wb") as fh:
            fh.write(b"contract")
    return info


@pytest.fixture()
def pkg(tmp_path):
    p = tmp_path / "SMEG_PLUS_UPG"
    make_package(str(p))
    return p


# ------------------------------------------------------------------ junk


def test_appledouble_and_ds_store_are_junk():
    assert prepare_usb.is_junk("._f_BigQuick.bin")
    assert prepare_usb.is_junk(".DS_Store")
    assert not prepare_usb.is_junk("f_BigQuick.bin")


def test_count_junk_finds_files_and_directories(tmp_path):
    (tmp_path / "._a").write_bytes(b"x")
    (tmp_path / ".DS_Store").write_bytes(b"x")
    (tmp_path / "keep").write_bytes(b"x")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "._b").write_bytes(b"x")
    got = sorted(os.path.basename(p) for p in prepare_usb.count_junk(str(tmp_path)))
    assert got == [".DS_Store", "._a", "._b"]


def test_copy_tree_skips_junk(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "keep.bin").write_bytes(b"data")
    (src / "._keep.bin").write_bytes(b"macos litter")
    (src / ".DS_Store").write_bytes(b"litter")
    dst = tmp_path / "dst"
    dst.mkdir()
    top, names = prepare_usb.copy_tree(str(src), str(dst))
    assert names == ["keep.bin"]
    assert sorted(os.listdir(top)) == ["keep.bin"]


# ------------------------------------------------------------- truncation


def test_verify_copy_catches_a_truncated_file(tmp_path):
    """The mid-copy removal, reproduced: a short file on the stick must be caught."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "f_BigQuick.bin").write_bytes(b"\xab" * 4096)
    dst = tmp_path / "dst"
    dst.mkdir()
    top, _ = prepare_usb.copy_tree(str(src), str(dst))
    with open(os.path.join(top, "f_BigQuick.bin"), "wb") as fh:
        fh.write(b"\xab" * 1000)  # the stick was pulled
    bad = prepare_usb.verify_copy(str(src), top)
    assert bad and "truncated" in bad[0][1]


def test_verify_copy_catches_a_missing_file(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "a.bin").write_bytes(b"x")
    dst = tmp_path / "dst"
    dst.mkdir()
    top, _ = prepare_usb.copy_tree(str(src), str(dst))
    os.remove(os.path.join(top, "a.bin"))
    bad = prepare_usb.verify_copy(str(src), top)
    assert bad and bad[0][1] == "not on the stick"


def test_verify_copy_passes_on_a_good_copy(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "a.bin").write_bytes(b"x" * 100)
    sub = src / "AppBin"
    sub.mkdir()
    (sub / "b.bin").write_bytes(b"y" * 50)
    dst = tmp_path / "dst"
    dst.mkdir()
    top, _ = prepare_usb.copy_tree(str(src), str(dst))
    assert prepare_usb.verify_copy(str(src), top) == []


# ----------------------------------------------------------------- layout


def test_a_complete_package_has_no_layout_problems(pkg):
    assert prepare_usb.check_layout(str(pkg)) == []


def test_missing_contract_is_a_layout_problem(tmp_path):
    p = tmp_path / "SMEG_PLUS_UPG"
    make_package(str(p), contract=False)
    problems = prepare_usb.check_layout(str(p))
    assert any("contract.dat" in x for x in problems)


def test_missing_app_image_is_a_layout_problem(tmp_path):
    p = tmp_path / "SMEG_PLUS_UPG"
    info = make_package(str(p))
    os.remove(info["app_image"])
    problems = prepare_usb.check_layout(str(p))
    assert any("f_BigQuick.bin" in x for x in problems)


def test_missing_manifest_is_a_layout_problem(tmp_path):
    p = tmp_path / "SMEG_PLUS_UPG"
    make_package(str(p))
    os.remove(os.path.join(str(p), "ctrl.bin"))
    problems = prepare_usb.check_layout(str(p))
    assert any("ctrl.bin" in x for x in problems)


# -------------------------------------------------------------- the CLI


def test_dry_run_copies_nothing(pkg, tmp_path):
    target = tmp_path / "stick"
    target.mkdir()
    r = run(
        os.path.join(TOOLS, "prepare_usb.py"),
        "--package",
        str(pkg),
        "--target",
        str(target),
        "--dry-run",
        "--force",
    )
    assert r.returncode == 0, r.stderr
    assert os.listdir(target) == []


def test_a_good_copy_succeeds_and_lands_the_package(pkg, tmp_path):
    target = tmp_path / "stick"
    target.mkdir()
    r = run(
        os.path.join(TOOLS, "prepare_usb.py"),
        "--package",
        str(pkg),
        "--target",
        str(target),
        "--force",
    )
    assert r.returncode == 0, r.stderr
    landed = os.path.join(str(target), "SMEG_PLUS_UPG")
    assert os.path.isfile(os.path.join(landed, "ctrl.bin"))
    assert os.path.isfile(os.path.join(landed, "contract.dat"))


def test_junk_on_the_stick_fails_rather_than_warning(pkg, tmp_path):
    """`._*` is a failure, not a warning - the updater does not expect it.

    The issue is explicit about this, and a warning would be ignored in practice, so the
    exit code has to be non-zero. Scoped to the copied package: the litter has to be inside it.
    """
    target = tmp_path / "stick"
    target.mkdir()
    landed = target / "SMEG_PLUS_UPG"
    landed.mkdir()
    (landed / "._control_guard").write_bytes(b"litter")
    r = run(
        os.path.join(TOOLS, "prepare_usb.py"),
        "--package",
        str(pkg),
        "--target",
        str(target),
        "--force",
    )
    assert r.returncode != 0
    assert "AppleDouble" in (r.stdout + r.stderr)


def test_junk_outside_the_package_is_ignored(pkg, tmp_path):
    """A stick legitimately holds other things.

    Counting litter elsewhere would fail the copy for a reason that has nothing to do with
    the package - which is what happened on the first real stick this was run against, where
    an unrelated older copy carried 988 `._*` files.
    """
    target = tmp_path / "stick"
    target.mkdir()
    (target / "._SMEG_PLUS_UPG_somethingelse").write_bytes(b"not our package")
    (target / ".DS_Store").write_bytes(b"nor this")
    r = run(
        os.path.join(TOOLS, "prepare_usb.py"),
        "--package",
        str(pkg),
        "--target",
        str(target),
        "--force",
    )
    assert r.returncode == 0, r.stdout + r.stderr


def test_it_refuses_to_write_into_an_existing_package(pkg, tmp_path):
    """Copying into a directory that already holds a package merges the two.

    The result still passes every checksum its own manifests declare, so nothing downstream
    notices - which is how a stick ends up flashing something nobody built. Found on the
    first real stick, so this is not hypothetical.
    """
    target = tmp_path / "stick"
    target.mkdir()
    landed = target / "SMEG_PLUS_UPG"
    landed.mkdir()
    (landed / "leftover.bin").write_bytes(b"from the previous package")
    r = run(
        os.path.join(TOOLS, "prepare_usb.py"),
        "--package",
        str(pkg),
        "--target",
        str(target),
        # --force past the filesystem check a temp directory on APFS trips; the merge
        # refusal is what this test is about and it is checked after that one
        "--force",
    )
    assert r.returncode != 0
    assert "already exists and is not empty" in (r.stdout + r.stderr)


def test_verify_copy_reports_a_stale_file_the_source_does_not_have(tmp_path):
    """The other direction: extra files on the stick, not just missing ones."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "a.bin").write_bytes(b"x")
    dst = tmp_path / "dst"
    dst.mkdir()
    top, _ = prepare_usb.copy_tree(str(src), str(dst))
    assert prepare_usb.verify_copy(str(src), top) == []
    with open(os.path.join(top, "stale.bin"), "wb") as fh:
        fh.write(b"left over from the last copy")
    bad = prepare_usb.verify_copy(str(src), top)
    assert bad and bad[0][0] == "stale.bin" and "stale file" in bad[0][1]


def test_a_bad_layout_is_refused_before_anything_is_copied(tmp_path):
    p = tmp_path / "SMEG_PLUS_UPG"
    make_package(str(p), contract=False)
    target = tmp_path / "stick"
    target.mkdir()
    r = run(
        os.path.join(TOOLS, "prepare_usb.py"),
        "--package",
        str(p),
        "--target",
        str(target),
        "--force",
    )
    assert r.returncode != 0
    assert os.listdir(target) == []


def test_it_refuses_to_copy_the_package_into_itself(tmp_path):
    p = tmp_path / "SMEG_PLUS_UPG"
    make_package(str(p))
    target = tmp_path / "stick"
    target.mkdir()
    r = run(
        os.path.join(TOOLS, "prepare_usb.py"),
        "--package",
        str(p),
        "--target",
        str(p),
        "--force",
    )
    assert r.returncode != 0
    assert "into itself" in (r.stdout + r.stderr)


def test_the_target_is_printed_before_anything_is_written(pkg, tmp_path):
    """It touches removable media, so it has to say where it is about to write first."""
    target = tmp_path / "stick"
    target.mkdir()
    r = run(
        os.path.join(TOOLS, "prepare_usb.py"),
        "--package",
        str(pkg),
        "--target",
        str(target),
        "--dry-run",
        "--force",
    )
    lines = [ln for ln in r.stdout.splitlines() if ln.strip()]
    assert lines[0].startswith("package :")
    assert lines[1].startswith("target  :")
