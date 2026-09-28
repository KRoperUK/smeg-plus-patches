# Ring tones and wait tones

Custom audio on the head unit, and the tooling to prepare it.

## What the unit plays

All plain PCM WAV. Two formats, depending on the slot:

| slot(s) | path | format |
|---|---|---|
| `ring1` … `ring5` | `ring_tones/ringNRT.wav` | 16-bit **mono 44 100 Hz** |
| `busy`, `error`, `ok`, `ko` | `ring_tones/{busy,error,ok,ko}RT.wav` | 16-bit **mono 44 100 Hz** |
| `wait:<LANG>` | `wait_tones/MM_HoldOn_<LANG>_8kHz.wav` | 16-bit **stereo 8 000 Hz** |

Wait-tone languages: `CRC CZC DUN ENG FRF GED HRH ITI PLP PTP RUR SPE TRT`.
The `RT` suffix in the ring-tone filenames is part of the real name.

Full inventory with durations is in [Media partition](MEDIA_PARTITION.md).

## The tool

`tools/ringtones.py` — no Python dependencies; uses **ffmpeg** when it needs to decode
anything other than an already-correct WAV (so mp3, ogg, flac, m4a all work). Without
ffmpeg it will still copy a WAV that is already in the target format.

```sh
uv run tools/ringtones.py list                          # slots and expected formats
uv run tools/ringtones.py probe song.mp3                # what is this file?
uv run tools/ringtones.py export --tree media/ -o stock/ # back up the stock tones
uv run tools/ringtones.py convert song.mp3 --slot ring1 -o ring1RT.wav
uv run tools/ringtones.py stage song.ogg --slot ring5 --tree media/
```

`--tree` is an **extracted media partition** — a directory containing `ring_tones/`
and `wait_tones/`. `stage` converts to the exact format and writes it under the correct
filename, ready to be packed back up.

## GUI

`tools/patch_studio.py` (Qt / PySide6) wraps the same conversion, lets you preview
and export the stock tones, and builds patched packages from the bundled
`patches/*.json` definitions — including the always-enable-AUX and sticky-AUX variants.
Multiple definitions can be ticked at once; a conflicting address is reported rather
than silently applied.

