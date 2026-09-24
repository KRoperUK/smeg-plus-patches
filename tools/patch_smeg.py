#!/usr/bin/env python3

# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///

"""Apply a SMEG+ patch set to an upgrade package and rebuild its checksum cascade.

The application for each variant is AppBin/f_BigQuick.bin: a 0x801-byte header
plus a zlib stream holding the PowerPC image loaded at 0x01000000. This tool:

  1. inflates the image,
  2. checks the original bytes at each patch address ("expect") and applies the
     replacement ("bytes"),
  3. re-deflates the image back into the container,
  4. rebuilds the checksum cascade:

        f_BigQuick.bin --crc32--> f_BigQuick.bin.inf
                       --crc32--> smeg.inf  (BIGQUICK_CRC32)
                       --crc32--> <module>_ctrl.bin
        <module>_ctrl.bin --crc32--> ctrl.bin (root manifest)

Only the changed files are written to --out (mirroring their package-relative
paths). Use tools/apply_files.sh to overlay them onto a copy of your package, or
pass --copy-package to have this tool copy the whole package into --out first.

No vendor firmware is bundled with this tool; point --src at your own legally
obtained package.

usage:
    python3 tools/patch_smeg.py --src SMEG_PLUS_UPG --out SMEG_PLUS_UPG_mod
    python3 tools/patch_smeg.py --src SMEG_PLUS_UPG --out out --only NAV
"""

import argparse
import json
import os
import re
import shutil
import struct
import sys
import zlib
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from appimage import DEFAULT_BASE, inflate  # noqa: E402
from fingerprint import identify, variants_from_spec  # noqa: E402
from smeglib import crc32, s32, swap_crc  # noqa: E402


def rewrite_inf(blob, new_crc):
    out, n = re.subn(rb"CRC32: -?\d+", ("CRC32: %d" % s32(new_crc)).encode(), blob, count=1)
    if n != 1:
        raise SystemExit("no 'CRC32:' field found in .inf")
    return out


def rewrite_smeg_inf(blob, new_crc):
    out, n = re.subn(
        rb"BIGQUICK_CRC32: -?\d+", ("BIGQUICK_CRC32: %d" % s32(new_crc)).encode(), blob, count=1
    )
    if n != 1:
        raise SystemExit("no 'BIGQUICK_CRC32:' field found in smeg.inf")
    return out


def load(path):
    return Path(path).read_bytes()


def write(path, data):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    Path(path).write_bytes(data)


BUILD_PATH_RE = re.compile(rb"04_HMI_DEV-([^/\x00]{1,32})/")


def firmware_hints(img):
    """Build-version tokens the vendor's own build paths leave in the image."""
    return sorted({m.group(1).decode("latin1") for m in BUILD_PATH_RE.finditer(bytes(img))})


def check_firmware(img, token, label):
    """Refuse to patch an image that is not the one these addresses came from.

    The per-patch ``expect`` bytes are only a heuristic. A short sequence like
    ``li r3,0 ; blr`` can sit at the recorded address in a different firmware version
    by coincidence, and two entries in this repository do exactly that on
    ``5.42.B.R4`` - they would be applied silently to the wrong offset. Addresses are
    per firmware version, so the version itself is checked explicitly.

    ``token`` is a substring of the build path the vendor leaves in the image, e.g.
    ``5.43.A.R2`` from ``E:/ccm_wa71/04_HMI_DEV-5.43.A.R2/04_HMI_DEV/...``. A variant
    with no ``firmware`` key is patched as before, with only the ``expect`` guard.
    """
    if not token:
        return
    if token.encode("latin1") in img:
        print("    firmware      %s" % token)
        return
    hints = firmware_hints(img)
    raise SystemExit(
        "%s: this image is not %s - refusing to patch.\n"
        "  Addresses are per firmware version, and the expect-byte check is not a\n"
        "  reliable substitute: short instruction sequences recur across versions.\n"
        "  Build tokens found in this image: %s"
        % (label, token, ", ".join(hints) if hints else "none")
    )


