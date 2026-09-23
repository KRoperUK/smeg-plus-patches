#!/usr/bin/env python3

# /// script
# requires-python = ">=3.10"
# dependencies = []

"""Identify which SMEG+ build an application image is, and fail loudly when it is unclear.

Patch addresses are per build. `patches/*.json` declares each variant's addresses, and
`patch_smeg.py` guards the *firmware version* by looking for the vendor's build token
(`5.43.A.R2`) inside the image. That leaves the *build* itself — `AUDIO_BT`,
`AUDIO_BT_256`, `NAV` — to be chosen by hand, which is the part that is easy to get
wrong: `AUDIO_BT` and `AUDIO_BT_256` share their patch addresses exactly.

This reads the image and answers that question from the bytes, rather than from what
the operator remembered:

  * inflate the application container,
  * evaluate every variant's recorded `expect` bytes at their addresses,
  * report a unique match, or refuse.

**It deliberately reports ambiguity instead of picking.** On the firmware in this
repository `AUDIO_BT` and `AUDIO_BT_256` carry identical addresses and identical
`expect` bytes, so the recorded probes genuinely cannot tell them apart. A tool that
quietly chose one would be worse than the manual step it replaced. The same applies
when nothing matches: the message names the build tokens actually present.

Both a package directory and a single image file are accepted. A raw inflated image
(the `0x02604450`-byte layout) is detected, since that is what an analysis pass has
lying around.

usage:
    python3 tools/fingerprint.py --src /path/to/SMEG_PLUS_UPG
    python3 tools/fingerprint.py --image app_nav.bin
    python3 tools/fingerprint.py --src PKG --json
"""

import argparse
import json
import os
import sys
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from patch_smeg import DEFAULT_BASE, firmware_hints, inflate  # noqa: E402

PATCH_DIR = os.path.normpath(os.path.join(HERE, os.pardir, "patches"))

# Below this an inflated image is a bad inflate rather than a real one
MIN_IMAGE = 0x100000


def variants_from_spec(spec, path):
    """One variant dict per entry in an already-parsed patch definition."""
    out = {}
    for name, v in spec.get("variants", {}).items():
        out[(spec.get("name", os.path.basename(path)), name)] = {
            "app_image": v["app_image"],
            "base": int(str(v.get("base", hex(DEFAULT_BASE))), 16),
            "firmware": v.get("firmware"),
            "probes": [(int(str(q["addr"]), 16), bytes.fromhex(q["expect"])) for q in v["patches"]],
            "source": path,
        }
    return out


def load_patch_sets(paths):
    """Every variant declared across the given patch files, keyed by (set, variant)."""
    out = {}
    for p in paths:
        out.update(variants_from_spec(json.loads(Path(p).read_text()), p))
    return out


def read_image(path):
    """Return (image, how). Accepts a package container or an already-inflated image."""
    raw = Path(path).read_bytes()
    try:
        start, img = inflate(raw)
        return img, "zlib stream at %#x" % start
    except SystemExit:
        if len(raw) > MIN_IMAGE:
            return raw, "already inflated"
        raise


def probe_results(img, variant):
    """(matched, total, details) for one variant against one image."""
    details = []
    matched = 0
    for addr, expect in variant["probes"]:
        off = addr - variant["base"]
        got = img[off : off + len(expect)] if 0 <= off else b""
        ok = got == expect
        matched += ok
        details.append((addr, expect.hex(), got.hex(), ok))
    return matched, len(variant["probes"]), details


def identify(img, variants):
    """The distinct *build names* whose probes all match.

    Keyed on the build name rather than the (patch set, variant) pair on purpose. Several
    patch sets each describe `NAV`, and all of them matching is agreement about the build,
    not a conflict — conflating the two made nine NAV variants read as "ambiguous".
    """
    return sorted(
        {
            key[1]
            for key, v in variants.items()
            if all(ok for _, _, _, ok in probe_results(img, v)[2])
        }
    )


def report_image(label, path, variants, as_json):
    """Identify one image, print the finding, and return (verdict, payload)."""
    img, how = read_image(path)
    tokens = firmware_hints(img)
    builds = identify(img, variants)

    payload = {
        "image": label,
        "path": str(path),
        "size": len(img),
        "container": how,
        "build_tokens": tokens,
        "matches": builds,
        "probes": {},
    }

    if not as_json:
        print("  %s" % label)
        print("    %-14s %d bytes, %s" % ("image", len(img), how))
        print("    %-14s %s" % ("build tokens", ", ".join(tokens) if tokens else "none"))
        for key, v in variants.items():
            m, n, details = probe_results(img, v)
            payload["probes"]["%s/%s" % key] = {
                "matched": m,
                "total": n,
                "firmware": v["firmware"],
                "detail": [
                    {"addr": hex(a), "expect": e, "found": g, "ok": ok} for a, e, g, ok in details
                ],
            }
            tag = "  <- match" if m == n and n else ""
            print(
                "    %-22s %d/%d probes   firmware=%s%s"
                % ("%s/%s" % key, m, n, v["firmware"] or "unset", tag)
            )

    if len(builds) == 1:
        if not as_json:
            print("    verdict: %s" % builds[0])
        payload["verdict"] = builds[0]
        return builds[0], payload

    payload["verdict"] = None
    if not builds:
        if not as_json:
            print("    verdict: UNKNOWN - no variant's probes match this image")
            print("             build tokens found: %s" % (", ".join(tokens) if tokens else "none"))
            print("             addresses are per build and per firmware version; do not guess one")
    else:
        payload["ambiguous"] = builds
        if not as_json:
            print(
                "    verdict: AMBIGUOUS - the probes cannot separate these builds: %s"
                % ", ".join(builds)
            )
            print("             they declare the same addresses and the same expect bytes;")
            print("             select the build explicitly rather than letting this decide")
    return None, payload


def main(argv=None):
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--src", help="a SMEG+ upgrade package directory")
    ap.add_argument("--image", help="a single application image (container or inflated)")
    ap.add_argument(
        "--patches",
        nargs="*",
        default=None,
        help="patch definition JSON files (default: all in patches/)",
    )
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args(argv)

    if bool(args.src) == bool(args.image):
        ap.error("give exactly one of --src or --image")

    paths = args.patches or sorted(str(p) for p in Path(PATCH_DIR).glob("*.json"))
    variants = load_patch_sets(paths)

    # group by the image they describe: each image is a separate build to identify
    by_image = {}
    for key, v in variants.items():
        by_image.setdefault(v["app_image"], []).append((key, v))

    findings = []
    ok = True
    if not args.json:
        print("patch sets: %d file(s), %d variant(s)" % (len(paths), len(variants)))
        print("subject   : %s" % (args.src or args.image))

    if args.image:
        # one image, tested against every variant: that is the "which build is this?" case
        groups = [("<image>", args.image, variants)]
    else:
        # a package holds one image per build, so each is identified against its own variant set
        groups = []
        for image, entries in sorted(by_image.items()):
            path = os.path.join(args.src, image)
            if os.path.exists(path):
                groups.append((image, path, dict(entries)))

    for label, path, subset in groups:
        verdict, payload = report_image(label, path, subset, args.json)
        findings.append(payload)
        ok = ok and verdict is not None

    if not findings:
        raise SystemExit("no application image found to identify")

    if args.json:
        print(json.dumps(findings, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
