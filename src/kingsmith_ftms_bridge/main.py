"""
Main entry: run bridge with web UI and optional auto-connect loop.
"""

import argparse
import asyncio
import logging
import sys
import threading
import time

from .bridge import Bridge
from .config import load_config
from .web import run_flask

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Kingsmith WalkingPad R2 → FTMS bridge. Connects Kingsmith treadmill to Apple Fitness / Zwift etc."
    )
    parser.add_argument(
        "--no-auto",
        action="store_true",
        help="Disable automatic discovery and connection to the treadmill",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="Web UI port (default from config)",
    )
    parser.add_argument(
        "--host",
        type=str,
        default=None,
        help="Web bind address (default 0.0.0.0)",
    )
    args = parser.parse_args()

    config = load_config()
    port = args.port or config.get("web_port", 8080)
    host = args.host or config.get("web_host", "0.0.0.0")

    bridge = Bridge()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    def run_web():
        run_flask(host, port, bridge, loop)

    web_thread = threading.Thread(target=run_web, daemon=True)
    web_thread.start()
    logger.info("Web UI: http://%s:%s", host if host != "0.0.0.0" else "localhost", port)
    # Give Flask time to bind to the port before we start the asyncio loop
    time.sleep(1.5)

    try:
        if args.no_auto:
            logger.info("Manual mode: connect to the treadmill via the web interface.")
            loop.run_forever()
        else:
            loop.run_until_complete(bridge.run_auto_loop())
    except KeyboardInterrupt:
        logger.info("Stopping...")
    finally:
        bridge.stop_auto_loop()
        loop.run_until_complete(bridge.disconnect_treadmill())
        loop.close()
    sys.exit(0)


if __name__ == "__main__":
    main()
