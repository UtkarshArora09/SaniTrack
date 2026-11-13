from pathlib import Path
from uuid import uuid4
from flask import Blueprint, request, jsonify
from werkzeug.utils import secure_filename

import config
from database import execute, fetch_one, utc_now_iso
from services.notifier import notify_targets, record_notification
from core.security import require_role

inspection_bp = Blueprint('inspection_bp', __name__)
ALLOWED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp'}


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


@inspection_bp.post('/api/inspection/analyze')
def analyze_inspection():
    """
    Asynchronous Non-Blocking Floor Inspection Endpoint.
    Returns HTTP 202 Accepted immediately so the web server never freezes during YOLO forward pass.
    """
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

    ward = fetch_one('SELECT * FROM wards WHERE name = ?', (ward_name,))
    assigned_key = (ward or {}).get('assigned_employee_key') if ward else None
    effective_employee_key = employee_key or assigned_key

    saved_path = save_upload(upload, config.UPLOADS_DIR)

    # 1. Insert initial inspection record with status 'Processing'
    inspection_id = execute(
        '''INSERT INTO inspection_logs 
           (ward_name, employee_key, status, object_found, confidence, object_count, raw_label, source_image, annotated_image, notes, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
        (ward_name, effective_employee_key, 'Processing', 0, None, 0, None, str(saved_path), None, notes, utc_now_iso())
    )

    # 2. Asynchronous callback executed when YOLO forward-pass completes in background thread
    from app import cleanliness_service

    def on_inference_complete(analysis, error):
        if error:
            execute(
                "UPDATE inspection_logs SET status = 'Failed', notes = ? WHERE id = ?",
                (f"Inference error: {str(error)}", inspection_id)
            )
            return

        # Update database with detected objects and cleanliness classification
        execute(
            '''UPDATE inspection_logs 
               SET status = ?, object_found = ?, confidence = ?, object_count = ?, 
                   raw_label = ?, annotated_image = ?, notes = ? 
               WHERE id = ?''',
            (
                analysis['status'],
                1 if analysis['object_found'] else 0,
                analysis['confidence'],
                analysis['object_count'],
                analysis['raw_label'],
                analysis['annotated_image'],
                notes,
                inspection_id
            )
        )

        # Trigger WhatsApp alerts according to hygiene findings
        if analysis['object_found']:
            msg = f"{ward_name} marked Not Clean. Waste detected on floor ({analysis['raw_label']}, {analysis['object_count']} objects)."
            notify_targets(ward_name, msg, employee_phone=employee_phone_for(effective_employee_key))
        else:
            msg = f"{ward_name} marked Clean after inspection."
            record_notification(ward_name, msg, channel='inspection', delivery_status='verified')

    # 3. Submit to non-blocking thread pool
    cleanliness_service.submit_async(saved_path, inspection_id, on_inference_complete)

    # 4. Immediate response with 202 Accepted
    return jsonify({
        'inspection_id': inspection_id,
        'status': 'Processing',
        'message': 'Image queued for non-blocking AI cleanliness verification.',
        'source_image': str(saved_path)
    }), 202


@inspection_bp.get('/api/inspection/<int:inspection_id>/status')
def get_inspection_status(inspection_id):
    """
    Polling endpoint consumed by client-side JavaScript.
    """
    row = fetch_one('SELECT * FROM inspection_logs WHERE id = ?', (inspection_id,))
    if not row:
        return jsonify({'error': 'Inspection not found'}), 404

    is_complete = row['status'] not in ('Processing', 'Pending')
    annotated_filename = Path(row['annotated_image']).name if row.get('annotated_image') else None

    return jsonify({
        'inspection_id': inspection_id,
        'complete': is_complete,
        'status': row['overridden_status'] or row['status'],
        'raw_status': row['status'],
        'object_found': bool(row['object_found']),
        'object_count': row['object_count'],
        'confidence': row['confidence'],
        'raw_label': row['raw_label'],
        'annotated_image_url': f'/inspections/{annotated_filename}' if annotated_filename else None,
        'overridden_status': row['overridden_status'],
        'override_reason': row['override_reason'],
        'notes': row['notes'],
        'created_at': row['created_at']
    })


@inspection_bp.post('/api/inspection/<int:inspection_id>/override')
@require_role('admin', 'supervisor')
def override_inspection(inspection_id):
    data = request.get_json(force=True) if request.data else {}
    override_status = (data.get('status') or '').strip()
    override_reason = (data.get('reason') or '').strip()
    overridden_by = (data.get('admin_name') or 'Supervisor').strip()

    if override_status not in {'Clean', 'Not Clean'}:
        return jsonify({'error': 'status must be Clean or Not Clean'}), 400

    inspection = fetch_one('SELECT * FROM inspection_logs WHERE id = ?', (inspection_id,))
    if not inspection:
        return jsonify({'error': 'Inspection not found'}), 404

    execute(
        '''UPDATE inspection_logs 
           SET overridden_status = ?, overridden_by = ?, override_reason = ?, overridden_at = ? 
           WHERE id = ?''',
        (override_status, overridden_by, override_reason or None, utc_now_iso(), inspection_id)
    )

    message = f"{inspection['ward_name']} override set to {override_status} by {overridden_by}."
    if override_reason:
        message += f" Reason: {override_reason}"
    record_notification(inspection['ward_name'], message, channel='override', delivery_status='logged')

    return jsonify({'status': 'overridden', 'new_status': override_status})

