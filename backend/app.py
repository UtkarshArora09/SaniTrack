import sys
from pathlib import Path

# Ensure both project root and backend directory are in sys.path
BACKEND_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BACKEND_DIR.parent
for p in [str(PROJECT_ROOT), str(BACKEND_DIR)]:
    if p not in sys.path:
        sys.path.insert(0, p)

from flask import Flask, jsonify, make_response, redirect, render_template, request, send_from_directory, session

import config
from database import fetch_all, fetch_one, init_db
from services.cleanliness_service import CleanlinessService
from services.face_service import FaceRecognitionService
from services.notifier import notify_targets
from ai_engine.cctv_monitor import CCTVStreamMonitor
from core.scheduler import ShiftMonitoringDaemon

# Import Blueprints
from routes.auth_routes import auth_bp
from routes.ward_routes import ward_bp
from routes.inspection_routes import inspection_bp
from routes.attendance_routes import attendance_bp
from routes.worker_routes import worker_bp
from routes.iot_routes import iot_bp
from routes.report_routes import report_bp

app = Flask(__name__, template_folder='templates', static_folder='static')
app.config['SECRET_KEY'] = config.SECRET_KEY

# Ensure required runtime directories exist
for path in [config.DATA_DIR, config.UPLOADS_DIR, config.INSPECTIONS_DIR, config.FACE_DATASET_DIR]:
    path.mkdir(parents=True, exist_ok=True)

# Initialize Database Schema & Seed Data
init_db()

# Initialize AI & Background Services
face_service = FaceRecognitionService()
cleanliness_service = CleanlinessService()

# CCTV Background Stream Monitor
cctv_monitor = CCTVStreamMonitor(
    yolo_engine=cleanliness_service.engine,
    db_execute_fn=__import__('database').execute,
    notify_fn=notify_targets,
    uploads_dir=config.UPLOADS_DIR
)

# Automated Shift & Absence Monitoring Daemon
shift_daemon = ShiftMonitoringDaemon(
    notify_fn=notify_targets,
    check_interval_seconds=60,
    grace_period_minutes=config.SHIFT_GRACE_PERIOD_MINUTES
)
shift_daemon.start()

# Telegram Worker Auto-Linking & Interaction Daemon
from services.telegram_bot_service import TelegramBotDaemon
telegram_daemon = TelegramBotDaemon(interval_seconds=5)
telegram_daemon.start()

# Register Blueprints
app.register_blueprint(auth_bp)
app.register_blueprint(ward_bp)
app.register_blueprint(inspection_bp)
app.register_blueprint(attendance_bp)
app.register_blueprint(worker_bp)
app.register_blueprint(iot_bp)
app.register_blueprint(report_bp)


# Core Views & Health Checks
@app.get('/')
def index():
    return render_template('index.html')


@app.get('/manifest.json')
def app_manifest():
    emp_key = request.args.get('emp') or request.cookies.get('sanitrack_emp_key')
    worker = None
    if emp_key:
        worker = fetch_one('SELECT * FROM employees WHERE emp_key = ?', (emp_key,))
    
    start_url = f"/worker/{emp_key}" if (emp_key and worker) else "/worker"
    worker_name = worker.get('name') if worker else "Staff"

    manifest_data = {
        "name": f"SaniTrack Staff ({worker_name})" if worker else "SaniTrack Staff Portal",
        "short_name": "SaniTrack",
        "description": "Hospital Sanitation & Ward Cleaning Staff Mobile App",
        "start_url": start_url,
        "scope": "/",
        "display": "standalone",
        "orientation": "portrait",
        "background_color": "#f8fafc",
        "theme_color": "#0284c7",
        "icons": [
            {
                "src": "/static/icon-192.png",
                "sizes": "192x192",
                "type": "image/png",
                "purpose": "any maskable"
            },
            {
                "src": "/static/icon-512.png",
                "sizes": "512x512",
                "type": "image/png",
                "purpose": "any maskable"
            }
        ]
    }
    return jsonify(manifest_data)


@app.get('/worker')
@app.get('/worker/')
def worker_portal_redirect():
    # If already logged in, redirect directly to active worker dashboard
    if session.get('worker_emp_key'):
        worker = fetch_one('SELECT emp_key FROM employees WHERE emp_key = ?', (session['worker_emp_key'],))
        if worker:
            return redirect(f"/worker/{worker['emp_key']}")

    emp_key = request.args.get('emp') or request.cookies.get('sanitrack_emp_key')
    if emp_key:
        worker = fetch_one('SELECT emp_key FROM employees WHERE emp_key = ?', (emp_key,))
        if worker:
            return redirect(f"/worker/{worker['emp_key']}")
    
    first_worker = fetch_one('SELECT emp_key FROM employees ORDER BY id ASC LIMIT 1')
    if first_worker:
        return redirect(f"/worker/{first_worker['emp_key']}")
    
    return "No sanitation personnel registered yet. Please register staff in the Admin Portal.", 404


