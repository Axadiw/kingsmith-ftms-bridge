"""
FTMS (Fitness Machine Service) GATT server for treadmill data.

Broadcasts treadmill metrics in Bluetooth SIG FTMS format so that
Apple Fitness, Zwift, Peloton, etc. can connect as to a standard treadmill.

Supports bidirectional control: fitness apps can start/stop the belt
and set target speed via the FTMS Control Point characteristic.
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
FM_FEATURE_UUID = "2ACC"
FM_CONTROL_POINT_UUID = "2AD9"

# FTMS Treadmill Data flags. Instantaneous Speed is always present (no flag needed).
# Bit 2 = Total Distance Present, Bit 10 = Elapsed Time Present.
FLAGS_SPEED_DISTANCE_TIME = 0x0404

# Fitness Machine Feature (uint32): bits for capabilities we report.
#   Bit 0: Average Speed Supported
#   Bit 2: Total Distance Supported
#   Bit 6: Step Count Supported
#   Bit 9: Elapsed Time Supported
FM_FEATURES = 0x00000245

# Target Setting Feature (uint32):
#   Bit 0: Speed Target Setting Supported
FM_TARGET_FEATURES = 0x00000001

# Control Point opcodes (from client)
CP_REQUEST_CONTROL = 0x00
CP_RESET = 0x01
CP_SET_TARGET_SPEED = 0x02
CP_START_RESUME = 0x07
CP_STOP_PAUSE = 0x08
# Response opcode
CP_RESPONSE = 0x80

# Result codes
CP_SUCCESS = 0x01
CP_NOT_SUPPORTED = 0x02
CP_INVALID_PARAM = 0x03
CP_OPERATION_FAILED = 0x04
CP_NOT_PERMITTED = 0x05


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


def _cp_response(request_opcode: int, result: int) -> bytes:
    return bytes([CP_RESPONSE, request_opcode, result])


class FtmsTreadmillService(Service):
    """GATT service: Fitness Machine Service with Treadmill Data and Control Point."""

    def __init__(
        self,
        get_status: Callable[[], WalkingPadStatus | None],
        on_control_command: Callable[..., None] | None = None,
    ):
        super().__init__(FTMS_SERVICE_UUID, True)
        self._get_status = get_status
        self._on_control_command = on_control_command
        self._has_control = False

    # --- Fitness Machine Feature (read-only) ---
    @characteristic(FM_FEATURE_UUID, CharFlags.READ)
    def fitness_machine_feature(self, options):
        buf = bytearray(8)
        struct.pack_into("<II", buf, 0, FM_FEATURES, FM_TARGET_FEATURES)
        return bytes(buf)

    # --- Treadmill Data (notify + read) ---
    @characteristic(TREADMILL_DATA_UUID, CharFlags.NOTIFY | CharFlags.READ)
    def treadmill_data(self, options):
        return _build_treadmill_data(self._get_status())

    def notify_treadmill_data(self) -> None:
        """Call when status changed so subscribers get notified."""
        c = self.treadmill_data
        if hasattr(c, "changed"):
            c.changed(_build_treadmill_data(self._get_status()))

    # --- Fitness Machine Control Point (write + indicate) ---
    @characteristic(FM_CONTROL_POINT_UUID, CharFlags.WRITE | CharFlags.INDICATE)
    def control_point(self, options):
        return bytes()

    @control_point.setter
    def control_point(self, val: bytes, opts):
        if not val:
            return
        opcode = val[0]
        payload = val[1:]
        logger.info("FTMS Control Point: opcode=0x%02X payload=%s", opcode, payload.hex())

        response = self._handle_control(opcode, payload)
        # Send indication back to client
        cp = self.control_point
        if hasattr(cp, "changed"):
            cp.changed(response)

    def _handle_control(self, opcode: int, payload: bytes) -> bytes:
        if opcode == CP_REQUEST_CONTROL:
            self._has_control = True
            logger.info("FTMS: client requested control")
            return _cp_response(opcode, CP_SUCCESS)

        if not self._has_control:
            logger.warning("FTMS: command 0x%02X rejected — control not requested", opcode)
            return _cp_response(opcode, CP_NOT_PERMITTED)

        if opcode == CP_RESET:
            self._has_control = False
            logger.info("FTMS: reset")
            return _cp_response(opcode, CP_SUCCESS)

        if opcode == CP_SET_TARGET_SPEED:
            if len(payload) < 2:
                return _cp_response(opcode, CP_INVALID_PARAM)
            # Speed in 0.01 km/h units (uint16 LE)
            speed_raw = struct.unpack_from("<H", payload, 0)[0]
            speed_kmh = speed_raw / 100.0
            logger.info("FTMS: set target speed %.2f km/h", speed_kmh)
            return self._dispatch_command(opcode, "set_speed", speed_kmh)

        if opcode == CP_START_RESUME:
            logger.info("FTMS: start/resume")
            return self._dispatch_command(opcode, "start")

        if opcode == CP_STOP_PAUSE:
            if not payload:
                return _cp_response(opcode, CP_INVALID_PARAM)
            param = payload[0]
            if param == 0x01:
                logger.info("FTMS: stop")
                return self._dispatch_command(opcode, "stop")
            elif param == 0x02:
                logger.info("FTMS: pause (treated as stop)")
                return self._dispatch_command(opcode, "stop")
            return _cp_response(opcode, CP_INVALID_PARAM)

        logger.warning("FTMS: unsupported opcode 0x%02X", opcode)
        return _cp_response(opcode, CP_NOT_SUPPORTED)

    def _dispatch_command(self, opcode: int, cmd: str, *args) -> bytes:
        if self._on_control_command is None:
            logger.warning("FTMS: no control command handler registered")
            return _cp_response(opcode, CP_OPERATION_FAILED)
        try:
            self._on_control_command(cmd, *args)
            return _cp_response(opcode, CP_SUCCESS)
        except Exception as e:
            logger.exception("FTMS: control command '%s' failed: %s", cmd, e)
            return _cp_response(opcode, CP_OPERATION_FAILED)

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
