#!/usr/bin/env python3
import os
import time
import subprocess
import sys
import json
from datetime import datetime, timezone

# --- CONFIGURATION ---
SOURCES = [
    {
        "name": "DECK A (ADIF)",
        "local": os.path.expanduser("~/merged.adi"),
        "remote": "silvan.eu.com:~/public_html/data/source_a.adi",
        "type": "file"
    },
    {
        "name": "DECK B (LOG)",
        "local": os.path.expanduser("~/.wine/drive_c/VarAC/VarAC.log"),
        "remote": "silvan.eu.com:~/public_html/data/source_b.log",
        "type": "tail",
        "lines": 500
    },
    {
        "name": "PROPAGATION",
        "local": os.path.expanduser("~/.wine/drive_c/VarAC/BBS/B_radio_propagation_report_today.txt"),
        "remote": "silvan.eu.com:~/public_html/data/propagation.txt",
        "type": "file"
    },
    {
        "name": "HEARTBEAT",
        "local": "/tmp/bridge_heartbeat.json",
        "remote": "silvan.eu.com:~/public_html/data/heartbeat.json",
        "type": "file"
    }
]

POLL_INTERVAL = 5
HEARTBEAT_INTERVAL = 60

def push_file(local_path, remote_path, type="file", lines=100):
    print(f"[TACTICAL LINK] PUSHING {type.upper()}: {os.path.basename(local_path)} -> {remote_path}")
    try:
        if type == "tail":
            temp_file = "/tmp/bridge_tail.tmp"
            with open(temp_file, "w") as f:
                subprocess.run(["tail", "-n", str(lines), local_path], stdout=f, check=True)
            subprocess.run(["scp", "-q", temp_file, remote_path], check=True)
        else:
            subprocess.run(["scp", "-q", local_path, remote_path], check=True)
        return True
    except Exception as e:
        print(f"[LINK FAILURE] ERROR: {e}")
        return False

def main():
    print("=== SS SILVAN BRIDGE DATALINK ACTIVE ===")
    last_mtimes = {s["local"]: 0 for s in SOURCES}
    last_heartbeat = 0
    
    while True:
        # Update heartbeat file
        now = time.time()
        if now - last_heartbeat >= HEARTBEAT_INTERVAL:
            with open("/tmp/bridge_heartbeat.json", "w") as f:
                json.dump({"last_seen": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")}, f)
            last_heartbeat = now

        for source in SOURCES:
            local_path = source["local"]
            if not os.path.exists(local_path): continue
            mtime = os.path.getmtime(local_path)
            if mtime > last_mtimes[local_path]:
                if push_file(local_path, source["remote"], source.get("type"), source.get("lines", 100)):
                    last_mtimes[local_path] = mtime
        time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    main()
