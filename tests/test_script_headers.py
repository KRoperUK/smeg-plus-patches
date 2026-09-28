"""Every tool's PEP 723 header is closed, so `uv run tools/<tool>.py` works.

Eight tools opened `# /// script` without the closing `# ///`; uv refuses such a file
("An opening tag ... was found without a closing tag"), which broke `uv run` - the
documented way to run every tool - for prepare_usb, survey and six others.
"""

import pathlib

import pytest

TOOLS = sorted(pathlib.Path(__file__).resolve().parent.parent.joinpath("tools").glob("*.py"))


@pytest.mark.parametrize("path", TOOLS, ids=lambda p: p.name)
def test_an_opened_script_header_is_closed(path):
    lines = path.read_text().splitlines()
    if "# /// script" not in lines:
        return
    start = lines.index("# /// script")
    for line in lines[start + 1 :]:
        if line == "# ///":
            return
        assert line.startswith("#"), "%s: header ends before its closing '# ///'" % path.name
    pytest.fail("%s: '# /// script' is never closed" % path.name)
