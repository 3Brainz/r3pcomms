import sys
import argparse
import time
import json

from collections.abc import Sequence

import r3pcomms

from r3pcomms import R3PComms


def run(com: str, usb: str, usb_direct: str, actions: list[dict], dbg: bool, hide_sn: bool, p, inf, h, all_hid: bool):
    inter_comms_delay_s = p

    with R3PComms(com, usb, dbg, usb_direct) as d:
        d.redact_sn = hide_sn
        do_sleep = False
        t0 = time.time()
        t1 = float("NaN")
        count = 0
        while actions:
            count += 1
            action = actions.pop()
            if do_sleep:
                time.sleep(inter_comms_delay_s)
            else:
                do_sleep = True
            kwargs = dict(action["kwargs"])
            if action["fun"] == "get":
                kwargs["all_hid"] = all_hid
            result = getattr(d, action["fun"])(*action["args"], **kwargs)
            t2 = time.time()
            dt = t2 - t1
            t = t2 - t0
            ver = r3pcomms.__version__
            result = {
                "Version": {"type": "i0", "data": ver, "value": ver, "unit": ""}
            } | result
            result = {
                "Unix Time": {"type": "i1", "data": t2.hex(), "value": t2, "unit": "s"}
            } | result
            result = {
                "Delta Time": {"type": "i2", "data": dt.hex(), "value": dt, "unit": "s"}
            } | result
            result = {
                "Run Time": {"type": "i3", "data": t.hex(), "value": t, "unit": "s"}
            } | result

            if "Present Status" in result:
                ac = result["Present Status"]["value"]["ac_present"]
                result = result | {
                    "AC In Live": {"type": "d0", "data": ac, "value": ac, "unit": ""}
                }

            if not d.debug_prints:
                result = {
                    k: v
                    for (k, v) in result.items()
                    if "unknown" not in k and "?" not in k
                }

            if h:
                if len(actions) != 0 or inf:
                    print(chr(27) + "[2J")
                result = {"Iteration": {"value": count, "unit": ""}} | result
                for key, val in result.items():
                    value = val["value"]
                    if isinstance(value, float):
                        print(f'{key}:\t{abs(value):.1f}{val["unit"]}')
                    else:
                        print(f'{key}:\t{value}{val["unit"]}')
            else:
                print(json.dumps(result), flush=True)
            if inf and action["fun"] == "get":
                actions.append(action)
            t1 = t2


def main_parser() -> argparse.ArgumentParser:
    description = "Local communication with a River 3 Plus over USB HID and/or CDC(ACM)"
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument(
        "--version",
        "-V",
        action="version",
        version=f'r3pcomms {r3pcomms.__version__} ({",".join(r3pcomms.__path__)})',
    )
    parser.add_argument(
        "--debug",
        "-d",
        action="count",
        default=0,
        help="print raw comms messages",
    )
    parser.add_argument(
        "--identify",
        "-i",
        action="store_true",
        help="get unit's serial number (must specify --serial)",
    )
    parser.add_argument(
        "--redact-serial",
        "-r",
        action="store_true",
        help="redact serial number from all prints",
    )
    parser.add_argument(
        "--serial",
        "-s",
        help="poll for data via serial comms using this port; eg. "
        '"COM3" or "/dev/ttyACM0" or '
        '"/dev/serial/by-id/usb-EcoFlow_EF-UPS-RIVER_3_Plus_${SERIALNUMBER}-if01"',
    )
    parser.add_argument(
        "--hid",
        nargs="?",
        const="3746:ffff",
        default="",
        help="poll for data via HID comms. "
        "optinally specify a VENDOR_ID:PRODUCT_ID to use instead of 3746:ffff",
    )
    parser.add_argument(
        "--usb-direct",
        nargs="?",
        const="3746:ffff",
        default="",
        help="read HID feature reports directly with libusb; optionally specify VENDOR_ID:PRODUCT_ID",
    )
    parser.add_argument(
        "--number",
        "-n",
        default=argparse.SUPPRESS,
        type=int,
        help="poll for data this many times (0 means forever)",
    )
    parser.add_argument(
        "--every",
        "-e",
        default=1.0,
        type=float,
        help="data poll period in seconds",
    )
    parser.add_argument(
        "--humanize",
        action="store_true",
        help="output formatted for humans, otherwise json for the robots",
    )
    parser.add_argument(
        "--all-hid",
        action="store_true",
        help="probe every report ID advertised by the device HID descriptor",
    )

    return parser


def main(cli_args: Sequence[str], prog: str | None = None) -> None:
    parser = main_parser()
    if prog:
        parser.prog = prog
    args = parser.parse_args(cli_args)

    if args.identify:
        if not args.serial:
            parser.error("--identify requires --serial.")
        if "number" not in args:
            args.number = -1
    if "number" not in args:
        args.number = 1
    if args.number == 0:
        forever = True
        args.number = 1
    else:
        forever = False

    run_actions = []
    if args.identify:
        run_actions.append(({"fun": "get_serial", "args": (), "kwargs": {}}))
    for i in range(args.number):
        run_actions.append(({"fun": "get", "args": (), "kwargs": {}}))

    run_args = {
        "com": args.serial,
        "usb": args.hid,
        "usb_direct": args.usb_direct,
        "actions": run_actions,
        "dbg": args.debug,
        "hide_sn": args.redact_serial,
        "p": args.every,
        "inf": forever,
        "h": args.humanize,
        "all_hid": args.all_hid,
    }
    run(**run_args)


def entrypoint() -> None:
    main(sys.argv[1:])


if __name__ == "__main__":
    main(sys.argv[1:], "python -m r3pcomms")


__all__ = [
    "main",
    "main_parser",
]
