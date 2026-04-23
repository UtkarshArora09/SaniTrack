import json
from pathlib import Path
from uuid import uuid4

from flask import Flask, jsonify, render_template, request, send_from_directory
from werkzeug.utils import secure_filename

import config
from database import execute, fetch_all, fetch_one, init_db, utc_now_iso
from services.cleanliness_service import CleanlinessService
from services.face_service import FaceRecognitionService
from services.notifier import notify_targets, record_notification

ALLOWED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp'}

app = Flask(__name__, template_folder='templates', static_folder='static')
app.config['SECRET_KEY'] = config.SECRET_KEY

for path in [config.DATA_DIR, config.UPLOADS_DIR, config.INSPECTIONS_DIR, config.FACE_DATASET_DIR]:
    path.mkdir(parents=True, exist_ok=True)

init_db()
face_service = FaceRecognitionService()
cleanliness_service = CleanlinessService()


def allowed_file(filename):
    return Path(filename).suffix.lower() in ALLOWED_EXTENSIONS


def save_upload(file_storage, folder):
    filename = secure_filename(file_storage.filename or f'upload_{uuid4().hex}.jpg')
    extension = Path(filename).suffix.lower() or '.jpg'
    saved_name = f'{uuid4().hex}{extension}'
    output_path = folder / saved_name
    file_storage.save(output_path)
    return output_path


def employee_phone_for(emp_key):
    if not emp_key:
        return None
    row = fetch_one('SELECT phone FROM employees WHERE emp_key = ?', (emp_key,))
    return row.get('phone') if row else None


@app.get('/')
def index():
    return render_template('index.html')


@app.get('/api/health')
def health():
    return jsonify({'status': 'ok'})


@app.get('/api/config/notifications')
def notification_mode():
    return jsonify(config.notification_config())


@app.get('/api/face/quality')
def face_quality():
    return jsonify({'report': face_service.quality_report()})


@app.get('/api/employees')
def get_employees():
    employees = fetch_all('SELECT * FROM employees ORDER BY created_at DESC')
    return jsonify({'employees': employees})


@app.post('/api/employees')
def create_employee():
    data = request.get_json(force=True)
    emp_key = (data.get('emp_key') or '').strip().lower()
    name = (data.get('name') or '').strip()
    designation = (data.get('designation') or '').strip()
    phone = (data.get('phone') or '').strip() or None
    if not emp_key or not name:
        return jsonify({'error': 'emp_key and name are required'}), 400

    execute('INSERT OR IGNORE INTO employees (emp_key, name, designation, phone, created_at) VALUES (?, ?, ?, ?, ?)', (emp_key, name, designation, phone, utc_now_iso()))
    metadata = {}
    if config.EMPLOYEES_JSON.exists():
        metadata = json.loads(config.EMPLOYEES_JSON.read_text(encoding='utf-8'))
    metadata[emp_key] = {'name': name, 'designation': designation, 'phone': phone}
    config.EMPLOYEES_JSON.write_text(json.dumps(metadata, indent=2), encoding='utf-8')
    face_service.reload()
    return jsonify({'status': 'created'})


@app.get('/api/wards')
def get_wards():
    wards = fetch_all("SELECT w.*, (SELECT status FROM inspection_logs i WHERE i.ward_name = w.name ORDER BY i.created_at DESC LIMIT 1) AS latest_status, (SELECT created_at FROM inspection_logs i WHERE i.ward_name = w.name ORDER BY i.created_at DESC LIMIT 1) AS latest_inspection_at, (SELECT object_count FROM inspection_logs i WHERE i.ward_name = w.name ORDER BY i.created_at DESC LIMIT 1) AS latest_object_count FROM wards w ORDER BY w.name")
    return jsonify({'wards': wards})


@app.post('/api/wards')
def create_ward():
    data = request.get_json(force=True)
    name = (data.get('name') or '').strip()
    location = (data.get('location') or '').strip() or name
    assigned_employee_key = (data.get('assigned_employee_key') or '').strip().lower() or None
    if not name:
        return jsonify({'error': 'Ward name is required'}), 400
    execute('INSERT OR IGNORE INTO wards (name, location, assigned_employee_key, created_at) VALUES (?, ?, ?, ?)', (name, location, assigned_employee_key, utc_now_iso()))
    return jsonify({'status': 'created'})


