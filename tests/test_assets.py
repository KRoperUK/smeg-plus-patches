"""Tests for the asset catalogue and its human-readable naming.

The naming is the feature: the point is that `MM_HoldOn_GED_8kHz.wav` can be offered as
"Call hold — German" and `AT_O3.png` as "Austria — O3 (large)". A wrong or empty label is
the failure that matters, because it is what a person acts on.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
TOOLS = os.path.join(ROOT, "tools")
sys.path.insert(0, TOOLS)
sys.path.insert(0, HERE)

import assets  # noqa: E402


def test_labels_read_as_english():
    assert assets.label("ring_tones/ring1RT.wav") == "Ring tone 1"
    assert assets.label("ring_tones/ring5RT.wav") == "Ring tone 5"
    assert assets.label("ring_tones/busyRT.wav") == "Engaged"
    assert assets.label("ring_tones/okRT.wav") == "Confirm"


def test_wait_tones_name_their_language():
    assert assets.label("wait_tones/MM_HoldOn_GED_8kHz.wav") == "Call hold — German"
    assert assets.label("wait_tones/MM_HoldOn_ENG_8kHz.wav") == "Call hold — English"
    assert assets.label("wait_tones/MM_HoldOn_TRT_8kHz.wav") == "Call hold — Turkish"


def test_radio_logos_name_country_station_and_size():
    got = assets.label("Data_base/radio/logo/Large/AT_O3.png")
    assert got == "Austria — O3 (large)"
    assert assets.label("Data_base/radio/logo/Small/BE_JoeFM.png") == "Belgium — JoeFM (small)"


def test_fonts_and_config_have_readable_names():
    assert "Gill Sans" in assets.label("Data_base/TMP/lib/fonts/GillSansPSA.ttf")
    assert assets.label("Data_base/boardfs/GUI_STYLE/gui_config.xml") == "Layout, size, harmony id"


def test_unknown_names_are_still_tidied_not_raw():
    """A label that is just the filename is not a label."""
    got = assets.label("Data_base/boardfs/GUI_STYLE/GUIS_RESSOURCES/gui_sounds/Brosser.wav")
    assert got == "Brush"
    got = assets.label("something/SOME_obscure_file.bin")
    assert "_" not in got and got != "SOME_obscure_file"


def test_catalogue_covers_the_groups_the_docs_promise():
    groups = {g for g, _, _, _, _ in assets.GROUPS}
    assert {"sounds", "logos", "graphics", "fonts", "strings", "config"} <= groups
    # every pattern must be absolute-free and relative to the media tree
    for _, _, pattern, _, _ in assets.GROUPS:
        assert not pattern.startswith("/")


def test_group_matching_is_generous_but_ordered(tmp_path):
    tree = tmp_path / "media"
    for rel in ("ring_tones/ring1RT.wav", "ring_tones/ring2RT.wav"):
        p = tree / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"RIFF")
    # an alias
    assert assets.group_for(str(tree), "ringtones")
    # a description fragment
    assert assets.group_for(str(tree), "Ring tones")
    # an exact label selects ONE file, not the whole group
    got = assets.group_for(str(tree), "Ring tone 2")
    assert len(got) == 1 and len(got[0][4]) == 1
    assert os.path.basename(got[0][4][0]) == "ring2RT.wav"


def test_aliases_do_not_import_a_whole_group_by_accident(tmp_path):
    """The bug this guards: a substring match pulling in unrelated groups."""
    tree = tmp_path / "media"
    (tree / "ring_tones").mkdir(parents=True)
    (tree / "ring_tones" / "ring1RT.wav").write_bytes(b"RIFF")
    got = assets.group_for(str(tree), "Ring tone 1")
    assert len(got) == 1


# ------------------------------------------------------- tranche-2 #256 assets
def _png(size, tag):
    d = size / "AT_O3.png"
    d.parent.mkdir(parents=True, exist_ok=True)
    d.write_bytes(b"png-" + tag.encode())
    return d


def _asset_args(tree, **kw):
    import argparse

    args = argparse.Namespace(tree=str(tree), force=False, **kw)
    return args


def test_export_keeps_same_named_files_from_every_size(tmp_path):
    """Same basename in Large/Medium/Small used to collapse into one pool file."""
    import assets

    tree = tmp_path / "media"
    for size in ("Large", "Medium", "Small"):
        _png(tree / "Data_base" / "radio" / "logo" / size, size)

    args = _asset_args(tree, asset="radio logos", out=str(tmp_path / "out"))
    assets.cmd_export(args)

    for size in ("Large", "Medium", "Small"):
        got = tmp_path / "out" / "Data_base" / "radio" / "logo" / size / "AT_O3.png"
        assert got.read_bytes() == b"png-" + size.encode()


def test_replace_refuses_an_ambiguous_flat_pool(tmp_path):
    """One pool file must not land in all three sizes silently."""
    import pytest

    import assets

    tree = tmp_path / "media"
    for size in ("Large", "Medium", "Small"):
        _png(tree / "Data_base" / "radio" / "logo" / size, size)
    pool = tmp_path / "pool"
    pool.mkdir()
    (pool / "AT_O3.png").write_bytes(b"new")

    import argparse

    args = argparse.Namespace(tree=str(tree), asset="radio logos", with_=str(pool), dry_run=True)
    with pytest.raises(SystemExit, match="ambiguous across sizes"):
        assets.cmd_replace(args)
    for size in ("Large", "Medium", "Small"):
        assert (tree / "Data_base" / "radio" / "logo" / size / "AT_O3.png").read_bytes() != b"new"


def test_replace_maps_a_mirrored_pool_per_size(tmp_path):
    import assets

    tree = tmp_path / "media"
    for size in ("Large", "Medium", "Small"):
        _png(tree / "Data_base" / "radio" / "logo" / size, size + "-old")
    pool = tmp_path / "pool"
    for size in ("Large", "Medium", "Small"):
        d = pool / "Data_base" / "radio" / "logo" / size
        d.mkdir(parents=True)
        (d / "AT_O3.png").write_bytes(b"png-" + size.encode() + b"-new")

    import argparse

    args = argparse.Namespace(tree=str(tree), asset="radio logos", with_=str(pool), dry_run=False)
    assets.cmd_replace(args)

    for size in ("Large", "Medium", "Small"):
        got = tree / "Data_base" / "radio" / "logo" / size / "AT_O3.png"
        assert got.read_bytes() == b"png-" + size.encode() + b"-new"
