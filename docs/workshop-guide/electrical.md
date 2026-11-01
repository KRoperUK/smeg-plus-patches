# Electrical & audio

The radio, speakers, aerial, harness and the SMEG ECU — the parts this project
actually patches around. Configuration entries at the end are read-only
interest for most work.

| # | Procedure | Code | Manual pages |
|---|---|---|---|
| 7 | Radio unit | `D5AG014WP0` | 1182 |
| 8 | Speakers | `D5AG014RP0` | 1174 |
| 9 | Radio aerial | `D5AG014UP0` | 1178 |
| 10 | Cabin harness | `D6AG013HP0` | 1347 |
| 11 | SMEG ECU | `D6AM01HFP0` | 1201 |
| — | Instrument panel configuration | `D6AM01CNP0` | 1231, 1870 |
| — | Matrix display configuration | `D6AM01CPP0` | 1199, 1233 |

## D5AG014WP0 - Radio unit

Page **1182**. The DIRANA2 tuner block the AUX project routes around.

Related: [The AUX chain](../AUX_CHAIN.md) · [The audio module](../AUDIO_MODULE.md) ·
[Hardware](../HARDWARE.md).

## D5AG014RP0 - Speakers

Front and rear doors. Page **1174**.

Related: [Hardware](../HARDWARE.md) (amplifier and speaker outputs).

## D5AG014UP0 - Radio aerial

Page **1178**. Roof-mounted; the GPS puck beside it is fed phantom power — do
not short it.

Related: [Hardware](../HARDWARE.md).

## D6AG013HP0 - Cabin harness

Passenger-compartment harness. Page **1347**. Harness repair principles are
under `D6AM03P0`, pages **1206, 1351, 1426**.

Related: [The AUX signal path](../AUX_SIGNAL.md) (the three AUX lines) ·
[Hardware](../HARDWARE.md) (pin table).

## D6AM01HFP0 - SMEG ECU

Configuration of the SMEG data-communication ECU. Page **1201**. This is the
unit's identity on the CAN buses — read-only interest for patch work; do not
reconfigure what you do not understand.

Related: [Kernel & partitions](../PLATFORM.md).

## D6AM01CNP0 - Instrument panel configuration

Pages **1231, 1870**. Display-side settings for the cluster.

## D6AM01CPP0 - Matrix display configuration

Pages **1199, 1233**. Matrix display settings; cosmetic for patch work.

## Related reading

- [Body & fascia](body.md) — getting the trim off to reach the wiring.
- [The AUX chain](../AUX_CHAIN.md) and [the AUX signal path](../AUX_SIGNAL.md)
  — what the radio and harness feed.
- [Hardware](../HARDWARE.md) — pin tables and connectors.
