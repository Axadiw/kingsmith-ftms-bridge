"""
FTMS (Fitness Machine Service) GATT server for treadmill data.

Broadcasts treadmill metrics in Bluetooth SIG FTMS format so that
Apple Fitness, Zwift, Peloton, etc. can connect as to a standard treadmill.
"""

import asyncio
import logging
import struct
from typing import Callable

from bluez_peripheral.gatt.service import Service
from bluez_peripheral.gatt.characteristic import characteristic, CharacteristicFlags as CharFlags
from bluez_peripheral.advert import Advertisement
from bluez_peripheral.util import get_message_bus

from .walkingpad import WalkingPadStatus

logger = logging.getLogger(__name__)

# Bluetooth SIG UUIDs (16-bit)
FTMS_SERVICE_UUID = "1826"
TREADMILL_DATA_UUID = "2ACD"
# Optional for full FTMS compatibility
FM_FEATURE_UUID = "2ACC"
FM_CONTROL_POINT_UUID = "2AD9"

# FTMS Treadmill Data flags. Instantaneous Speed is always present (no flag needed).
# Bit 2 = Total Distance Present, Bit 10 = Elapsed Time Present.
FLAGS_SPEED_DISTANCE_TIME = 0x0404


def _build_treadmill_data(status: WalkingPadStatus | None) -> bytes:
    if status is None:
        speed_kmh, distance_m, time_s = 0.0, 0, 0
    else:
        speed_kmh = status.speed_kmh
        distance_m = int(status.distance_km * 1000)
        time_s = status.time_seconds
    speed_uint16 = min(0xFFFE, max(0, int(round(speed_kmh * 100))))
    distance_m = min(0xFFFFFF, max(0, distance_m))
    time_s = min(0xFFFF, max(0, time_s))
    buf = bytearray(9)
    struct.pack_into("<HH", buf, 0, FLAGS_SPEED_DISTANCE_TIME, speed_uint16)
    buf[4] = distance_m & 0xFF
    buf[5] = (distance_m >> 8) & 0xFF
    buf[6] = (distance_m >> 16) & 0xFF
    struct.pack_into("<H", buf, 7, time_s)  # 7-8: elapsed time
    return bytes(buf)


class FtmsTreadmillService(Service):
    """GATT service: Fitness Machine Service with Treadmill Data."""

    def __init__(self, get_status: Callable[[], WalkingPadStatus | None]):
        super().__init__(FTMS_SERVICE_UUID, True)
        self._get_status = get_status
        self._treadmill_char = None

    @characteristic(TREADMILL_DATA_UUID, CharFlags.NOTIFY | CharFlags.READ)
    def treadmill_data(self, options):
        return _build_treadmill_data(self._get_status())

    def notify_treadmill_data(self) -> None:
        """Call when status changed so subscribers get notified."""
        c = self.treadmill_data
        if hasattr(c, "changed"):
            c.changed(_build_treadmill_data(self._get_status()))  # noqa: type ignore


async def run_ftms_server(
    device_name: str,
    get_status: Callable[[], WalkingPadStatus | None],
    adapter_id: str | None = None,
) -> None:
    """
    Run FTMS GATT server and advertisement until cancelled.
    get_status is called to build treadmill data for read/notify.
    """
    bus = await get_message_bus()
    from bluez_peripheral.util import Adapter
    adapter = await Adapter.get_first(bus)

    service = FtmsTreadmillService(get_status)
    await service.register(bus)
    advert = Advertisement(
        device_name,
        [FTMS_SERVICE_UUID],
        appearance=0x0340,  # Running Walking (treadmill)
    )
    await advert.register(bus, adapter=adapter)

    logger.info("FTMS advertising as %s", device_name)
    try:
        while True:
            await asyncio.sleep(3600)
    except asyncio.CancelledError:
        await advert.unregister()
        service.unexport()
        raise
