"""Tests for the build fingerprint.

These use synthetic images, so no vendor firmware is needed and the suite stays honest about
what it proves: the matching logic, not that any particular real build is correct. The real
check was run by hand against a NAV image, where it identified NAV and rejected every
AUDIO_BT variant — that is the validation, and it cannot live in CI.
"""

import os
import sys
import zlib

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "tools"))

import fingerprint as fp  # noqa: E402
import patch_smeg  # noqa: E402

BASE = 0x01000000
HEADER = 0x801


def image_with(probes, size=0x2000):
    """A stand-in image with the given bytes placed at the given addresses."""
    img = bytearray(b"\x00" * size)
    for addr, data in probes:
        off = addr - BASE
        img[off : off + len(data)] = data
    return bytes(img)


def spec(variants):
    return {"name": "synthetic", "variants": variants}


def variant(app_image, probes, firmware="9.99.Z.R1"):
    return {
        "app_image": app_image,
        "base": hex(BASE),
        "firmware": firmware,
        "patches": [
            {"addr": hex(a), "expect": d.hex(), "bytes": "60000000", "why": "test"}
            for a, d in probes
        ],
    }


def container(img):
    """Wrap an image the way a package does: header, marker, zlib stream."""
    return b"\x00" * HEADER + zlib.compress(bytes(img), 6)


def test_identifies_the_matching_build():
    want = [(BASE + 0x100, b"\x94\x21\xff\xa0")]
    other = [(BASE + 0x100, b"\x94\x21\xff\xb0")]
    s = spec(
        {
            "GOOD": variant("GOOD/AppBin/f_BigQuick.bin", want),
            "BAD": variant("GOOD/AppBin/f_BigQuick.bin", other),
        }
    )
    assert fp.identify(image_with(want), fp.variants_from_spec(s, "<t>")) == ["GOOD"]


def test_a_build_matching_nothing_is_reported_as_none():
    s = spec({"NAV": variant("NAV/AppBin/f_BigQuick.bin", [(BASE + 0x10, b"\xaa\xbb\xcc\xdd")])})
    assert (
        fp.identify(
            image_with([(BASE + 0x10, b"\x11\x22\x33\x44")]), fp.variants_from_spec(s, "<t>")
        )
        == []
    )


def test_identical_probes_report_every_build_they_cannot_separate():
    """The real AUDIO_BT / AUDIO_BT_256 case: same addresses, same bytes, no way to choose.

    The point is that it does *not* pick one. Choosing silently is worse than the manual step
    it would replace, because the addresses really are the same and the choice is invisible.
    """
    same = [(BASE + 0x100, b"\x94\x21\xff\xa0"), (BASE + 0x200, b"\x41\x9e\x01\x4c")]
    s = spec({"AUDIO_BT": variant("i.bin", same), "AUDIO_BT_256": variant("i.bin", same)})
    got = fp.identify(image_with(same), fp.variants_from_spec(s, "<t>"))
    assert got == ["AUDIO_BT", "AUDIO_BT_256"]


def test_identical_builds_across_patch_sets_are_agreement_not_ambiguity():
    """Several patch sets describing the same build is consensus, and must read that way.

    Keying the verdict on (patch set, variant) instead of the build name made nine NAV
    variants come out as "ambiguous", which is the opposite of what the bytes say.
    """
    probes = [(BASE + 0x100, b"\x94\x21\xff\xa0")]
    combined = {}
    for name in ("set-one", "set-two", "set-three"):
        for key, v in fp.variants_from_spec(spec({"NAV": variant("i.bin", probes)}), name).items():
            combined[key] = v
    assert fp.identify(image_with(probes), combined) == ["NAV"]


def test_read_image_accepts_both_a_container_and_a_raw_image(tmp_path):
    probes = [(BASE + 0x100, b"\x94\x21\xff\xa0")]
    # the container path goes through patch_smeg.inflate, which rejects anything that
    # inflates to less than 1 MB as a bad inflate rather than a real image
    img = image_with(probes, size=0x110000)

    packed = tmp_path / "f_BigQuick.bin"
    packed.write_bytes(container(img))
    got, how = fp.read_image(str(packed))
    assert got == img and "zlib" in how

    # a raw image only counts as one if it is big enough to be an image rather than a bad inflate
    raw = tmp_path / "app.bin"
    raw.write_bytes(b"\x00" * 4)
    with pytest.raises(SystemExit):
        fp.read_image(str(raw))


def test_patch_smeg_refuses_a_build_the_image_is_not():
    """The guard the issue asked for: name the build rather than report a byte mismatch."""
    good = [(BASE + 0x100, b"\x94\x21\xff\xa0")]
    bad = [(BASE + 0x100, b"\x94\x21\xff\xb0")]
    s = spec({"NAV": variant("i.bin", good), "AUDIO_BT": variant("i.bin", bad)})

    # patching NAV against an image that is AUDIO_BT must refuse, and say what it found
    with pytest.raises(SystemExit) as e:
        patch_smeg.check_build(image_with(bad), "NAV", s)
    assert "AUDIO_BT" in str(e.value)

    # and the matching case must pass through quietly
    patch_smeg.check_build(image_with(good), "NAV", s)


def test_an_image_matching_no_build_is_left_to_the_other_checks():
    """The guard stays quiet here, on purpose.

    "Matches nothing" and "matches another build" look alike and are not. The former is
    already reported precisely by the firmware-token check and by the expect-byte check, so
    adding a third message would pre-empt the more specific one — and did, until this was
    narrowed.
    """
    s = spec({"NAV": variant("i.bin", [(BASE + 0x100, b"\x94\x21\xff\xa0")])})
    patch_smeg.check_build(image_with([(BASE + 0x100, b"\x00\x00\x00\x00")]), "NAV", s)
