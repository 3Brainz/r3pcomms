import struct

import pytest

from r3pcomms import R3PComms


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
