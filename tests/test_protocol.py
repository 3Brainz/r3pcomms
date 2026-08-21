import struct
from pathlib import Path

import pytest

from r3pcomms import (
    R3PComms,
    decode_bms_heartbeat,
    decode_eu_battery_ack,
    request_eu_battery_data,
)


def segment(segment_type: int, payload: bytes) -> bytes:
    return struct.pack("<HB", segment_type, len(payload)) + payload


def test_crc16_arc_known_vector():
    assert R3PComms.crc16(b"123456789") == 0xBB3D


def test_unknown_serial_segments_are_lossless_at_any_length():
    device = R3PComms()
    parsed = device.serial_segmenter(
        segment(101, b"\x01")
        + segment(102, b"\x02\x03\x04")
        + segment(103, b"\x05\x06\x07\x08\x09")
    )

    assert parsed["Serial Segment 101"]["value"] == "01"
    assert parsed["Serial Segment 102"]["value"] == "020304"
    assert parsed["Serial Segment 103"]["value"] == "0506070809"
    assert parsed["Serial Segment 103"]["data"] == "0x0506070809"


def test_truncated_serial_segment_is_rejected_cleanly():
    device = R3PComms()
    with pytest.raises(ValueError, match="Truncated serial segment 99"):
        device.serial_segmenter(struct.pack("<HB", 99, 4) + b"\x01\x02")


def test_hid_report_metadata_covers_every_advertised_report():
    assert set(R3PComms.HID_REPORT_IDS) == set(R3PComms.HID_REPORT_SPECS)


def test_anonymized_real_serial_capture():
    fixture = Path(__file__).parent / "fixtures" / "serial_metrics.hex"
    parsed = R3PComms().serial_segmenter(bytes.fromhex(fixture.read_text().strip()))

    assert parsed["Design Charge Capacity"]["value"] == 12800
    assert parsed["Remaining Time Limit"]["value"] == 600
    assert parsed["AC Load Frequency"]["value"] == 50
    assert parsed["Remaining Capacity Limit"]["value"] == 20


def test_bms_heartbeat_health_fields_and_packed_cells():
    # cycles=142, soh=97, cell_vol=[3298, 3301], real_soh=96.5
    payload = bytes.fromhex("708e0178618a0204e219e519a5030000c142")
    parsed = decode_bms_heartbeat(payload)

    assert parsed["cycles"] == 142
    assert parsed["soh"] == 97
    assert parsed["cell_vol"] == [3298, 3301]
    assert parsed["real_soh"] == pytest.approx(96.5)


def test_eu_battery_ack_and_safe_request():
    # soh=98, deep_dsg_cnt=3, bp_cycles=27, round-trip efficiency=91.25
    payload = bytes.fromhex("10623803681b7d0080b642")
    parsed = decode_eu_battery_ack(payload)

    assert parsed == {
        "soh": 98,
        "deep_dsg_cnt": 3,
        "bp_cycles": 27,
        "bp_round_trip_eff": pytest.approx(91.25),
    }
    assert request_eu_battery_data() == bytes.fromhex("2801")
    assert request_eu_battery_data("PACK") == bytes.fromhex("0a045041434b2801")
