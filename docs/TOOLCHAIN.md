# The reverse-engineering toolchain

Everything in [Running the tools](RUNNING.md) needs nothing but `uv`. Everything on *this*
page is for the other half of the work: reading PowerPC, writing PowerPC, and comparing two
firmware versions. None of it is bundled — it is per-machine, and it is the same whether you
are on the Mac or the Windows box.

Two of these tools are already used by the repository's own analysis:

| tool | what it is for |
|---|---|
| **`clang`** | compiles C to PowerPC. The e300 core is plain 32-bit big-endian PowerPC, so an ordinary cross-compile works. |
| **`ld.lld`** | links that code at a **fixed address**, which is what a patch site needs. |
| **`llvm-mc`** | assembles or disassembles a *single* instruction, without a linker. |
| **`llvm-objdump`**, **`llvm-objcopy`** | read a linked ELF; emit the raw injectable bytes. |
| **`rizin`** | `rz-diff` compares two firmware images — the quickest way to re-derive addresses across a version shift. |
| **Ghidra** | the decompiler. `tools/mkelf.py` output imports straight in, symbols and all. |

`capstone` and `unicorn` — used by `tools/ppcdis.py` and `tools/ppcemu.py` — are not in this
list because the `dev` extra already installs them.

## Installing

=== "macOS"

    ```sh
    brew install llvm lld rizin ghidra
    ```

    Homebrew's LLVM is **keg-only**, so it is not on your `PATH`:

    ```sh
    LLVM="$(brew --prefix llvm)/bin"
    ```

    This repository was set up against `llvm@22`, where the prefix is
    `$(brew --prefix llvm@22)`. If you installed that formula instead of the latest, use it.

