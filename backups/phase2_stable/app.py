import os
import json
import time
import requests
from flask import Flask, send_from_directory, jsonify, Response, request, make_response
from datetime import datetime, timezone

app = Flask(__name__)

# --- CONFIGURATION (Synced with bridge_datalink.py logic) ---
CONFIG = {
    "source_a": os.path.expanduser("~/merged.adi"),
    "source_b": os.path.expanduser("~/.wine/drive_c/VarAC/VarAC.log"),
    "propagation": os.path.expanduser("~/.wine/drive_c/VarAC/BBS/B_radio_propagation_report_today.txt"),
    "heartbeat": "/tmp/bridge_heartbeat.json"
}

# Cache-busting helper
def nocache(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

@app.route('/')
def index():
    return nocache(send_from_directory('.', 'index.html'))

@app.route('/world.geojson')
def get_map():
    return send_from_directory('.', 'world.geojson')

@app.route('/data/source_a.adi')
def get_source_a():
    if not os.path.exists(CONFIG["source_a"]): return "SOURCE_A_NOT_FOUND", 404
    with open(CONFIG["source_a"], 'r') as f:
        return nocache(Response(f.read(), mimetype='text/plain'))

@app.route('/data/source_b.log')
def get_source_b():
    if not os.path.exists(CONFIG["source_b"]): return "SOURCE_B_NOT_FOUND", 404
    try:
        with open(CONFIG["source_b"], 'r', errors='ignore') as f:
            lines = f.readlines()
            return nocache(Response("".join(lines[-500:]), mimetype='text/plain'))
    except:
        return "ERROR_READING_B", 500

@app.route('/data/propagation.txt')
def get_propagation():
    if not os.path.exists(CONFIG["propagation"]): return "PROPAGATION_LINK_DOWN", 200
    with open(CONFIG["propagation"], 'r') as f:
        return nocache(Response(f.read(), mimetype='text/plain'))

@app.route('/data/heartbeat.json')
def get_heartbeat():
    hb_data = {"last_seen": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")}
    return nocache(jsonify(hb_data))

@app.route('/psk_proxy')
def psk_proxy():
    call = request.args.get('call', 'OH8XAT')
    seconds = request.args.get('seconds', '3600')
    url = f"https://pskreporter.info/query?senderCallsign={call}&flow=receptionReport&lastSeconds={seconds}"
    try:
        r = requests.get(url, timeout=10)
        return nocache(Response(r.text, mimetype='application/xml'))
    except Exception as e:
        return str(e), 500

@app.route('/<path:path>')
def static_files(path):
    return send_from_directory('.', path)

if __name__ == "__main__":
    print("--- OUTPOST 23 LOCAL BRIDGE ACTIVE ---")
    print("UI available at: http://localhost:5000")
    app.run(host='0.0.0.0', port=5000)
