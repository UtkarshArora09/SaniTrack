from flask import Blueprint, request, jsonify
from database import fetch_all, fetch_one, execute, utc_now_iso
from services.notifier import notify_targets, record_notification
from core.security import require_role

ward_bp = Blueprint('ward_bp', __name__)


def employee_row(emp_key):
    if not emp_key:
        return None
    return fetch_one('SELECT * FROM employees WHERE emp_key = ?', (emp_key,))


def ward_response_rows():
    return fetch_all(
        """
        SELECT w.id,
               w.name,
               w.location,
               w.assigned_employee_key,
               w.auto_monitor,
               w.cctv_stream_url,
               COALESCE(w.worker_presence, 'Inactive') AS worker_presence,
               w.last_presence_at,
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


@ward_bp.get('/api/wards')
def get_wards():
    return jsonify({'wards': ward_response_rows()})


@ward_bp.post('/api/wards')
@require_role('admin', 'supervisor')
def create_ward():
    data = request.get_json(force=True) if request.data else {}
    name = (data.get('name') or '').strip()
    location = (data.get('location') or '').strip() or name
    assigned_employee_key = (data.get('assigned_employee_key') or '').strip().lower() or None
    
    if not name:
        return jsonify({'error': 'Ward name is required'}), 400
        
    execute(
        'INSERT OR IGNORE INTO wards (name, location, assigned_employee_key, created_at) VALUES (?, ?, ?, ?)',
        (name, location, assigned_employee_key, utc_now_iso())
    )
    return jsonify({'status': 'created'})


@ward_bp.post('/api/wards/<int:ward_id>/assign')
@require_role('admin', 'supervisor')
def assign_ward(ward_id):
    data = request.get_json(force=True) if request.data else {}
    employee_key = (data.get('employee_key') or '').strip().lower() or None
    admin_name = (data.get('admin_name') or 'Supervisor').strip()
    
    ward = fetch_one('SELECT * FROM wards WHERE id = ?', (ward_id,))
    if not ward:
        return jsonify({'error': 'Ward not found'}), 404
        
    if employee_key and not employee_row(employee_key):
        return jsonify({'error': 'Employee not found'}), 404

    previous_assignee = ward.get('assigned_employee_key')
    new_presence = 'Away / Inactive' if employee_key else 'Unassigned'
    execute('UPDATE wards SET assigned_employee_key = ?, worker_presence = ? WHERE id = ?', (employee_key, new_presence, ward_id))

    if employee_key:
        employee = employee_row(employee_key)
        if previous_assignee and previous_assignee != employee_key:
            previous_employee = employee_row(previous_assignee)
            previous_name = previous_employee['name'] if previous_employee else previous_assignee
            message = f"{ward['name']} reassigned from {previous_name} to {employee['name']} by {admin_name}."
        else:
            message = f"{ward['name']} assigned to {employee['name']} by {admin_name}."
            
        notifications = notify_targets(
            ward['name'],
            message,
            employee_phone=employee.get('phone'),
            employee_chat_id=employee.get('telegram_chat_id')
        )
    else:
        message = f"{ward['name']} assignment cleared by {admin_name}."
        notifications = [record_notification(ward['name'], message, channel='assignment', delivery_status='logged')]

    return jsonify({
        'status': 'updated',
        'ward': fetch_one('SELECT * FROM wards WHERE id = ?', (ward_id,)),
        'notifications': notifications
    })


@ward_bp.post('/api/wards/<int:ward_id>/alert-absence')
@require_role('admin', 'supervisor')
def alert_absence(ward_id):
    data = request.get_json(force=True) if request.data else {}
    ward = fetch_one('SELECT * FROM wards WHERE id = ?', (ward_id,))
    if not ward:
        return jsonify({'error': 'Ward not found'}), 404
        
    employee = employee_row(ward.get('assigned_employee_key'))
    if not employee:
        return jsonify({'error': 'No assigned worker for this ward'}), 400

    reason = (data.get('reason') or 'Assigned worker absent during scheduled cleaning window.').strip()
    message = f"{ward['name']} Urgent: {reason}"
    notifications = notify_targets(
        ward['name'],
        message,
        employee_phone=employee.get('phone'),
        employee_chat_id=employee.get('telegram_chat_id')
    )
    return jsonify({'status': 'sent', 'notifications': notifications})


@ward_bp.post('/api/wards/<int:ward_id>/auto-monitor')
@require_role('admin', 'supervisor')
def toggle_auto_monitor(ward_id):
    ward = fetch_one('SELECT * FROM wards WHERE id = ?', (ward_id,))
    if not ward:
        return jsonify({'error': 'Ward not found'}), 404

    current_state = int(ward.get('auto_monitor') or 0)
    new_state = 0 if current_state == 1 else 1
    execute('UPDATE wards SET auto_monitor = ? WHERE id = ?', (new_state, ward_id))

    from app import cctv_monitor
    if new_state == 1:
        cctv_monitor.start_monitoring(ward['name'], interval_seconds=15)
        action_msg = 'started'
    else:
        cctv_monitor.stop_monitoring(ward['name'])
        action_msg = 'stopped'

    return jsonify({
        'status': 'updated',
        'ward_name': ward['name'],
        'auto_monitor': new_state,
        'action': action_msg
    })


@ward_bp.post('/api/wards/<int:ward_id>/presence')
def update_presence(ward_id):
    data = request.get_json(force=True) if request.data else {}
    is_present = bool(data.get('is_present', False))
    status_label = 'Active (Working)' if is_present else 'Away / Inactive'
    execute(
        'UPDATE wards SET worker_presence = ?, last_presence_at = ? WHERE id = ?',
        (status_label, utc_now_iso(), ward_id)
    )
    return jsonify({
        'status': 'updated',
        'ward_id': ward_id,
        'worker_presence': status_label,
        'last_presence_at': utc_now_iso()
    })


@ward_bp.post('/api/wards/<int:ward_id>/detect-presence')
def detect_live_presence(ward_id):
    ward = fetch_one(
        'SELECT w.*, e.name as assigned_employee_name FROM wards w LEFT JOIN employees e ON e.emp_key = w.assigned_employee_key WHERE w.id = ?',
        (ward_id,)
    )
    if not ward:
        return jsonify({'error': 'Ward not found'}), 404

    image_bytes = None
    if 'frame' in request.files:
        image_bytes = request.files['frame'].read()
    elif request.is_json and 'image' in request.json:
        import base64
        raw = request.json['image']
        if ',' in raw:
            raw = raw.split(',', 1)[1]
        image_bytes = base64.b64decode(raw)

    if not image_bytes:
        return jsonify({'error': 'No image frame provided'}), 400

    import cv2
    import numpy as np
    from app import face_service

    nparr = np.frombuffer(image_bytes, np.uint8)
    frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if frame is None:
        return jsonify({'error': 'Unable to decode frame'}), 400

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    cascade = face_service.engine.cascade
    faces = cascade.detectMultiScale(gray, scaleFactor=1.2, minNeighbors=4, minSize=(40, 40))

    is_present = len(faces) > 0
    assigned_key = ward.get('assigned_employee_key')
    worker_match = False
    recognized_name = None

    if is_present and len(face_service.engine.sample_labels) > 0:
        faces_sorted = sorted(faces, key=lambda r: r[2] * r[3], reverse=True)
        x, y, w, h = faces_sorted[0]
        roi = frame[y:y+h, x:x+w]
        if roi.size > 0:
            probe = face_service.engine._preprocess_face(roi)
            classification = face_service.engine._classify_probe(probe)
            best_key = classification['best_key']
            best_dist = classification['best_distance']
            if best_dist <= face_service.engine.distance_threshold:
                emp_meta = face_service.engine.employees.get(best_key, {})
                recognized_name = emp_meta.get('name', best_key.capitalize())
                if assigned_key and best_key == assigned_key:
                    worker_match = True

    if not assigned_key:
        status_label = 'Unassigned'
        is_present = False
    else:
        status_label = 'Active (Working)' if is_present else 'Away / Inactive'
    now_iso = utc_now_iso()
    execute(
        'UPDATE wards SET worker_presence = ?, last_presence_at = ? WHERE id = ?',
        (status_label, now_iso, ward_id)
    )

    return jsonify({
        'ward_id': ward_id,
        'ward_name': ward['name'],
        'assigned_employee_name': ward.get('assigned_employee_name'),
        'is_present': is_present,
        'faces_detected': len(faces),
        'worker_match': worker_match,
        'recognized_name': recognized_name,
        'worker_presence': status_label,
        'last_presence_at': now_iso
    })



@ward_bp.get('/api/shifts')
def get_shifts():
    shifts = fetch_all('''
        SELECT s.*, e.name as employee_name 
        FROM shift_schedules s
        LEFT JOIN employees e ON e.emp_key = s.assigned_employee_key
        ORDER BY s.start_time
    ''')
    return jsonify({'shifts': shifts})

