"""Patched `ctrl` files keep a valid trailing CRC32, as every stock one has.

Every stock `ctrl.bin`, `<MODULE>_ctrl.bin` and `system_ctrl.bin` ends in a CRC32 of the
bytes before it. The patchers rewrote the records with `swap_crc` and left that trailer as
the stock value, so every patched package carried three stale trailers. Units accepted those
packages, which suggests the trailer is not checked - but that is inferred, and a package
that looks like stock is the safer thing to hand an updater.

The synthetic fixtures carry no trailer, so these tests add one the way stock files have it,
keeping the checksum chain above each file intact, then patch and check.
"""

import json
import os
import struct
import subprocess
import sys
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
TOOLS = os.path.join(ROOT, "tools")
sys.path.insert(0, HERE)
sys.path.insert(0, TOOLS)

import helpers  # noqa: E402
import media_helpers as mh  # noqa: E402
from smeglib import crc32, has_trailer, refresh_trailer, swap_crc  # noqa: E402


def with_trailer(buf):
    return bytes(buf) + struct.pack(">I", crc32(bytes(buf)))


def add_trailers(pkg, chain):
    """Give each file in `chain` (lowest first) a stock-style trailer.

    Each file's record in the next one up is re-pointed before that file gets its own
    trailer, so the checksum chain stays intact all the way to `ctrl.bin`.
    """
    recorded = {rel: (Path(pkg) / rel).read_bytes() for rel in chain}  # as each parent holds it
    for i, rel in enumerate(chain):
        path = Path(pkg) / rel
        new = with_trailer(path.read_bytes())
        path.write_bytes(new)
        if i + 1 < len(chain):
            parent = Path(pkg) / chain[i + 1]
            parent.write_bytes(swap_crc(parent.read_bytes(), crc32(recorded[rel]), crc32(new), rel))


def run(*args):
    return subprocess.run([sys.executable, *map(str, args)], capture_output=True, text=True)


def test_refresh_leaves_a_file_without_a_trailer_alone():
    assert refresh_trailer(b"no trailer here", b"changed records") == b"changed records"


def test_refresh_recomputes_a_trailer_that_was_valid():
    old = with_trailer(b"records v1")
    new = refresh_trailer(old, b"records v2" + old[-4:])
    assert has_trailer(new) and new[:-4] == b"records v2"


def test_patch_smeg_keeps_module_and_root_trailers_valid(tmp_path):
    src = tmp_path / "SMEG_PLUS_UPG"
    src.mkdir()
    info = helpers.build_package(str(src), variant="NAV")
    add_trailers(src, ["NAV_ctrl.bin", "ctrl.bin"])

    spec = tmp_path / "p.json"
    spec.write_text(json.dumps(helpers.patch_spec(variant="NAV")))
    out = tmp_path / "out"
    r = run(os.path.join(TOOLS, "patch_smeg.py"), "--src", src, "--out", out, "--patches", spec)
    assert r.returncode == 0, r.stderr

    mod, root = (out / "NAV_ctrl.bin").read_bytes(), (out / "ctrl.bin").read_bytes()
    assert mod != (src / "NAV_ctrl.bin").read_bytes(), "the patch changed nothing"
    assert has_trailer(mod) and has_trailer(root)
    assert struct.pack(">I", crc32(mod)) in root, "root records the refreshed module ctrl"
    assert info  # the fixture described what it built


def test_patch_media_keeps_all_three_trailers_valid(tmp_path):
    pkg = tmp_path / "SMEG_PLUS_UPG"
    pkg.mkdir()
    mh.build_media_package(str(pkg))
    add_trailers(pkg, ["NAV/system_ctrl.bin", "NAV_ctrl.bin", "ctrl.bin"])

    tree = tmp_path / "tree"
    tool = os.path.join(TOOLS, "patch_media.py")
    r = run(tool, "extract", "--package", pkg, "--module", "NAV", "--tree", tree)
    assert r.returncode == 0, r.stderr
    (tree / "ring_tones" / "ring1RT.wav").write_bytes(mh.wav_bytes(frames=2000))
    out = tmp_path / "out"
    r = run(tool, "apply", "--package", pkg, "--module", "NAV", "--tree", tree, "--out", out)
    assert r.returncode == 0, r.stderr

    sys_ctrl = (out / "NAV" / "system_ctrl.bin").read_bytes()
    mod, root = (out / "NAV_ctrl.bin").read_bytes(), (out / "ctrl.bin").read_bytes()
    assert has_trailer(sys_ctrl) and has_trailer(mod) and has_trailer(root)
    assert struct.pack(">I", crc32(sys_ctrl)) in mod
    assert struct.pack(">I", crc32(mod)) in root
