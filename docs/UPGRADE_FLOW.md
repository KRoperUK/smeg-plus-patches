# The update flow in the application

What the **application image** does when a stick carrying `SMEG_PLUS_UPG` is present. It
covers everything from the mount, through loading the vendor's plugin and the contract check,
to the point where control passes to `upgrade.out`. [Boot & update chain](FLASH_CHAIN.md)
covers what happens after that point, from `upgrade.out`'s strings.
[Media protection](MEDIA_PROTECTION.md) covers the contract format and re-sealing.

This is a close reading of the stock **NAV `SMEG5.43.A.R2`** image, at base `0x01000000`. It
covers the families `C_BCM_UPGRADE` (353 functions), `C_HMI_UPGRADE` (293), `C_HMI_UPG`
(195), `C_HMI_UpgradeMessage` (35), `TranslateUPGString` (2), and the 48
`C_BCM_HMI_UPGRADE_CLIENT::EVT_UPG_*` forwarders. The method was:

- every `C_BCM_UPGRADE` method, and the HMI functions named below, were decompiled through
  Ghidra;
- calls below `0x01000000` were resolved against the BSP symbol map from the same `SPYSTORE`
  dump;
- the disassembly was checked where it mattered;
- the stock contract was decrypted with `tools/patch_contract.py`'s own functions to confirm
  the header layout.

Evidence tiers are as in [Verification](VERIFICATION.md). Nothing on this page was run on the
car.

## What matters for package safety

!!! warning "Code from the stick runs before the contract is checked"

    `C_BCM_UPGRADE::LoadUpgradePlugin` (`0x0187699c`) does the following, in this order
    *(read)*:

    1. It runs the BSP's `CheckCRCFile` on `<media>/SMEG_PLUS_UPG/UpgPlugin.out`.
    2. It loads the file with `MMdlopen` and resolves 25 `upgplugin_*` symbols.
    3. It **calls the plugin's own functions**: `GetInstance`, `GetVersionOfInterface`
       (which must return 6), `GetVersionOfPlugin` (which must be at least 100) and
       `GetUpgradeType`.
    4. Only then does it spawn the task `tCheckTrustedSource` (the contract check).

    So the contract does not stop stick code from running. It gates the rest of the flow:
    without `KNOWN_KEY_INSERTED`, the HMI never offers the update.

    - The contract covers `UpgPlugin.out` with a CRC record *(read; confirmed by decrypting
      the stock contract, executed)*, but that check runs after the plugin has been loaded.
    - What `CheckCRCFile` compares against is **not known**; it lives in the BSP, not this
      image. That it checks `UpgPlugin.out.inf` beside it is *inferred*.
    - **This project's tools never modify `UpgPlugin.out`.** A re-sealed package carries the
      vendor's plugin byte for byte, so this ordering does not change what our packages
      run. It does mean that "the unit checks a package before running anything from it"
      would be false.

1. **Map-country plugins skip the contract.** *(read)*
   - If the loaded plugin's `upgplugin_GetUpgradeType` returns `0x10001`
     (`UPG_PLUGIN_TYPE_MODULE_COUNTRY`) or `0x20001` (`..._LIST_COUNTRY`),
     `LoadUpgradePlugin` posts private message 9 and never spawns `tCheckTrustedSource`.
   - Message 9 is `MSG_BCM_UPGRADE_KNOWN_KEY_INSERTED`, the same message a passing contract
     check posts. `HandlePrivateMessage` handles it by moving the CDD state to 2
     ("identified") and raising `EVT_UPG_DEVICE_IDENTIFIED` *(read; the per-case reading of
     `HandlePrivateMessage` was a skim)*.
   - The type comes from the plugin on the stick. The stock application package's plugin is
     not a country type (inferred: its packages carry a contract and have been seen checked).
