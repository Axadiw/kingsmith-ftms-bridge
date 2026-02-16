"""Configuration: adapter ID, web port, device name."""

import json
import os
from pathlib import Path

CONFIG_PATH = Path(os.environ.get("KINGSMITH_FTMS_CONFIG", "/etc/kingsmith-ftms-bridge/config.json"))
FALLBACK_CONFIG = Path.home() / ".config" / "kingsmith-ftms-bridge" / "config.json"


def load_config() -> dict:
    """Load config from file or return defaults."""
    for path in (CONFIG_PATH, FALLBACK_CONFIG):
        if path.exists():
            try:
                with open(path, encoding="utf-8") as f:
                    return {**_default_config(), **json.load(f)}
            except (json.JSONDecodeError, OSError):
                pass
    return _default_config()


def _default_config() -> dict:
    return {
        # BLE adapter used for both treadmill connection and FTMS advertising.
        "ble_adapter": "hci0",
        # Web UI port.
        "web_port": 8080,
        # Web UI bind address.
        "web_host": "0.0.0.0",
        # Scan interval in seconds when searching for treadmill.
        "scan_interval": 5.0,
        # Stats request interval to treadmill (ms) when connected.
        "stats_interval_ms": 750,
        # Auto-start bridge after connecting to treadmill.
        "auto_start_bridge": True,
        # BLE device name prefix used for auto-discovery (e.g. "KS-SC-" matches "KS-SC-BLR2C").
        "kingsmith_ble_name_prefix": "KS-SC-",
    }


def save_config(config: dict) -> None:
    """Save config to user config path (creates dirs if needed)."""
    path = FALLBACK_CONFIG
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)
