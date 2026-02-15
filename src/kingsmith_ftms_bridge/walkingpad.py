"""
Kingsmith WalkingPad BLE client (A1 / R1 / R2 compatible protocol).

Protocol reverse-engineered by ph4r05/ph4-walkingpad and matmunn/ftms-walkingpad.
"""

import asyncio
import logging
import platform
from dataclasses import dataclass
from typing import Callable

from bleak import BleakClient, BleakScanner

logger = logging.getLogger(__name__)

# WalkingPad uses FTMS-like UUIDs but proprietary protocol.
SERVICE_UUID = "00001826-0000-1000-8000-00805f9b34fb"
CHAR_WRITE = "00002ad9-0000-1000-8000-00805f9b34fb"
CHAR_NOTIFY = "00002acd-0000-1000-8000-00805f9b34fb"


@dataclass
class WalkingPadStatus:
    """Current treadmill status from WalkingPad."""

    speed_kmh: float  # current speed
    distance_km: float
    time_seconds: int
    steps: int
    belt_state: int  # 1=running, 5=stopped, etc.
    manual_mode: int
    app_speed_kmh: float

    @property
    def is_running(self) -> bool:
        return self.belt_state == 1


def _byte2int(b: bytes, start: int, width: int = 3) -> int:
    return sum(b[start + i] << (8 * (width - 1 - i)) for i in range(width))


def parse_status(data: bytes) -> WalkingPadStatus | None:
    """Parse WalkingPad current status message (prefix f8 a2)."""
    if len(data) < 19 or data[0:2] != bytes([0xF8, 0xA2]):
        return None
    speed_raw = data[3]  # speed * 10
    manual_mode = data[4]
    time_s = _byte2int(data, 5)
    dist_units = _byte2int(data, 8)  # 1 unit = 10 m
    steps = _byte2int(data, 11)
    app_speed_raw = data[14]  # 30 units = 6 km/h -> 1 unit = 0.2 km/h
    return WalkingPadStatus(
        speed_kmh=speed_raw / 10.0,
        distance_km=dist_units / 100.0,
        time_seconds=time_s,
        steps=steps,
        belt_state=data[2],
        manual_mode=manual_mode,
        app_speed_kmh=(app_speed_raw / 30.0) if app_speed_raw else 0.0,
    )


def _fix_crc(cmd: bytearray) -> bytearray:
    cmd[-2] = sum(cmd[1:-2]) % 256
    return cmd


