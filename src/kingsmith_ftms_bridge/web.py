"""
Web UI and REST API for the bridge.
"""

import asyncio
import logging

from flask import Flask, jsonify, request
from flask_cors import CORS

logger = logging.getLogger(__name__)

app = Flask(__name__, static_folder=None)
CORS(app)

# Injected by main
bridge_ref = None
loop_ref = None


def _run_coro(coro):
    if loop_ref is None:
        return None
    fut = asyncio.run_coroutine_threadsafe(coro, loop_ref)
    return fut.result(timeout=30)


@app.route("/")
def index():
    return _html()


def _html():
    return """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, user-scalable=no">
  <title>Kingsmith FTMS Bridge</title>
  <style>
    :root {
      --bg: #0a0a0e;
      --card: #16161c;
      --accent: #00c853;
      --accent-dim: rgba(0,200,83,0.15);
      --muted: #6b7280;
      --text: #e5e7eb;
      --danger: #ef4444;
      --border: rgba(255,255,255,0.06);
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: -apple-system, 'SF Pro Display', 'Segoe UI', system-ui, sans-serif;
      background: var(--bg);
      color: var(--text);
      min-height: 100vh;
      overflow-x: hidden;
    }

    /* --- Tabs --- */
    .tabs {
      display: flex;
      background: var(--card);
      border-bottom: 1px solid var(--border);
      position: sticky;
      top: 0;
      z-index: 10;
    }
    .tab {
      flex: 1;
      padding: 0.9rem;
      text-align: center;
      font-size: 0.85rem;
      font-weight: 600;
      color: var(--muted);
      cursor: pointer;
      border-bottom: 2px solid transparent;
      transition: all 0.2s;
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }
    .tab.active {
      color: var(--accent);
      border-bottom-color: var(--accent);
    }
    .tab-content { display: none; }
    .tab-content.active { display: block; }

    /* --- Status bar --- */
    .status-bar {
      display: flex;
      gap: 0.5rem;
      padding: 0.6rem 1rem;
      background: var(--card);
      border-bottom: 1px solid var(--border);
      align-items: center;
      font-size: 0.75rem;
    }
    .status-dot {
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: var(--muted);
      flex-shrink: 0;
    }
    .status-dot.on { background: var(--accent); animation: glow 2s ease-in-out infinite; }
    .status-dot.off { background: var(--danger); }
    @keyframes glow { 50% { box-shadow: 0 0 8px var(--accent); } }
    .status-label { color: var(--muted); }

    /* --- Dashboard --- */
    .dashboard { padding: 1rem; }

    .hero-metric {
      text-align: center;
      padding: 2rem 1rem 1.5rem;
    }
    .hero-value {
      font-size: 5rem;
      font-weight: 200;
      line-height: 1;
      font-variant-numeric: tabular-nums;
      letter-spacing: -2px;
    }
    .hero-unit {
      font-size: 1.1rem;
      color: var(--muted);
      margin-top: 0.3rem;
    }

    .metrics-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 0.75rem;
      padding: 0 0 1rem;
    }
    .metric-card {
      background: var(--card);
      border-radius: 16px;
      padding: 1.2rem;
      text-align: center;
    }
    .metric-label {
      font-size: 0.7rem;
      font-weight: 600;
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: 0.08em;
      margin-bottom: 0.4rem;
    }
    .metric-value {
      font-size: 2.2rem;
      font-weight: 300;
      line-height: 1.1;
      font-variant-numeric: tabular-nums;
    }
    .metric-unit {
      font-size: 0.75rem;
      color: var(--muted);
      margin-top: 0.15rem;
    }
    .metric-card.wide {
      grid-column: 1 / -1;
    }

    .secondary-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 0.75rem;
      padding: 0 0 1rem;
    }
    .sec-metric {
      background: var(--card);
      border-radius: 12px;
      padding: 0.9rem 0.6rem;
      text-align: center;
    }
    .sec-label {
      font-size: 0.6rem;
      font-weight: 600;
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: 0.06em;
      margin-bottom: 0.3rem;
    }
    .sec-value {
      font-size: 1.3rem;
      font-weight: 400;
      font-variant-numeric: tabular-nums;
    }

    /* --- Devices tab --- */
    .devices-panel { padding: 1rem; }
    .devices-panel h2 {
      font-size: 0.85rem;
      font-weight: 600;
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: 0.05em;
      margin-bottom: 0.75rem;
    }
    .conn-card {
      background: var(--card);
      border-radius: 12px;
      padding: 1rem;
      margin-bottom: 1rem;
    }
    .conn-row {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 0.4rem 0;
    }
    .conn-label { color: var(--muted); font-size: 0.85rem; }
    .conn-value { font-size: 0.85rem; font-weight: 500; }
    .badge {
      display: inline-block;
      padding: 0.15rem 0.5rem;
      border-radius: 6px;
      font-size: 0.7rem;
      font-weight: 600;
    }
    .badge--ok { background: var(--accent-dim); color: var(--accent); }
    .badge--off { background: rgba(107,114,128,0.25); color: var(--muted); }
    .actions { display: flex; flex-wrap: wrap; gap: 0.5rem; margin-top: 0.75rem; }
    .btn {
      display: inline-flex;
      align-items: center;
      gap: 0.4rem;
      padding: 0.55rem 1rem;
      border: none;
      border-radius: 8px;
      font-size: 0.8rem;
      font-weight: 500;
      cursor: pointer;
      transition: opacity 0.2s;
    }
    .btn:hover { opacity: 0.85; }
    .btn:disabled { opacity: 0.4; cursor: not-allowed; }
    .btn--primary { background: var(--accent); color: var(--bg); }
    .btn--secondary { background: rgba(255,255,255,0.08); color: var(--text); }
    .btn--danger { background: var(--danger); color: white; }
    #devices { list-style: none; }
    #devices li {
      padding: 0.55rem 0.75rem;
      background: rgba(255,255,255,0.03);
      border-radius: 8px;
      margin-bottom: 0.4rem;
      display: flex;
      justify-content: space-between;
      align-items: center;
      font-size: 0.85rem;
    }
    #devices li small { color: var(--muted); margin-left: 0.3rem; }
    .hint { color: var(--muted); font-size: 0.8rem; }

    /* --- Controls --- */
    .controls-card {
      background: var(--card);
      border-radius: 16px;
      padding: 1.2rem;
      margin-bottom: 1rem;
    }
    .controls-card h3 {
      font-size: 0.7rem;
      font-weight: 600;
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: 0.08em;
      margin-bottom: 1rem;
    }
    .speed-row {
      display: flex;
      align-items: center;
      gap: 0.75rem;
      margin-bottom: 1rem;
    }
    .speed-display {
      font-size: 1.4rem;
      font-weight: 300;
      font-variant-numeric: tabular-nums;
      min-width: 3.5rem;
      text-align: right;
    }
    .speed-unit { color: var(--muted); font-size: 0.75rem; }
    input[type=range] {
      flex: 1;
      -webkit-appearance: none;
      height: 4px;
      border-radius: 2px;
      background: rgba(255,255,255,0.12);
      outline: none;
    }
    input[type=range]::-webkit-slider-thumb {
      -webkit-appearance: none;
      width: 20px;
      height: 20px;
      border-radius: 50%;
      background: var(--accent);
      cursor: pointer;
    }
    input[type=range]::-moz-range-thumb {
      width: 20px;
      height: 20px;
      border-radius: 50%;
      background: var(--accent);
      cursor: pointer;
      border: none;
    }
    .ctrl-btns { display: flex; gap: 0.5rem; flex-wrap: wrap; }
    .btn--start { background: var(--accent); color: var(--bg); }
    .btn--stop { background: var(--danger); color: white; }
    .speed-steps { display: flex; gap: 0.4rem; flex-wrap: wrap; margin-bottom: 0.75rem; }
    .speed-step {
      padding: 0.3rem 0.65rem;
      border-radius: 6px;
      font-size: 0.75rem;
      font-weight: 500;
      background: rgba(255,255,255,0.07);
      color: var(--text);
      cursor: pointer;
      border: 1px solid transparent;
      transition: all 0.15s;
    }
    .speed-step:hover { background: rgba(255,255,255,0.13); }
    .speed-step.active { border-color: var(--accent); color: var(--accent); }
  </style>
</head>
<body>

  <div class="tabs">
    <div class="tab active" data-tab="workout">Workout</div>
    <div class="tab" data-tab="devices">Devices</div>
  </div>

  <div class="status-bar">
    <span class="status-dot off" id="sd-treadmill"></span>
    <span class="status-label" id="sl-treadmill">Disconnected</span>
    <span style="margin-left:auto"></span>
    <span class="status-dot off" id="sd-bridge"></span>
    <span class="status-label" id="sl-bridge">FTMS off</span>
  </div>

  <!-- ===== WORKOUT TAB ===== -->
  <div class="tab-content active" id="tab-workout">
    <div class="dashboard">
      <div class="hero-metric">
        <div class="hero-value" id="w-speed">0.0</div>
        <div class="hero-unit">km/h</div>
      </div>

      <div class="metrics-grid">
        <div class="metric-card">
          <div class="metric-label">Time</div>
          <div class="metric-value" id="w-time">0:00</div>
        </div>
        <div class="metric-card">
          <div class="metric-label">Pace</div>
          <div class="metric-value" id="w-pace">--:--</div>
          <div class="metric-unit">min/km</div>
        </div>
        <div class="metric-card">
          <div class="metric-label">Steps</div>
          <div class="metric-value" id="w-steps">0</div>
        </div>
        <div class="metric-card">
          <div class="metric-label">Distance</div>
          <div class="metric-value" id="w-distance">0.00</div>
          <div class="metric-unit">km</div>
        </div>
      </div>

      <div class="secondary-grid">
        <div class="sec-metric">
          <div class="sec-label">Avg speed</div>
          <div class="sec-value" id="w-avg-speed">0.0</div>
        </div>
        <div class="sec-metric">
          <div class="sec-label">Cadence</div>
          <div class="sec-value" id="w-cadence">0</div>
        </div>
      </div>

      <div class="controls-card" id="controls-card">
        <h3>Control</h3>
        <div class="speed-row">
          <input type="range" id="speed-slider" min="5" max="60" step="1" value="20">
          <span class="speed-display" id="speed-target-val">2.0</span>
          <span class="speed-unit">km/h</span>
        </div>
        <div class="speed-steps" id="speed-presets"></div>
        <div class="ctrl-btns">
          <button class="btn btn--start" id="btn-start-belt" disabled>Start</button>
          <button class="btn btn--stop" id="btn-stop-belt" disabled>Stop</button>
          <button class="btn btn--primary" id="btn-set-speed" disabled>Set speed</button>
        </div>
      </div>
    </div>
  </div>

  <!-- ===== DEVICES TAB ===== -->
  <div class="tab-content" id="tab-devices">
    <div class="devices-panel">
      <div class="conn-card">
        <h2>Connection</h2>
        <div class="conn-row">
          <span class="conn-label">Treadmill</span>
          <span class="conn-value" id="d-conn"><span class="badge badge--off">Disconnected</span></span>
        </div>
        <div class="conn-row">
          <span class="conn-label">FTMS Bridge</span>
          <span class="conn-value" id="d-bridge"><span class="badge badge--off">Off</span></span>
        </div>
        <div class="actions">
          <button class="btn btn--danger" id="btn-disconnect" disabled>Disconnect</button>
          <button class="btn btn--primary" id="btn-bridge-start" disabled>Start bridge</button>
          <button class="btn btn--secondary" id="btn-bridge-stop" disabled>Stop bridge</button>
        </div>
      </div>

      <div class="conn-card">
        <h2>Scan for devices</h2>
        <p id="scan-hint" class="hint">Click Scan to search for BLE devices.</p>
        <ul id="devices"></ul>
        <div class="actions">
          <button class="btn btn--primary" id="btn-scan">Scan</button>
        </div>
      </div>
    </div>
  </div>

  <script>
    /* --- Tabs --- */
    document.querySelectorAll('.tab').forEach(tab => {
      tab.onclick = () => {
        document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
        document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
        tab.classList.add('active');
        document.getElementById('tab-' + tab.dataset.tab).classList.add('active');
      };
    });

    /* --- API --- */
    const api = (path, opts = {}) =>
      fetch('/api' + path, { headers: { 'Content-Type': 'application/json' }, ...opts }).then(r => r.json());

    function fmt(t) {
      if (t == null) return '0:00';
      const m = Math.floor(t / 60), s = t % 60;
      return m + ':' + String(s).padStart(2, '0');
    }

    function refresh() {
      api('/status').then(d => {
        const spd = d.speed_kmh != null ? d.speed_kmh : 0;
        const dist = d.distance_km != null ? d.distance_km : 0;
        const t = d.time_seconds != null ? d.time_seconds : 0;
        const steps = d.steps != null ? d.steps : 0;
        const avgSpd = t > 0 ? (dist / (t / 3600)) : 0;
        const cadence = t > 0 ? Math.round(steps / (t / 60)) : 0;
        let pace = '--:--';
        if (spd > 0.3) {
          const paceTotal = 60 / spd;
          pace = Math.floor(paceTotal) + ':' + String(Math.round((paceTotal % 1) * 60)).padStart(2, '0');
        }

        /* Workout tab */
        document.getElementById('w-speed').textContent = spd.toFixed(1);
        document.getElementById('w-time').textContent = fmt(t);
        document.getElementById('w-distance').textContent = dist.toFixed(2);
        document.getElementById('w-steps').textContent = steps;
        document.getElementById('w-pace').textContent = pace;
        document.getElementById('w-avg-speed').textContent = avgSpd.toFixed(1);
        document.getElementById('w-cadence').textContent = cadence;

        /* Control buttons */
        const connected = !!d.connected;
        document.getElementById('btn-start-belt').disabled = !connected || !!d.belt_running;
        document.getElementById('btn-stop-belt').disabled = !connected || !d.belt_running;
        document.getElementById('btn-set-speed').disabled = !connected;

        /* Status bar */
        const sdT = document.getElementById('sd-treadmill');
        const slT = document.getElementById('sl-treadmill');
        sdT.className = 'status-dot ' + (d.connected ? 'on' : 'off');
        slT.textContent = d.connected ? (d.address || 'Connected') : 'Disconnected';
        const sdB = document.getElementById('sd-bridge');
        const slB = document.getElementById('sl-bridge');
        sdB.className = 'status-dot ' + (d.bridge_active ? 'on' : '');
        slB.textContent = d.bridge_active ? 'FTMS on' : 'FTMS off';

        /* Devices tab */
        document.getElementById('d-conn').innerHTML = d.connected
          ? '<span class="badge badge--ok">' + (d.address || 'Connected') + '</span>'
          : '<span class="badge badge--off">Disconnected</span>';
        document.getElementById('d-bridge').innerHTML = d.bridge_active
          ? '<span class="badge badge--ok">On</span>'
          : '<span class="badge badge--off">Off</span>';
        document.getElementById('btn-disconnect').disabled = !d.connected;
        document.getElementById('btn-bridge-start').disabled = !d.connected || d.bridge_active;
        document.getElementById('btn-bridge-stop').disabled = !d.bridge_active;
      }).catch(() => {});
    }

    /* --- Controls --- */
    const PRESETS = [1.0, 1.5, 2.0, 3.0, 4.0, 5.0, 6.0];
    const presetsEl = document.getElementById('speed-presets');
    PRESETS.forEach(v => {
      const s = document.createElement('span');
      s.className = 'speed-step';
      s.textContent = v.toFixed(1);
      s.onclick = () => {
        document.getElementById('speed-slider').value = Math.round(v * 10);
        updateSpeedDisplay();
        setSpeed(v);
      };
      presetsEl.appendChild(s);
    });

    function updateSpeedDisplay() {
      const raw = parseInt(document.getElementById('speed-slider').value, 10);
      const kmh = raw / 10;
      document.getElementById('speed-target-val').textContent = kmh.toFixed(1);
      presetsEl.querySelectorAll('.speed-step').forEach(s => {
        s.classList.toggle('active', parseFloat(s.textContent) === kmh);
      });
    }

    document.getElementById('speed-slider').oninput = updateSpeedDisplay;
    updateSpeedDisplay();

    function setSpeed(val) {
      api('/treadmill/speed', { method: 'POST', body: JSON.stringify({ speed_kmh: val }) });
    }

    document.getElementById('btn-set-speed').onclick = () => {
      const raw = parseInt(document.getElementById('speed-slider').value, 10);
      setSpeed(raw / 10);
    };

    document.getElementById('btn-start-belt').onclick = () =>
      api('/treadmill/start', { method: 'POST' }).then(() => refresh());

    document.getElementById('btn-stop-belt').onclick = () =>
      api('/treadmill/stop', { method: 'POST' }).then(() => refresh());

    /* --- Devices actions --- */
    document.getElementById('btn-scan').onclick = () => {
      document.getElementById('scan-hint').textContent = 'Scanning...';
      api('/scan', { method: 'POST' }).then(d => {
        const devs = d.devices || [];
        const ul = document.getElementById('devices');
        ul.innerHTML = '';
        devs.forEach(([addr, name]) => {
          const li = document.createElement('li');
          li.innerHTML = '<span>' + (name || addr) + '<small>' + addr + '</small></span>'
            + '<button class="btn btn--primary">Connect</button>';
          li.querySelector('button').onclick = () => {
            api('/connect', { method: 'POST', body: JSON.stringify({ address: addr, name: name }) }).then(() => refresh());
          };
          ul.appendChild(li);
        });
        document.getElementById('scan-hint').textContent = devs.length
          ? 'Select your treadmill:' : 'No devices found. Is the treadmill on?';
      });
    };
    document.getElementById('btn-disconnect').onclick = () => api('/disconnect', { method: 'POST' }).then(() => refresh());
    document.getElementById('btn-bridge-start').onclick = () => api('/bridge/start', { method: 'POST' }).then(() => refresh());
    document.getElementById('btn-bridge-stop').onclick = () => api('/bridge/stop', { method: 'POST' }).then(() => refresh());

    setInterval(refresh, 1000);
    refresh();
  </script>
</body>
</html>"""