def check_build(img, name, spec):
    """Refuse to patch a variant when the image is a *different* build in the patch set.

    This deliberately fires only when the image matches some other build, and stays quiet when
    it matches none. Those two cases look similar and are not: "matches none" is already
    answered by ``check_firmware`` (wrong version) and by the per-patch ``expect`` check inside
    ``apply_patches`` (wrong bytes), and both say so precisely. Adding a third message for it
    would pre-empt the more specific one.

    What is genuinely new here is the wrong-*build* case, where the expect check fails at some
    address and reports a byte mismatch rather than the fact that the package is simply a
    different build. It also covers what the expect bytes cannot: ``AUDIO_BT`` and
    ``AUDIO_BT_256`` declare identical addresses and identical bytes, so no amount of
    spot-checking separates them.
    """
    builds = identify(img, variants_from_spec(spec, "<inline>"))
    if name in builds or not builds:
        return
    raise SystemExit(
        "%s: this image is not the %s build - refusing to patch.\n"
        "  It matches: %s. Addresses are per build, so patching it with these addresses\n"
        "  would write to the wrong locations. Run tools/fingerprint.py for a verdict."
        % (name, name, ", ".join(builds))
    )


INF_CRC_RE = re.compile(rb"CRC32: (-?\d+)")
SMEG_CRC_RE = re.compile(rb"BIGQUICK_CRC32: (-?\d+)")


def disassemble(blob):
    """PowerPC disassembly, or None when capstone is not installed.

    Returns None rather than raising so the caller can skip the check: this tool declares no
    dependencies, and it has to keep running on a machine with nothing but the standard
    library. capstone is in the `dev` extra, so CI does run the check.
    """
    try:
        import capstone
    except ImportError:
        return None
    md = capstone.Cs(capstone.CS_ARCH_PPC, capstone.CS_MODE_BIG_ENDIAN | capstone.CS_MODE_32)
    md.detail = True
    # stripped because capstone renders a no-operand instruction as "blr " with a trailing
    # space, which would otherwise never compare equal to a declared "blr"
    return [("%s %s" % (i.mnemonic, i.op_str)).strip() for i in md.disasm(bytes(blob), 0)]


def check_site(site, label, addr, declared):
    """Assert a patched site decodes to whole, valid instructions.

    The `expect` check catches patching the wrong firmware. This catches the other half: a
    `bytes` string that is corrupt, truncated, or not instruction-aligned, which would leave
    the site decoding as something nobody intended. `disasm`, when a patch declares it, pins
    the exact instructions.

    Returns the disassembly, or None when capstone is unavailable.
    """
    if len(site) % 4:
        raise SystemExit(
            "%s: patch at %#x is %d bytes, not a whole number of PowerPC instructions"
            % (label, addr, len(site))
        )
    got = disassemble(site)
    if got is None:
        return None
    if len(got) != len(site) // 4:
        raise SystemExit(
            "%s: patch at %#x does not decode cleanly (%d instruction(s) from %d bytes): %s"
            % (label, addr, len(got), len(site), " ; ".join(got))
        )
    if declared:
        want = [d.strip() for d in declared.split(";")]
        if got != want:
            raise SystemExit(
                "%s: patch at %#x decodes to [%s] but declares [%s]"
                % (label, addr, " ; ".join(got), " ; ".join(want))
            )
    return got


def assert_crc_field(out_dir, rel, regex, want, what):
    """A `.inf` names its file's CRC32 in text; check the written file agrees."""
    blob = load(os.path.join(out_dir, rel))
    m = regex.search(blob)
    if not m:
        raise SystemExit("%s: no CRC field in %s" % (what, rel))
    if int(m.group(1)) != s32(want):
        raise SystemExit(
            "%s: %s declares CRC32 %d but the file hashes to %d"
            % (what, rel, int(m.group(1)), s32(want))
        )


def assert_crc_record(out_dir, rel, want, what):
    """A `ctrl` record stores a CRC as a raw big-endian word, so look for the bytes."""
    blob = load(os.path.join(out_dir, rel))
    if struct.pack(">I", want) not in blob:
        raise SystemExit("%s: %s does not record CRC %#010x" % (what, rel, want))