2. **The abort flag rejects the media.** *(read)* `m_abort_contract_checking` (`this+0x1d3`)
   works like this:
   - `CheckTrustedSource` clears it when it starts.
   - If it is set during the check, every path leads to `MSG_BCM_UPGRADE_ILLEGAL_MEDIA`.
   - It is set, unconditionally, when the stick is pulled (`MSG_BCM_UPGRADE_USB_DEVICE_REMOVED`).
   - It is also set on `MSG_BCM_UPGRADE_BACKUP_STATE` when context key `0x6721` reads 2.

   Pulling the stick mid-check therefore gives a refusal, not a pass.
3. **A package is examined again at every boot while the stick is in.** *(read)*
   - `C_BCM_UPGRADE::StartUp` ends with `CheckDeviceToMount`, which probes `/bd0` to `/bd5`.
   - On the first device present it runs `HandleMountEvent`. If
     `/SMEG_PLUS_UPG/UpgPlugin.out` exists there, the whole flow starts again.
   - That explains the re-offer [Recovery](RECOVERY.md) records as observed. Take the stick
     out once the update has finished.
4. **The first boot after an update can rewrite the skin keys.** *(read)*
   - `StartUp` calls `AreHarmoniesUpdatedAfterUpgrade`. It compares a value in
     `/SYSTEM_TMP_DATA/HarmoniesChecked.tst` with the user-profile key
     `upgrade/HarmoniesChecked`.
   - If they differ, or the file is missing, `VerifyAndUpdateHarmoniesSetting` rebuilds the
     skin entries in the user profile's common keys (`supervisor/harmony<n>`,
     `harm<n>_number`) and increments the counter. `End()` writes the `.tst` file.
   - So `USER_DATA` is touched on that boot. Whether a normal re-flash triggers it, and what
     the user would see, is *inferred*, not observed.
5. **This image makes no firmware version comparison.** *(read; the negative result comes
   from a string search)*
   - `CheckVersions`, `CheckCtrlFilesBeforeLaunchingUpgrade`, `CheckEntryFile`, the
     `media.inf` version gate and the NAND writes are all strings of `upgrade.out` or the
     plugin. None of them occurs in this image.
   - The application's compatibility and media checks are calls into the plugin:
     `upgplugin_LaunchCheckCompatibility` and `upgplugin_LaunchCheckMedia`.

## The flow, end to end

```
mount event, or the boot probe of /bd0../bd5
  HandleMountEvent -> MSG 0x24 UPG_KEY_INSERTED (HMI: EVT_UPG_KEY_INSERTED)
  UpgPlugin.out present? -> this+0x7c = mount path; MSG 3 USB_DEVICE_PRESENT
MSG 3 -> CDD state 1; EVT_UPG_DEVICE_DETECTED (HMI popup 0x232c "checking")
  LoadUpgradePlugin
    BT communication in progress?     -> MSG 0x2d, stop
    CheckCRCFile(UpgPlugin.out) fails -> MSG 5  PLUGIN_BAD_CRC          (HMI 0x70c)
    MMdlopen fails                    -> MSG 6  PLUGIN_LOADING_FAIL     (HMI 0x70d)
    upgplugin_GetInstance == 0        -> MSG 7  BAD_INTERFACE           (HMI 0x70e)
    interface != 6 or plugin < 100    -> MSG 8  BAD_INTERFACE_VERSION   (HMI 0x70f)
    type 0x10001 / 0x20001            -> MSG 9  KNOWN_KEY_INSERTED, no contract check
    otherwise taskSpawn tCheckTrustedSource (priority 100, 32 KB stack)
      pass -> MSG 9    KNOWN_KEY_INSERTED
      fail -> MSG 0x2c ILLEGAL_MEDIA -> EVT_UPG_ILLEGAL_MEDIA (HMI 0x72a -> popup 0x232f)
MSG 9 -> CDD state 2; EVT_UPG_DEVICE_IDENTIFIED
HMI asks CheckCompatibility -> MSG 10 -> plugin LaunchCheckCompatibility
  -> 0xb OK | 0xc too old | 0xd not authorised | 0xe not enough space | 0xf KO
HMI (application type 0x10003): popup 0x232b with two strings from the plugin
  (inferred: current and new version) - the user's confirmation
HMI StartUpgrade -> CheckMedia -> MSG 0x10 -> plugin LaunchCheckMedia
  -> 0x11 OK | 0x12 data missing | 0x13 corrupted | 0x14 KO
HMI ValidityMatchingSignalTreatment: popup 0x232c, then launches at once
  -> MSG 0x18 LAUNCH_UPGRADE (refused while BT communication is in progress)
  -> CDD state 5 -> plugin LaunchUpgrade          <-- the trail leaves the image here
plugin reports PluginSetResultOfUpgrade: 1 OK (0x1c) | 2 by user (0x1e)
  | 3 by extraction (0x1d) | 4 KO (0x1f)
plugin asks for a reboot: PluginWantToRebootSystem -> MSG 0x29
  -> EVT_UPG_UPDATE_REBOOT_REQUEST (popup 0x232c)
```

