import io
import os
import sys
import tarfile
import wave
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.join(os.path.dirname(HERE), "tools")
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

# the fixture writes `ctrl` records with the same builder the tools read them with (#68)
from smeglib import build_ctrl, crc32, roundup, s32  # noqa: E402

# --- media partition (for patch_media.py) ----------------------------------


def wav_bytes(channels=1, rate=44100, frames=441):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x00\x00" * channels * frames)
    return buf.getvalue()


def build_system_ctrl(files):
    """A stock-shaped `system_ctrl.bin`: header, u32 count, 264-byte records."""
    return build_ctrl([("/SYSTEM/" + name, 2, crc32(data)) for name, data in files.items()])


def up_common_bytes(names=None):
    """A minimal `up_common.sqlite` holding the phone ringtone name list.

    The unit takes the names it shows in the phone UI from here, not from the WAVs.
    """
    import sqlite3
    import tempfile

    names = names or [
        "Alien",
        "Blue_lemon",
        "Blue_tangerine",
        "Green_apple",
        "Green_lemon",
        "Green_pin_apple",
        "Green_tangerine",
        "Red_strawberry",
        "Red_tangerine",
        "Ufo",
    ]
    tmp = tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False)  # noqa: SIM115  # closed on the next line; delete=False so sqlite can reopen it by name
    tmp.close()
    con = sqlite3.connect(tmp.name)
    con.execute(
        "create table UP_Keys (Section text, Name text, Type int, Idx int,"
        " IntValue int, FloatValue real, StringValue text, BlobValue blob,"
        " reset_factory_enabled int, modified int)"
    )
    for i, n in enumerate(names):
        con.execute(
            "insert into UP_Keys (Section, Name, Type, Idx, StringValue,"
            " reset_factory_enabled, modified) values ('phone','Ringing_List',4,?,?,0,0)",
            (i, n),
        )
    con.commit()
    con.close()
    data = Path(tmp.name).read_bytes()
    os.unlink(tmp.name)
    return data


def build_media_package(root, module="NAV", extra_constant=True, extra_files=None):
    """A minimal but structurally faithful media partition.

    `extra_constant` adds the same unexplained offset the vendor's SIZE_1/2/4 carry,
    so the tests prove the patcher preserves those values rather than recomputing them.
    """
    files = {
        "Data_base/media.inf": b"00000000\nVER:0\n",
        "Data_base/smeg.inf": b"BSP_CRC32: 0 \r\nVER: X \r\nGUI_VER:00.00 \r\n",
        "ring_tones/ring1RT.wav": wav_bytes(frames=441),
        "ring_tones/ring2RT.wav": wav_bytes(frames=882),
        "wait_tones/MM_HoldOn_ENG_8kHz.wav": wav_bytes(channels=2, rate=8000, frames=800),
    }
    files.update(extra_files or {})

    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w", format=tarfile.GNU_FORMAT) as tf:
        for name, data in files.items():
            ti = tarfile.TarInfo(name)
            ti.size = len(data)
            ti.mtime = 0
            ti.mode = 0o644
            tf.addfile(ti, io.BytesIO(data))
    tar_bytes = buf.getvalue()
    bin_bytes = __import__("gzip").compress(tar_bytes, 6)

    mod_dir = os.path.join(root, module)
    os.makedirs(mod_dir, exist_ok=True)
    Path(os.path.join(mod_dir, "system.bin")).write_bytes(bin_bytes)

    sizes = {"SIZE": sum(len(v) for v in files.values())}
    for n in (1, 2, 4, 8, 16, 32):
        v = sum(roundup(len(x), n * 1024) for x in files.values())
        if extra_constant:
            v += {1: 29696, 2: 18432, 4: 8192}.get(n, 0)
        sizes["SIZE_%d" % n] = v
    lines = ["CRC32: %d" % s32(crc32(bin_bytes))]
    lines += ["%s: %d" % (k, v) for k, v in sizes.items()]
    Path(os.path.join(mod_dir, "system.bin.inf")).write_bytes(
        ("\r\n".join(lines) + "\r\n").encode()
    )

    ctrl = build_system_ctrl(files)
    Path(os.path.join(mod_dir, "system_ctrl.bin")).write_bytes(ctrl)

    # module + root manifests (same shape as ctrl.bin: header, u32 count, records)
    mod_ctrl_path = os.path.join(root, "%s_ctrl.bin" % module)
    mod_ctrl = build_ctrl(
        [
            ("/%s/system.bin" % module, 1, crc32(bin_bytes)),
            (
                "/%s/system.bin.inf" % module,
                1,
                crc32(Path(os.path.join(mod_dir, "system.bin.inf")).read_bytes()),
            ),
            ("/%s/system_ctrl.bin" % module, 1, crc32(ctrl)),
        ]
    )
    Path(mod_ctrl_path).write_bytes(mod_ctrl)
    Path(os.path.join(root, "ctrl.bin")).write_bytes(
        build_ctrl([("/%s_ctrl.bin" % module, 1, crc32(mod_ctrl))])
    )

    return {
        "module": module,
        "files": files,
        "tar": tar_bytes,
        "bin": bin_bytes,
        "ctrl": ctrl,
        "sizes": sizes,
    }
