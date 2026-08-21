"""Zero-dependency decoders for EcoFlow RIVER 3 Plus BMS protobuf payloads.

These payloads are carried by EcoFlow's V3 protocol over BLE/MQTT.  Keeping
the protobuf wire decoder here dependency-free also makes it useful for
offline captures while the transport is still being researched.
"""

from __future__ import annotations

import struct


BMS_HEARTBEAT_FIELDS = {
    1: "num", 2: "type", 3: "cell_id", 4: "err_code", 5: "sys_ver",
    6: "soc", 7: "vol", 8: "amp", 9: "temp", 10: "open_bms_flag",
    11: "design_cap", 12: "remain_cap", 13: "full_cap", 14: "cycles",
    15: "soh", 16: "max_cell_vol", 17: "min_cell_vol",
    18: "max_cell_temp", 19: "min_cell_temp", 20: "max_mos_temp",
    21: "min_mos_temp", 22: "bms_fault", 23: "bq_sys_stat_reg",
    24: "tag_chg_amp", 25: "show_soc", 26: "input_watts",
    27: "output_watts", 28: "remain_time", 29: "mos_state",
    30: "balance_state", 31: "max_vol_diff", 32: "cell_series_num",
    33: "cell_vol", 34: "cell_ntc_num", 35: "cell_temp", 36: "hw_ver",
    37: "bms_heartbeat_ver", 38: "ecloud_ocv", 39: "bms_sn",
    40: "product_type", 41: "product_detail", 42: "act_soc",
    43: "diff_soc", 44: "target_soc", 45: "sys_loader_ver",
    46: "sys_state", 47: "chg_dsg_state", 48: "all_err_code",
    49: "all_bms_fault", 50: "accu_chg_cap", 51: "accu_dsg_cap",
    52: "real_soh", 53: "calendar_soh", 54: "cycle_soh",
    55: "mos_ntc_num", 56: "mos_temp", 57: "env_ntc_num",
    58: "env_temp", 59: "heatfilm_ntc_num", 60: "heatfilm_temp",
    61: "cur_sensor_ntc_num", 62: "cur_sensor_temp",
    63: "max_env_temp", 64: "min_env_temp", 65: "max_heatfilm_temp",
    66: "min_heatfilm_temp", 67: "max_cur_sensor_temp",
    68: "min_cur_sensor_temp", 69: "balance_cmd",
    70: "remain_balance_time", 71: "afe_sys_status",
    72: "mcu_pin_in_status", 73: "mcu_pin_out_status",
    74: "bms_alarm_state1", 75: "bms_alarm_state2",
    76: "bms_protect_state1", 77: "bms_protect_state2",
    78: "bms_fault_state", 79: "accu_chg_energy", 80: "accu_dsg_energy",
    81: "pack_sn", 82: "water_in_flag",
}

EU_BATTERY_ACK_FIELDS = {
    1: "bms_sn", 2: "soh", 3: "accu_chg_cap", 4: "accu_dsg_cap",
    5: "accu_chg_energy", 6: "accu_dsg_energy", 7: "deep_dsg_cnt",
    8: "high_temp_use_time", 9: "low_temp_use_time",
    10: "high_temp_chg_time", 11: "low_temp_chg_time",
    12: "bp_launch_date", 13: "bp_cycles", 14: "bp_power_capability",
    15: "bp_round_trip_eff", 16: "bp_self_dsg_rate", 17: "bp_ohm_res",
    18: "bp_reset_flag", 19: "bp_launch_date_flag", 20: "num",
}

_SIGNED = {8, 9, 18, 19, 20, 21, 35, 56, 58, 60, 62, 63, 64, 65, 66, 67, 68}
_FLOATS = {25, 42, 43, 44, 52, 53, 54}
_STRINGS = {36, 39, 81}
_REPEATED = {33, 35, 56, 58, 60, 62, 70}
_EU_FLOATS = {14, 15, 16, 17}
_EU_STRINGS = {1}


def _varint(data: bytes, offset: int) -> tuple[int, int]:
    value = 0
    for shift in range(0, 70, 7):
        if offset >= len(data):
            raise ValueError("truncated protobuf varint")
        byte = data[offset]
        offset += 1
        value |= (byte & 0x7f) << shift
        if not byte & 0x80:
            return value, offset
    raise ValueError("protobuf varint is too long")


def _zigzag_32(value: int) -> int:
    value &= 0xffffffff
    return value - 0x100000000 if value & 0x80000000 else value


def _decode(data: bytes, names: dict[int, str], floats: set[int], strings: set[int],
            signed: set[int] = set(), repeated: set[int] = set()) -> dict:
    result: dict = {}
    offset = 0
    while offset < len(data):
        key, offset = _varint(data, offset)
        field, wire = key >> 3, key & 7
        name = names.get(field, f"field_{field}")
        if wire == 0:
            value, offset = _varint(data, offset)
            if field in signed:
                value = _zigzag_32(value)
        elif wire == 5:
            if offset + 4 > len(data):
                raise ValueError("truncated protobuf fixed32")
            raw = data[offset:offset + 4]
            offset += 4
            value = struct.unpack("<f", raw)[0] if field in floats else struct.unpack("<I", raw)[0]
        elif wire == 2:
            size, offset = _varint(data, offset)
            if offset + size > len(data):
                raise ValueError("truncated protobuf length-delimited field")
            raw = data[offset:offset + size]
            offset += size
            if field in strings:
                value = raw.decode("utf-8", errors="replace")
            elif field in repeated:
                value = []
                packed_offset = 0
                while packed_offset < len(raw):
                    item, packed_offset = _varint(raw, packed_offset)
                    value.append(_zigzag_32(item) if field in signed else item)
            else:
                value = raw.hex()
        elif wire == 1:
            if offset + 8 > len(data):
                raise ValueError("truncated protobuf fixed64")
            value = struct.unpack_from("<Q", data, offset)[0]
            offset += 8
        else:
            raise ValueError(f"unsupported protobuf wire type {wire}")

        if name in result:
            current = result[name]
            result[name] = current + [value] if isinstance(current, list) else [current, value]
        else:
            result[name] = value
    return result


def decode_bms_heartbeat(payload: bytes) -> dict:
    """Decode cmd_set=0x20, cmd_id=0x32 (main pack has num=0)."""
    return _decode(payload, BMS_HEARTBEAT_FIELDS, _FLOATS, _STRINGS, _SIGNED, _REPEATED)


def decode_eu_battery_ack(payload: bytes) -> dict:
    """Decode cmd_set=0x32, cmd_id=0x02 EU battery-data response."""
    return _decode(payload, EU_BATTERY_ACK_FIELDS, _EU_FLOATS, _EU_STRINGS)


def request_eu_battery_data(pack_sn: str = "", upload: bool = True) -> bytes:
    """Build AppRuquestBpEuLawData payload for cmd_set=0x32, cmd_id=0x62.

    Empty/default-valued fields are deliberately omitted.  ``upload=True``
    requests BMS data upload without setting dates or reset flags.
    """
    out = bytearray()
    if pack_sn:
        encoded = pack_sn.encode()
        out += bytes((0x0a, len(encoded))) + encoded
    if upload:
        out += b"\x28\x01"
    return bytes(out)