=== "Windows 11 (x86_64)"

    ```powershell
    winget install -e --id LLVM.LLVM
    winget install -e --id Gyan.FFmpeg
    ```

    The official LLVM build includes `clang`, `clang++`, `lld`, `llvm-mc`, `llvm-objdump`
    and `llvm-objcopy`, and installs to `C:\Program Files\LLVM\bin`, which the installer
    puts on `PATH`. **All targets are enabled in the Windows build**, so this `clang` can
    target PowerPC out of the box — see the warning below, which is a macOS-only trap.

    `rizin` has no `winget` package; take the portable `rizin-windows-share64-*.zip` from
    the [Rizin releases](https://rizin.re/install/) and put its `bin` on `PATH`. Ghidra's
    ZIP release needs a JDK 21 or newer.

!!! warning "On macOS, the `clang` on your `PATH` cannot do this"

    `/usr/bin/clang` is Apple's, and Apple's build has **no PowerPC backend**. `clang
    -print-targets` on it will not list `ppc32`, and a `--target=powerpc-…` compile fails.
    Every command below has to use Homebrew LLVM's binary by path — which is why the
    examples set `$LLVM` first. This is the single most common way to waste an afternoon
    here. The Windows installer has no equivalent trap.

    `ld.lld` is the exception: Homebrew links it into `$(brew --prefix)/bin`, so it is on
    `PATH` after `brew install lld`. The `llvm-*` tools are not.

## Reading the image

The repository's own tools read a raw image directly:

```sh
uv run tools/unpack.py SMEG_PLUS_UPG/NAV/AppBin/f_BigQuick.bin app_nav.bin
uv run tools/ppcdis.py app_nav.bin abs_symbols_base.txt 0x0230331c 0x02303460
```

For anything larger than a function or two, wrap it into an ELF and use a real disassembler
or decompiler. `tools/mkelf.py` attaches the shipped symbol map, so the names come with it:

```sh
uv run tools/mkelf.py app_nav.bin abs_symbols_base.txt app_nav.elf
llvm-objdump -d --triple=powerpc app_nav.elf
```

To decompile rather than read assembly, import `app_nav.elf` into Ghidra and pick
**`PowerPC:BE:32:default`** as the language. There is deliberately no `e300` language ID —
Ghidra's PowerPC list has `4xx`, `e500`, `e500mc`, `MPC8270`, `QUICC` and `default`, and the
e300 is none of the specific ones, which matches the [architecture notes](ARCHITECTURE.md)
calling it plain PowerPC with no vendor extensions. Import the ELF, not the raw image: the
symbols are the reason to bother.

## Writing PowerPC

For a handful of instructions — which is what most entries in `patches/*.json` are — you do
not need a compiler or a linker. `llvm-mc` assembles text and prints the encoding, so the
`bytes` field can be written from source rather than from memory:

```sh
$LLVM/llvm-mc --triple=powerpc --show-encoding <<'EOF'
    li 3, 1
    blr
EOF
#   li   3, 1        # encoding: [0x38,0x60,0x00,0x01]
#   blr              # encoding: [0x4e,0x80,0x00,0x20]
```

That is the `aux-always-available` patch, and it is worth noticing *why* this works: the
encoding `38 60 00 01 4e 80 00 20` is exactly what `patches/aux-always-available.json`
carries. The patch was hand-assembled, and the compiler agrees with it byte for byte.

For a whole function, compile and link it. All three steps are needed, because the linker is
what places the code at the address the patch expects:

```sh
LLVM="$(brew --prefix llvm)/bin"          # Windows: C:\Program Files\LLVM\bin
LLD="$(brew --prefix lld)/bin"            # Windows: in the LLVM bin directory

$LLVM/clang --target=powerpc-unknown-none-eabi -mbig-endian -O2 -ffreestanding \
    -c mycode.c -o mycode.o

$LLD/ld.lld -m elf32ppc --image-base=0 -Ttext=0x02247718 \
    -e my_function mycode.o -o mycode.elf

$LLVM/llvm-objcopy -O binary --only-section=.text mycode.elf mycode.bin
xxd mycode.bin
```

`-ffreestanding` because there is no libc to link against. `-e` names the entry point.

!!! note "`ld.lld` needs an explicit `--image-base`"

    Without it, the linker defaults the image base to `0x10000000` and then refuses every
    patch address as being below it:

    ```
    ld.lld: error: section '.text' address (0x2247718) is smaller than image base (0x10000000);
    specify --image-base
    ```

    `--image-base=0` is the fix. This is not a mistake in the address.

To check the result before trusting it, disassemble the ELF — which, unlike the flat binary,
still carries the load address and the symbol:

```sh
$LLVM/llvm-objdump -d --triple=powerpc mycode.elf
```

## Comparing two firmware versions

Addresses move between firmware versions — the NAV image from `SMEG_5.42.B.R4` is the 5.43
one displaced by a constant 152 bytes — so this comes up every time. `rz-diff` does it
without unpacking either side into a disassembler:

```sh
rz-diff -t raw app_nav_542.bin app_nav_543.bin
```

!!! note "`rizin`'s PPC assembler is not self-contained"

    `rz-asm -a ppc` disassembles, and its separate `ppc.as` plugin wants a real assembler
    behind it via `RZ_PPC_AS`; without that variable set it prints
    `Please set 'RZ_PPC_AS' env …` and gives you nothing. Use `llvm-mc` for assembling and
    keep `rizin` for diffing, where it needs no help.

## What is verified, and what is not

The macOS side of the above was run end to end while adding this page: compiled a C function
to PowerPC, linked it at `0x02247718`, emitted a flat binary, and disassembled the result.
The bytes are `38 60 00 01 4e 80 00 20` — `li r3,1 ; blr`, the same four-word sequence the
shipped patch carries, which is the whole point of doing it this way rather than by hand.

The Windows instructions are written from the vendors' own installers and have **not** been
run on a Windows machine here. Treat the paths as right and the tools as untested.

Two things are deliberately *not* claimed:

- **Nothing here has been flashed.** The toolchain produces the bytes a patch wants; whether
  a given patch works on a car is a separate question, answered in
  [Hardware verification](VERIFICATION.md).
- **A routine larger than its patch site is unsolved.** There is no usable code cave in
  `.text`, so anything that does not fit has to branch out and back, and nothing in
  `patches/*.json` expresses a trampoline yet. Fitting the edit into the four words already
  there is still the way that works.