@app.get('/static')
@app.get('/static/')
def static_root_redirect():
    # If a user's previously installed PWA shortcut opens /static/ due to old start_url=".", redirect to /worker
    return redirect('/worker')


@app.get('/worker/<emp_key>')
def worker_view(emp_key):
    worker = fetch_one('SELECT * FROM employees WHERE emp_key = ?', (emp_key,))
    if not worker:
        return 'Worker not found', 404
    is_authed = bool(session.get('worker_emp_key') == emp_key)
    resp = make_response(render_template(
        'worker.html',
        emp_key=emp_key,
        worker_name=worker.get('name', emp_key),
        worker=worker,
        is_authenticated=is_authed
    ))
    resp.set_cookie('sanitrack_emp_key', emp_key, max_age=31536000, samesite='Lax', path='/')
    return resp


@app.get('/api/health')
def health():
    return jsonify({
        'status': 'ok',
        'service': 'SaniTrack Enterprise',
        'yolo_loaded': cleanliness_service.engine._model is not None,
        'scheduler_active': shift_daemon.running
    })


@app.get('/api/config/notifications')
def notification_mode():
    return jsonify(config.notification_config())


@app.get('/api/history')
def history():
    inspections = fetch_all('SELECT * FROM inspection_logs ORDER BY created_at DESC LIMIT 20')
    attendance = fetch_all('SELECT * FROM attendance_logs ORDER BY created_at DESC LIMIT 20')
    notifications = fetch_all('SELECT * FROM notifications ORDER BY created_at DESC LIMIT 20')
    confirmations = fetch_all('SELECT * FROM task_confirmations ORDER BY created_at DESC LIMIT 20')
    return jsonify({
        'inspections': inspections,
        'attendance': attendance,
        'notifications': notifications,
        'confirmations': confirmations
    })


@app.get('/api/overview')
def overview():
    total_wards = fetch_one('SELECT COUNT(*) AS count FROM wards')['count']
    total_employees = fetch_one('SELECT COUNT(*) AS count FROM employees')['count']
    dirty_wards = fetch_one("SELECT COUNT(*) AS count FROM inspection_logs WHERE COALESCE(overridden_status, status) = 'Not Clean'")['count']
    clean_wards = fetch_one("SELECT COUNT(*) AS count FROM inspection_logs WHERE COALESCE(overridden_status, status) = 'Clean'")['count']
    attendance_mismatches = fetch_one('SELECT COUNT(*) AS count FROM attendance_logs WHERE assigned_match = 0')['count']
    overrides = fetch_one('SELECT COUNT(*) AS count FROM inspection_logs WHERE overridden_status IS NOT NULL')['count']
    return jsonify({
        'total_wards': total_wards,
        'total_employees': total_employees,
        'clean_inspections': clean_wards,
        'not_clean_inspections': dirty_wards,
        'attendance_mismatches': attendance_mismatches,
        'overrides': overrides
    })


@app.get('/inspections/<path:filename>')
def inspection_file(filename):
    return send_from_directory(config.INSPECTIONS_DIR, filename)


@app.get('/uploads/<path:filename>')
def upload_file(filename):
    return send_from_directory(config.UPLOADS_DIR, filename)


def find_available_port(preferred_port, host='0.0.0.0'):
    import socket
    for p in range(preferred_port, preferred_port + 50):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind((host, p))
                return p
            except OSError:
                continue
    return preferred_port


if __name__ == '__main__':
    port = config.APP_PORT
    if len(sys.argv) > 1:
        for i, arg in enumerate(sys.argv[1:]):
            if arg in ('--port', '-p') and i + 1 < len(sys.argv) - 1:
                try:
                    port = int(sys.argv[i + 2])
                except ValueError:
                    pass
            elif arg.isdigit():
                port = int(arg)

    actual_port = find_available_port(port, config.APP_HOST)
    if actual_port != port:
        print(f"\n⚠️ Port {port} was already busy. Automatically redirected to open port {actual_port}.")

    print("\n" + "=" * 65)
    print("🏥 SaniTrack Healthcare System is Online & Ready!")
    print(f"👉 Open in browser:  http://127.0.0.1:{actual_port}")
    print(f"👉 Local Network:    http://{config.APP_HOST}:{actual_port}")
    print("=" * 65 + "\n")

    app.run(debug=config.APP_DEBUG, host=config.APP_HOST, port=actual_port)
