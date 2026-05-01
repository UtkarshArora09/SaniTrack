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


def employee_row(emp_key):
    if not emp_key:
        return None
    return fetch_one('SELECT * FROM employees WHERE emp_key = ?', (emp_key,))


def employee_phone_for(emp_key):
    row = employee_row(emp_key)
    return row.get('phone') if row else None


def ward_row_by_name(ward_name):
    return fetch_one('SELECT * FROM wards WHERE name = ?', (ward_name,))


def ward_response_rows():
    return fetch_all(
        """
        SELECT w.id,
               w.name,
               w.location,
               w.assigned_employee_key,
               e.name AS assigned_employee_name,
               e.designation AS assigned_employee_designation,
               i.id AS latest_inspection_id,
               COALESCE(i.overridden_status, i.status) AS latest_status,
               i.status AS model_status,
               i.overridden_status,
               i.override_reason,
               i.overridden_by,
               i.overridden_at,
               i.created_at AS latest_inspection_at,
               i.object_count AS latest_object_count,
               i.confidence AS latest_confidence,
               i.annotated_image AS latest_annotated_image,
               a.employee_key AS latest_attendance_employee_key,
               a.assigned_match AS latest_attendance_match,
               a.created_at AS latest_attendance_at
        FROM wards w
        LEFT JOIN employees e ON e.emp_key = w.assigned_employee_key
        LEFT JOIN inspection_logs i ON i.id = (
            SELECT ii.id FROM inspection_logs ii WHERE ii.ward_name = w.name ORDER BY ii.created_at DESC LIMIT 1
        )
        LEFT JOIN attendance_logs a ON a.id = (
            SELECT aa.id FROM attendance_logs aa WHERE aa.ward_name = w.name ORDER BY aa.created_at DESC LIMIT 1
        )
        ORDER BY w.name
        """
    )


@app.get('/')
def index():
    return render_template('index.html')


@app.get('/worker/<emp_key>')
def worker_view(emp_key):
    worker = employee_row(emp_key)
    if not worker:
        return 'Worker not found', 404
    return render_template('worker.html', emp_key=emp_key, worker_name=worker.get('name', emp_key))


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


@app.get('/api/workers')
def get_workers():
    workers = fetch_all(
        """
        SELECT e.emp_key, e.name, e.designation, e.phone,
               COUNT(w.id) AS assigned_ward_count,
               MAX(a.created_at) AS last_attendance_at,
               MAX(t.created_at) AS last_confirmation_at
        FROM employees e
        LEFT JOIN wards w ON w.assigned_employee_key = e.emp_key
        LEFT JOIN attendance_logs a ON a.employee_key = e.emp_key
        LEFT JOIN task_confirmations t ON t.employee_key = e.emp_key
        GROUP BY e.emp_key, e.name, e.designation, e.phone
        ORDER BY e.name
        """
    )
    return jsonify({'workers': workers})


@app.get('/api/workers/<emp_key>/dashboard')
def worker_dashboard(emp_key):
    worker = employee_row(emp_key)
    if not worker:
        return jsonify({'error': 'Worker not found'}), 404

    assigned_wards = fetch_all(
        """
        SELECT w.id, w.name, w.location,
               COALESCE(i.overridden_status, i.status) AS latest_status,
               i.created_at AS latest_inspection_at,
               i.object_count AS latest_object_count,
               i.override_reason,
               a.created_at AS latest_attendance_at,
               a.assigned_match AS latest_attendance_match,
               t.created_at AS last_confirmation_at,
               t.notes AS last_confirmation_notes
        FROM wards w
        LEFT JOIN inspection_logs i ON i.id = (
            SELECT ii.id FROM inspection_logs ii WHERE ii.ward_name = w.name ORDER BY ii.created_at DESC LIMIT 1
        )
        LEFT JOIN attendance_logs a ON a.id = (
            SELECT aa.id FROM attendance_logs aa WHERE aa.ward_name = w.name AND aa.employee_key = ? ORDER BY aa.created_at DESC LIMIT 1
        )
        LEFT JOIN task_confirmations t ON t.id = (
            SELECT tt.id FROM task_confirmations tt WHERE tt.ward_name = w.name AND tt.employee_key = ? ORDER BY tt.created_at DESC LIMIT 1
        )
        WHERE w.assigned_employee_key = ?
        ORDER BY w.name
        """,
        (emp_key, emp_key, emp_key),
    )
    notifications = fetch_all(
        'SELECT * FROM notifications WHERE ward_name IN (SELECT name FROM wards WHERE assigned_employee_key = ?) ORDER BY created_at DESC LIMIT 12',
        (emp_key,),
    )
    return jsonify({'worker': worker, 'assigned_wards': assigned_wards, 'notifications': notifications})


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
    existing = metadata.get(emp_key, {})
    metadata[emp_key] = {'name': name, 'designation': designation, 'phone': phone or existing.get('phone')}
    config.EMPLOYEES_JSON.write_text(json.dumps(metadata, indent=2), encoding='utf-8')
    face_service.reload()
    return jsonify({'status': 'created'})