def verify_written(out_dir, name, v, base, stock=False):
    """Re-read a variant's written files and close the loop on them.

    Everything up to here has been checked in memory. This goes back to the files on disk,
    because a write that did not land, or landed twice, is exactly the failure the earlier
    checks cannot see. Returns the module `ctrl` CRC for the root check.

    `ctrl.bin` is not checked here: it records every module's ctrl CRC, so it can only be
    verified once every variant has been written.
    """
    bq = load(os.path.join(out_dir, v["app_image"]))
    start, img = inflate(bq)
    for p in v["patches"]:
        off = int(str(p["addr"]), 16) - base
        # in stock mode nothing was written, so the site must still hold the original
        want = bytes.fromhex(p["expect"] if stock else p["bytes"])
        if img[off : off + len(want)] != want:
            raise SystemExit(
                "%s: after writing, %#x does not hold the %s bytes"
                % (name, int(str(p["addr"]), 16), "original" if stock else "patched")
            )

    bq_crc = crc32(bq)
    assert_crc_field(out_dir, v["inf"], INF_CRC_RE, bq_crc, name)
    assert_crc_field(out_dir, v["smeg_inf"], SMEG_CRC_RE, bq_crc, name)

    inf_crc = crc32(load(os.path.join(out_dir, v["inf"])))
    smeg_crc = crc32(load(os.path.join(out_dir, v["smeg_inf"])))
    ctrl_crc = crc32(load(os.path.join(out_dir, v["ctrl"])))
    assert_crc_record(out_dir, v["ctrl"], bq_crc, name)
    assert_crc_record(out_dir, v["ctrl"], inf_crc, name)
    assert_crc_record(out_dir, v["ctrl"], smeg_crc, name)

    print("    %-14s verified end to end" % "crc chain")
    print("      f_BigQuick.bin      %#010x" % bq_crc)
    print("      f_BigQuick.bin.inf  %#010x" % inf_crc)
    print("      smeg.inf            %#010x" % smeg_crc)
    print("      %-19s %#010x" % (v["ctrl"], ctrl_crc))
    return ctrl_crc


def verify_root(out_dir, ctrl_crcs):
    """`ctrl.bin` records every module ctrl CRC; check each one landed."""
    for name, crc in ctrl_crcs.items():
        assert_crc_record(out_dir, "ctrl.bin", crc, name)
    print("    %-14s name=%s (%d)" % ("ctrl.bin", "verified", len(ctrl_crcs)))


