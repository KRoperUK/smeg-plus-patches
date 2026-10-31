# Workshop guide (208, 2012–2019)

Pick a part on the car to jump to its workshop procedure. Every entry gives the
procedure **code and manual page** — open your own copy of the manual there and
follow it. The manual itself is not reproduced here (see the box below).

!!! warning "Bring your own manual — it is not in this repository"

    The 208 workshop manual (a ~3,100-page, ~600-procedure PSA document) is a
    copyrighted vendor publication. Like firmware (see [the no-firmware rule](index.md#smeg-patches)),
    it is **never committed here**: no PDF, no extracted pages, no OCR text, no
    rendered diagrams. This page carries codes, part names, page numbers and
    our own cross-links only. Anything built from the manual's content runs on
    your machine, against your legally obtained copy.

!!! danger "Airbags, high voltage, and the fascia"

    Several procedures near the ones below work around pyrotechnic components
    (airbags, seat-belt pre-tensioners). Follow the manual's own safety
    sequences — battery disconnect, waiting times, connector handling — and treat
    them as mandatory, not advisory. If in doubt, stop and ask a professional.

## Car map

<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 660 340" width="100%" role="img" aria-label="Schematic 208 side view with selectable parts">
  <g fill="none" stroke="#555" stroke-width="2">
    <line x1="20" y1="292" x2="640" y2="292" stroke-width="1.5"/>
    <path d="M60,252 L72,208 Q76,192 96,190 L152,184 L212,126 Q220,116 234,116
             L358,116 Q370,116 378,126 L428,180 L518,192 Q558,197 574,216
             L588,236 Q593,250 578,252 L540,252 A38,38 0 0 0 462,252
             L208,252 A38,38 0 0 0 132,252 Z"/>
    <path d="M228,128 L356,128 L400,172 L208,172 Z" stroke-width="1.5"/>
    <line x1="292" y1="128" x2="292" y2="172" stroke-width="1.5"/>
    <line x1="208" y1="172" x2="400" y2="172" stroke-width="1.5"/>
    <line x1="300" y1="176" x2="296" y2="250" stroke-width="1.2"/>
    <line x1="318" y1="196" x2="340" y2="196" stroke-width="2.5"/>
    <line x1="228" y1="196" x2="250" y2="196" stroke-width="2.5"/>
    <path d="M576,220 L588,238 L576,240 Z" stroke-width="1.5"/>
    <path d="M62,224 L74,224 L70,240 L60,240 Z" stroke-width="1.5"/>
    <circle cx="500" cy="262" r="30"/>
    <circle cx="500" cy="262" r="12" stroke-width="1.5"/>
    <circle cx="170" cy="262" r="30"/>
    <circle cx="170" cy="262" r="12" stroke-width="1.5"/>
    <path d="M246,116 L252,98 L258,116 Z" stroke-width="1.5"/>
  </g>
  <g font-family="system-ui,sans-serif" font-size="11" font-weight="bold" text-anchor="middle">
    <a href="#c5fg01a6p0-multifunction-screen"><title>Multifunction screen</title><circle cx="470" cy="128" r="11" fill="#3f51b5"/><text x="470" y="132" fill="#fff">1</text></a>
    <a href="#c5fg01a7p0-instrument-panel"><title>Instrument panel</title><circle cx="430" cy="132" r="11" fill="#3f51b5"/><text x="430" y="136" fill="#fff">2</text></a>
    <a href="#d6am01hfp0-smeg-ecu"><title>SMEG ECU</title><circle cx="404" cy="152" r="11" fill="#3f51b5"/><text x="404" y="156" fill="#fff">3</text></a>
    <a href="#c5fg01a8p0-centre-console"><title>Centre console</title><circle cx="492" cy="222" r="11" fill="#3f51b5"/><text x="492" y="226" fill="#fff">4</text></a>
    <a href="#d5ag014wp0-radio-unit"><title>Radio unit</title><circle cx="516" cy="190" r="11" fill="#3f51b5"/><text x="516" y="194" fill="#fff">5</text></a>
    <a href="#c5fg01aap0-fascia-air-vents"><title>Fascia air vents</title><circle cx="548" cy="160" r="11" fill="#3f51b5"/><text x="548" y="164" fill="#fff">6</text></a>
    <a href="#c5fg01adp0-fascia-panel-switches"><title>Fascia panel switches</title><circle cx="540" cy="198" r="11" fill="#3f51b5"/><text x="540" y="202" fill="#fff">7</text></a>
    <a href="#c5fg01aep0-dashboard"><title>Dashboard</title><circle cx="368" cy="118" r="11" fill="#3f51b5"/><text x="368" y="122" fill="#fff">8</text><line x1="376" y1="126" x2="398" y2="158" stroke="#3f51b5" stroke-width="1.5"/></a>
    <a href="#d5ag014rp0-speakers"><title>Speakers</title><circle cx="262" cy="246" r="11" fill="#3f51b5"/><text x="262" y="250" fill="#fff">9</text></a>
    <a href="#d5ag014up0-radio-aerial"><title>Radio aerial</title><circle cx="252" cy="82" r="11" fill="#3f51b5"/><text x="252" y="86" fill="#fff">10</text><line x1="252" y1="93" x2="252" y2="99" stroke="#3f51b5" stroke-width="1.5"/></a>
    <a href="#d6ag013hp0-cabin-harness"><title>Cabin harness</title><circle cx="300" cy="270" r="11" fill="#3f51b5"/><text x="300" y="274" fill="#fff">11</text><line x1="300" y1="259" x2="300" y2="253" stroke="#3f51b5" stroke-width="1.5"/></a>
  </g>
</svg>

1. [Multifunction screen](#c5fg01a6p0-multifunction-screen) · 2. [Instrument panel](#c5fg01a7p0-instrument-panel) ·
3. [SMEG ECU](#d6am01hfp0-smeg-ecu) · 4. [Centre console](#c5fg01a8p0-centre-console) ·
5. [Radio unit](#d5ag014wp0-radio-unit) · 6. [Fascia air vents](#c5fg01aap0-fascia-air-vents) ·
7. [Fascia panel switches](#c5fg01adp0-fascia-panel-switches) · 8. [Dashboard](#c5fg01aep0-dashboard) ·
9. [Speakers](#d5ag014rp0-speakers) · 10. [Radio aerial](#d5ag014up0-radio-aerial) ·
11. [Cabin harness](#d6ag013hp0-cabin-harness)

## Procedures

Page numbers are 1-based PDF pages in a complete copy (the manual repeats some
procedures in several sections; every listed page reaches the same sequence).
3-door, 5-door and right-hand-drive variants each have their own entries — check
the bookmark matches your car before starting.

### C5FG01A6P0 - Multifunction screen

The SMEG+ display itself. Pages **1046, 1220, 1793**.

Related: [Hardware](HARDWARE.md) (connectors, LVDS), [Flashing](FLASHING.md)
(once the trim is back together).

### C5FG01A7P0 - Instrument panel

Pages **1227, 1800**. See also the configuration entries below.

### D6AM01HFP0 - SMEG ECU

Configuration of the SMEG data-communication ECU. Page **1201**. This is the
unit's identity on the CAN buses — read-only interest for patch work; do not
reconfigure what you do not understand.

Related: [Kernel & partitions](PLATFORM.md).

### C5FG01A8P0 - Centre console

Page **1804**. Gives access to the lower stack and cabling runs.

### D5AG014WP0 - Radio unit

Page **1182**. The DIRANA2 tuner block the AUX project routes around.

Related: [The AUX chain](AUX_CHAIN.md), [The audio module](AUDIO_MODULE.md).

### C5FG01AAP0 - Fascia air vents

Pages **1055, 1813**.

### C5FG01ADP0 - Fascia panel switches

Pages **1063, 1821**.

### C5FG01AEP0 - Dashboard

Removal/refit page **1826** (page **1852** for right-hand drive);
stripping/assembling under `C5FS011AP0` page **1860** (`C5FS011BP0` page
**1865** for right-hand drive). The big job: everything above hangs off it.

### D5AG014RP0 - Speakers

Front and rear doors. Page **1174**.

Related: [Hardware](HARDWARE.md) (amplifier, speaker outputs).

### D5AG014UP0 - Radio aerial

Page **1178**. Roof-mounted; the GPS puck beside it is fed phantom power —
do not short it.

Related: [Hardware](HARDWARE.md).

### D6AG013HP0 - Cabin harness

Passenger-compartment harness. Page **1347**. Harness repair principles under
`D6AM03P0`, pages **1206, 1351, 1426**.

Related: [The AUX signal path](AUX_SIGNAL.md) (the three AUX lines),
[Hardware](HARDWARE.md) (pin table).

### D6AM01CNP0 - Instrument panel configuration

Page **1231, 1870**.

### D6AM01CPP0 - Matrix display configuration

Pages **1199, 1233**. Display-side settings; cosmetic for patch work.

## Reading the manual on your machine

The stock manual is scanned images: no search, no selectable text. To fix your
own copy:

```sh
# WSL2 Ubuntu (tesseract-ocr-eng installed):
ocrmypdf --force-ocr -l eng --output-type pdf --optimize 1 \
  "peugeot-208-2012-2019_CHAPTERS_FIXED.pdf" \
  "peugeot-208-2012-2019_OCR_searchable.pdf"
```

Then build the searchable procedure index (stays in gitignored
`.workshop_cache/`):

```sh
uv run tools/workshop_build.py --src /path/to/peugeot-208-2012-2019_OCR_searchable.pdf
uv run tools/workshop_build.py --src /path/to/manual.pdf --relevant-only --print-table
```

For the full native-docs treatment — one page per procedure with its text and
rendered diagrams, browsable locally — run `tools/workshop_convert.py --help`
(see [Tool reference](TOOLS.md#workshop-convert)). That output is also
local-only and never committed.

## What this page does not do

- It does not replace the manual's safety sequences — those live in your copy.
- It does not host, quote, or paraphrase procedure steps beyond codes, short
  part names, and page numbers.
- It does not know your car's exact trim: 3-door vs 5-door and left- vs
  right-hand drive each have their own procedure variants, listed separately in
  the manual's bookmarks.