@app.route("/api/status")
def api_status():
    b = bridge_ref
    if not b:
        return jsonify(connected=False, bridge_active=False)
    s = b.get_status()
    return jsonify({
        "connected": b.is_connected,
        "address": b.treadmill_address,
        "bridge_active": b.bridge_active,
        "speed_kmh": round(s.speed_kmh, 2) if s else None,
        "distance_km": round(s.distance_km, 3) if s else None,
        "time_seconds": s.time_seconds if s else None,
        "steps": s.steps if s else None,
        "belt_running": s.is_running if s else False,
    })


@app.route("/api/scan", methods=["POST"])
def api_scan():
    b = bridge_ref
    if not b:
        return jsonify(devices=[])
    devices = _run_coro(b.scan(timeout=10.0))
    return jsonify(devices=devices or [])


@app.route("/api/connect", methods=["POST"])
def api_connect():
    b = bridge_ref
    if not b:
        return jsonify(ok=False)
    data = request.get_json() or {}
    addr = data.get("address")
    if not addr:
        return jsonify(ok=False, error="address required")
    name = data.get("name")
    ok = _run_coro(b.connect_treadmill(addr, name=name))
    if ok and b.config.get("auto_start_bridge"):
        _run_coro(b.start_bridge())
    return jsonify(ok=ok)


