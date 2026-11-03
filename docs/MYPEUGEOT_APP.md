# The MyPeugeot companion app (static inventory)

What the phone-side **MyPeugeot** app (APKPure XAPK, version **1.55.1**) contains at the
archive level, and which SMEG+ research tracks it could inform once decompiled. No
behaviour is claimed here: every entry below is either *read* from archive metadata or an
*inference* from entry names, and the page says which.

## The package

| fact | value | tier |
|---|---|---|
| package | `com.psa.mym.mypeugeot` | read — XAPK `manifest.json` |
| version | `1.55.1` (versionCode `2656`) | read — XAPK `manifest.json` |
| SDK range | min `28`, target `35` | read — XAPK `manifest.json` |
| distribution | APKPure XAPK v2, 94,538,026 bytes | read — local file metadata |
| splits | `config.arm64_v8a`, `config.mdpi` | read — XAPK `manifest.json` |

XAPK members (all sizes read from the local file's zip central directory):

| member | bytes |
|---|---|
| `com.psa.mym.mypeugeot.apk` (base) | 87,680,440 |
| `config.arm64_v8a.apk` | 5,014,104 |
| `config.mdpi.apk` | 1,805,569 |
| `icon.png` | 31,420 |
| `manifest.json` | 5,849 |

The base APK holds 4,599 entries: 19 DEX files (`classes.dex` plus `classes2`–`classes19`,
largest `classes7.dex` at ~11.7 MB), 3,590 `res/` entries, 696 `com/` entries and 42
`assets/` entries. There is no `lib/` in the base APK; the native libraries ship in the
`arm64_v8a` split (`libbarhopper_v3.so`, `libimage_processing_util_jni.so`,
`libsurface_util_jni.so` — barcode-scanner dependencies, not car code). Signing follows
the v2/v3 scheme (no `META-INF/*.RSA` files; `stamp-cert-sha256` present, binary, not
reproduced here).

Phone-side permissions relevant to the car (read from `manifest.json`, not observed in
use): `BLUETOOTH`, `BLUETOOTH_ADMIN`, `BLUETOOTH_CONNECT`, `BLUETOOTH_SCAN`,
`BLUETOOTH_ADVERTISE`, coarse and fine location, `NFC`, `CAMERA`, plus the app-defined
`com.psa.mym.mypeugeot.permission.IMPORT_TRIPS` and `EXPORT_TRIPS`. There is no USB
accessory permission in the manifest list.

## Entry-name triage (inference only)

Counts of base-APK entry names matching substrings. These locate where to look with a
decompiler; they do **not** establish behaviour:

| area | matches | SMEG+ track it could inform |
|---|---|---|
| `ble` | 1,724 | Bluetooth LE / connected services |
| `trip` | 91 | trip import/export permissions above |
| `map` | 47 | [Cartography](CARTOGRAPHY.md) |
| `poi` | 46 | user-POI import (record layout unknown) |
| `navig` | 36 | navigation / routing to the head unit |
| `bluetooth` | 28 | pairing, phone-side call audio |
| `vehicle` | 26 | VIN / vehicle state |
| `pan` / `tether` | 21 / 0 | Bluetooth PAN tethering + onboard browser |
| `mqtt` | 19 | connected-services transport |
| `vin` | 12 | vehicle identity |
| `usb` / `accessory` | 0 / 4 | no USB-accessory manifest permission; 4 accessory-named entries to inspect |

Notable `assets/` entries (names read, contents not inspected): per-brand `env*/apps.json`
and `configuration.json` files (`envAmi20`, `envKx`, `envLinkAndDrive`, `envRockse`,
`envSmartCar`, `envTopolino`), `mediaSource*.json`, `stations.json`, `program_names.json`
and `localizable.json` (~7.1 MB). Whether any of these mirror head-unit concepts (media
sources, station lists) is *not known* until the code that reads them is decompiled.

## What this does not say

- No API endpoint, hostname, credential, token, certificate or key material is claimed
  or reproduced here.
- The phone app talks to Stellantis servers and to the car over Bluetooth; nothing here
  says which of the below code paths touch the SMEG+ generation specifically (2012–2017
  Magneti Marelli units) as opposed to newer head units. The app targets current
  vehicles — treat every lead below as a phone-side pattern to check against SMEG+,
  not as a SMEG+ behaviour.

## Decompiled with JADX (*read* tier)

Engine: `jadx-headless-mcp` 0.7.1 (audited artifact SHA-256
`6e5eacf500b64292bfb73c49797c1958f6ee44646e43e868039ae7feb573ff75`,
source revision `5844800a`), run on Temurin JDK 21.0.13 (`jdk.compiler` present),
via `inspect_android_package` → `search_android_classes` → `inspect_android_class` →
`inspect_android_method` → `trace_android_references`. Package identity confirmed from
the decoded manifest: `com.psa.mym.mypeugeot`, 1.55.1 (2656), minSdk 28, targetSdk 35;
33,119 classes, 4,599 resources, manifest coverage `complete`. The APK was never
launched; per the engine's own limits, display names may be aliases, overload indices
are engine-local, and incoming-reference totals cover JADX using-nodes only (not every
possible dynamic or reflective call site). Nothing below establishes runtime behaviour.

### Send-to-navigation is a VIN-keyed server round-trip

The destination flow is a clean-architecture stack, all *read* from decompiled bodies:

- `com.psa.mym.activity.send2nav.SendToNavActivity` / `SendToNavFragment` (UI) →
  `com.base.view.viewmodel.SendToNavFragmentViewModel` →
  `com.base.domain.usecases.sendtonav.SaveSendToNavDestinationUseCase.invoke(lat: double,
  lon: double, label: String)` → `SendToNavRepositoryImpl` →
  `DBSendToNavDataSourceImpl` → Room `SendToNavDestinationDAO` (local persistence).
- Retrieval is VIN-keyed and remote:
  `com.inetpsa.pims.sendtonav.interactors.GetDestinationByVinStoredInteractor.execute(vin)`
  calls `repository.retrieveDestinationLoginVin(vin)` and resumes with
  `StoredDestinationLoginVin.Success(NavigationLocation)` or `Failed(error)`.
- `trace_android_references` on `SaveSendToNavDestinationUseCase` (class-level, 8 using
  nodes) confirms the callers: `SendToNavFragmentViewModel` (+ inner class), the
  `SendToNavModulesKt` DI module, and — reused — `com.psa.mym.evrouting.domain.usecases.EVSendDestinationUseCase`
  (+ inner, via `EVRoutingModulesKt`).
- Component metadata: `com.inetpsa.pims.sendtonav.SendToNavigationComponent` carries
  `name` / `serviceName` / `version` / `repository` fields — a plugin-style descriptor,
  not the transport.

SMEG+ relevance (*inferred*): destination entry is phone-side plus server-side; there
is no head-unit-push protocol in this chain. Useful only as the shape of the
`NavigationLocation` model if a SMEG+ POI/destination import is ever attempted.

### O2X dongle flow is eligibility-gated per car

- `com.psa.mym.activity.dongle.*`: `DiscoverDongleActivity` →
  `ActivateDongleActivity` → `ConnectionSuccessDongleActivity`, driven by
  `DongleViewModel`, which starts `StartO2xServiceWithTimeOut.invoke(requireVin,
  timeOut): Flow<Result<O2XVehicleInformationMYM>>` and stops via
  `stopO2XServiceUseCase` with `stopO2xAlreadyCalled` / `isStopO2XCalledOnError` guards
  (*read* from decompiled `startO2XServiceWithTimer`, `startService`, `invoke` bodies).
- The gate is server-side, not a local VIN-pattern check (*read*):
  `com.base.domain.usecases.IsVinO2XVehicleUseCase.invoke()` returns
  `mymUserCarBOEligibilityRepository.hasEligibility(selectedCar, "o2x")`.
- Related names seen but not decompiled (*not known* tier, leads only):
  `SetConnectedVinUseCase`, `GetUserDataForVinUseCase`, `MyNavDecryptVinUseCase`,
  `ImportTripCategoriesByVinUseCase`, `com.inetpsa.pims.vehicleinformation.commands.SetVinCommand`.

SMEG+ relevance (*inferred*): the O2X path is the same family as the USB "connected
key" dongle work cited in [Sources & prior art](REFERENCES.md) (`Mwyann/psakey`).
The eligibility flag means a SMEG+-era car will almost certainly report ineligible —
confirming that would need a logged-in account session, which was not attempted.

### Bluetooth phone↔car channel is bidirectional — but not SMEG+

`com.inetpsa.cd2.careasyapps.kernel.transport.bluetooth.BluetoothConnectionManager`
implements `ITransportManager` with both client threads (phone connects out) and
server threads (phone listens), plus `connect`/`disconnect`, `discover`, data /
connect / disconnect / endpoint-found / error callbacks, and `sendData(byte[])` →
`write()` (*read* from the decompiled bodies). The RFCOMM UUID is chosen per brand
(*read* from `getUUIDForBrand`): `CEA_PEUGEOT`, `CEA_CITROEN`, `CEA_DS`, `CEA_OPEL`,
`CEA_VAUXHALL`, `CEA_ABARTH`, `CEA_ALFA_ROMEO`, `CEA_CHRYSLER`, `CEA_DODGE`,
`CEA_FIAT`, `CEA_JEEP`, `CEA_LANCIA`, `CEA_MASERATI`, `CEA_RAM`.

Observed users of the channel (*read* from class/member inventory): navigation status
(`VCSendNavigationStatus`, `CeaNavigation*` callbacks), smart-audio triggers
(`SmartAudioConnectedBluetoothReceiver`), BLE car-key enrolment
(`CarKeyBluetoothTuto*`), dongle discovery over BLE
(`DiscoverDongleActivity.showEligibilityBluetoothLowEnergy`), connection events
(`BluetoothDeviceReceiver`), and `StartAllBluetoothServicesUseCase` /
`StopAllBluetoothServicesUseCase` lifecycle hooks with a dedicated permission helper.
Send-to-nav notably does *not* use it — destinations travel phone → server → car.

SMEG+ relevance (*inferred*): the 2012–2017 unit exposes Bluetooth for handsfree and
A2DP only — no CarEasyApps data endpoint — which is why the piggyback feeds audio via
AUX. This channel targets newer CEA-capable head units. Bluetooth PAN tethering as a
back door stays research, unproven.

### Transport and remaining leads (*inferred* / *not known*)

- MQTT is vendored Paho (`com.inetpsa.mmx.foundation.mqtt.*`, incl. `MqttAndroidClient`,
  `MqttService`) — the app's connected-services transport, but no SMEG+-relevant topic
  was traced. Which topics carry vehicle data is *not known*.
- First-party `Poi`/`Navig` hits are EV-routing and CarEasyApps navigation components
  (`FetchEVChargingPointsAndRouteUseCase`, `CarEasyAppsNavigationComponent`,
  `CeaNavigation*`, `VCSendNavigationStatus`, `NavigationUtils`) — navigation to new
  head units, not SMEG+ map tiles. The user-POI import record layout stays unknown;
  [Cartography](CARTOGRAPHY.md) remains the SMEG+ map reference.
- `Dongle` (10 classes), `Bluetooth` (43), `Mqtt` (71), `Trip` (340), `Vehicle` (306),
  `Map` (628) and `Charg` (153) match counts are class-name search totals over all
  33,119 classes (third-party libraries included) — triage only, not behaviour.