Every step above is *read*, apart from the meaning of the `0x232b` strings, which is
inferred. Everything after `LaunchUpgrade` is outside this image: the reboots, the NAND
writes, the `*_ctrl.bin` checks and the `media.inf` version gate.

**CDD state** (`SetCDDState` writes context key `0x4651`, *read*; the names are *inferred*
from the messages that set each value):

| value | state | value | state |
|---|---|---|---|
| 0 | idle | 5 | upgrading or removing |
| 1 | device present | 6 | OK |
| 2 | identified | 7 | KO |
| 3 | checking | 8 | aborted |
| 4 | check OK | | |

## The contract check

`CheckTrustedSource` is at `0x018778b4` in NAV. [Media protection](MEDIA_PROTECTION.md)
quotes `0x0187775c`, which is most likely the AUDIO_BT address *(inferred)*. The check
runs as follows *(read)*:

1. **Open the contract.** It opens `<mount>/SMEG_PLUS_UPG/contract.dat`. If that fails, the
   result is `ILLEGAL_MEDIA`.
2. **Decrypt the header.** It reads 256 bytes and calls `RsaHeaderDecrypt`. The key is built
   from decimal literals inside the function, not reproduced here.
   `C_ENG_CRYPTO::RsaDecrypt` (`0x0126be34`) calls `RSA_private_decrypt` with padding 4
   (**OAEP**) and requires a 256-byte key. It returns only 0 or −1, so no third outcome
   skips the checks. 152 bytes go to `this+0x22c`.
3. **Read the record count** from the header's **u32 at offset 44** (`this+0x258`). The stock
   header holds **115**, the number of records *(executed: decrypted)*. The application reads
   no other header field; the date, the version string and the magic are never compared.
4. **Read the records.** It reads `count` 256-byte blocks and decrypts each one; a decrypt
   failure means `ILLEGAL_MEDIA`.
5. **Check each record.** `RsaCheckDataBlock` (`0x0186d9fc`) reads **`CheckType` as a u32 at
   `+0x3c`** (bytes 60–63) and checks the file at `<mount>` + the path at `+0`:

    | type | check |
    |---|---|
    | 1 | `open` + `fstat`; the size must equal the u32 at `+0x48` |
    | 2 | the BSP's `FileCRC(path)` must equal `+0x48`; on a mismatch it waits 100 ticks, then fails |
    | 3 | read `+0x40` bytes at offset `+0x44`; they must `memcmp` equal to the bytes at `+0x48` |
    | anything else | fails |

    The first failure gives `ILLEGAL_MEDIA`. If every record passes, the result is
    `KNOWN_KEY_INSERTED`.
6. **Edge cases** *(read)*. Neither affects a contract `patch_contract.py` writes:
   - A header whose count is 0 passes straight to `KNOWN_KEY_INSERTED`.
   - A short `fread` is not checked, so a truncated contract would decrypt the previous block
     again. Whether that passes is not tested.

**What the stock contract covers** *(executed: decrypted and compared with the package)*:

- **Records and paths.** There are 115 records over 102 distinct paths, and the package holds
  137 files.
- **Manifests.** Every one has a CRC record: `ctrl.bin`, every `*_ctrl.bin`, every
  `smeg.inf`, `media.inf`, and every `.inf` beside an image.
- **Large binaries** get only a **size record** and a **140-byte spot check at a fixed
  offset**. These are `f_BigQuick.bin`, `system.bin`, `vxWorks.bin`, `upgrade*.out`,
  `sd_dir*.bin`, `db_dwnl_gl.out` and `BIG_HARMONY.bin`. Their content is bound through
  the CRCs in their `.inf` files, which the contract does CRC-check. The check of an image
  against its own `.inf` happens in `upgrade.out`, not in this image *(inferred from the
  checksum cascade in [Boot & update chain](FLASH_CHAIN.md))*.
- **41 files have no record.** They are:
  - all of `USERGUIDE/`;
  - `SD_DIR_TTS*`;
  - `flasher.inf` and `flasher.crc`;
  - the BSP, USERGUIDE and HARMONY `_ctrl.bin` files, as spelt on disk;
  - `contract.dat` itself.
- **Case mismatches.** Six record paths differ in case from the files on disk, for example
  `bsp_smeg_plus_256_ctrl.bin`. They pass on the car, which fits a case-insensitive FAT
  *(inferred)*.

## Messages and what the user sees

The HMI event ids come from the `EVT_UPG_*` forwarders' `li r4` *(read)*. The popup and
text ids come from `C_HMI_UPGRADE_APP_BASE::HandleDBUSMessage` (`0x0295b140`). They were
extracted from the decompile automatically, so treat the per-branch pairing as *read,
approximate*.

| HMI event | id | popup |
|---|---|---|
| `DEVICE_DETECTED` | `0x709` | `0x232c` |
| `PLUGIN_CRC_MISMATCHING` | `0x70c` | `0x2336` |
| `PLUGIN_LOAD_FAILED` | `0x70d` | `0x2336` |
| `PLUGIN_INTERFACE_(VERSION_)MISMATCHING` | `0x70e` / `0x70f` | `0x2336` |
| `COMPATIBILITY_MISMATCHING` / `NOT_AUTHORISED` | `0x713` / `0x71c` | `0x2336` |
| `COMPATIBILITY_TOO_OLD` | `0x71b` | `0x232a` |
| `COMPATIBILITY_NOT_ENOUGH_SPACE` | `0x71d` | `0x2336` |
| `VALIDITY_MISMATCHING` | `0x715` | `0x2336` |
| `VALIDITY_DATA_MISSING` | `0x71e` | `0x2336` |
| `VALIDITY_DATA_CORRUPTED` | `0x71f` | `0x2336` |
| `UPDATE_REBOOT_REQUEST` | `0x719` | `0x232c` |
| `UPDATE_OK` | `0x722` | `0x2339` / `0x233b` |
| `UPDATE_KO` | `0x725` | `0x2335`, `0x233b` |
| `UPDATE_ABORTED_BY_EXTRACTION` | `0x723` | `0x2336` |
| `CHECK_IN_PROGRESS` | `0x728` | `0x232c` |
| **`ILLEGAL_MEDIA`** | **`0x72a`** | **`0x232f`** |

**How popup `0x232f` becomes string 2099 is not in this image** *(not known)*.
- No immediate in the range 2000–2300 sets the text of an upgrade popup, and
  `C_HMI_UPGRADE_APP_BASE::SetPopupTextId` is an empty stub (`blr`) *(read)*.
- The binding presumably lives in the media partition's resources *(inferred)*.

## `C_BCM_UPGRADE` fields

