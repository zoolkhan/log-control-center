import os
import json
import time
import requests
import threading
import xml.etree.ElementTree as ET
from flask import Flask, send_from_directory, jsonify, Response, request, make_response
from datetime import datetime, timezone
import adif_io

app = Flask(__name__)

# --- CONFIGURATION (Loaded from bridge_config.json) ---
CONFIG_FILE = "bridge_config.json"
DEFAULT_CONFIG = {
    "input_adif_files": [os.path.expanduser("~/merged.adi")],
    "output_adif_file": os.path.expanduser("~/bridge/data/merged_output.adi"),
    "manual_adif_file": os.path.expanduser("~/bridge/data/manual_log.adi"),
    "varac_log_file": os.path.expanduser("~/.wine/drive_c/VarAC/VarAC.log"),
    "propagation_file": os.path.expanduser("~/.wine/drive_c/VarAC/BBS/B_radio_propagation_report_today.txt"),
    "fetch_propagation_data": True,
    "propagation_fetch_interval": 14400, # 4 hours in seconds
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
                
                # Auto-inject manual log into input files if not present
                if config["manual_adif_file"] not in config["input_adif_files"]:
                    config["input_adif_files"].append(config["manual_adif_file"])
                
                return config
            except:
                return DEFAULT_CONFIG
    
    # Fallback if no file: ensure manual log is in defaults
    conf = DEFAULT_CONFIG.copy()
    if conf["manual_adif_file"] not in conf["input_adif_files"]:
        conf["input_adif_files"].append(conf["manual_adif_file"])
    return conf

CONFIG = load_config()

# Ensure data directory exists
os.makedirs(os.path.dirname(CONFIG["output_adif_file"]), exist_ok=True)

# Shared state for propagation
current_propagation_report = "[Propagation data not yet fetched]"
last_propagation_fetch = 0

# --- PROPAGATION FETCHING LOGIC ---
def fetch_propagation_data():
    global current_propagation_report
    global last_propagation_fetch
    url = "https://www.hamqsl.com/solarxml.php"
    print(f"[PROPAGATION] Fetching data from {url}...")
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        
        root = ET.fromstring(response.content)
        data = root.find('solardata')
        if data is None: 
            print("[PROPAGATION] Could not find 'solardata' tag.")
            return

        solarflux = data.findtext('solarflux', 'N/A')
        sunspots = data.findtext('sunspots', 'N/A')
        aindex = data.findtext('aindex', 'N/A')
        kindex = data.findtext('kindex', 'N/A')
        geomagfield = data.findtext('geomagfield', 'N/A')
        
        report_parts = [
            f"Radio Propagation Report ({datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')})",
            "Solar Data:",
            f"- Solar Flux: {solarflux}",
            f"- Sunspots: {sunspots}",
            f"- A-Index: {aindex}",
            f"- K-Index: {kindex}",
            f"- Geomagnetic Field: {geomagfield}",
            "Band Conditions (Day):"
        ]
        
        calc = data.find('calculatedconditions')
        if calc is not None:
            for band in calc.findall("./band[@time='day']"):
                band_name = band.get('name', 'N/A')
                condition = band.text.strip() if band.text else 'N/A'
                report_parts.append(f"- {band_name}: {condition}")
            
            report_parts.append("Band Conditions (Night):")
            for band in calc.findall("./band[@time='night']"):
                band_name = band.get('name', 'N/A')
                condition = band.text.strip() if band.text else 'N/A'
                report_parts.append(f"- {band_name}: {condition}")
        else:
            report_parts.append("Band conditions data unavailable.")
            
        current_propagation_report = "\n".join(report_parts)
        last_propagation_fetch = time.time()
        print("[PROPAGATION] Data fetched successfully.")
        
    except Exception as e:
        current_propagation_report = f"Error fetching propagation data: {e}"
        print(f"[PROPAGATION] Fetch failed: {e}")

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
    # Simplified header that adif_io should be happy with
    header = {"ADIF_VER": "3.1.0", "PROGRAMID": "Bridge ADIF Merger", "CREATED_TIMESTAMP": datetime.now().strftime("%Y%m%d %H%M%S")}
    for key, value in header.items():
        parts.append(f"<{key}:{len(str(value))}>{value}")
    parts.append("<EOH>")
    for qso in qso_list:
        # Avoid including header fields in the QSO records
        for key, value in qso.items():
            if key.upper() not in ["ADIF_VER", "PROGRAMID", "CREATED_TIMESTAMP"]:
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
                # read_from_file returns (qsos, header)
                qsos, _ = adif_io.read_from_file(file_path)
                if qsos:
                    all_qsos.extend(qsos)
            except Exception as e:
                print(f"[ADIF ENGINE] Error reading {file_path}: {e}")
    
    if not all_qsos:
        print("[ADIF ENGINE] No QSOs found in input files.")
        return

    # Deduplicate and sort
    deduped = deduplicate_qsos(all_qsos)
    # Sort by date and time descending
    deduped.sort(key=lambda q: (str(q.get('QSO_DATE', '00000000')), str(q.get('TIME_ON', '000000'))), reverse=True)
    
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

            # --- Propagation Data Fetching ---
            if CONFIG.get("fetch_propagation_data", True):
                now = time.time()
                if now - last_propagation_fetch > CONFIG.get("propagation_fetch_interval", 14400):
                    fetch_propagation_data()
                
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
    if CONFIG.get("fetch_propagation_data", True):
        return nocache(Response(current_propagation_report, mimetype='text/plain'))
    
    # Fallback to file if fetching is disabled
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

@app.route('/api/add_qso', methods=['POST'])
def add_qso():
    try:
        data = request.json
        call = data.get('call', '').upper()
        band = data.get('band', '')
        mode = data.get('mode', '')
        rst_s = data.get('rst_sent', '')
        rst_r = data.get('rst_rcvd', '')
        name = data.get('name', '')
        qth = data.get('qth', '')
        comment = data.get('comment', '')
        
        if not call:
            return jsonify({"status": "error", "message": "Callsign required"}), 400
            
        now = datetime.now(timezone.utc)
        date_str = now.strftime("%Y%m%d")
        time_str = now.strftime("%H%M%S")
        
        record = f"<CALL:{len(call)}>{call} <QSO_DATE:{len(date_str)}>{date_str} <TIME_ON:{len(time_str)}>{time_str} "
        if band: record += f"<BAND:{len(band)}>{band} "
        if mode: record += f"<MODE:{len(mode)}>{mode} "
        if rst_s: record += f"<RST_SENT:{len(rst_s)}>{rst_s} "
        if rst_r: record += f"<RST_RCVD:{len(rst_r)}>{rst_r} "
        if name: record += f"<NAME:{len(name)}>{name} "
        if qth: record += f"<QTH:{len(qth)}>{qth} "
        if comment: record += f"<COMMENT:{len(comment)}>{comment} "
        record += "<EOR>\n"
        
        target_file = CONFIG["manual_adif_file"]
        file_exists = os.path.exists(target_file)
        
        # Ensure directory exists
        os.makedirs(os.path.dirname(target_file), exist_ok=True)
        
        with open(target_file, 'a', encoding='utf-8') as f:
            if not file_exists or os.path.getsize(target_file) == 0:
                f.write("ADIF Export from Bridge\n<EOH>\n")
            f.write(record)
            
        print(f"[MANUAL LOG] Added QSO: {call} on {band}")
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

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
    print("--- LOG CONTROL CENTER by OH8XAT v1.2 ACTIVE ---")
    print("UI available at: http://localhost:5000")
    app.run(host='0.0.0.0', port=5000)
