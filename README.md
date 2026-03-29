# Log Control Center by OH8XAT v1.0

A real-time dual-source telemetry dashboard and ADIF log merger for Amateur Radio.  
Built for high-performance station monitoring and seamless log consolidation.

## 🚀 Key Features
- **ADIF Engine:** Automatically merges up to 10 input ADIF logs with robust deduplication.
- **Real-Time Tactical Map:** Visualizes contacts dynamically on an offline-capable HTML5 Canvas map.
- **Log Watcher:** Streams live updates from VarAC (or other raw log sources) in real-time.
- **Web Configurator:** Manage all file paths directly through the built-in "CONFIG" dashboard.
- **Aesthetic:** High-contrast "Tactical Telemetry" CRT theme with optional audio alerts.

---

## 🛠️ Installation & Setup (Step-by-Step)

### 1. Prerequisites
Ensure you have Python 3 and the `venv` module installed:
```bash
sudo apt update
sudo apt install python3 python3-venv
```

### 2. Download and Environment Setup
Clone the repository (or copy the files) and set up the virtual environment:
```bash
cd ~/bridge
python3 -m venv venv
```

### 3. Install Dependencies
Activate the environment and install required libraries:
```bash
source venv/bin/activate
pip install -r requirements.txt
```

### 4. Running the Application
Start the server:
```bash
python3 app.py
```
Open your browser and go to: **`http://localhost:5000`**

---

## ⚙️ Configuration
The first time you run the app, click the red **CONFIG** button in the header.  
From there, you can define:
1. **ADIF Input Files:** Paths to your various logger output files (one per line).
2. **VarAC Log Path:** The path to your `VarAC.log` file for the live feed (Deck B).
3. **Output Merged ADIF:** Where you want the consolidated, deduplicated log to be saved.

The background engine monitors these files every 5 seconds and updates the dashboard automatically when changes are detected.

---

## ⚖️ License
This project is licensed under the **GNU General Public License v3.0**.  
See the [LICENSE](LICENSE) file for more details.

**Author:** OH8XAT (2026)
