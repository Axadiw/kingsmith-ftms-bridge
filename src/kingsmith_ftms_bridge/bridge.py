"""
Bridge logic: scan for WalkingPad, connect, run FTMS server, forward status.
"""

import asyncio
import logging
from typing import Callable

from .config import load_config
from .walkingpad import WalkingPadClient, WalkingPadStatus, SERVICE_UUID as WALKINGPAD_SERVICE_UUID
from .ftms_server import FtmsTreadmillService, FTMS_SERVICE_UUID

logger = logging.getLogger(__name__)


class Bridge:
    """Orchestrates WalkingPad client and FTMS server."""

    def __init__(self):
        self.config = load_config()
        self._status: WalkingPadStatus | None = None
        self._ftms_service: FtmsTreadmillService | None = None
        self._ftms_task: asyncio.Task | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._client = WalkingPadClient(
            adapter=self.config.get("ble_adapter"),
            on_status=self._on_walkingpad_status,
            stats_interval_ms=self.config.get("stats_interval_ms", 750),
        )
        self._running = False
        self._bridge_active = False
        self._treadmill_name: str | None = None

    def _on_walkingpad_status(self, status: WalkingPadStatus) -> None:
        """Called from BLE callback (may be from another thread)."""
        self._status = status
        if self._ftms_service and self._loop:
            self._loop.call_soon_threadsafe(self._notify_ftms)

    def _notify_ftms(self) -> None:
        """Run on main loop: push current status to FTMS subscribers."""
        if self._ftms_service:
            self._ftms_service.notify_treadmill_data()

    def get_status(self) -> WalkingPadStatus | None:
        return self._status

    # --- Treadmill control (used by both FTMS Control Point and web UI) ---

    async def start_belt(self) -> None:
        """Start the treadmill belt."""
        if not self._client.is_connected:
            raise RuntimeError("Not connected to treadmill")
        await self._client.start_belt()
        logger.info("Belt started")

    async def stop_belt(self) -> None:
        """Stop the treadmill belt."""
        if not self._client.is_connected:
            raise RuntimeError("Not connected to treadmill")
        await self._client.stop_belt()
        logger.info("Belt stopped")

    async def set_speed(self, speed_kmh: float) -> None:
        """Set treadmill target speed in km/h."""
        if not self._client.is_connected:
            raise RuntimeError("Not connected to treadmill")
        await self._client.set_speed_kmh(speed_kmh)
        logger.info("Speed set to %.2f km/h", speed_kmh)

    def _handle_ftms_control(self, cmd: str, *args) -> None:
        """Handle FTMS Control Point commands.

        Called from the D-Bus/asyncio event loop thread (via bluez_peripheral setter),
        so we schedule commands with asyncio.ensure_future — NOT run_coroutine_threadsafe.
        """
        if not self._client.is_connected:
            return
        if cmd == "start":
            asyncio.ensure_future(self._client.start_belt())
        elif cmd == "stop":
            asyncio.ensure_future(self._client.stop_belt())
        elif cmd == "set_speed" and args:
            asyncio.ensure_future(self._client.set_speed_kmh(args[0]))

    @property
    def is_connected(self) -> bool:
        return self._client.is_connected

    @property
    def bridge_active(self) -> bool:
        return self._bridge_active

    @property
    def treadmill_address(self) -> str | None:
        return self._client.address

    @property
    def treadmill_name(self) -> str | None:
        return self._treadmill_name

    async def scan(self, timeout: float = 8.0) -> list[tuple[str, str]]:
        """Scan for WalkingPad devices."""
        return await self._client.scan(timeout=timeout)

    async def connect_treadmill(self, address: str, name: str | None = None) -> bool:
        """Connect to treadmill by address. Returns True on success."""
        try:
            await self._client.connect(address)
            self._treadmill_name = name
            return True
        except Exception as e:
            logger.exception("Connect failed: %s", e)
            return False

    async def disconnect_treadmill(self) -> None:
        """Disconnect from treadmill and stop FTMS if running."""
        await self.stop_bridge()
        await self._client.disconnect()
        self._treadmill_name = None

    async def start_bridge(self) -> bool:
        """Start FTMS server (advertise treadmill data). Requires already connected to WalkingPad."""
        if not self._client.is_connected:
            logger.warning("Cannot start bridge: not connected to treadmill")
            return False
        if self._bridge_active:
            return True
        self._loop = asyncio.get_running_loop()
        # Status getter for FTMS
        def get_status() -> WalkingPadStatus | None:
            return self._status
        # We need to register the service and then run the advert loop; we also need to
        # expose the service so _on_walkingpad_status can call notify. So we register
        # the service, store a ref, then run advertisement and a loop that keeps the task alive.
        from bluez_peripheral.util import get_message_bus, Adapter
        from bluez_peripheral.advert import Advertisement
        bus = await get_message_bus()
        ble_adapter_name = self.config.get("ble_adapter") or "hci0"
        adapter_path = f"/org/bluez/{ble_adapter_name}"
        try:
            introspection = await bus.introspect("org.bluez", adapter_path)
            proxy = bus.get_proxy_object("org.bluez", adapter_path, introspection)
            adapter = Adapter(proxy)
        except Exception as e:
            logger.error(
                "Cannot access BLE adapter '%s' for FTMS server: %s. "
                "Set 'ble_adapter' in config (e.g. 'hci0').",
                ble_adapter_name, e,
            )
            return False
        service = FtmsTreadmillService(get_status, on_control_command=self._handle_ftms_control)
        await service.register(bus, adapter=adapter)
        self._ftms_service = service
        # Use explicit config override if set, otherwise derive from connected device name.
        name = self.config.get("ftms_device_name") or (
            f"{self._treadmill_name} FTMS" if self._treadmill_name else "Kingsmith FTMS"
        )
        advert = Advertisement(name, [FTMS_SERVICE_UUID], 0x0340, 0)  # appearance, timeout=0
        await advert.register(bus, adapter=adapter)
        self._bridge_active = True
        logger.info("FTMS bridge active: advertising as %s", name)

        async def keep_alive():
            try:
                while self._bridge_active:
                    await asyncio.sleep(60)
            except asyncio.CancelledError:
                pass
            finally:
                try:
                    await advert.unregister()
                except AttributeError:
                    pass
                await service.unregister()
                self._ftms_service = None
                self._bridge_active = False

        self._ftms_task = asyncio.create_task(keep_alive())
        return True

    async def stop_bridge(self) -> None:
        """Stop FTMS advertising."""
        self._bridge_active = False
        if self._ftms_task:
            self._ftms_task.cancel()
            try:
                await self._ftms_task
            except asyncio.CancelledError:
                pass
            self._ftms_task = None
        self._ftms_service = None
        logger.info("FTMS bridge stopped")

    async def run_auto_loop(self, on_state_change: Callable[[], None] | None = None) -> None:
        """
        Run forever: scan for treadmill, connect, optionally start bridge, reconnect if disconnected.
        """
        self._running = True
        scan_interval = float(self.config.get("scan_interval", 5.0))
        auto_start_bridge = self.config.get("auto_start_bridge", True)
        name_prefix = self.config.get("kingsmith_ble_name_prefix", "KS-SC-")
        last_address: str | None = None

        logger.info("Auto-discovery: looking for devices with name prefix '%s'", name_prefix)

        while self._running:
            try:
                if not self._client.is_connected:
                    if on_state_change:
                        on_state_change()
                    devices = await self._client.scan(
                        timeout=min(10.0, scan_interval + 2),
                        name_prefix=name_prefix,
                    )
                    if devices:
                        address, name = devices[0]
                        logger.info("Found treadmill: %s (%s), connecting...", name, address)
                        ok = await self.connect_treadmill(address, name=name)
                        if ok:
                            last_address = address
                            if auto_start_bridge:
                                await self.start_bridge()
                            if on_state_change:
                                on_state_change()
                        else:
                            last_address = None
                    else:
                        logger.debug("No treadmill found, retrying in %s s", scan_interval)
                    await asyncio.sleep(scan_interval)
                else:
                    await asyncio.sleep(scan_interval)
                    if not self._client.is_connected:
                        await self.stop_bridge()
                        if on_state_change:
                            on_state_change()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.exception("Auto loop error (web UI still available): %s", e)
                await asyncio.sleep(scan_interval)

    def stop_auto_loop(self) -> None:
        self._running = False