@app.get('/api/wards')
def get_wards():
    return jsonify({'wards': ward_response_rows()})


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


@app.post('/api/wards/<int:ward_id>/assign')
def assign_ward(ward_id):
    data = request.get_json(force=True)
    employee_key = (data.get('employee_key') or '').strip().lower() or None
    admin_name = (data.get('admin_name') or 'Admin').strip()
    ward = fetch_one('SELECT * FROM wards WHERE id = ?', (ward_id,))
    if not ward:
        return jsonify({'error': 'Ward not found'}), 404
    if employee_key and not employee_row(employee_key):
        return jsonify({'error': 'Employee not found'}), 404

    previous_assignee = ward.get('assigned_employee_key')
    execute('UPDATE wards SET assigned_employee_key = ? WHERE id = ?', (employee_key, ward_id))
    if employee_key:
        employee = employee_row(employee_key)
        if previous_assignee and previous_assignee != employee_key:
            previous_employee = employee_row(previous_assignee)
            previous_name = previous_employee['name'] if previous_employee else previous_assignee
            message = f"{ward['name']} reassigned from {previous_name} to {employee['name']} by {admin_name}."
        else:
            message = f"{ward['name']} assigned to {employee['name']} by {admin_name}."
        notifications = notify_targets(ward['name'], message, employee_phone=employee.get('phone'))
    else:
        message = f"{ward['name']} assignment cleared by {admin_name}."
        notifications = [record_notification(ward['name'], message, channel='assignment', delivery_status='logged')]
    record_notification(ward['name'], message, channel='assignment', delivery_status='logged')
    return jsonify({'status': 'updated', 'ward': fetch_one('SELECT * FROM wards WHERE id = ?', (ward_id,)), 'notifications': notifications})


@app.post('/api/wards/<int:ward_id>/alert-absence')
def alert_absence(ward_id):
    data = request.get_json(force=True) if request.data else {}
    ward = fetch_one('SELECT * FROM wards WHERE id = ?', (ward_id,))
    if not ward:
        return jsonify({'error': 'Ward not found'}), 404
    employee = employee_row(ward.get('assigned_employee_key'))
    if not employee:
        return jsonify({'error': 'No assigned worker for this ward'}), 400

    reason = (data.get('reason') or 'Assigned worker absent during scheduled cleaning window.').strip()
    message = f"{ward['name']}: {reason}"
    notifications = notify_targets(ward['name'], message, employee_phone=employee.get('phone'))
    return jsonify({'status': 'sent', 'notifications': notifications})


@app.post('/api/tasks/confirm')
def confirm_task():
    data = request.get_json(force=True)
    ward_name = (data.get('ward_name') or '').strip()
    employee_key = (data.get('employee_key') or '').strip().lower()
    notes = (data.get('notes') or 'Cleaning completed and ready for inspection.').strip()
    if not ward_name or not employee_key:
        return jsonify({'error': 'ward_name and employee_key are required'}), 400
    ward = ward_row_by_name(ward_name)
    if not ward:
        return jsonify({'error': 'Ward not found'}), 404
    execute('INSERT INTO task_confirmations (ward_name, employee_key, notes, created_at) VALUES (?, ?, ?, ?)', (ward_name, employee_key, notes, utc_now_iso()))
    record_notification(ward_name, f'{employee_key} marked task complete: {notes}', channel='worker-confirmation', delivery_status='logged')
    return jsonify({'status': 'confirmed'})