def apply_patches(img, base, patches, label):
    for p in patches:
        addr = int(str(p["addr"]), 16)
        off = addr - base
        if off < 0 or off + 4 > len(img):
            raise SystemExit("%s: patch address %#x outside image" % (label, addr))
        expect = bytes.fromhex(p["expect"])
        if img[off : off + len(expect)] != expect:
            raise SystemExit(
                "%s: at %#x expected %s, found %s (wrong firmware build?)"
                % (label, addr, expect.hex(), img[off : off + len(expect)].hex())
            )
        new = bytes.fromhex(p["bytes"])
        check_site(new, label, addr, p.get("disasm"))
        img[off : off + len(new)] = new
        print(
            "    %-14s %#010x  %s -> %s   %s"
            % (label, addr, expect.hex(), new.hex(), p.get("why", ""))
        )
        after = disassemble(new)
        if after:
            print("      %-14s %s" % ("", " ; ".join(after)))
    return img


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    default_patches = os.path.normpath(
        os.path.join(here, os.pardir, "patches", "aux-autoswitch.json")
    )

    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--src", required=True, help="original package directory")
    ap.add_argument("--out", required=True, help="output directory for changed files")
    ap.add_argument("--patches", default=default_patches, help="patch definition JSON")
    ap.add_argument("--only", nargs="*", default=None, help="variant name(s) to patch")
    ap.add_argument(
        "--copy-package",
        action="store_true",
        help="copy the whole package into --out before overlaying changes",
    )
    ap.add_argument("--level", type=int, default=6, help="zlib level for re-packing (default 6)")
    ap.add_argument(
        "--stock",
        action="store_true",
        help="apply no patches, but rebuild and verify the checksum cascade",
    )
    args = ap.parse_args()

    spec = json.loads(Path(args.patches).read_text())
    variants = spec["variants"]
    if args.only:
        variants = {k: v for k, v in variants.items() if k in args.only}
        missing = set(args.only) - set(variants)
        if missing:
            raise SystemExit("unknown variant(s): %s" % ", ".join(sorted(missing)))

    print("patch set : %s (%s)" % (spec.get("name", "?"), args.patches))
    print("source    : %s" % args.src)
    print("output    : %s" % args.out)
    if args.copy_package:
        print("copying package ...")
        shutil.copytree(args.src, args.out, dirs_exist_ok=True)

    root_ctrl = bytearray(load(os.path.join(args.src, "ctrl.bin")))
    done = 0
    ctrl_crcs = {}

    for name, v in variants.items():
        paths = {k: os.path.join(args.src, v[k]) for k in ("app_image", "inf", "smeg_inf", "ctrl")}
        if not all(os.path.exists(p) for p in paths.values()):
            print("  [skip] %s not present in package" % name)
            continue

        base = int(str(v.get("base", hex(DEFAULT_BASE))), 16)
        old_bq = load(paths["app_image"])
        old_inf = load(paths["inf"])
        old_smeg = load(paths["smeg_inf"])
        old_ctrl = load(paths["ctrl"])

        old_crc = {
            "bq": crc32(old_bq),
            "inf": crc32(old_inf),
            "smeg": crc32(old_smeg),
            "ctrl": crc32(old_ctrl),
        }

        print("  [%s] %d bytes" % (name, len(old_bq)))
        start, img = inflate(old_bq)
        img = bytearray(img)
        check_firmware(img, v.get("firmware"), name)
        if args.stock:
            # No patches, but everything else - re-pack, re-seal, verify. The unit rewrites
            # the application only when its content differs, so this is a baseline to
            # restore from, and a canary for the packaging path itself: if a re-sealed stock
            # package is refused, the sealing is wrong rather than the patch.
            print("    %-14s stock: no patches applied" % "mode")
        else:
            check_build(img, name, spec)
            apply_patches(img, base, v["patches"], name)

        new_bq = old_bq[:start] + zlib.compress(bytes(img), args.level)
        chk = zlib.decompressobj()
        if chk.decompress(new_bq[start:]) + chk.flush() != bytes(img):
            raise SystemExit("%s: round-trip verification failed" % name)

        new_crc_bq = crc32(new_bq)
        new_inf = rewrite_inf(old_inf, new_crc_bq)
        new_smeg = rewrite_smeg_inf(old_smeg, new_crc_bq)
        new_crc_inf, new_crc_smeg = crc32(new_inf), crc32(new_smeg)

        ctrl = bytearray(old_ctrl)
        ctrl = swap_crc(ctrl, old_crc["bq"], new_crc_bq, "%s/BigQuick" % name)
        ctrl = swap_crc(ctrl, old_crc["inf"], new_crc_inf, "%s/BigQuick.inf" % name)
        ctrl = swap_crc(ctrl, old_crc["smeg"], new_crc_smeg, "%s/smeg.inf" % name)
        new_ctrl = bytes(ctrl)
        new_crc_ctrl = crc32(new_ctrl)

        root_ctrl = bytearray(
            swap_crc(root_ctrl, old_crc["ctrl"], new_crc_ctrl, "%s_ctrl.bin" % name)
        )

        for key, data in (
            ("app_image", new_bq),
            ("inf", new_inf),
            ("smeg_inf", new_smeg),
            ("ctrl", new_ctrl),
        ):
            write(os.path.join(args.out, v[key]), data)

        print(
            "    %-14s %9d -> %-9d  crc %#010x -> %#010x"
            % ("f_BigQuick", len(old_bq), len(new_bq), old_crc["bq"], new_crc_bq)
        )
        ctrl_crcs[name] = verify_written(args.out, name, v, base, stock=args.stock)
        done += 1

    if done:
        write(os.path.join(args.out, "ctrl.bin"), bytes(root_ctrl))
        verify_root(args.out, ctrl_crcs)
        print("wrote ctrl.bin (root manifest)")

    print("changed files written to %s (%d variant(s))" % (args.out, done))
    if not done:
        sys.exit(1)


if __name__ == "__main__":
    main()
