# RIVER 3 Plus extended BMS protocol

The USB HID/CDC interface does not currently expose battery cycle count or a
numeric state of health. EcoFlow's V3 protobuf protocol, observed over BLE and
MQTT, does.

## Relevant messages

| cmd_set | cmd_id | protobuf message | direction |
|---:|---:|---|---|
| `0x20` | `0x32` | `BMSHeartBeatReport` | device upload |
| `0x32` | `0x62` | `AppRuquestBpEuLawData` | client request |
| `0x32` | `0x02` | `AppRuquestBpEuLawDataAck` | device response |

`BMSHeartBeatReport.num` identifies the pack: `0` is the built-in R631 pack;
`1` is an attached extra battery. Its useful fields include cycle count, SOH,
design/remaining/full capacity, accumulated charge/discharge capacity and
energy, per-cell voltage and temperature, balancing state, alarms, protection
flags, pack serial, water ingress flag, and separate real/calendar/cycle SOH.

The explicit EU battery-data response adds deep-discharge count, hot/cold use
and charge time, commissioning date, battery-pack cycles, power capability,
round-trip efficiency, self-discharge rate, and internal resistance.

`r3pcomms.bms` decodes both response payloads without requiring generated
protobuf modules. It also builds the non-mutating request payload; transport
framing and live BLE acquisition remain separate work. No request that changes
the launch date or resets battery data is generated.

## Provenance

The message schema and command mapping were independently cross-checked against
the Apache-2.0 `ha-ef-ble` project and MIT-licensed `ioBroker.ecoflow-mqtt`
project. A River 3 Plus fixture in the latter confirms two pack indices and the
field population for the R631 family.