| offset | meaning | tier |
|---|---|---|
| `+0x7c` | mount path of the device carrying `SMEG_PLUS_UPG` | read |
| `+0x84` | `MMdlopen` handle of `UpgPlugin.out` | read |
| `+0x88` | the plugin instance (`upgplugin_GetInstance`) | read |
| `+0x90` | DBUS server `com.MM.Upgrade` | read |
| `+0xa0`–`+0x104` | the 25 resolved `upgplugin_*` entry points | read |
| `+0x1d3` | `m_abort_contract_checking` | read |
| `+0x1dc` | erase task id (`tEraseNavData`, `tEraseAllPoiUser`, `tErasePoi`) | read |
| `+0x210` | `<mount>/SMEG_PLUS_UPG` | read |
| `+0x22c` | decrypted contract header (`0x98` bytes); the record count is at `+0x258` | read, executed |
| `+0x2c4` | the last decrypted contract record (`0xd4` bytes) | read |
| `+0x398`–`+0x39b` | key state: 1 on key inserted, 2 on device present, 0 on removal | read |

## Functions read

| address | function | what it does |
|---|---|---|
| `0x0187699c` | `LoadUpgradePlugin` | CRC-checks and loads `UpgPlugin.out`, resolves its symbols, runs the version gates and the country bypass, then spawns the contract task |
| `0x018778b4` | `CheckTrustedSource` | the contract check above |
| `0x0186bdd8` | `RsaHeaderDecrypt` | builds the key and decrypts block 0 into `+0x22c` |
| `0x0186e068` | `RsaReadDataBlockDecrypt` | decrypts one record into `+0x2c4` |
| `0x0186d9fc` | `RsaCheckDataBlock` | the type 1/2/3 check against the file on the stick |
| `0x0186bb58` | `VerifyCRC32ofFile` | `FileCRC(mount + path)` against the expected value |
| `0x0126be34` | `C_ENG_CRYPTO::RsaDecrypt` | `RSA_private_decrypt` with OAEP, 256-byte key; returns 0 or −1 |
| `0x01886b14` | `HandlePrivateMessage` | the switch over messages `0x00`–`0x36` (skimmed per case) |
| `0x0188676c` | `HandleMountEvent` | key inserted; if the plugin exists, records the mount path and posts device present |
| `0x01886430` | `CheckIfUpgradeInserted` | tries to open `<mount>/SMEG_PLUS_UPG/UpgPlugin.out` |
| `0x0186c688` | `CheckDeviceToMount` | probes `/bd0`–`/bd5` at start-up |
| `0x01884328` | `StartUp` | skin check, list refresh, deletion resume, device probe |
| `0x0186f164` | `AreHarmoniesUpdatedAfterUpgrade` | compares `HarmoniesChecked.tst` with the user-profile key |
| `0x01874510` | `VerifyAndUpdateHarmoniesSetting` | rebuilds the skin keys and increments the counter |
| `0x018727a4` | `SetCDDState` | writes context key `0x4651` |
| `0x0187a9dc` | `PluginSetResultOfUpgrade` | maps the plugin's result 1–4 to messages `0x1c`/`0x1e`/`0x1d`/`0x1f` |
| `0x018780b8` | `PluginWantToRebootSystem` | posts message `0x29` |
| `0x0295b140` | `C_HMI_UPGRADE_APP_BASE::HandleDBUSMessage` | HMI event to popup (read, approximate) |
| `0x02959118` | `CompatibilityMatchingSignalTreatment` | application type: confirmation popup `0x232b`; country type: straight to the media check |
| `0x02958588` | `ValidityMatchingSignalTreatment` | application type: popup `0x232c`, then launches with no further prompt |
| `0x02959a88` | `DeviceRemovedSignalTreatment` | cancels in CDD states 1–3 and closes the popups |
| `0x0293f664` | `SetPopupTextId` | empty stub |

**The rest, by purpose** (*inferred* from names and strings; not read):

- **`C_BCM_UPGRADE` (about 135 functions):** map, POI, risky-zone and skin lists and their
  deletion; DRM and map activation codes; free-space monitoring; the `Plugin_instance_*`
  trampolines; test hooks.
- **HMI (about 480 functions):** menus, popups and progress screens.
- **Generated code (about 165 functions):** DBUS client and server stubs.