@app.route("/api/disconnect", methods=["POST"])
def api_disconnect():
    b = bridge_ref
    if not b:
        return jsonify(ok=True)
    _run_coro(b.disconnect_treadmill())
    return jsonify(ok=True)


@app.route("/api/treadmill/start", methods=["POST"])
def api_treadmill_start():
    b = bridge_ref
    if not b:
        return jsonify(ok=False, error="bridge not ready")
    try:
        _run_coro(b.start_belt())
        return jsonify(ok=True)
    except Exception as e:
        return jsonify(ok=False, error=str(e))


@app.route("/api/treadmill/stop", methods=["POST"])
def api_treadmill_stop():
    b = bridge_ref
    if not b:
        return jsonify(ok=False, error="bridge not ready")
    try:
        _run_coro(b.stop_belt())
        return jsonify(ok=True)
    except Exception as e:
        return jsonify(ok=False, error=str(e))


@app.route("/api/treadmill/speed", methods=["POST"])
def api_treadmill_speed():
    b = bridge_ref
    if not b:
        return jsonify(ok=False, error="bridge not ready")
    data = request.get_json() or {}
    speed = data.get("speed_kmh")
    if speed is None:
        return jsonify(ok=False, error="speed_kmh required")
    try:
        speed = float(speed)
    except (TypeError, ValueError):
        return jsonify(ok=False, error="invalid speed_kmh")
    try:
        _run_coro(b.set_speed(speed))
        return jsonify(ok=True)
    except Exception as e:
        return jsonify(ok=False, error=str(e))


@app.route("/api/bridge/start", methods=["POST"])
def api_bridge_start():
    b = bridge_ref
    if not b:
        return jsonify(ok=False)
    ok = _run_coro(b.start_bridge())
    return jsonify(ok=ok)


@app.route("/api/bridge/stop", methods=["POST"])
def api_bridge_stop():
    b = bridge_ref
    if not b:
        return jsonify(ok=True)
    _run_coro(b.stop_bridge())
    return jsonify(ok=True)


def run_flask(host: str, port: int, bridge, loop) -> None:
    global bridge_ref, loop_ref
    bridge_ref = bridge
    loop_ref = loop
    app.run(host=host, port=port, threaded=True, use_reloader=False)
