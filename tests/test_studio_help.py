"""`patch_studio.py --help` must work without PySide6, like every other tool's `--help`.

It imported Qt at module level before looking at its arguments, so on a machine without the
GUI dependency `--help` printed "PySide6 is required" and exited non-zero.
"""

import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.join(os.path.dirname(HERE), "tools", "patch_studio.py")

# a sitecustomize-free way to make PySide6 unimportable in the child process
BLOCK_QT = (
    "import sys, runpy\n"
    "class Block:\n"
    "    def find_spec(self, name, path=None, target=None):\n"
    "        if name == 'PySide6' or name.startswith('PySide6.'):\n"
    "            raise ImportError('blocked for the test')\n"
    "sys.meta_path.insert(0, Block())\n"
    "sys.argv = [%r, '--help']\n"
    "runpy.run_path(%r, run_name='__main__')\n"
)


def test_help_works_without_pyside6():
    r = subprocess.run(
        [sys.executable, "-c", BLOCK_QT % (TOOL, TOOL)], capture_output=True, text=True
    )
    assert r.returncode == 0, r.stderr
    assert "Ringtone Studio" in r.stdout and "usage:" in r.stdout
