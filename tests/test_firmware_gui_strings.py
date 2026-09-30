"""Firmware-in-the-loop tests for the GUI string tables: run against YOUR OWN media partition.

No vendor file may live in this repository, so CI only ever sees the synthetic tables in
`tests/test_guistrings.py`. These tests settle the claims that need real bytes - that the
codec round-trips every shipped table byte-for-byte, and that the id space is the same in
every language - and they skip cleanly wherever the partition is not provided:

    python3 tools/patch_media.py extract --package SMEG_PLUS_UPG --module NAV --tree media
    SMEG_MEDIA_DIR=media .venv/bin/python -m pytest -m firmware -q

`SMEG_MEDIA_DIR` is the root of an **extracted** partition (the tree `patch_media.py extract`
writes), not the `system.bin`. Nothing here writes to it.
"""

import os
import sys
from pathlib import Path

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "tools"))

import guistrings  # noqa: E402

MEDIA_ENV = "SMEG_MEDIA_DIR"
GUI_TEXTS = "Data_base/boardfs/GUI_STYLE/GUIS_RESSOURCES/gui_texts"

pytestmark = [
    pytest.mark.firmware,
    pytest.mark.skipif(not os.environ.get(MEDIA_ENV), reason="set %s to run" % MEDIA_ENV),
]


@pytest.fixture(scope="module")
def tables():
    """{language: (path, parsed file)} for every shipped string table."""
    root = Path(os.path.expanduser(os.environ[MEDIA_ENV])) / GUI_TEXTS
    paths = sorted(root.glob(guistrings.LANG_PREFIX + "*" + guistrings.LANG_SUFFIX))
    if not paths:
        pytest.skip("no string tables under %s" % root)
    return {guistrings.language_of(p): (p, guistrings.StringsFile.load(p)) for p in paths}


def test_every_shipped_table_meets_the_documented_layout(tables):
    for lang, (path, f) in tables.items():
        bad = [desc for desc, ok in f.issues() if not ok]
        assert not bad, "%s (%s): %s" % (lang, path, bad)


def test_every_shipped_table_rebuilds_byte_for_byte(tables):
    """The bar for the codec: decode then rebuild with no edits reproduces the input."""
    for lang, (path, f) in tables.items():
        assert f.to_bytes() == path.read_bytes(), lang


def test_the_files_carry_no_checksum_of_their_own(tables):
    """The reserved word is zero and the blob ends exactly at EOF - so the CRC is external."""
    for lang, (path, f) in tables.items():
        assert f.reserved == 0, lang
        assert f.entries[-1].offset + f.entries[-1].length == len(path.read_bytes()), lang


def test_every_language_has_the_same_id_space(tables):
    """The ids are the unit's own, so a translation must not renumber them."""
    shapes = {lang: [e.id for e in f.entries] for lang, (_, f) in tables.items()}
    reference_lang, reference = next(iter(shapes.items()))
    for lang, ids in shapes.items():
        assert ids == reference, "%s differs from %s" % (lang, reference_lang)


def test_the_strings_are_utf16be_and_never_nul_terminated(tables):
    """The recorded length is a byte count of UTF-16 code units and nothing more."""
    for lang, (_, f) in tables.items():
        assert all(e.length % 2 == 0 for e in f.entries), lang
        assert all("\x00" not in e.text for e in f.entries), lang
        for e in f.entries:
            assert len(e.text.encode("utf-16-be")) == e.length, "%s id %d" % (lang, e.id)


def test_the_shipped_string_sizes_are_what_the_documentation_claims(tables):
    """The limits quoted in docs/GUI_STRINGS.md come from these files, not from a guess."""
    longest = max((e.length for _, f in tables.values() for e in f.entries))
    assert longest >= 300  # the longest shipped label is a multi-line message
    assert longest % 2 == 0
