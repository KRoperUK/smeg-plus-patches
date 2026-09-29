"""Firmware-in-the-loop tests for the AUDIO_BT builds: YOUR OWN stock 5.43.A.R2 images, never CI.

The AUDIO_BT counterpart of `test_firmware_nav.py`, for the variants carried over from NAV.
Each module is a separate image, and runs when its variable is set:

    SMEG_AUDIO_BT_IMAGE=~/Downloads/SMEG_PLUS_UPG/AUDIO_BT/AppBin/f_BigQuick.bin \\
    SMEG_AUDIO_BT_256_IMAGE=~/Downloads/SMEG_PLUS_UPG/AUDIO_BT_256/AppBin/f_BigQuick.bin \\
        .venv/bin/python -m pytest -m firmware -q

The application functions are at the same addresses in both builds; the BSP routines the
scheduler calls (below the image) are not. Each test says what it stubs; a stub's return value
is an assumption, not an observation.
"""

import json
import os
import struct
import sys
from pathlib import Path

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "tools"))

FIRMWARE = "5.43.A.R2"
MODULES = {"AUDIO_BT": "SMEG_AUDIO_BT_IMAGE", "AUDIO_BT_256": "SMEG_AUDIO_BT_256_IMAGE"}

ADDREQ, EXEC_ALLOC, FORCE, SETNEXT = 0x01698004, 0x016972B4, 0x01697678, 0x01695438
BSP = {  # module -> (watchdog cancel, memcpy)
    "AUDIO_BT": (0x0058C6E4, 0x002CB648),
    "AUDIO_BT_256": (0x0058C5A4, 0x002CB508),
}
HANDLER = 0x023031DC
GET_SETTING, GET_SIGNAL = 0x025CB118, 0x025CCAA4
CLIENT_PTR, GET_DEVICE, SET_STATE = 0x022AD180, 0x022F3610, 0x022F374C
ACTIVATE = 0x0273A108

pytestmark = pytest.mark.firmware


@pytest.fixture(scope="module", params=sorted(MODULES))
def build(request):
    module = request.param
    path = os.environ.get(MODULES[module])
    if not path:
        pytest.skip("set %s to run" % MODULES[module])
    from appimage import inflate

    raw = Path(os.path.expanduser(path)).read_bytes()
    if len(raw) > 0x801 and raw[0x800] == 0x08:
        raw = inflate(raw)[1]
    return module, raw


def patch_file(name):
    return os.path.join(ROOT, "patches", name + ".json")


def sets_for(module):
    return sorted(
        p.stem
        for p in Path(ROOT, "patches").glob("*.json")
        if json.loads(p.read_text()).get("variants", {}).get(module, {}).get("firmware") == FIRMWARE
    )


def emulator(image):
    ppcemu = pytest.importorskip("ppcemu")
    pytest.importorskip("unicorn")
    return ppcemu, ppcemu.Emulator(image)


def reg(uc, n):
    from unicorn import ppc_const

    return uc.reg_read(getattr(ppc_const, "UC_PPC_REG_%s" % n))


def test_every_expect_matches_the_real_image(build):
    module, image = build
    names = sets_for(module)
    assert {"aux-autoswitch", "aux-boot-default", "aux-boot-restore"} <= set(names)
    for name in names:
        for e in json.loads(Path(patch_file(name)).read_text())["variants"][module]["patches"]:
            off = int(e["addr"], 16) - 0x01000000
            want = bytes.fromhex(e["expect"])
            assert image[off : off + len(want)] == want, "%s %s" % (name, e["addr"])


def add_request(build, pronly):
    """AddRequest for AUX's request (SrcId 0xe200, type 5, pos 7, prio 20).

    Stubbed: the watchdog cancel, ExecuteAllocation, ForceSchedulerPosition, the node
    allocator (returns a scratch node) and memcpy (performed for real).
    """
    module, image = build
    wdcancel, memcpy_addr = BSP[module]
    ppcemu, e = emulator(image)
    this, req, node = ppcemu.SCRATCH, ppcemu.SCRATCH + 0x1000, ppcemu.SCRATCH + 0x2000
    e.write(this, b"\0" * 0x400)
    e.write_u32(this + 0xB4, 7)  # Last_Source, as aux-boot-default forces it
    e.write_u32(this + 0xAC, 20)  # Last_Source_Priority, as aux-boot-restore forces it
    e.write_u32(this + 0x84, 0x1234)  # the init timer exists
    r = bytearray(0x2C)
    struct.pack_into(">H", r, 0, 3)
    struct.pack_into(">I", r, 4, 0xE200)
    struct.pack_into(">I", r, 8, 20)
    struct.pack_into(">I", r, 0x14, 5)
    struct.pack_into(">I", r, 0x18, 7)
    r[0x28] = pronly
    e.write(req, bytes(r))

    def memcpy(uc):
        d, s, n = reg(uc, 3), reg(uc, 4), reg(uc, 5)
        uc.mem_write(d, bytes(uc.mem_read(s, n)))
        return d

    for addr, how in (
        (memcpy_addr, memcpy),
        (SETNEXT, node),
        (wdcancel, 0),
        (EXEC_ALLOC, 0),
        (FORCE, 0),
    ):
        e.stub(addr, how)
    e.call(ADDREQ, [this, req])
    assert e.error is None, e.error
    table = [struct.unpack(">II", e.read(this + 0x370 + 8 * i, 8)) for i in range(10)]
    return {
        "table": [t for t in table if t != (0, 0)],
        "flag": e.read(this + 0x3C0, 1)[0],
        "timer_cancelled": e.reached(wdcancel),
    }


def test_pronly_keeps_aux_out_of_the_boot_restore(build):
    out = add_request(build, pronly=1)
    assert out["table"] == [] and out["flag"] == 0 and not out["timer_cancelled"]


def test_without_pronly_aux_matches_the_restore_and_cancels_the_timer(build):
    out = add_request(build, pronly=0)
    assert out["table"] == [(7, 20)] and out["flag"] == 1 and out["timer_cancelled"]


def handler_activations(build, patches):
    """HandleAudioAuxInputStatusChnged with the AUX setting on, every callee stubbed.

    The client pointer, the setting query (writing 1), GetMediaDevice (0, with a fake
    source), SetMediaDeviceState and ActivateSource, whose PrOnly argument is recorded.
    """
    module, image = build
    ppcemu, e = emulator(image)
    for name in patches:
        e.apply_patch_file(patch_file(name), module)
    e.stub_all = True
    this, client, src = ppcemu.SCRATCH, ppcemu.SCRATCH + 0x80000, ppcemu.SCRATCH + 0x90000
    e.write(this, b"\0" * 0x100)
    e.write(this + 0x51449, b"\0")
    acts = []

    def get_setting(uc):
        uc.mem_write(reg(uc, 4), struct.pack(">I", 1))

    def get_device(uc):
        uc.mem_write(reg(uc, 5) + 0x10, struct.pack(">I", src))

    for addr, how in (
        (GET_SETTING, get_setting),
        (GET_SIGNAL, 0),
        (CLIENT_PTR, client),
        (GET_DEVICE, get_device),
        (SET_STATE, 0),
        (ACTIVATE, lambda uc: acts.append(reg(uc, 4))),
    ):
        e.stub(addr, how)
    e.call(HANDLER, [this])
    assert e.error is None, e.error
    return acts


def test_stock_handler_activates_aux_with_pronly(build):
    assert handler_activations(build, []) == [1]


def test_boot_restore_makes_the_handler_pass_pronly_zero(build):
    assert handler_activations(build, ["aux-boot-restore"]) == [0]