@app.post('/api/inspection/<int:inspection_id>/override')
def override_inspection(inspection_id):
    data = request.get_json(force=True)
    override_status = (data.get('status') or '').strip()
    override_reason = (data.get('reason') or '').strip()
    overridden_by = (data.get('admin_name') or 'Admin').strip()
    if override_status not in {'Clean', 'Not Clean'}:
        return jsonify({'error': 'status must be Clean or Not Clean'}), 400
    inspection = fetch_one('SELECT * FROM inspection_logs WHERE id = ?', (inspection_id,))
    if not inspection:
        return jsonify({'error': 'Inspection not found'}), 404
    execute(
        'UPDATE inspection_logs SET overridden_status = ?, overridden_by = ?, override_reason = ?, overridden_at = ? WHERE id = ?',
        (override_status, overridden_by, override_reason or None, utc_now_iso(), inspection_id),
    )
    message = f"{inspection['ward_name']} override set to {override_status} by {overridden_by}."
    if override_reason:
        message += f' Reason: {override_reason}'
    record_notification(inspection['ward_name'], message, channel='override', delivery_status='logged')
    return jsonify({'status': 'overridden'})


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
    if not result.get('matched'):
        return jsonify(result)

    ward = ward_row_by_name(ward_name)
    assigned_key = (ward or {}).get('assigned_employee_key') if ward else None
    assigned_match = 1 if not assigned_key or assigned_key == result['employee_key'] else 0
    execute(
        'INSERT INTO attendance_logs (employee_key, ward_name, confidence, source_image, assigned_match, created_at) VALUES (?, ?, ?, ?, ?, ?)',
        (result['employee_key'], ward_name, result.get('confidence'), str(saved_path), assigned_match, utc_now_iso()),
    )

    if assigned_match:
        message = f"Attendance verified for {result['name']} in {ward_name}."
        record_notification(ward_name, message, channel='attendance', delivery_status='logged')
        result['attendance_verified'] = True
        result['message'] = message
    else:
        assigned_employee = employee_row(assigned_key)
        expected_name = assigned_employee['name'] if assigned_employee else assigned_key
        message = f"Attendance mismatch in {ward_name}. Expected {expected_name}, detected {result['name']}."
        notifications = notify_targets(ward_name, message, employee_phone=employee_phone_for(assigned_key))
        result['attendance_verified'] = False
        result['assigned_worker'] = expected_name
        result['message'] = message
        result['notifications'] = notifications
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

    ward = ward_row_by_name(ward_name)
    assigned_key = (ward or {}).get('assigned_employee_key') if ward else None
    effective_employee_key = employee_key or assigned_key
    saved_path = save_upload(upload, config.UPLOADS_DIR)
    inspection_id = execute(
        'INSERT INTO inspection_logs (ward_name, employee_key, status, object_found, confidence, object_count, raw_label, source_image, annotated_image, notes, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
        (ward_name, effective_employee_key, 'Pending', 0, None, 0, None, str(saved_path), None, notes, utc_now_iso()),
    )
    analysis = cleanliness_service.analyze(saved_path, inspection_id=inspection_id)
    execute(
        'UPDATE inspection_logs SET status = ?, object_found = ?, confidence = ?, object_count = ?, raw_label = ?, annotated_image = ?, notes = ? WHERE id = ?',
        (analysis['status'], 1 if analysis['object_found'] else 0, analysis['confidence'], analysis['object_count'], analysis['raw_label'], analysis['annotated_image'], notes, inspection_id),
    )

    if analysis['object_found']:
        message = f"{ward_name} marked Not Clean. Waste detected on floor."
        notification_results = notify_targets(ward_name, message, employee_phone=employee_phone_for(effective_employee_key))
    else:
        message = f"{ward_name} marked Clean after inspection."
        notification_results = [record_notification(ward_name, message, channel='inspection', delivery_status='verified')]

    return jsonify({'inspection_id': inspection_id, **analysis, 'source_image': str(saved_path), 'notifications': notification_results})


@app.get('/api/history')
def history():
    inspections = fetch_all('SELECT * FROM inspection_logs ORDER BY created_at DESC LIMIT 20')
    attendance = fetch_all('SELECT * FROM attendance_logs ORDER BY created_at DESC LIMIT 20')
    notifications = fetch_all('SELECT * FROM notifications ORDER BY created_at DESC LIMIT 20')
    confirmations = fetch_all('SELECT * FROM task_confirmations ORDER BY created_at DESC LIMIT 20')
    return jsonify({'inspections': inspections, 'attendance': attendance, 'notifications': notifications, 'confirmations': confirmations})


@app.get('/api/overview')
def overview():
    total_wards = fetch_one('SELECT COUNT(*) AS count FROM wards')['count']
    total_employees = fetch_one('SELECT COUNT(*) AS count FROM employees')['count']
    dirty_wards = fetch_one("SELECT COUNT(*) AS count FROM inspection_logs WHERE COALESCE(overridden_status, status) = 'Not Clean'")['count']
    clean_wards = fetch_one("SELECT COUNT(*) AS count FROM inspection_logs WHERE COALESCE(overridden_status, status) = 'Clean'")['count']
    attendance_mismatches = fetch_one('SELECT COUNT(*) AS count FROM attendance_logs WHERE assigned_match = 0')['count']
    overrides = fetch_one('SELECT COUNT(*) AS count FROM inspection_logs WHERE overridden_status IS NOT NULL')['count']
    return jsonify({'total_wards': total_wards, 'total_employees': total_employees, 'clean_inspections': clean_wards, 'not_clean_inspections': dirty_wards, 'attendance_mismatches': attendance_mismatches, 'overrides': overrides})


@app.get('/inspections/<path:filename>')
def inspection_file(filename):
    return send_from_directory(config.INSPECTIONS_DIR, filename)


@app.get('/uploads/<path:filename>')
def upload_file(filename):
    return send_from_directory(config.UPLOADS_DIR, filename)


if __name__ == '__main__':
    app.run(debug=config.APP_DEBUG, host=config.APP_HOST, port=config.APP_PORT)