It has three tabs: **Ringtones**, **Splash screens** (the brand artwork — see
[Media partition](MEDIA_PARTITION.md#brand-logo-packages-data_basegraphicslogopkg)) and
**Pack & patch**.

```sh
pip install -r tools/requirements-gui.txt
uv run tools/patch_studio.py
```

The studio builds and runs (verified on macOS with PySide6 6.11.2 — it also has headless
GUI tests in `tests/test_studio.py`, which skip when PySide6 is absent). It has not been
used to produce a package that was then flashed to a car, so treat the end-to-end result
as unverified; the pieces it drives are covered by tests. The **CLI sequence below is the
verified path** — walk it if the studio gives you trouble.

## How a tone gets onto the unit

The tones live **inside the media partition** (`system.bin`), a gzip'd tar with its own
checksum cascade. `tools/patch_media.py` swaps a file inside the tar and rebuilds
`system_ctrl.bin` → `system.bin` → `system.bin.inf` → the module manifest → the root manifest.
A replacement tone almost never matches the original size, so the tar and every manifest above
it change; the `SIZE:` / `SIZE_1..SIZE_32` fields are computed from the tar (see
[Media partition](MEDIA_PARTITION.md#the-size-fields-solved)).

## Worked example: replacing a ring tone

The whole path, from an mp3 to a package that will flash, replacing `ring1`.

The one-command version is `uv run tools/build_package.py --manifest builds/alien-piano-riff.json`
(edit its paths first); in a manifest, `media.tones` maps a slot's file to the source audio and
an optional `gain_db`. The manual steps below are what it runs.

```sh
# 1. work on a copy — never edit your rollback package
cp -a SMEG_PLUS_UPG SMEG_PLUS_UPG_custom

# 2. application patches first (they rewrite ctrl.bin and NAV_ctrl.bin)
uv run tools/patch_smeg.py --src SMEG_PLUS_UPG --out overlay
rsync -a overlay/ SMEG_PLUS_UPG_custom/

# 3. extract the media partition, keeping the stock tones for restore
uv run tools/patch_media.py extract --package SMEG_PLUS_UPG_custom --module NAV \
    --tree media --backup backup --backup-tones-only

# 4. convert and stage the replacement into the tree
uv run tools/ringtones.py convert my-tone.mp3 --slot ring1 -o media/ring_tones/ring1RT.wav

# 5. rebuild the partition and its checksum cascade
uv run tools/patch_media.py apply --package SMEG_PLUS_UPG_custom --module NAV \
    --tree media --out overlay2
rsync -a overlay2/ SMEG_PLUS_UPG_custom/

# 6. re-seal — without this the unit refuses the media
uv run tools/patch_contract.py --package SMEG_PLUS_UPG_custom
```

!!! warning "Order matters"

    `patch_smeg` rewrites `NAV_ctrl.bin` and `ctrl.bin` for the application image;
    `patch_media` then swaps the `system.bin` records inside those same manifests. Running
    the media step against the already-patched package means it carries the application
    change rather than reverting it. The contract step goes **last**, because it seals
    whatever the package finally contains. This is the same app → media → contract rule laid
    out in [Running the tools](RUNNING.md#cheat-sheet).

`apply --dry-run` shows the diff and writes nothing:

```
changes (1):
   ring_tones/ring1RT.wav                                 157018 ->   278556
```

To put the original back:

```sh
uv run tools/patch_media.py restore --backup backup --tree media \
    --module NAV --only ring_tones/ring1RT.wav
```

## Names

The name each slot shows in the phone's ringtone menu is **a string literal in the
application image**, not part of the audio file and not a database row *(read, #190)*:
`C_SRV_RING_TOUCH::SetRingFilePath` pairs each `ringN RT.wav` with one of them and serves the
list over DBus (`GetRingToneList`), and the menu displays those strings.

| slot | stock name | address (NAV 5.43.A.R2) | max length |
|---|---|---|---|
| ring1 | `Alien` | `0x03063198` | 7 |
| ring2 | `Blue_lemon` | `0x030631ac` | 11 |
| ring3 | `Blue_tangerine` | `0x030631c4` | 15 |
| ring4 | `Green_apple` | `0x030631e0` | 11 |
| ring5 | `Green_lemon` | `0x030631f8` | 11 |

The maximum is the string plus the NUL padding before the next literal; each string has
exactly one reference *(read)*. `build_package.py`'s `media.names` turns into an application
patch that rewrites the literal in place:

```json
"media": { "names": { "ring1": "Piano" } }
```

It refuses a name that is too long, non-ASCII, or for a module whose addresses are not
mapped (only NAV 5.43.A.R2 is).

Built and verified offline (the patched image carries the new name and nothing else
changes); **not yet confirmed on a car**.

`ringtones.py names` / `rename` inspect and edit a different list: `phone/Ringing_List` in the
seed `up_common.sqlite`. The unit does not display that list; the key appears nowhere in the
application image *(read)*.

## Level — the thing that will annoy you

The stock tones are mastered loud: peak around **−1 dBFS**. A normalised music track is
typically 6–8 dB quieter, and in a car that difference is obvious — the new tone sounds
muted next to the others.

`ringtones.py convert` deliberately does **not** touch level. It converts format only
(`-ac <n> -ar <rate> -c:a pcm_s16le`), so what you supply is exactly what plays. Check
your file against the stock tone before you flash:

```sh
ffmpeg -i old.wav  -af volumedetect -f null - 2>&1 | grep -E "mean_volume|max_volume"
ffmpeg -i ring1RT.wav -af volumedetect -f null - 2>&1 | grep -E "mean_volume|max_volume"
```

If it is quiet, match the level yourself rather than letting the tool guess:

```sh
# simple gain, then convert
ffmpeg -i my-tone.mp3 -af "volume=7dB" -ar 44100 -ac 1 -c:a pcm_s16le ring1RT.wav

# or loudness-normalise with a true-peak ceiling, so nothing clips
ffmpeg -i my-tone.mp3 -af "loudnorm=I=-16:TP=-1.0" -ar 44100 -ac 1 -c:a pcm_s16le ring1RT.wav
```

As a reference, the stock `ring1RT.wav` measures `mean_volume: -14.4 dB`,
`max_volume: -1.1 dB`.
