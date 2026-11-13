# SaniTrack Enterprise — Production Architecture & Usage Guide

AI-Powered Ward-Sanitation Verification, Facial Attendance, and IoT Hygiene Telemetry System.

---

## 🏗️ Production System Architecture

The codebase has been refactored into an enterprise-grade modular architecture:

```
D:\SANITRACK FINAL\
├── ai_engine/                         # AI & Computer Vision Service
│   ├── yolo_service.py                # Non-blocking YOLOv8 engine (ThreadPoolExecutor)
│   ├── face_engine.py                 # Haar Cascade + KNN face recognition & LOO diagnostics
│   └── cctv_monitor.py                # Automated 24/7 background CCTV feed polling worker
│
├── backend/                           # Backend Web & API Service
│   ├── core/
│   │   ├── config.py                  # Centralized configuration & environment loader
│   │   ├── security.py                # RBAC (Admin, Supervisor, Worker) & password hashing
│   │   └── scheduler.py               # Automated shift & absence daemon
│   ├── database.py                    # Thread-safe SQLite relational layer & migrations
│   ├── services/
│   │   ├── cleanliness_service.py     # Cleanliness evaluation facade
│   │   ├── face_service.py            # Biometric attendance facade
│   │   ├── notifier.py                # Twilio WhatsApp + real-time broadcast bus
│   │   ├── iot_service.py             # Smart dustbin, bed proximity, & UV stain telemetry
│   │   └── report_service.py          # Hospital hygiene compliance & CSV audit generator
│   ├── routes/
│   │   ├── auth_routes.py             # Login, logout, role profiles
│   │   ├── ward_routes.py             # Ward CRUD, assignments, shift schedules, auto-CCTV
│   │   ├── inspection_routes.py       # Asynchronous floor inspection & polling
│   │   ├── attendance_routes.py       # Facial recognition verification
│   │   ├── worker_routes.py           # Worker mobile portal & task confirmations
│   │   ├── iot_routes.py              # IoT telemetry ingest & simulation triggers
│   │   └── report_routes.py           # Hospital compliance scorecards & CSV downloads
│   ├── static/                        # Frontend assets (styles.css, app.js, worker.js)
│   ├── templates/                     # Jinja2 views (index.html, worker.html)
│   ├── app.py                         # Application factory & route registration
│   └── wsgi.py                        # Production WSGI entrypoint
│
├── scripts/                           # Offline Automation & Viva Demo Utilities
│   ├── enroll_face.py                 # Webcam biometric staff registration
│   ├── face_dataset_report.py         # Cross-validation accuracy diagnostics
│   ├── simulate_cctv.py               # Continuous CCTV feed simulation script
│   └── simulate_iot.py                # Live IoT telemetry simulator (Gauges demo)
│
├── docker-compose.yml                 # Multi-container production stack orchestration
├── Dockerfile                         # Production container definition
└── requirements.txt                   # Pinned production dependencies
```

---

## 🚀 How to Run the Project

### 1. Launch Backend Server
Activate your virtual environment and start the server:

```powershell
cd "D:\SANITRACK FINAL"
.venv\Scripts\activate
python backend\app.py
```
Or with Gunicorn:
```powershell
gunicorn wsgi:app --workers 2 --worker-class gthread --threads 4 --bind 0.0.0.0:5050
```
Open **`http://127.0.0.1:5050`** in your browser.

---

## 🎯 Key Features Implemented

### 1. Non-Blocking Asynchronous Floor Inspection
* Floor images submitted to `/api/inspection/analyze` return **`HTTP 202 Accepted` immediately** in under 20ms.
* A background `ThreadPoolExecutor` runs YOLOv8 forward-pass without freezing the web server.
* The frontend polls `/api/inspection/<id>/status` with a live spinner and renders annotated bounding boxes when finished.

### 2. Automated CCTV Feed Ingestion Daemon
* Background worker in `ai_engine/cctv_monitor.py` polls camera feeds every 15 seconds.
* Evaluates ward floor cleanliness continuously and updates the database without manual human clicking.
* Toggle auto-monitoring for any ward directly from the dashboard.

### 3. Automated Shift & Absence Monitoring Daemon
* Background scheduler in `backend/core/scheduler.py` runs every 60 seconds.
* Compares shift hours against `attendance_logs`.
* If a cleaner does not check in within the 15-minute grace period, an automated absence alert is dispatched.

### 4. Hospital IoT Sensor Network & Simulation
* Real-time tracking of:
  * **Smart Dustbin Fill Level**: Triggers automated alarm when capacity $\ge 80\%$.
  * **Near-Bed Proximity Sensor**: Tracks staff cleaning motion duration ($> 30\text{s}$ marks bed sanitized).
  * **Blue-Light / UV Micro-Contamination**: Detects non-visible biological residue scores.
* **Viva Demo**: Click any button under the **IoT Telemetry** tab to trigger live telemetry packets!

### 5. Hospital Accreditation Compliance & CSV Audit Export
* Computes real-time hygiene compliance rates ($\%$ clean audits) and attendance verification rates.
* Generates a downloadable **Official Audit CSV** (`/api/reports/audit.csv`) for NABH/JCI hospital audits.

### 6. Role-Based Access Control (RBAC)
* Integrated user roles: `admin` (System Administrator), `supervisor` (Floor In-Charge), `worker` (Sanitation Staff).

---

## 🧪 Demonstration Scripts for Viva

While the server is running, open a separate terminal to run these demonstration scripts:

### Test Automated CCTV Ingestion
```powershell
python scripts\simulate_cctv.py
```

### Test IoT Hardware Sensor Simulation
```powershell
python scripts\simulate_iot.py
```

### Check Face Recognition Leave-One-Out Accuracy
```powershell
python scripts\face_dataset_report.py
```
