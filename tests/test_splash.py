import os
import struct
import subprocess
import sys
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
TOOLS = os.path.join(ROOT, "tools")
sys.path.insert(0, HERE)

HEADER = 0x800
MARKER = 0x08


def run(*args):
    return subprocess.run([sys.executable, *args], capture_output=True, text=True)


def evil_pkg():
    """A minimal logo bundle whose record name escapes the output dir."""
    raw = bytearray(HEADER)
    struct.pack_into(">4I", raw, 0, 0, 0, 0, 0)
    name = b"../../evil.bmp"
    raw[0x10 : 0x10 + 32] = name + b"\x00" * (32 - len(name))
    raw += bytes([MARKER]) + zlib.compress(b"x" * 64) + b"\x00\x00"
    return bytes(raw)


def test_extract_refuses_record_names_escaping_the_out_dir(tmp_path):
    tree = tmp_path / "tree"
    pkg_dir = tree / "Data_base" / "graphics" / "logo"
    pkg_dir.mkdir(parents=True)
    (pkg_dir / "peugeot.pkg").write_bytes(evil_pkg())
    out = tmp_path / "out"
    escaped = tmp_path.parent / "evil.bmp"
    if escaped.exists():
        escaped.unlink()
    r = run(
        os.path.join(TOOLS, "splash.py"),
        "--tree",
        str(tree),
        "extract",
        "--marque",
        "peugeot",
        "-o",
        str(out),
    )
    assert r.returncode != 0
    assert "unsafe" in (r.stdout + r.stderr)
    assert not escaped.exists()