class WalkingPadClient:
    """Async client for Kingsmith WalkingPad over BLE."""

    def __init__(
        self,
        adapter: str | None = None,
        on_status: Callable[["WalkingPadStatus"], None] | None = None,
        stats_interval_ms: int = 750,
    ):
        self.adapter = adapter
        self.on_status = on_status
        self.stats_interval_ms = stats_interval_ms
        self._client: BleakClient | None = None
        self._address: str | None = None
        self._last_status: WalkingPadStatus | None = None
        self._notify_task: asyncio.Task | None = None
        self._min_cmd_interval = 0.69
        self._scan_lock = asyncio.Lock()
        self._active_char_write: str = CHAR_WRITE

    @property
    def last_status(self) -> WalkingPadStatus | None:
        return self._last_status

    @property
    def is_connected(self) -> bool:
        return self._client is not None and self._client.is_connected

    @property
    def address(self) -> str | None:
        return self._address

    @staticmethod
    def _scanner_kwargs(adapter: str | None) -> dict:
        kwargs = {}
        if adapter:
            kwargs["adapter"] = adapter
        return kwargs

    async def scan(
        self,
        timeout: float = 8.0,
        service_uuids: list[str] | None = None,
        name_prefix: str | None = None,
    ) -> list[tuple[str, str]]:
        """Scan for BLE devices. Optionally filter by *name_prefix* (case-insensitive)."""
        async with self._scan_lock:
            kwargs = self._scanner_kwargs(self.adapter)
            if service_uuids:
                kwargs["service_uuids"] = service_uuids
            discovered = await BleakScanner.discover(timeout=timeout, return_adv=True, **kwargs)
        out = []
        for addr, (dev, adv) in discovered.items():
            name = adv.local_name or dev.name or addr
            if name_prefix and not (name or "").upper().startswith(name_prefix.upper()):
                continue
            out.append((addr, name))
        # Sort: devices with service 1826 (typical treadmill) and with a name first
        def order(item):
            addr, name = item
            adv_entry = discovered.get(addr)
            uuids = adv_entry[1].service_uuids if adv_entry else []
            has_1826 = bool(uuids and any("1826" in str(u).lower() for u in uuids))
            has_name = name and name != addr
            return (0 if has_1826 else 1, 0 if has_name else 1, addr)
        out.sort(key=order)
        return out

    def _notification_handler(self, _sender, data: bytearray):
        status = parse_status(bytes(data))
        if status:
            self._last_status = status
            if self.on_status:
                try:
                    self.on_status(status)
                except Exception as e:
                    logger.exception("on_status callback error: %s", e)

    async def _poll_stats_loop(self):
        """Periodically ask for stats (belt sends status in response)."""
        ask_cmd = bytearray([0xF7, 0xA2, 0x00, 0x00, 0xA2, 0xFD])
        _fix_crc(ask_cmd)
        while self._client and self._client.is_connected:
            try:
                await self._send_cmd(ask_cmd)
            except Exception as e:
                logger.warning("Stats poll failed: %s", e)
            await asyncio.sleep(self.stats_interval_ms / 1000.0)

    async def _send_cmd(self, cmd: bytearray) -> None:
        if not self._client or not self._client.is_connected:
            return
        await self._client.write_gatt_char(self._active_char_write, cmd)

    async def connect(self, address: str) -> None:
        """Connect to WalkingPad by address."""
        if self._client and self._client.is_connected:
            await self.disconnect()
        # Acquire scan lock – BleakClient.connect() does an internal scan
        # (find_device_by_address) which conflicts with any ongoing scan.
        async with self._scan_lock:
            kwargs = self._scanner_kwargs(self.adapter)
            self._client = BleakClient(address, **kwargs)
            await self._client.connect(timeout=15.0)
        self._address = address
        logger.info("Connected to WalkingPad at %s", address)

        # Log all services and characteristics for diagnostics
        for service in self._client.services:
            logger.info("  Service: %s (%s)", service.uuid, service.description)
            for char in service.characteristics:
                props = ", ".join(char.properties)
                logger.info("    Char: %s (%s) [%s]", char.uuid, char.description, props)

        # Find the right characteristics dynamically
        char_notify, char_write = self._find_char_pair()

        if not char_notify:
            raise RuntimeError(
                f"No notify characteristic found (expected {CHAR_NOTIFY}). "
                "Check logged services above for the correct UUID."
            )
        if not char_write:
            raise RuntimeError(
                f"No write characteristic found (expected {CHAR_WRITE}). "
                "Check logged services above for the correct UUID."
            )

        self._active_char_write = char_write.uuid
        logger.info("Using notify char: %s, write char: %s", char_notify.uuid, char_write.uuid)

        await self._client.start_notify(char_notify, self._notification_handler)
        self._notify_task = asyncio.create_task(self._poll_stats_loop())
        # Initial stats request
        ask_cmd = bytearray([0xF7, 0xA2, 0x00, 0x00, 0xA2, 0xFD])
        _fix_crc(ask_cmd)
        await self._send_cmd(ask_cmd)

    def _find_char_pair(self):
        """Find notify + write characteristics. Prefers exact UUIDs, then same-service pairing."""
        if not self._client:
            return None, None

        def _has_write(char):
            return "write" in char.properties or "write-without-response" in char.properties

        def _has_notify(char):
            return "notify" in char.properties

        skip_prefixes = ("00001800-", "00001801-", "0000180a-")

        # 1) Try exact UUID match
        notify_char = write_char = None
        for service in self._client.services:
            for char in service.characteristics:
                if char.uuid == CHAR_NOTIFY and _has_notify(char):
                    notify_char = char
                if char.uuid == CHAR_WRITE and _has_write(char):
                    write_char = char
        if notify_char and write_char:
            return notify_char, write_char

        # 2) Look for a vendor service that has BOTH notify and write chars
        for service in self._client.services:
            if any(service.uuid.startswith(p) for p in skip_prefixes):
                continue
            svc_notify = svc_write = None
            for char in service.characteristics:
                if _has_notify(char) and svc_notify is None:
                    svc_notify = char
                if _has_write(char) and svc_write is None:
                    svc_write = char
            if svc_notify and svc_write:
                logger.info(
                    "Using vendor service %s: notify=%s, write=%s",
                    service.uuid, svc_notify.uuid, svc_write.uuid,
                )
                return svc_notify, svc_write

        # 3) Fall back to first notify + first write from any non-generic service
        fallback_notify = notify_char  # may already have one from step 1
        fallback_write = write_char
        for service in self._client.services:
            if any(service.uuid.startswith(p) for p in skip_prefixes):
                continue
            for char in service.characteristics:
                if _has_notify(char) and fallback_notify is None:
                    fallback_notify = char
                if _has_write(char) and fallback_write is None:
                    fallback_write = char
        if fallback_notify and fallback_notify.uuid != CHAR_NOTIFY:
            logger.warning("Notify: falling back to %s", fallback_notify.uuid)
        if fallback_write and fallback_write.uuid != CHAR_WRITE:
            logger.warning("Write: falling back to %s", fallback_write.uuid)
        return fallback_notify, fallback_write

    async def disconnect(self) -> None:
        """Disconnect from the treadmill."""
        if self._notify_task:
            self._notify_task.cancel()
            try:
                await self._notify_task
            except asyncio.CancelledError:
                pass
            self._notify_task = None
        if self._client:
            await self._client.disconnect()
            self._client = None
        self._address = None
        logger.info("Disconnected from WalkingPad")

    async def start_belt(self) -> None:
        """Start the belt."""
        cmd = bytearray([0x07])
        await self._send_cmd(cmd)

    async def stop_belt(self) -> None:
        """Stop the belt."""
        cmd = bytearray([0x08, 0x01])
        await self._send_cmd(cmd)

    async def set_speed_kmh(self, speed: float) -> None:
        """Set target speed in km/h (0.5–6.0 typical)."""
        val = int(round(speed * 100))
        val = max(0, min(600, val))
        hex_val = f"{val:04x}"
        le_bytes = bytearray.fromhex(hex_val)
        le_bytes.reverse()
        cmd = bytearray([0x02]) + le_bytes
        await self._send_cmd(cmd)