@app.post('/api/attendance/recognize')
def recognize_attendance():
    if 'image' not in request.files:
        return jsonify({'error': 'Image file is required'}), 400
    ward_name = (request.form.get('ward_name') or '').strip()
    if not ward_name:
        return jsonify({'error': 'ward_name is required'}), 400

    upload = request.files['image']
    if not allowed_file(upload.filename):
        return jsonify({'error': 'Unsupported image format'}), 400

    saved_path = save_upload(upload, config.UPLOADS_DIR)
    result = face_service.recognize(saved_path)
    if result.get('matched'):
        execute('INSERT INTO attendance_logs (employee_key, ward_name, confidence, source_image, created_at) VALUES (?, ?, ?, ?, ?)', (result['employee_key'], ward_name, result.get('confidence'), str(saved_path), utc_now_iso()))
        message = f"Attendance verified for {result['name']} in {ward_name}."
        record_notification(ward_name, message, delivery_status='logged')
        result['message'] = message
    return jsonify(result)


@app.post('/api/inspection/analyze')
def analyze_inspection():
    if 'image' not in request.files:
        return jsonify({'error': 'Image file is required'}), 400
    ward_name = (request.form.get('ward_name') or '').strip()
    employee_key = (request.form.get('employee_key') or '').strip().lower() or None
    notes = (request.form.get('notes') or '').strip() or None
    if not ward_name:
        return jsonify({'error': 'ward_name is required'}), 400

    upload = request.files['image']
    if not allowed_file(upload.filename):
        return jsonify({'error': 'Unsupported image format'}), 400

    saved_path = save_upload(upload, config.UPLOADS_DIR)
    inspection_id = execute('INSERT INTO inspection_logs (ward_name, employee_key, status, object_found, confidence, object_count, raw_label, source_image, annotated_image, notes, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)', (ward_name, employee_key, 'Pending', 0, None, 0, None, str(saved_path), None, notes, utc_now_iso()))
    analysis = cleanliness_service.analyze(saved_path, inspection_id=inspection_id)
    execute('UPDATE inspection_logs SET status = ?, object_found = ?, confidence = ?, object_count = ?, raw_label = ?, annotated_image = ?, notes = ? WHERE id = ?', (analysis['status'], 1 if analysis['object_found'] else 0, analysis['confidence'], analysis['object_count'], analysis['raw_label'], analysis['annotated_image'], notes, inspection_id))

    if analysis['object_found']:
        message = f"{ward_name} marked Not Clean. Waste detected on floor."
        notification_results = notify_targets(ward_name, message, employee_phone=employee_phone_for(employee_key))
    else:
        message = f"{ward_name} marked Clean after inspection."
        notification_results = [record_notification(ward_name, message, delivery_status='verified')]

    return jsonify({'inspection_id': inspection_id, **analysis, 'source_image': str(saved_path), 'notifications': notification_results})


@app.get('/api/history')
def history():
    inspections = fetch_all('SELECT * FROM inspection_logs ORDER BY created_at DESC LIMIT 20')
    attendance = fetch_all('SELECT * FROM attendance_logs ORDER BY created_at DESC LIMIT 20')
    notifications = fetch_all('SELECT * FROM notifications ORDER BY created_at DESC LIMIT 20')
    return jsonify({'inspections': inspections, 'attendance': attendance, 'notifications': notifications})


@app.get('/api/overview')
def overview():
    total_wards = fetch_one('SELECT COUNT(*) AS count FROM wards')['count']
    total_employees = fetch_one('SELECT COUNT(*) AS count FROM employees')['count']
    dirty_wards = fetch_one("SELECT COUNT(*) AS count FROM inspection_logs WHERE status = 'Not Clean'")['count']
    clean_wards = fetch_one("SELECT COUNT(*) AS count FROM inspection_logs WHERE status = 'Clean'")['count']
    return jsonify({'total_wards': total_wards, 'total_employees': total_employees, 'clean_inspections': clean_wards, 'not_clean_inspections': dirty_wards})


@app.get('/inspections/<path:filename>')
def inspection_file(filename):
    return send_from_directory(config.INSPECTIONS_DIR, filename)


@app.get('/uploads/<path:filename>')
def upload_file(filename):
    return send_from_directory(config.UPLOADS_DIR, filename)


if __name__ == '__main__':
    app.run(debug=True, host='127.0.0.1', port=5000)
