# Log Control Center by OH8XAT v1.2

A real-time dual-source telemetry dashboard and ADIF log merger for Amateur Radio.  
Built for high-performance station monitoring and seamless log consolidation.

## 🚀 Key Features
- **ADIF Engine:** Automatically merges multiple input ADIF logs with robust deduplication.
- **Manual QSO Entry:** Full-screen tactical interface for manual log entry.
- **Windows Control GUI:** Integrated desktop control panel for the standalone EXE version.
- **Real-Time Tactical Maps:** Dual-deck visualization (Tactical A/B) with independent zoom controls.
- **Log Watcher:** Streams live updates from VarAC (or other raw log sources) in real-time.
- **Web Configurator:** Manage all file paths directly through the built-in "CONFIG" dashboard.
- **PSK Reporter Integration:** Live spot visualization with magenta tactical lines and adjustable time windows.
- **Persistence:** UI settings (Size, Audio, Zoom, PSK) are preserved across sessions.
- **Aesthetic:** High-contrast "Tactical Telemetry" CRT theme with sci-fi glow and audio alerts.

---

## 🕒 Changelog (v1.2)
- **NEW:** Windows Desktop Control GUI (for Launching Browser and Shutting down).
- **NEW:** Manual QSO Entry system with full-screen tactical modal.
- **NEW:** Tactical UI Persistence (settings save automatically to local storage).
- **NEW:** Individual ZOOM controls for Tactical A and Tactical B maps.
- **NEW:** Cycling PSK Reporter button (OFF / 15m / 30m / 1h).
- **ENHANCED:** "Smart Layout" - Maps stack vertically for East-West contacts (e.g., North America) to maximize width.
- **ENHANCED:** Set defaults to LARGE UI, Audio ON, and PSK 1H.
- **FIXED:** UI button synchronization and clock heartbeat issues.
- **FIXED:** ADIF engine robustness and manual log auto-injection.

---

## 🛠️ Installation & Setup (Step-by-Step)

### 🪟 Windows (Recommended for Windows Users)
**Download the standalone executable:**  
👉 [**Download LogControlCenterBridge_v1.2.exe**](https://github.com/zoolkhan/log-control-center/releases/download/v1.2/LogControlCenterBridge_v1.2.exe)

*No installation required. Just download, run the EXE, and it will handle everything.*

---

### 🐧 Linux (Recommended for Linux Users)

#### 1. Prerequisites
Ensure you have Python 3 and the `venv` module installed:
```bash
sudo apt update
sudo apt install python3 python3-venv
```

#### 2. Setup Environment
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

#### 3. Running the Application
```bash
python3 app.py
```
Open your browser and go to: **`http://localhost:5000`**

---

## ⚖️ License
GNU GPLv3. Author: OH8XAT (2026)
