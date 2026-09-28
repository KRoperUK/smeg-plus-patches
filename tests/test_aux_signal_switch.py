"""`aux-signal-switch` routes the real AUX signal event to the AUX handler.

The dispatch rewrite reorders eight words, so the risk is not a wrong byte but a message id
that used to go one way and now goes another. The window is replayed under the emulator on a
synthetic image carrying only the original words: every id must land where stock sends it,
except 0xcc, which must now reach the handler. The handler edits are decoded instead; their
behaviour was executed against the real image (see docs/AUX_SIGNAL.md), which the tests
cannot ship.
"""

import json
import os
import struct
import subprocess
import sys
from pathlib import Path

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
TOOLS = os.path.join(ROOT, "tools")
sys.path.insert(0, HERE)
sys.path.insert(0, TOOLS)

import helpers  # noqa: E402

PATCH_FILE = os.path.join(ROOT, "patches", "aux-signal-switch.json")
BASE = 0x01000000
WINDOW = 0x0230961C, 0x02309650  # from the id load to the >0xd9 chain
HANDLER_CASE, SHARED_D7_D9, DEFAULT, ABOVE_D9 = 0x02309FBC, 0x0230A190, 0x0230A664, 0x02309650
STOCK_WINDOW = {  # words not edited by the patch, which the window also executes
    0x0230961C: "801f0220",  # lwz r0,0x220(r31)
    0x02309620: "2f8000d9",  # cmpwi cr7,r0,0xd9
    0x02309624: "419e0b6c",  # beq cr7,0x0230a190
    0x0230963C: "419e0980",  # beq cr7,0x02309fbc
    0x0230964C: "48001018",  # b 0x0230a664
}
GET_SIGNAL = 0x025CCBE4  # C_BCM_HMI_AUDIO_CLIENT::Get_AUX_signal_status


def edits():
    spec = json.loads(Path(PATCH_FILE).read_text())
    return {int(p["addr"], 16): p for p in spec["variants"]["NAV"]["patches"]}


def stock_image():
    img = bytearray(DEFAULT - BASE + 0x100)  # every exit target must be mapped
    for addr, word in STOCK_WINDOW.items():
        img[addr - BASE : addr - BASE + 4] = bytes.fromhex(word)
    for addr, p in edits().items():
        img[addr - BASE : addr - BASE + 4] = bytes.fromhex(p["expect"])
    return bytes(img)


def exit_of(message_id, patched):
    """Run the dispatch window for one message id; return the first address outside it."""
    ppcemu = pytest.importorskip("ppcemu")
    from unicorn import UC_HOOK_CODE, ppc_const

    e = ppcemu.Emulator(stock_image())
    if patched:
        e.apply_patch_file(PATCH_FILE, "NAV")
    e.write_u32(ppcemu.SCRATCH + 0x220, message_id)
    out = []

    def leave(uc, addr, _size, _ctx):
        if not WINDOW[0] <= addr < WINDOW[1]:
            out.append(addr)
            uc.emu_stop()

    e.uc.hook_add(UC_HOOK_CODE, leave)
    e.uc.reg_write(ppc_const.UC_PPC_REG_31, ppcemu.SCRATCH)
    e.uc.emu_start(WINDOW[0], 0, count=40)
    return out[0]


def test_the_signal_event_reaches_the_aux_handler_only_when_patched():
    pytest.importorskip("unicorn")
    assert exit_of(0xCC, patched=False) == DEFAULT
    assert exit_of(0xCC, patched=True) == HANDLER_CASE


@pytest.mark.parametrize("message_id", [0xCB, 0xD7, 0xD9, 0xD8, 0xCA, 0xDA, 0x385, 0x10, 0])
def test_every_other_message_goes_where_stock_sends_it(message_id):
    pytest.importorskip("unicorn")
    assert exit_of(message_id, patched=True) == exit_of(message_id, patched=False)


def test_stock_routes_are_what_the_description_claims():
    """Guards the synthetic window itself: if these fail, the fixture is wrong, not the patch."""
    pytest.importorskip("unicorn")
    assert exit_of(0xCB, patched=False) == HANDLER_CASE
    assert exit_of(0xD7, patched=False) == SHARED_D7_D9
    assert exit_of(0xDA, patched=False) == ABOVE_D9


def test_handler_call_now_targets_the_signal_query():
    """`lis r9,0x25d` stays; the new `addi` low half must land on Get_AUX_signal_status."""
    w = struct.unpack(">I", bytes.fromhex(edits()[0x0230338C]["bytes"]))[0]
    assert w >> 26 == 14 and (w >> 21) & 31 == 9 and (w >> 16) & 31 == 9, "addi r9,r9,imm"
    imm = w & 0xFFFF
    imm = imm - 0x10000 if imm & 0x8000 else imm
    assert (0x025D << 16) + imm == GET_SIGNAL


@pytest.mark.parametrize("addr", [0x02303398, 0x0230342C])
def test_result_is_read_as_a_byte(addr):
    p = edits()[addr]
    before, after = (struct.unpack(">I", bytes.fromhex(p[k]))[0] for k in ("expect", "bytes"))
    assert before >> 26 == 32 and after >> 26 == 34, "lwz -> lbz"
    assert before & 0x03FFFFFF == after & 0x03FFFFFF, "same register and offset"


def test_shipped_definition_applies_and_cascades(tmp_path):
    img = bytearray(helpers.make_image_with_build("5.43.A.R2", size=0x1310000))
    for addr, p in edits().items():
        img[addr - BASE : addr - BASE + 4] = bytes.fromhex(p["expect"])
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
    patched = helpers.inflate_container((out / "NAV" / "AppBin" / "f_BigQuick.bin").read_bytes())
    for addr, p in edits().items():
        assert patched[addr - BASE : addr - BASE + 4].hex() == p["bytes"], hex(addr)
