# EcoFlow Power Manager interoperability notes

These notes document the observable interface of the official EcoFlow Power
Manager 1.0.0.14 Windows package. They are recorded for clean-room
interoperability work; no vendor source code is included.

## Architecture

The desktop client combines three data paths:

1. USB HID through Network UPS Tools (NUT).
2. EcoFlow's CDC/ACM serial interface for per-port telemetry.
3. A localhost JSON-RPC WebSocket used by the UI at
   `ws://127.0.0.1:57890`.

The official package list is returned by:

`GET https://ecomatrix-cn.ecoflow.com/powerManager/package/getOsVersion`

## Read-only JSON-RPC methods

- `connectModeParam.getSettings`
- `homePage.getLastTimeRec`
- `batterySetting.getSettingParam`
- `homePage.getLast100TurnOffChargeTime`
- `homePage.getLastSelfTestTime`
- `global.hasDeviceDetailPage`
- `global.getSystemInfoAndVersion`
- `homePage.getModeAndFirmwareVersion`
- `batterySetting.getBatteryChargeLow`
- `global.getDeviceSn`
- `global.getLowPowerShutdown`
- `global.getLowPowerTip`
- `global.getVersion`

## Notification streams

- `homePage.notifyCompositeDeviceInfo`
  - `battery.temperature`
  - `input.realpower`
  - `output.realpower`
- `homePage.notifyUPSDeviceInfo`
  - `battery.charge`
  - `ups.devName`
  - `ups.realpower.nominal`
  - `ups.status`
  - `ups.chargeStatus`
- `homePage.notifyBatteryTime`
- `homePage.notifyLastTurnOffChargeTime`
- `deviceDetail.notifyInfo`
  - per-port `input` and `output` objects
- `global.notifyBatteryChargeLow`
- `global.notifyDevConnectStatus`

Notifications are enabled and disabled by page name with
`global.enableNotify` and `global.disableNotify`.

## Mutating or host-control methods

These are intentionally not called by the research tooling:

- `batterySetting.setSettingParam`
- `connectModeParam.setSettings`
- `connectModeParam.setEnableConnectStatus`
- `setEnableConnect.status`
- `homePage.selfTest`
- `global.shutdown`
- `global.softwareUpdate`
- `global.usbDriverInstall`

Power Manager's battery settings control host-side low-battery warnings and
shutdown behavior. They are not evidence of an undocumented BMS write command.

## Current conclusion

The official client exposes more *host API endpoints*, but the data shown by
its UI is sourced from the same HID and CDC/ACM paths implemented here. The
client does not expose cycle count or state-of-health in its documented UI
payloads. Further BMS discovery therefore requires identifying additional safe
CDC/ACM query frames or studying the BLE/MQTT protobuf protocol separately.
