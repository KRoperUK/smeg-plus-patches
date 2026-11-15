#!/usr/bin/env python3
"""PowerPC (32-bit, big-endian) disassembler for SMEG+ application images.

Resolves symbols from an absolute symbol map (e.g. Application/PKG/abs_symbols_base.txt)
and annotates indirect calls made through the `lis/addi -> mtctr -> bctrl` idiom that
the compiler emits, so `bctrl` shows the callee name.

usage:
    python3 tools/ppcdis.py IMAGE SYMFILE ADDRESS END
    python3 tools/ppcdis.py app_nav.bin abs_symbols_base.txt 0x0230331c 0x02303460
"""

import argparse
import bisect
import os
import struct
import sys
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from symbols import load_symbols

try:
    import capstone.ppc
    from capstone import CS_ARCH_PPC, CS_MODE_32, CS_MODE_BIG_ENDIAN, Cs
    from capstone.ppc import PPC_OP_IMM, PPC_OP_REG
except ImportError:
    sys.exit("capstone is required:  pip install capstone")

_GPR = tuple(getattr(capstone.ppc, "PPC_REG_R%d" % n) for n in range(32))

# Opcodes whose result lands in RT (bits 21-25) or RA (bits 16-20), mirroring
# survey.written: dropping a register an instruction overwrote only loses a reference,
# while keeping it past the overwrite invents a call target that is not there.
# lis/addi/ori are absent: the tracking below overwrites (or drops) them itself.
_CLOBBER_RT = {7, 8, 12, 13, 32, 33, 34, 35, 40, 41, 42, 43, 46}
_CLOBBER_RA = {20, 21, 23, 25, 26, 27, 28, 29}


def _clobbered(w, op, mnemonic=""):
    """Capstone register ids this instruction word overwrites, if any."""
    # mtctr/mtlr only move a GPR into a special register, which the tracking below
    # reads — popping their source would blind the very call they set up.
    out = []
    if op == 31:
        if mnemonic not in ("mtctr", "mtlr"):
            out = [_GPR[(w >> 21) & 31], _GPR[(w >> 16) & 31]]
    elif op in _CLOBBER_RT:
        out = [_GPR[(w >> 21) & 31]]
    elif op in _CLOBBER_RA:
        out = [_GPR[(w >> 16) & 31]]
    return tuple(out)


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("image")
    ap.add_argument("symbols")
    ap.add_argument("start")
    ap.add_argument("end")
    ap.add_argument("--base", default="0x01000000")
    args = ap.parse_args()

    base = int(args.base, 16)
    start, end = int(args.start, 16), int(args.end, 16)
    img = Path(args.image).read_bytes()
    if not (base <= start < end <= base + len(img)):
        sys.exit(
            "range %#x..%#x outside the image (%#x..%#x); a start below base wraps "
            "via negative indexing and disassembles the wrong bytes"
            % (start, end, base, base + len(img))
        )
    syms = load_symbols(args.symbols)
    addrs = sorted(syms)

    def name(a, tol=0x100):
        if a in syms:
            return syms[a]
        i = bisect.bisect_right(addrs, a) - 1
        if i >= 0 and a - addrs[i] <= tol:
            return "%s+0x%x" % (syms[addrs[i]], a - addrs[i])
        return "0x%x" % a

    md = Cs(CS_ARCH_PPC, CS_MODE_32 | CS_MODE_BIG_ENDIAN)
    md.detail = True

    regs, ctr, lr = {}, None, None
    for ins in md.disasm(img[start - base : end - base], start):
        m, ops = ins.mnemonic, ins.op_str
        o = ins.operands
        ann = ""
        raw = img[ins.address - base : ins.address - base + 4]
        if len(raw) == 4:
            w = struct.unpack(">I", raw)[0]
            op = w >> 26
            if op != 15 and op not in (14, 24):
                for r in _clobbered(w, op, m):
                    regs.pop(r, None)
        if m == "lis" and len(o) == 2 and o[1].type == PPC_OP_IMM:
            regs[o[0].reg] = o[1].imm << 16
        elif m == "addi" and len(o) == 3 and o[1].type == PPC_OP_REG and o[2].type == PPC_OP_IMM:
            b = regs.get(o[1].reg)
            if b is not None:
                regs[o[0].reg] = (b + o[2].imm) & 0xFFFFFFFF
            else:
                regs.pop(o[0].reg, None)  # overwritten with an untracked value
        elif m == "ori" and len(o) == 3 and o[1].type == PPC_OP_REG and o[2].type == PPC_OP_IMM:
            b = regs.get(o[1].reg)
            if b is not None:
                regs[o[0].reg] = b | o[2].imm
            else:
                regs.pop(o[0].reg, None)  # overwritten with an untracked value
        elif m == "mtctr" and len(o) == 1:
            ctr = regs.get(o[0].reg)
        elif m == "mtlr" and len(o) == 1:
            lr = regs.get(o[0].reg)
        elif m in ("bctrl", "bcctrl", "blrl"):
            t = lr if m == "blrl" else ctr
            if t:
                ann = "  ; call %s" % name(t)
        elif m in ("b", "bl", "ba", "bla") and o and o[-1].type == PPC_OP_IMM:
            ann = "  ; -> %s" % name(o[-1].imm)
        elif m.startswith("bc") and o and o[-1].type == PPC_OP_IMM:
            ann = "  ; -> %s" % name(o[-1].imm)
        print("  %08x: %-9s %-34s%s" % (ins.address, m, ops, ann))


if __name__ == "__main__":
    main()
