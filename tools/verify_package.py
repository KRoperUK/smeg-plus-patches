#!/usr/bin/env python3

# /// script
# requires-python = ">=3.10"
# dependencies = []

"""Audit a package's checksum cascade before it goes near a car.

A package is refused by the unit if any of its recorded CRC32s disagree with the files they
describe, and the failure it produces in the car looks like a firmware fault rather than a
packaging one. This reads every record the package carries and checks it against the bytes.

**It never assumes the record layout.** `*_ctrl.bin` manifests are binary and their exact
stride is not something this repository has verified against a vendor package — `patch_media`
still refuses a record count it has never seen for the same reason. So rather than parse
them, this looks for the CRC *as a value*: each manifest must contain, as a raw big-endian
word, the CRC32 of every file it is responsible for. That is layout-free and still catches
the failure that matters, which is a manifest that does not describe what shipped.

What it checks:

  * every `*.inf` sidecar's `CRC32:` field against the file beside it,
  * `smeg.inf`'s `BIGQUICK_CRC32:` against the module's `AppBin/f_BigQuick.bin`,
  * each `<MODULE>_ctrl.bin` against the three files of that module,
  * `ctrl.bin` against each `<MODULE>_ctrl.bin`.

usage:
    python3 tools/verify_package.py --package out/SMEG_PLUS_UPG
    python3 tools/verify_package.py --package out/SMEG_PLUS_UPG --json
"""

import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import struct  # noqa: E402

from appimage import crc32_file  # noqa: E402

# `smeg.inf` carries BSP_CRC32 and BIGQUICK_CRC32, which are different things entirely, so
# the sidecar match has to be a bare CRC32 field and not a suffix of another key
INF_SIDECAR_RE = re.compile(rb"(?<![A-Z_])CRC32: (-?\d+)")
SMEG_CRC_RE = re.compile(rb"BIGQUICK_CRC32: (-?\d+)")
MODULE_IMAGE = os.path.join("AppBin", "f_BigQuick.bin")


def as_signed(v):
    return struct.unpack(">i", struct.pack(">I", v & 0xFFFFFFFF))[0]


def read_field(path, regex):
    """The integer in a text field, or None when the field is absent."""
    with open(path, "rb") as fh:
        m = regex.search(fh.read(1 << 16))
    return int(m.group(1)) if m else None


def records(path):
    """The manifest's bytes, for searching. Small files, so read whole."""
    with open(path, "rb") as fh:
        return fh.read()


def holds_word(blob, value):
    """Is this CRC32 present in the manifest as a raw big-endian word?"""
    return struct.pack(">I", value & 0xFFFFFFFF) in blob


def modules(root):
    return sorted(
        n
        for n in os.listdir(root)
        if os.path.isdir(os.path.join(root, n)) and not n.startswith(".")
    )


def audit(root):
    """Every problem found, as dicts. Empty means the package is internally consistent."""
    problems = []

    def bad(kind, where, detail):
        problems.append({"kind": kind, "where": where, "detail": detail})

    # 1. every *.inf sidecar describes the file beside it
    for dirpath, _, filenames in os.walk(root):
        for n in filenames:
            if not n.endswith(".inf"):
                continue
            inf = os.path.join(dirpath, n)
            declared = read_field(inf, INF_SIDECAR_RE)
            if declared is None:
                continue  # smeg.inf and friends carry other fields; checked separately
            sibling = inf[: -len(".inf")]
            rel = os.path.relpath(inf, root)
            if not os.path.isfile(sibling):
                bad(
                    "inf-sidecar",
                    rel,
                    "describes %s, which does not exist" % os.path.basename(sibling),
                )
                continue
            actual = crc32_file(sibling)
            if declared != as_signed(actual):
                bad(
                    "inf-sidecar",
                    rel,
                    "declares CRC32 %d, but %s hashes to %d"
                    % (declared, os.path.basename(sibling), as_signed(actual)),
                )

    # 2. each module's smeg.inf and its own manifest
    for mod in modules(root):
        mod_dir = os.path.join(root, mod)
        image = os.path.join(mod_dir, MODULE_IMAGE)
        if not os.path.isfile(image):
            bad("module", mod, "no %s" % MODULE_IMAGE)
            continue
        image_crc = crc32_file(image)

        smeg = os.path.join(mod_dir, "smeg.inf")
        if os.path.isfile(smeg):
            declared = read_field(smeg, SMEG_CRC_RE)
            if declared is None:
                bad("smeg-inf", os.path.join(mod, "smeg.inf"), "no BIGQUICK_CRC32 field")
            elif declared != as_signed(image_crc):
                bad(
                    "smeg-inf",
                    os.path.join(mod, "smeg.inf"),
                    "declares BIGQUICK_CRC32 %d, but the image hashes to %d"
                    % (declared, as_signed(image_crc)),
                )

        manifest = os.path.join(root, "%s_ctrl.bin" % mod)
        if not os.path.isfile(manifest):
            bad("manifest", mod, "no %s_ctrl.bin" % mod)
            continue
        blob = records(manifest)
        for label, path in (
            ("AppBin/f_BigQuick.bin", image),
            ("f_BigQuick.bin.inf", image + ".inf"),
            ("smeg.inf", smeg),
        ):
            if not os.path.isfile(path):
                bad("module", os.path.join(mod, label), "missing")
                continue
            want = crc32_file(path)
            if not holds_word(blob, want):
                bad(
                    "manifest",
                    "%s_ctrl.bin" % mod,
                    "does not record the CRC of %s (%#010x)" % (label, want),
                )

    # 3. the root manifest describes every module manifest
    root_manifest = os.path.join(root, "ctrl.bin")
    if not os.path.isfile(root_manifest):
        bad("manifest", "ctrl.bin", "missing from the package root")
    else:
        blob = records(root_manifest)
        for mod in modules(root):
            manifest = os.path.join(root, "%s_ctrl.bin" % mod)
            if not os.path.isfile(manifest):
                continue
            want = crc32_file(manifest)
            if not holds_word(blob, want):
                bad(
                    "manifest",
                    "ctrl.bin",
                    "does not record the CRC of %s_ctrl.bin (%#010x)" % (mod, want),
                )

    return problems


def summary(root):
    """The facts worth printing even when nothing is wrong."""
    mods = modules(root)
    return {
        "package": root,
        "modules": mods,
        "root_manifest": os.path.isfile(os.path.join(root, "ctrl.bin")),
        "contract": os.path.isfile(os.path.join(root, "contract.dat")),
    }


def main(argv=None):
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--package", required=True, help="the package directory to audit")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args(argv)

    root = os.path.abspath(args.package)
    if not os.path.isdir(root):
        raise SystemExit("not a directory: %s" % root)

    problems = audit(root)
    info = summary(root)

    if args.json:
        print(json.dumps({"summary": info, "problems": problems}, indent=2))
        return 1 if problems else 0

    print("package : %s" % root)
    print("modules : %s" % (", ".join(info["modules"]) or "none"))
    print("contract: %s" % ("present" if info["contract"] else "MISSING"))

    if not info["modules"]:
        print("no module directories - nothing to audit")
        return 1

    for p in problems:
        print("  FAIL  %-10s %s" % (p["kind"], p["where"]))
        print("        %s" % p["detail"])

    if problems:
        print("\n%d problem(s) - do not flash this package" % len(problems))
        return 1

    print("checksum cascade consistent across %d module(s)" % len(info["modules"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
