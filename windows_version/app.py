import os
import sys
import json
import time
import requests
import threading
from flask import Flask, send_from_directory, jsonify, Response, request
from datetime import datetime, timezone
from pathlib import Path
import adif_io
import xml.etree.ElementTree as ET

# Handle paths when running as a compiled EXE (PyInstaller)
def get_base_path():
    if getattr(sys, 'frozen', False):
        return Path(sys._MEIPASS)
    return Path(__file__).parent

BASE_PATH = get_base_path()
app = Flask(__name__, static_folder=str(BASE_PATH))

# --- CONFIGURATION (Cross-platform with Pathlib) ---
CONFIG_FILE = "bridge_config.json"
HOME = Path.home()
DEFAULT_CONFIG = {
    "input_adif_files": [str(HOME / "merged.adi")],
    "output_adif_file": str(Path("data") / "merged_output.adi"),
    "manual_adif_file": str(Path("data") / "manual_log.adi"),
    "varac_log_file": str(HOME / "Documents" / "VarAC" / "VarAC.log"),
    "fetch_propagation_data": True,
    "propagation_fetch_interval": 14400, # 4 hours in seconds
    "update_interval": 5
}

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r') as f:
            try:
                config = json.load(f)
                for key in DEFAULT_CONFIG:
                    if key not in config:
                        config[key] = DEFAULT_CONFIG[key]
                
                # Auto-inject manual log into input files if not present
                if config["manual_adif_file"] not in config["input_adif_files"]:
                    config["input_adif_files"].append(config["manual_adif_file"])
                
                return config
            except:
                return DEFAULT_CONFIG
    
    conf = DEFAULT_CONFIG.copy()
    if conf["manual_adif_file"] not in conf["input_adif_files"]:
        conf["input_adif_files"].append(conf["manual_adif_file"])
    return conf

CONFIG = load_config()
Path(CONFIG["output_adif_file"]).parent.mkdir(parents=True, exist_ok=True)
Path(CONFIG["manual_adif_file"]).parent.mkdir(parents=True, exist_ok=True)

# Shared state for the UI
last_heartbeat_time = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
current_propagation_report = "[Propagation data not yet fetched]"
last_propagation_fetch = 0

# --- PROPAGATION FETCHING LOGIC ---
def fetch_propagation_data():
    global current_propagation_report
    global last_propagation_fetch
    url = "https://www.hamqsl.com/solarxml.php"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status() # Raise an exception for bad status codes
        
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
        
    except requests.exceptions.RequestException as e:
        current_propagation_report = f"Error fetching propagation data: {e}"
        print(f"[PROPAGATION] Fetch failed: {e}")
    except ET.ParseError as e:
        current_propagation_report = f"Error parsing propagation data: {e}"
        print(f"[PROPAGATION] Parse failed: {e}")
    except Exception as e:
        current_propagation_report = f"An unexpected error occurred: {e}"
        print(f"[PROPAGATION] Unexpected error: {e}")

# --- ADIF MERGING LOGIC ---
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
    header = {"ADIF_VER": "3.1.0", "PROGRAMID": "Log Control Center", "CREATED_TIMESTAMP": datetime.now().strftime("%Y%m%d %H%M%S")}
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
    print("[ADIF ENGINE] Merging logs...")
    all_qsos = []
    for f_path in CONFIG["input_adif_files"]:
        p = Path(f_path)
        if p.exists():
            try:
                # read_from_file returns (qsos, header)
                qsos, _ = adif_io.read_from_file(str(p))
                if qsos:
                    all_qsos.extend(qsos)
            except Exception as e:
                print(f"[ADIF ENGINE] Error reading {f_path}: {e}")
    
    if not all_qsos: return

    deduped = deduplicate_qsos(all_qsos)
    # Sort by date and time descending
    deduped.sort(key=lambda q: (str(q.get('QSO_DATE', '00000000')), str(q.get('TIME_ON', '000000'))), reverse=True)
    
    try:
        adif_string = generate_adif_string(deduped)
        with open(CONFIG["output_adif_file"], 'w', encoding='utf-8') as f:
            f.write(adif_string)
        print(f"[ADIF ENGINE] Merged {len(deduped)} unique QSOs.")
    except Exception as e:
        print(f"[ADIF ENGINE] Error saving: {e}")

