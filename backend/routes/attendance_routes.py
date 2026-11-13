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
    return jsonify({
        'error': 'Biometric face scan is required to register new workers and set their passwords. Please use 80-Frame Biometric Capture or upload a face photo in the Admin Portal.'
    }), 400


@attendance_bp.post('/api/employees/enroll-web')
def enroll_employee_web():
    emp_key = (request.form.get('emp_key') or '').strip().lower()
    name = (request.form.get('name') or '').strip()
    designation = (request.form.get('designation') or 'Sanitation Staff').strip()
    phone = (request.form.get('phone') or '').strip()
    password = (request.form.get('password') or '').strip()

    if not name:
        return jsonify({'error': 'Name is required'}), 400

    if not phone:
        return jsonify({'error': 'Worker mobile number is required for login access'}), 400

    if not password or len(password) < 4:
        return jsonify({'error': 'Password is required (minimum 4 characters) to set staff login password'}), 400

    if not emp_key:
        import re
        emp_key = re.sub(r'[^a-zA-Z0-9_]+', '_', name.replace(' ', '_')).lower().strip('_')

    uploaded_files = request.files.getlist('images')
    if not uploaded_files or len(uploaded_files) == 0:
        if 'image' in request.files:
            uploaded_files = [request.files['image']]
        else:
            return jsonify({'error': 'At least one face image or live biometric scan is required'}), 400

    import cv2
    import numpy as np
    from app import face_service
    from core.security import hash_password

    cascade = face_service.engine.cascade
    face_crops = []

    for file_obj in uploaded_files:
        try:
            file_bytes = file_obj.read()
            if not file_bytes:
                continue
            nparr = np.frombuffer(file_bytes, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            if img is None:
                continue

            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            faces = cascade.detectMultiScale(gray, scaleFactor=1.2, minNeighbors=4, minSize=(40, 40))
            if len(faces) > 0:
                faces_sorted = sorted(faces, key=lambda r: r[2] * r[3], reverse=True)
                x, y, w, h = faces_sorted[0]
                crop = img[y:y+h, x:x+w]
                if crop.size > 0:
                    resized = cv2.resize(crop, (100, 100), interpolation=cv2.INTER_AREA)
                    face_crops.append(resized)
        except Exception:
            continue

    if not face_crops:
        return jsonify({'error': 'No clear face detected in the submitted image(s). Ensure face is well-lit and facing the camera directly.'}), 400

    total_samples = face_service.enroll_samples(emp_key, face_crops)

    # Face verification succeeded — hash password and store credentials
    pwd_hash, _ = hash_password(password)

    execute(
        '''
        INSERT INTO employees (emp_key, name, designation, phone, password_hash, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(emp_key) DO UPDATE SET
            name = excluded.name,
            designation = excluded.designation,
            phone = excluded.phone,
            password_hash = excluded.password_hash
        ''',
        (emp_key, name, designation, phone, pwd_hash, utc_now_iso())
    )

    metadata = {}
    if config.EMPLOYEES_JSON.exists():
        try:
            metadata = json.loads(config.EMPLOYEES_JSON.read_text(encoding='utf-8'))
        except Exception:
            metadata = {}
    metadata[emp_key] = {
        'name': name,
        'designation': designation,
        'phone': phone,
        'password_hash': pwd_hash,
        'telegram_chat_id': metadata.get(emp_key, {}).get('telegram_chat_id')
    }
    config.EMPLOYEES_JSON.write_text(json.dumps(metadata, indent=2), encoding='utf-8')

    face_service.reload()

    return jsonify({
        'status': 'enrolled',
        'emp_key': emp_key,
        'name': name,
        'phone': phone,
        'samples_captured': len(face_crops),
        'total_samples': total_samples
    })


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
    try:
        execute('DELETE FROM password_resets WHERE emp_key = ?', (emp_key,))
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

