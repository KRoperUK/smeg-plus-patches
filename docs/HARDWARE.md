# The hardware

What the unit physically is. Everything else on this site is about its software; this page
is the box underneath it.

!!! note "How this was obtained, and what it is not"

    Summarised from the Magneti Marelli **SMEG+ Integrated Hardware Technical Specification**
    (rev 1, dated 14/10/13) — a vendor document that is not ours and is **not** reproduced
    here — enriched with the [smeg-rce](https://github.com/vidarrt9/smeg-rce/wiki/Hardware)
    wiki summary. Every fact below is therefore *read*, from a document or a third party,
    not measured by this project on our own bench. Where a value looks like a simulation or
    an inspection artefact it is flagged. See [Sources and prior art](REFERENCES.md).

    We summarise; we do not ship the document. If you want the original, it is mirrored by
    the Brazilian regulator at `fccid.io` (see [References](REFERENCES.md)) — link to it, do
    not copy it into a repository.

## The board in one paragraph

A single-DIN Magneti Marelli head unit built around an **NXP/Freescale MPC5121e** PowerPC
SoC (the `e300` core this project executes in emulation), with **512 MB DDR2** and **4 GB
NAND flash**, plus a **16 GB internal microSD** holding cartography and the jukebox. Radio
and audio are a separate **DIRANA2** DSP front end; navigation is a **SiRFstarIV** GPS
receiver; Bluetooth is an **Infineon PBA31308** module. The display is a 7-inch **800×480**
panel on **LVDS**, optionally mirrored to a second output. An Apple authentication chip
(`MFI337S2313`) sits on the USB path so the unit can talk to iPods/iPhones.

## Logic core and generic peripherals

| part | detail |
|---|---|
| CPU | MPC5121, 396 MHz |
| core | `e300` Power Architecture (enhanced MPC603e) |
| display controller | up to 1280×720 at 60 Hz, up to 24 bpp |
| memory controller | DDR2, 512 MB @ 200 MHz |
| NAND | 4 GB, NAND flash controller |
| card host | SDHC / MMC / SD / SDIO |
| USB | USB 2.0 OTG with on-chip PHY, plus an internal USB 2.0 hub |
| Apple | `MFI337S2313` authentication chip, on a dedicated I²C bus, reset via the secondary MCU |
| internal storage | 16 GB microSD (cartography database + jukebox) |

*(The smeg-rce wiki additionally names the display controller as a PowerVR MBX; the spec
says only "embedded display controller". Treat the MBX name as the wiki's attribution, not
the spec's.)*

### Board variants

The spec lists variants `A1`, `B1`, `B2`, `D1`, `D2`, `H1`, `H2`. What changes:

- the **second USB socket** exists only on `B1`, `B2`, `D1`, `D2`, `H1`, `H2`;
- the **second LVDS output** (a copy of the first) exists only on `D1` and `D2`;
- **DAB** is available only on `B2` and `D2`;
- **external video 1** (the rear camera) is **not** fitted on `A1`.

The `A9` / `B78` / `E3` / `T9` / `G7` codes elsewhere in this site are **car models**, not
board variants — they drive which HARMONY skin and user guide a unit gets, not which board
it is built on.

## Navigation

- 12-channel GPS receiver based on a **SiRFstarIV** processor.
- Nominal cold start under 40 seconds.
- GPS antenna: active, fed **5 V** phantom power through a FAKRA code **C** (blue) connector.

## Audio and radio

- Radio with **three tuners**, phase diversity, built around the **DIRANA2** DSP and
  "LeafDice" analog tuners; RDS and TMC decoding.
- Power amplifier: class **AB**, **4 channels**, 16 W RMS at 1 % THD (13.5 V, 4 Ω).
- External HiFi amplifier support: analog (booster) ×4, or digital ×2 driven over CAN.
- External mono CD reader: stereo inputs, half-differential, on three lines.
- AUX: stereo inputs, half-differential, on three lines.
- Microphone: analog mono.

### The three audio paths

The spec describes the DSP's routing as three named paths:

| path | permanent input | output |
|---|---|---|
| 1 | tuner, analog AUX, CD changer, GSM/Bluetooth | audio process 1 → 4× speaker outputs, with an echo tap to the CPU over I²S |
| 1 (temporary, mixed) | TTS (I²S from the CPU), Beep (DSP) | — |
| 2 | external microphone (analog) | `Mic in` to the CPU, I²S |
| 3 | `Micro out` from the CPU (I²S) | `GSM in` to the GSM/Bluetooth module |

When the GSM/Bluetooth module does its own echo cancellation, paths **2 and 3 are shorted
into a single "audio process 4"**. This is the hardware under the software described in
[The audio module](AUDIO_MODULE.md): the "AUX input" the unit switches on is the
half-differential analog input of path 1.

## Video out

- One **LVDS** pair to a 7-inch **800×480** TFT at 60 Hz.
- A second LVDS pair (a copy of the first) on `D1` / `D2`.
- **DGT display** compatibility over **CAN High Speed** (touch feedback, brightness
  commands).

## USB

- One customer USB 2.0 port, guaranteed **1 A at 4.75 V**; a second on the variants above.
- An internal hub is present even on single-port units, to interface USB peripherals to the
  main MCU.
- Over-current/ESD protection (Maxim `MAX16944`) feeds an `OVERCURRENT` signal the software
  turns into a popup.
- The **Apple chip** is what makes iPod/iPhone USB work: the unit drives it over I²C and
  checks a code exchanged with the peripheral against a value in the chip.

## Bluetooth

- **Infineon PBA31308** module, with an internal printed antenna (an external-antenna BOM
  option exists).
- HFP and A2DP profiles.

## Thermal management

| threshold | behaviour |
|---|---|
| ≥ 78 °C board temperature | **degraded mode** — maximum volume limited to 15, with a popup |
| back to ≤ 74 °C | the volume limit is removed |
| ≥ 84 °C | **self-protection** — the unit switches pseudo-OFF (main board off, secondary MCU kept awake for CAN) |
| restart | after 5 minutes, filtered at 80 °C |

This is a plausible cause of "the volume would not go up" reports on a hot dash — it is a
hardware safety limit, not a software setting.

## Power

- Supplied on the 40-pin connector: **A12** `+VBAT`, **A16** `CAR_GND`.
- Operating range 10–18 V; up to 24 V for one minute (unusual supply); load-dump protection
  opens the main switch above 18 V; reverse-battery protection.
- Standby current under **1 mA** worst case at 12 V; normal mode up to ~13 A.
- A **15 A** fuse in the 40-pin connector protects the unit and the CD changer; the CD
  changer output is additionally protected by an on-board 6 A fuse.
- Below 9 V some peripherals (amplifier mute, diagnostics) are disabled, but vital
  functions work above 4.75 V.

## Connectors

Rear face:

- **40-pin** main connector — Molex `91905-1225`.
- **LVDS** display connector — Rosenberger `D4S10F-40MA5-A` / `-D`.
- **USB** rear connector — Hirose `GT17HM-4P-2DSA`.
- FAKRA antenna connectors: AM/FM1 code **B** (cream), FM2 code **G** (grey), GPS code
  **C** (blue), Bluetooth code **D**; DAB (where fitted) is orange.

### 40-pin connector — the pins the software cares about

The spec gives the full pin table as figures, so only the pins named in its prose are listed
here *(read)*:

| pin(s) | signal | notes |
|---|---|---|
| A1–A8 | speaker outputs | 4 channels, `HP_*` |
| A9 | `+DISP` | display power, switched by the unit (0.6–1.5 A) |
| A10 / A13 | comfort **CAN_L / CAN_H** | the unit is a **node** on the comfort low-speed bus, 125 kbit/s |
| A11 / A15 | DGT display **CAN HS** | 250 kbit/s, for the separate touchscreen display |
| A12 / A16 | `+VBAT` / `CAR_GND` | power |
| B1 / B7 | `VIDEO_1+ / -` | differential CVBS — the **rear camera** |
| B6 / B12 | `VIDEO_2+ / -` | CVBS; B12 is tied to ground |
| B3 / B9 | `MICRO- / MICRO+` | differential microphone with phantom power |
| **B4 / B10 / B11** | **`AUX_RIGHT` / `AUX_LEFT` / `AUX_REF`** | the analog AUX input — **this is what the whole AUX project is about** |
| C1 / C3 | CD-changer `GND` / `+VBATP_CDC` | CD-changer power |
| C2 / C7 | CD-changer `CAN_L / CAN_H` | the unit only **relays** the BSI bus here |
| C6 / C11 | deported-keyboard `CAN_H / CAN_L` | also relayed |
| C4 / C10 / C8 | `CDC_RIGHT` / `CDC_LEFT` / `CDC_REF` | CD-changer half-differential input |

The AUX input is **half-differential on three lines** (right, left, reference), 0.7 Vrms
nominal, ~10–20 kΩ, 3.6–4.4 V DC bias — which is why the unit measures it with a detector
and a threshold rather than treating it as a simple line-in. How the software does that is
in [The AUX signal path](AUX_SIGNAL.md).

## Mechanics

- 1-DIN system box, **900 g** maximum.
- Installation angle: −5° to +45° (front-to-back); slope −15° to +15°.
- FAN cooled, driven by a temperature sensor.

## What this does not tell you

- Nothing here is a supported service procedure. Opening the unit, removing it from the car
  and reflashing the front-panel MCU are all outside anything Magneti Marelli would endorse.
- Board variant is not read by any tool here. If a behaviour depends on which board a car
  has, this page is where to start looking, but the project has not correlated the two.
- The spec is from **2013** and describes the `SMEG+ Integrated` (`5.x`) generation. The
  successor (`6.x`) is a different board.
