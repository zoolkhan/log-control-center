import os
import json
import time
import requests
import threading
from flask import Flask, send_from_directory, jsonify, Response, request, make_response
from datetime import datetime, timezone
import adif_io

app = Flask(__name__)

# --- CONFIGURATION (Loaded from bridge_config.json) ---
CONFIG_FILE = "bridge_config.json"
DEFAULT_CONFIG = {
    "input_adif_files": [os.path.expanduser("~/merged.adi")],
    "output_adif_file": os.path.expanduser("~/bridge/data/merged_output.adi"),
    "varac_log_file": os.path.expanduser("~/.wine/drive_c/VarAC/VarAC.log"),
    "propagation_file": os.path.expanduser("~/.wine/drive_c/VarAC/BBS/B_radio_propagation_report_today.txt"),
    "update_interval": 5
}

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r') as f:
            try:
                config = json.load(f)
                # Ensure all keys exist
                for key in DEFAULT_CONFIG:
                    if key not in config:
                        config[key] = DEFAULT_CONFIG[key]
                return config
            except:
                return DEFAULT_CONFIG
    return DEFAULT_CONFIG

CONFIG = load_config()

# Ensure data directory exists
os.makedirs(os.path.dirname(CONFIG["output_adif_file"]), exist_ok=True)

# --- ADIF MERGING LOGIC (Inherited from TALP) ---
def deduplicate_qsos(qso_list):
    unique_qsos = {}
    for qso in qso_list:
        fingerprint = (
            qso.get('CALL', '').upper(),
            qso.get('QSO_DATE', ''),
            qso.get('TIME_ON', ''),
            qso.get('BAND', '').upper(),
            qso.get('MODE', '').upper()
        )
        if fingerprint not in unique_qsos:
            unique_qsos[fingerprint] = qso
    return list(unique_qsos.values())

def generate_adif_string(qso_list):
    parts = []
    header = {"PROGRAMID": "Bridge ADIF Merger", "CREATED_TIMESTAMP": datetime.now().strftime("%Y%m%d %H%M%S")}
    for key, value in header.items():
        parts.append(f"<{key}:{len(str(value))}>{value}")
    parts.append("<EOH>")
    for qso in qso_list:
        for key, value in qso.items():
            if value is not None and str(value).strip() != "":
                val_str = str(value)
                parts.append(f"<{key.upper()}:{len(val_str)}>{val_str}")
        parts.append("<EOR>")
    return "\n".join(parts)

def merge_adif_files():
    print("[ADIF ENGINE] Merging input logs...")
    all_qsos = []
    for file_path in CONFIG["input_adif_files"]:
        if os.path.exists(file_path):
            try:
                qsos, _ = adif_io.read_from_file(file_path)
                all_qsos.extend(qsos)
            except Exception as e:
                print(f"[ADIF ENGINE] Error reading {file_path}: {e}")
    
    if not all_qsos:
        print("[ADIF ENGINE] No QSOs found in input files.")
        return

    # Deduplicate and sort
    deduped = deduplicate_qsos(all_qsos)
    deduped.sort(key=lambda q: (q.get('QSO_DATE', '0'), q.get('TIME_ON', '0')), reverse=True)
    
    try:
        adif_string = generate_adif_string(deduped)
        with open(CONFIG["output_adif_file"], 'w', encoding='utf-8') as f:
            f.write(adif_string)
        print(f"[ADIF ENGINE] Successfully merged {len(deduped)} unique QSOs into {CONFIG['output_adif_file']}")
    except Exception as e:
        print(f"[ADIF ENGINE] Error saving merged ADIF: {e}")

def monitor_adif_files():
    last_mtimes = {}
    while True:
        try:
            should_merge = False
            # Check for config changes (reload if needed)
            global CONFIG
            current_config = load_config()
            if current_config != CONFIG:
                print("[CONFIG] Reloading bridge_config.json")
                CONFIG = current_config
                should_merge = True

            # Check for input file changes
            for file_path in CONFIG["input_adif_files"]:
                if os.path.exists(file_path):
                    mtime = os.path.getmtime(file_path)
                    if file_path not in last_mtimes or mtime > last_mtimes[file_path]:
                        last_mtimes[file_path] = mtime
                        should_merge = True
            
            if should_merge:
                merge_adif_files()
                
        except Exception as e:
            print(f"[MONITOR] Error in monitoring thread: {e}")
        
        time.sleep(CONFIG["update_interval"])

# Start background monitor
threading.Thread(target=monitor_adif_files, daemon=True).start()

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
    target = CONFIG["output_adif_file"]
    if not os.path.exists(target): 
        # Fallback to first input file if merged doesn't exist yet
        if CONFIG["input_adif_files"] and os.path.exists(CONFIG["input_adif_files"][0]):
            target = CONFIG["input_adif_files"][0]
        else:
            return "SOURCE_A_NOT_FOUND", 404
    with open(target, 'r') as f:
        return nocache(Response(f.read(), mimetype='text/plain'))

@app.route('/data/source_b.log')
def get_source_b():
    if not os.path.exists(CONFIG["varac_log_file"]): return "SOURCE_B_NOT_FOUND", 404
    try:
        with open(CONFIG["varac_log_file"], 'r', errors='ignore') as f:
            lines = f.readlines()
            return nocache(Response("".join(lines[-500:]), mimetype='text/plain'))
    except:
        return "ERROR_READING_B", 500

@app.route('/data/propagation.txt')
def get_propagation():
    if not os.path.exists(CONFIG["propagation_file"]): return "PROPAGATION_LINK_DOWN", 200
    with open(CONFIG["propagation_file"], 'r') as f:
        return nocache(Response(f.read(), mimetype='text/plain'))

@app.route('/api/config', methods=['GET', 'POST'])
def api_config():
    global CONFIG
    if request.method == 'POST':
        try:
            new_config = request.json
            # Validate and save
            with open(CONFIG_FILE, 'w') as f:
                json.dump(new_config, f, indent=4)
            CONFIG = new_config
            print("[CONFIG] Settings updated via API.")
            return jsonify({"status": "success"})
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500
    return jsonify(CONFIG)

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
    print("--- LOG CONTROL CENTER by OH8XAT v1.0 ACTIVE ---")
    print("UI available at: http://localhost:5000")
    app.run(host='0.0.0.0', port=5000)
