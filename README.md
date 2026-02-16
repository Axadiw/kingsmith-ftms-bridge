# Kingsmith FTMS Bridge

A bridge that connects a **Kingsmith treadmill (WalkingPad R2)** to the **FTMS** (Fitness Machine Service) protocol, so you can use it with **Apple Fitness (Workout)**, Zwift, Peloton, and other apps that support standard Bluetooth FTMS treadmills.

The Kingsmith treadmill uses its own BLE protocol; this app continuously connects to the treadmill, receives data (speed, distance, time) and rebroadcasts it as a standard **FTMS server** — all from a single Bluetooth adapter.

Tested on **Kingsmith WalkingPad R2** with **Raspberry Pi 4**.

## Features

- **Automatic discovery** of Kingsmith treadmills (WalkingPad A1/R1/R2) in a loop
- **Automatic connection** and FTMS bridge start when a device is found
- **Web interface** for control, status, and manual connection
- **Real-time data**: speed, distance, time — forwarded to FTMS apps (e.g. Apple Fitness)
- Ready for **autostart** on Raspberry Pi (e.g. via systemd)

## Requirements

- **Python 3.10+**
- **Linux** with BlueZ (e.g. Raspberry Pi OS, Debian, Ubuntu)
- **Bluetooth adapter** (e.g. built-in on Raspberry Pi 4)
- Treadmill in range and ready (Bluetooth on).

## Installation

### 1. System dependencies (BlueZ, Python venv)

```bash
sudo apt update
sudo apt install -y bluez python3-pip python3-venv
```

### 2. Project (development install)

```bash
cd kingsmith-ftms-bridge
pip install -e .
# or: pip install .
```

Dependencies (installed automatically): `bleak`, `bluez-peripheral`, `dbus-fast`, `flask`, `flask-cors`.

### Install and run scripts (recommended)

From the project root:

```bash
# Install: creates .venv, installs the package. Use --system-deps to install bluez + python3-pip.
./install.sh
./install.sh --system-deps   # on Debian/Ubuntu/Raspberry Pi OS

# Run the bridge (uses .venv if present)
./run.sh
./run.sh --no-auto           # manual mode
./run.sh --port 9000         # custom port
```

### 3. Configuration (optional)

Default config is loaded from:

- `/etc/kingsmith-ftms-bridge/config.json`
- or `~/.config/kingsmith-ftms-bridge/config.json`

Example `config.json`:

```json
{
  "ble_adapter": "hci0",
  "ftms_device_name": "Kingsmith R2 FTMS",
  "web_port": 8080,
  "web_host": "0.0.0.0",
  "scan_interval": 5.0,
  "stats_interval_ms": 750,
  "auto_start_bridge": true
}
```

- **ble_adapter** — BLE adapter to use (e.g. `hci0`). Empty = default.
- **ftms_device_name** — Device name visible in apps (e.g. Apple Fitness).
- **web_port** / **web_host** — Web UI port and bind address.
- **scan_interval** — How often (seconds) to scan for the treadmill.
- **stats_interval_ms** — How often (ms) to poll the treadmill for data (750 ms is typical).
- **auto_start_bridge** — Whether to start the FTMS bridge right after connecting to the treadmill.

## Running

### Using the run script

```bash
./run.sh
```

This uses the virtualenv in `.venv` if it exists (created by `install.sh`). You can pass any app options, e.g. `./run.sh --no-auto --port 9000`.

### Automatic mode (default)

The app scans in a loop, connects to a discovered treadmill, and starts the FTMS bridge:

```bash
./run.sh
# or:
python -m kingsmith_ftms_bridge.main
# or after pip install:
kingsmith-ftms-bridge
```

Open in a browser: **http://localhost:8080** (or your Raspberry Pi address and port from config).

### Manual mode

No automatic scanning or connection — control only via the web interface:

```bash
python -m kingsmith_ftms_bridge.main --no-auto
```

### Command-line options

- `--no-auto` — Disable automatic discovery and connection.
- `--port PORT` — Web UI port (overrides config).
- `--host ADDRESS` — Bind address (e.g. `0.0.0.0`).

## Using with Apple Fitness (Workout)

1. Run the bridge on a Raspberry Pi (or other Linux host with a BLE adapter).
2. Ensure the treadmill is on and in range.
3. After connection, the bridge will advertise FTMS data.
4. On **iPhone / Apple Watch**: Open **Fitness** → **Workout** → choose e.g. “Treadmill” / “Walking” and in Bluetooth device settings search for the device name from **ftms_device_name** (e.g. “Kingsmith R2 FTMS”) and connect.
5. Start the workout — speed, distance, and time from the treadmill will be sent to Workout.

## Autostart on Raspberry Pi (headless)

1. Copy the systemd service file:

```bash
sudo cp kingsmith-ftms-bridge.service /etc/systemd/system/
```

2. Edit paths and user in the file (e.g. `User=pi`, `WorkingDirectory`, and optionally the path to `python3` or venv):

```bash
sudo nano /etc/systemd/system/kingsmith-ftms-bridge.service
```

For a `pip install .` install you can set:

```ini
ExecStart=/home/pi/.local/bin/kingsmith-ftms-bridge
WorkingDirectory=/home/pi
```

(or your venv path in `ExecStart`).

3. Enable and start the service:

```bash
sudo systemctl daemon-reload
sudo systemctl enable kingsmith-ftms-bridge
sudo systemctl start kingsmith-ftms-bridge
```

4. After powering the Raspberry Pi, the bridge will start on its own, scan, connect to the treadmill, and start the FTMS bridge.

5. Check status and logs:

```bash
sudo systemctl status kingsmith-ftms-bridge
journalctl -u kingsmith-ftms-bridge -f
```

## API (for integration)

- `GET /api/status` — Connection status, FTMS bridge status, and current data (speed, distance, time).
- `POST /api/scan` — Scan for devices; returns list of addresses and names.
- `POST /api/connect` — Body: `{"address": "XX:XX:XX:XX:XX:XX"}` — connect to the chosen treadmill; with `auto_start_bridge: true` the FTMS bridge will start automatically.
- `POST /api/disconnect` — Disconnect from the treadmill and stop the bridge.
- `POST /api/bridge/start` — Start FTMS advertising (when already connected to the treadmill).
- `POST /api/bridge/stop` — Stop FTMS advertising.

## Protocol and licensing

- The Kingsmith WalkingPad protocol was reverse-engineered in [ph4-walkingpad](https://github.com/ph4r05/ph4-walkingpad) and [ftms-walkingpad](https://github.com/matmunn/ftms-walkingpad).
- FTMS (Fitness Machine Service) is a Bluetooth SIG standard.
- This project is provided “as is” for home integration with the Kingsmith R2 treadmill and FTMS apps (e.g. Apple Fitness).

## Troubleshooting

- **Treadmill not discovered** — Ensure the treadmill’s Bluetooth is on and no other app (e.g. the official Kingsmith app) is connected to it (only one connection is allowed).
- **Apple Fitness doesn't see the device** — Check that the FTMS bridge is on (in the UI: "FTMS Bridge: On"); on iPhone go to Settings → Bluetooth and look for the name from **ftms_device_name**.
- **BlueZ / GATT permission error** — Run with permissions that allow Bluetooth access (e.g. user in the `bluetooth` group) or run with `sudo` only for testing.
