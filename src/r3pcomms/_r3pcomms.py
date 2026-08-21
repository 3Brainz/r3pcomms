#!/usr/bin/env python3

import serial
import hid
import struct
import usb.core
from operator import xor


class R3PComms:
    """
    River 3 Plus comms from scratch via USB CDC (ACM) and HID
    """

    sequence_num: int
    debug_prints: int
    redact_sn: bool
    serial_number: bytes
    held_xdbg: bytes
    held_dbg: bytes
    s: serial.Serial | None
    h: hid.device | None
    u: object | None
    hid_path: str

    # Every feature/input report ID advertised by the RIVER 3 Plus HID
    # descriptor.  Most are not decoded yet, but exposing their bytes is
    # essential for reproducible protocol research.
    HID_REPORT_IDS = (
        1, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20,
        22, 23, 24, 26, 28, 31, 32,
    )
    HID_STATUS_BITS = (
        "charging",
        "discharging",
        "ac_present",
        "battery_present",
        "below_remaining_capacity_limit",
        "remaining_time_limit_expired",
        "need_replacement",
        "voltage_not_regulated",
        "fully_charged",
        "fully_discharged",
        "shutdown_requested",
        "shutdown_imminent",
    )

    # Names and scaling come from the USB-IF Usage Tables for HID Power
    # Devices and the report descriptor shipped by the RIVER 3 Plus.
    HID_REPORT_SPECS = {
        1: ("Configured Active Power", "u16", "W"),
        6: ("Rechargeable", "bool", ""),
        7: ("Present Status", "status", ""),
        8: ("Remaining Time Limit", "u16", "s"),
        9: ("Manufacturer Date", "date", ""),
        10: ("Configured Voltage", "centivolt", "V"),
        11: ("Battery Voltage", "centivolt", "V"),
        12: ("Remaining Capacity", "u8", "%"),
        13: ("Runtime To Empty", "u16", "s"),
        14: ("Full Charge Capacity", "u8", "%"),
        15: ("Warning Capacity Limit", "u8", "%"),
        16: ("Capacity Granularity 1", "u8", "%"),
        17: ("Remaining Capacity Limit", "u8", "%"),
        18: ("Delay Before Shutdown", "s16", "s"),
        19: ("Delay Before Reboot", "s16", "s"),
        20: ("Audible Alarm Control", "u8", ""),
        22: ("Capacity Mode", "u8", ""),
        23: ("Design Capacity", "u8", "%"),
        24: ("Capacity Granularity 2", "u8", "%"),
        26: ("Average Time To Full", "u16", "s"),
        28: ("Average Time To Empty", "u16", "s"),
        31: ("Device Chemistry String Index", "u8", ""),
        32: ("OEM Information String Index", "u8", ""),
    }

    def __init__(
        self,
        comport: str = "",
        hiddev: str = "",
        debug: int = 0,
        usbdev: str = "",
    ) -> None:
        self.sequence_num = 0
        self.debug_prints = debug

        if comport:
            comms_args = {
                "port": None,
                "baudrate": 115200,
                "bytesize": serial.EIGHTBITS,
                "parity": serial.PARITY_NONE,
                "stopbits": serial.STOPBITS_ONE,
            }
            self.s = serial.Serial(**comms_args)
            self.s.port = comport
            self.s.timeout = 1
        else:
            self.s = None

        if hiddev:
            vid, pid = hiddev.split(":")
            vid = int(vid, 16)
            pid = int(pid, 16)
            self.hid_path = self.find_hid_device(pid, vid)
            if self.hid_path:
                self.h = hid.device()
                if self.debug_prints >= 2:
                    print(f"Found HID device: {self.hid_path}")
            else:
                raise ValueError(
                    f"{hex(vid)}:{hex(pid)} not found. Check Vendor ID and Product ID"
                )
        else:
            self.h = None

        if usbdev:
            vid, pid = (int(value, 16) for value in usbdev.split(":"))
            self.u = usb.core.find(idVendor=vid, idProduct=pid)
            if self.u is None:
                raise ValueError(
                    f"Direct USB device {hex(vid)}:{hex(pid)} not found or inaccessible"
                )
        else:
            self.u = None

        self.sequence_num = 0
        self.serial_number = b""
        self.redact_sn = True
        self.held_xdbg = b""
        self.held_dbg = b""

    def __enter__(self):
        if self.s:
            self.sequence_num = 0
            self.s.open()
        if self.h:
            self.h.open_path(self.hid_path)

        return self

    def __exit__(self, type, value, traceback):
        if self.h:
            self.h.close()
        if self.s:
            self.s.close()
            ret = self.s.__exit__(type, value, traceback)
        else:
            ret = None
        return ret

    def find_hid_device(self, pid: str, vid: str) -> str | None:
        ret = None
        devices = hid.enumerate()
        for device in devices:
            if device["vendor_id"] == vid and device["product_id"] == pid:
                if "hidraw" in device["path"].decode("utf-8"):
                    ret = device["path"]
        return ret

    @staticmethod
    def crc16(data: bytes) -> int:
        """
        CRC-16/ARC
        """
        offset = 0
        length = len(data)
        crc = 0x0000
        for i in range(length):
            crc ^= data[offset + i]
            for j in range(8):
                if (crc & 0x1) == 1:
                    crc = int((crc / 2)) ^ 40961
                else:
                    crc = int(crc / 2)
        return crc & 0xFFFF

    def tx(self, msg: str) -> int | None:
        if self.s:
            overhead_len = 14
            start = 0x03AA

            bmsg = bytes.fromhex(msg)
            msg_len = len(bmsg) - overhead_len
            bsequence = struct.pack("<I", self.sequence_num)
            bmsg_seq = bmsg[:2] + bsequence + bmsg[6:]
            headmsg = struct.pack("<HH", start, msg_len) + bmsg_seq
            crc_val = R3PComms.crc16(headmsg)
            out = headmsg + struct.pack("<H", crc_val)
            if self.debug_prints >= 1:
                print(f">s> {out.hex()}")
            ret = self.s.write(out)
            self.sequence_num += 1
        else:
            ret = None
        return ret

    def rx(self) -> bytes | None:
        ret = None
        if self.s:
            header_len = 4
            base_len = 20

            header = self.s.read(header_len)
            preamble, var_len = struct.unpack("<HH", header)
            payload = self.s.read(base_len + var_len - header_len - 2)
            crc = self.s.read(2)
            full_message = header + payload + crc
            if R3PComms.crc16(full_message) == 0:
                if self.debug_prints >= 1:
                    self.debug_print(full_message)
            else:
                # TODO: gracefully handle this
                raise RuntimeError("CRC check fail")
            ret = header + payload
        return ret

    @staticmethod
    def xorit(data: bytes, sequence_num: int | None = None) -> bytes:
        obfuscattion_offset = 18
        if isinstance(sequence_num, int):
            not_obfuscated = bytes([])
            obfuscated = data
        else:
            not_obfuscated = data[:obfuscattion_offset]
            obfuscated = data[obfuscattion_offset:]
            sequence_num = R3PComms.get_sequencenum(not_obfuscated)

        deobfuscated = bytes([xor(x, sequence_num) & 0xFF for x in obfuscated])
        return not_obfuscated + deobfuscated

    @staticmethod
    def get_sequencenum(data: bytes) -> int:
        offset = 6
        return struct.unpack("<I", data[offset : offset + 4])[0]

    def serial_segmenter(self, source: bytes) -> dict:
        offset = 0
        ssize = len(source)
        result = {}
        while offset < ssize:
            if ssize - offset < 3:
                raise ValueError(f"Truncated serial segment header at offset {offset}")
            seg_type, seg_len = struct.unpack_from("<HB", source, offset=offset)
            if offset + 3 + seg_len > ssize:
                raise ValueError(
                    f"Truncated serial segment {seg_type} at offset {offset}: "
                    f"expected {seg_len} payload bytes, got {ssize - offset - 3}"
                )
            seg_data = source[offset + 3 : offset + 3 + seg_len]
            offset += 3 + seg_len
            if seg_type == 3:
                name = "Design Charge Capacity"
                seg_val = struct.unpack("<I", seg_data)[0]
                unit = "mAh"
            elif seg_type == 4:
                name = "Temperatures"
                seg_val = struct.unpack("<BBBB", seg_data)
                # the second one is for the battery
                unit = "degC"
            elif seg_type == 7:
                name = "Total Load"
                seg_val = struct.unpack("f", seg_data)[0]
                unit = "W"
            elif seg_type == 8:
                name = "Total Draw"
                seg_val = struct.unpack("f", seg_data)[0]
                unit = "W"
            elif seg_type == 9:
                name = "AC Draw"
                seg_val = struct.unpack("f", seg_data)[0]
                unit = "W"
            elif seg_type == 12:
                name = "Solar/DC Draw"
                seg_val = struct.unpack("f", seg_data)[0]
                unit = "W"
            elif seg_type == 13:
                name = "Line Frequency?"
                seg_val = struct.unpack("<L", seg_data)[0] / 10
                unit = "Hz"
            elif seg_type == 14:
                name = "AC Load"
                seg_val = struct.unpack("f", seg_data)[0] * -1
                unit = "W"
            elif seg_type == 15:
                name = "AC Load Frequency?"
                seg_val = struct.unpack("<HH", seg_data)
                unit = "Hz"
            elif seg_type == 16:
                name = "DC Load"
                seg_val = struct.unpack("f", seg_data)[0] * -1
                unit = "W"
            elif seg_type == 17:
                name = "USB-A Load"
                seg_val = struct.unpack("f", seg_data)[0] * -1
                unit = "W"
            elif seg_type == 18:
                name = "USB-C Load"
                seg_val = struct.unpack("f", seg_data)[0] * -1
                unit = "W"
            elif seg_type == 22:
                name = "Serial Num"
                seg_val = struct.unpack(f"{seg_len}s", seg_data)[0]
                self.serial_number = seg_val
                if self.debug_print:
                    if self.held_dbg:
                        self.debug_print(self.held_dbg)
                        self.held_dbg = b""
                    if self.held_xdbg:
                        self.debug_print(self.held_xdbg, xord=True)
                        self.held_xdbg = b""
                if self.redact_sn:
                    seg_val = "REDACTED"
                    seg_data = bytes.fromhex("ff") * len(self.serial_number)
                else:
                    seg_val = seg_val.decode()
                unit = ""
            elif seg_type == 23:
                name = "Remaining Charge Time"
                unpacked = struct.unpack("<HH", seg_data)
                if seg_data[:2] == bytes.fromhex("3317"):
                    # 0x3317 means the battery is not charging?
                    seg_val = -1
                else:
                    seg_val = unpacked
                # seg_val = tuple([x / 60 for x in seg_val])
                unit = "min"
                # unit = "Hr"
            elif seg_type == 25:
                name = "Model/Mfg. Batch/Date?"
                seg_val = seg_data.hex()
                unit = "?"
            else:
                name = f"Serial Segment {seg_type}"
                # Unknown fields are deliberately lossless.  The former
                # parser assumed every segment was four bytes and crashed as
                # soon as firmware returned a differently-sized field.
                seg_val = seg_data.hex()
                unit = "raw"
            i = 0
            last_name = name
            while name in result:
                name = f"{last_name}{i}"
                i += 1
            result[name] = {
                "type": f"s{seg_type}",
                "data": "0x" + seg_data.hex(),
                "value": seg_val,
                "unit": unit,
            }
        return result

    def query(self, msg: str) -> bytes:
        self.tx(msg)
        rx = self.rx()
        if rx is None:
            raise ValueError(f"Failure getting response to {msg}")
        return rx

    def read_raw_report(self, report_id, length=16) -> bytes | None:
        if self.h:
            try:
                if self.debug_prints >= 1:
                    dbg_out = (report_id.to_bytes(1), length.to_bytes(1))
                    print(f">h> {dbg_out[0].hex()}{dbg_out[1].hex()}")
                data = self.h.get_feature_report(report_id, length)
                data = bytes(data)
                if self.debug_prints >= 1:
                    print(f"<h< {data.hex()}")
                ret = data
            except Exception as e:
                raise ValueError(f"Failure reading report {report_id}: {e}")
        elif self.u:
            try:
                if self.debug_prints >= 1:
                    print(f">u> {report_id:02x}{length:02x}")
                # USB HID GET_REPORT, feature report, interface 0. This direct
                # control transfer works even when Linux rejects EcoFlow's
                # malformed HID report descriptor and creates no hidraw node.
                data = bytes(
                    self.u.ctrl_transfer(
                        0xA1,
                        0x01,
                        (0x03 << 8) | report_id,
                        0,
                        length,
                        timeout=1000,
                    )
                )
                if not data or data[0] != report_id:
                    data = bytes((report_id,)) + data
                if self.debug_prints >= 1:
                    print(f"<u< {data.hex()}")
                ret = data
            except Exception as e:
                raise ValueError(f"Failure reading direct USB report {report_id}: {e}")
        else:
            ret = None

        return ret

    def get_serial(self) -> dict:
        serial_answer_offset = 19
        answer = self.query("f40d00000000ffff2202010166031600")
        serial_result = self.serial_segmenter(answer[serial_answer_offset:])
        return serial_result

    def ser_get(self) -> dict:
        metrics_answer_offset = 22
        answer = self.query("de2d00000000ffff220201016602")
        xanswer = R3PComms.xorit(answer)
        if self.debug_prints >= 1:
            self.debug_print(xanswer, xord=True)
        metrics_result = self.serial_segmenter(xanswer[metrics_answer_offset:])
        metrics_result["preamble?"] = {
            "type": "pre",
            "data": xanswer[:metrics_answer_offset].hex(),
            "value": 0,
            "unit": "",
        }

        return metrics_result

    def get(self, all_hid: bool = False) -> dict:
        metrics = {}
        if self.s:
            metrics |= self.ser_get()
        if self.h or self.u:
            metrics |= self.hid_get(all_reports=all_hid)
        return metrics

    def hid_get(self, all_reports: bool = False) -> dict:
        result = {}
        to_read = self.HID_REPORT_IDS if all_reports else (12, 17, 13, 11, 18, 19, 1, 7)
        # to_read.append((12, 16))  # Cnst,Var,Abs,Vol
        # to_read.append((17, 16))  # Data,Var,Abs,NoPref,Vol
        # to_read.append((13, 16))  # Cnst,Var,Abs,NoPref,Vol
        # to_read.append((11, 16))  # Cnst,Var,Abs,NoPref
        # to_read.append((18, 16))  # Data,Var,Abs,NoPref,Vol
        # to_read.append((19, 16))  # Data,Var,Abs,NoPref,Vol
        # to_read.append((1,  128))  # Cnst,Var,Abs,Vol
        # to_read.append((7,  1))  #
        for rid in to_read:
            try:
                data = self.read_raw_report(rid)
            except ValueError:
                # Some descriptor entries are constant or unavailable through
                # get_feature_report. Keep probing the remaining reports.
                if all_reports:
                    continue
                raise
            if data:
                payload = data[1:]
                name, kind, unit = self.HID_REPORT_SPECS.get(
                    rid, (f"HID Report {rid}", "raw", "raw")
                )
                if kind == "u8":
                    rpt_val = payload[0]
                elif kind == "bool":
                    rpt_val = bool(payload[0])
                elif kind == "u16":
                    rpt_val = struct.unpack("<H", payload[:2])[0]
                elif kind == "s16":
                    rpt_val = struct.unpack("<h", payload[:2])[0]
                elif kind == "centivolt":
                    rpt_val = struct.unpack("<H", payload[:2])[0] / 100
                elif kind == "status":
                    bits = int.from_bytes(payload, "little")
                    rpt_val = {
                        status: bool(bits & (1 << offset))
                        for offset, status in enumerate(self.HID_STATUS_BITS)
                    }
                elif kind == "date":
                    encoded = struct.unpack("<H", payload[:2])[0]
                    year = 1980 + ((encoded >> 9) & 0x7F)
                    month = (encoded >> 5) & 0x0F
                    day = encoded & 0x1F
                    rpt_val = (
                        f"{year:04d}-{month:02d}-{day:02d}"
                        if encoded and 1 <= month <= 12 and 1 <= day <= 31
                        else None
                    )
                else:
                    rpt_val = payload.hex()
                i = 0
                last_name = name
                while name in result:
                    name = f"{last_name}{i}"
                    i += 1
                result[name] = {
                    "type": f"h{rid}",
                    "data": "0x" + payload.hex(),
                    "value": rpt_val,
                    "unit": unit,
                }

        return result

    def debug_print(self, data: bytes, xord: bool = False) -> None:
        if xord:
            prompt = "<x< "
        else:
            prompt = "<s< "

        if self.redact_sn and serial:
            if self.serial_number:
                if xord:
                    to_redact = self.serial_number
                else:
                    seq = R3PComms.get_sequencenum(data)
                    to_redact = R3PComms.xorit(self.serial_number, seq)
                data = data.replace(to_redact, bytes.fromhex("ff") * len(to_redact))

                print(prompt + data.hex())
            else:
                if xord:
                    self.held_xdbg = data
                else:
                    self.held_dbg = data
        else:
            print(prompt + data.hex())
