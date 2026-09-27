"""`aux-boot-restore` lets AUX's source request take part in C_MGR_SRC's boot restore.

Two edits. `AddRequest` skips the ScheduledInit/restore block for a request whose PrOnly
byte is set, and AUX's is the request that sets it; `StartUp` restores Last_Source_Priority,
which has to equal AUX's 20 for the comparison to match. Neither check needs firmware:

  1. each `expect` and `bytes` decodes to the instruction the definition claims, so a wrong
     branch encoding or register fails here rather than on a car, and
  2. the shipped definition applies through `patch_smeg.py`, against a synthetic image
     carrying the expect bytes at both addresses.
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

PATCH_FILE = os.path.join(ROOT, "patches", "aux-boot-restore.json")
PRONLY_BRANCH = 0x01698474  # C_MGR_SRC::AddRequest
PRIORITY_LOAD = 0x01699444  # C_MGR_SRC::StartUp


def word(hexstr):
    return struct.unpack(">I", bytes.fromhex(hexstr))[0]


def edits():
    spec = json.loads(Path(PATCH_FILE).read_text())
    return {int(p["addr"], 16): p for p in spec["variants"]["NAV"]["patches"]}


def test_first_edit_nops_the_pronly_branch_back_into_addrequest():
    """`bne cr7` to 0x01698364, the jump past the ScheduledInit block, becomes a nop."""
    p = edits()[PRONLY_BRANCH]
    w = word(p["expect"])
    assert w >> 26 == 16, "expect should be a conditional branch (opcode 16)"
    assert (w >> 21) & 0x1F == 4, "BO=4: branch if the condition bit is clear, i.e. bne"
    assert (w >> 16) & 0x1F == 30, "BI=30: cr7[eq], set by the preceding cmpwi cr7,r0,0"
    disp = w & 0xFFFC
    disp = disp - 0x10000 if disp & 0x8000 else disp
    assert PRONLY_BRANCH + disp == 0x01698364, "it must be the jump past the restore block"
    assert p["bytes"] == "60000000", "replaced by a nop"


def test_second_edit_loads_auxs_priority_instead_of_the_saved_one():
    """`lwz r0, 8(r1)` (saved Last_Source_Priority) becomes `li r0, 20`."""
    p = edits()[PRIORITY_LOAD]
    w = word(p["expect"])
    assert (w >> 26, (w >> 21) & 0x1F, (w >> 16) & 0x1F, w & 0xFFFF) == (32, 0, 1, 8)
    w = word(p["bytes"])
    assert w >> 26 == 14 and (w >> 16) & 0x1F == 0, "li form: addi rD, 0, imm"
    assert (w >> 21) & 0x1F == 0, "into r0, which 0x01699448 stores to this+0xac"
    assert w & 0xFFFF == 20, "AUX's priority, from the spy request-list dump"


def test_shipped_definition_applies_and_cascades(tmp_path):
    """End-to-end: patches/aux-boot-restore.json applies through patch_smeg.py."""
    img = bytearray(helpers.make_image_with_build("5.43.A.R2", size=0x6A0000))
    for addr, p in edits().items():
        off = addr - 0x01000000
        img[off : off + 4] = bytes.fromhex(p["expect"])

    src = tmp_path / "SMEG_PLUS_UPG"
    src.mkdir()
    helpers.build_package(str(src), variant="NAV", img=bytes(img))

    out = tmp_path / "out"
    r = subprocess.run(
        [
            sys.executable,
            os.path.join(TOOLS, "patch_smeg.py"),
            "--src",
            str(src),
            "--out",
            str(out),
            "--patches",
            PATCH_FILE,
            "--only",
            "NAV",
        ],
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, r.stderr

    bq = out / "NAV" / "AppBin" / "f_BigQuick.bin"
    patched = helpers.inflate_container(bq.read_bytes())
    for addr, p in edits().items():
        off = addr - 0x01000000
        assert patched[off : off + 4].hex() == p["bytes"], "edit at %#x did not land" % addr