# --- MONITOR THREAD ---
def monitor_tasks():
    last_mtimes = {}
    global last_heartbeat_time
    global current_propagation_report
    
    while True:
        try:
            # Update heartbeat for UI
            last_heartbeat_time = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
            
            # Check for config changes (reload if needed)
            global CONFIG
            current_config = load_config()
            if current_config != CONFIG:
                CONFIG = current_config
                print("[CONFIG] Settings reloaded.")
            
            # --- ADIF File Monitoring ---
            should_merge = False
            for f_path in CONFIG["input_adif_files"]:
                p = Path(f_path)
                if p.exists():
                    mtime = p.stat().st_mtime
                    if f_path not in last_mtimes or mtime > last_mtimes[f_path]:
                        last_mtimes[f_path] = mtime
                        should_merge = True
            if should_merge: merge_adif_files()
                
            # --- Propagation Data Fetching ---
            if CONFIG.get("fetch_propagation_data", False):
                try:
                    now = time.time()
                    if now - last_propagation_fetch > CONFIG.get("propagation_fetch_interval", 14400):
                        fetch_propagation_data()
                except Exception as e:
                    print(f"[PROPAGATION] Error in fetch routine: {e}")
                    current_propagation_report = f"Error during fetch: {e}"
            else:
                current_propagation_report = "Propagation fetching disabled."

        except Exception as e:
            print(f"[MONITOR] General thread error: {e}")
        
        time.sleep(CONFIG.get("update_interval", 5)) # Use default if not set

# Start the monitoring thread
threading.Thread(target=monitor_tasks, daemon=True).start()

# --- ROUTES ---
@app.route('/')
def index():
    return send_from_directory(str(BASE_PATH), 'index.html')

@app.route('/api/config', methods=['GET', 'POST'])
def api_config():
    global CONFIG
    if request.method == 'POST':
        try:
            new_config = request.json
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
    return jsonify({"last_seen": last_heartbeat_time})

@app.route('/data/propagation.txt')
def get_propagation():
    if not CONFIG.get("fetch_propagation_data", False):
        return "Propagation fetching disabled.", 200
    
    # Serve the fetched report from memory
    return Response(current_propagation_report, mimetype='text/plain', headers={"Cache-Control": "no-cache"})

@app.route('/data/source_a.adi')
def get_source_a():
    p = Path(CONFIG["output_adif_file"])
    if not p.exists(): return "NOT_FOUND", 404
    try:
        with open(p, 'r', encoding='utf-8', errors='ignore') as f:
            return Response(f.read(), mimetype='text/plain', headers={"Cache-Control": "no-cache"})
    except:
        return "ERROR", 500

@app.route('/data/source_b.log')
def get_source_b():
    p = Path(CONFIG["varac_log_file"])
    if not p.exists(): return "NOT_FOUND", 404
    try:
        with open(p, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
            return Response("".join(lines[-500:]), mimetype='text/plain', headers={"Cache-Control": "no-cache"})
    except:
        return "ERROR", 500

@app.route('/psk_proxy')
def psk_proxy():
    call = request.args.get('call', 'OH8XAT')
    seconds = request.args.get('seconds', '3600')
    url = f"https://pskreporter.info/query?senderCallsign={call}&flow=receptionReport&lastSeconds={seconds}"
    try:
        r = requests.get(url, timeout=10)
        return Response(r.text, mimetype='application/xml')
    except: return "ERROR", 500

@app.route('/<path:path>')
def static_files(path):
    return send_from_directory(str(BASE_PATH), path)

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
        
        target_file = Path(CONFIG["manual_adif_file"])
        file_exists = target_file.exists()
        target_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(target_file, 'a', encoding='utf-8') as f:
            if not file_exists or target_file.stat().st_size == 0:
                f.write("ADIF Export from Bridge\n<EOH>\n")
            f.write(record)
            
        print(f"[MANUAL LOG] Added QSO: {call} on {band}")
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == "__main__":
    print("--- LOG CONTROL CENTER by OH8XAT v1.2 Active ---")
    
    # If running as a frozen EXE (PyInstaller), launch a small control GUI
    if getattr(sys, 'frozen', False):
        import webbrowser
        import tkinter as tk
        from tkinter import messagebox

        def on_exit():
            if messagebox.askokcancel("Quit", "Shutdown Log Control Center?"):
                root.destroy()
                os._exit(0)

        def open_browser():
            webbrowser.open("http://localhost:5000")

        # Start Flask in a background thread
        threading.Thread(target=lambda: app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False), daemon=True).start()

        # Create Control Window
        root = tk.Tk()
        root.title("OH8XAT Bridge v1.2")
        root.geometry("300x150")
        root.configure(bg='#050a0a')
        root.protocol("WM_DELETE_WINDOW", on_exit)
        
        # Styling
        label = tk.Label(root, text="BRIDGE STATUS: ACTIVE", fg="#00f2ff", bg="#050a0a", font=("Courier", 10, "bold"))
        label.pack(pady=15)
        
        btn_open = tk.Button(root, text="LAUNCH BROWSER", command=open_browser, fg="#000", bg="#00f2ff", font=("Courier", 9, "bold"), width=20)
        btn_open.pack(pady=5)
        
        btn_exit = tk.Button(root, text="SHUTDOWN SERVER", command=on_exit, fg="#fff", bg="#ff3c00", font=("Courier", 9, "bold"), width=20)
        btn_exit.pack(pady=5)

        root.mainloop()
    else:
        # Normal CLI run
        app.run(host='0.0.0.0', port=5000)
