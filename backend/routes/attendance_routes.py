import json
from pathlib import Path
from uuid import uuid4
from flask import Blueprint, request, jsonify
from werkzeug.utils import secure_filename

import config
from database import execute, fetch_all, fetch_one, utc_now_iso
from services.notifier import notify_targets, record_notification
from core.security import require_role

attendance_bp = Blueprint('attendance_bp', __name__)
ALLOWED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp'}


def allowed_file(filename):
    return Path(filename).suffix.lower() in ALLOWED_EXTENSIONS


def save_upload(file_storage, folder):
    filename = secure_filename(file_storage.filename or f'face_{uuid4().hex}.jpg')
    extension = Path(filename).suffix.lower() or '.jpg'
    saved_name = f'{uuid4().hex}{extension}'
    output_path = folder / saved_name
    file_storage.save(output_path)
    return output_path


def employee_row(emp_key):
    if not emp_key:
        return None
    return fetch_one('SELECT * FROM employees WHERE emp_key = ?', (emp_key,))


@attendance_bp.get('/api/employees')
def get_employees():
    employees = fetch_all('SELECT * FROM employees ORDER BY created_at DESC')
    return jsonify({'employees': employees})


@attendance_bp.post('/api/employees')
@require_role('admin', 'supervisor')
def create_employee():
    data = request.get_json(force=True) if request.data else {}
    emp_key = (data.get('emp_key') or '').strip().lower()
    name = (data.get('name') or '').strip()
    designation = (data.get('designation') or '').strip()
    phone = (data.get('phone') or '').strip() or None

    if not emp_key or not name:
        return jsonify({'error': 'emp_key and name are required'}), 400

    execute(
        'INSERT OR IGNORE INTO employees (emp_key, name, designation, phone, created_at) VALUES (?, ?, ?, ?, ?)',
        (emp_key, name, designation, phone, utc_now_iso())
    )

    metadata = {}
    if config.EMPLOYEES_JSON.exists():
        try:
            metadata = json.loads(config.EMPLOYEES_JSON.read_text(encoding='utf-8'))
        except Exception:
            metadata = {}
    existing = metadata.get(emp_key, {})
    metadata[emp_key] = {'name': name, 'designation': designation, 'phone': phone or existing.get('phone')}
    config.EMPLOYEES_JSON.write_text(json.dumps(metadata, indent=2), encoding='utf-8')

    from app import face_service
    face_service.reload()
    return jsonify({'status': 'created'})


@attendance_bp.delete('/api/employees/<emp_key>')
def delete_employee(emp_key):
    emp_key = emp_key.strip().lower()
    from app import face_service
    face_service.delete_face(emp_key)

    execute('DELETE FROM employees WHERE emp_key = ?', (emp_key,))
    execute('UPDATE wards SET assigned_employee_key = NULL WHERE assigned_employee_key = ?', (emp_key,))
    try:
        execute('UPDATE shift_schedules SET assigned_employee_key = NULL WHERE assigned_employee_key = ?', (emp_key,))
    except Exception:
        pass

    if config.EMPLOYEES_JSON.exists():
        try:
            metadata = json.loads(config.EMPLOYEES_JSON.read_text(encoding='utf-8'))
            if emp_key in metadata:
                del metadata[emp_key]
                config.EMPLOYEES_JSON.write_text(json.dumps(metadata, indent=2), encoding='utf-8')
        except Exception:
            pass

    face_service.reload()
    return jsonify({'status': 'deleted', 'emp_key': emp_key})


@attendance_bp.post('/api/employees/reset-all')
def reset_all_workers():
    from app import face_service
    if config.FACE_DATASET_DIR.exists():
        for f in config.FACE_DATASET_DIR.glob('*.npy'):
            try:
                f.unlink()
            except Exception:
                pass

    if config.EMPLOYEES_JSON.exists():
        config.EMPLOYEES_JSON.write_text('{}', encoding='utf-8')

    execute('DELETE FROM employees')
    execute("UPDATE wards SET assigned_employee_key = NULL, worker_presence = 'Inactive', last_presence_at = NULL")
    execute('DELETE FROM attendance_logs')
    execute('DELETE FROM task_confirmations')
    try:
        execute('UPDATE shift_schedules SET assigned_employee_key = NULL')
    except Exception:
        pass

    face_service.reload()
    return jsonify({'status': 'all_workers_and_faces_deleted'})


@attendance_bp.get('/api/face/quality')
def face_quality():
    from app import face_service
    return jsonify({'report': face_service.quality_report()})


@attendance_bp.post('/api/attendance/recognize')
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
    
    from app import face_service
    result = face_service.recognize(saved_path)
    if not result.get('matched'):
        return jsonify(result)

    ward = fetch_one('SELECT * FROM wards WHERE name = ?', (ward_name,))
    assigned_key = (ward or {}).get('assigned_employee_key') if ward else None
    assigned_match = 1 if not assigned_key or assigned_key == result['employee_key'] else 0

    execute(
        '''INSERT INTO attendance_logs (employee_key, ward_name, confidence, source_image, assigned_match, created_at) 
           VALUES (?, ?, ?, ?, ?, ?)''',
        (result['employee_key'], ward_name, result.get('confidence'), str(saved_path), assigned_match, utc_now_iso())
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
        employee_phone = assigned_employee.get('phone') if assigned_employee else None
        notifications = notify_targets(ward_name, message, employee_phone=employee_phone)
        result['attendance_verified'] = False
        result['assigned_worker'] = expected_name
        result['message'] = message
        result['notifications'] = notifications

    return jsonify(result)

