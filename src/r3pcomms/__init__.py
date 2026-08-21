"""
River 3 Plus comms from scratch via USB CDC (ACM)
"""

from ._r3pcomms import R3PComms
from .bms import decode_bms_heartbeat, decode_eu_battery_ack, request_eu_battery_data
from ._version import version

__version__ = version

__all__ = [
    "R3PComms",
    "__version__",
]


def __dir__() -> list[str]:
    return __all__
