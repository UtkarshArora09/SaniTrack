from flask import Blueprint, request, jsonify, session
from datetime import datetime, timezone, timedelta
import re
import json
import secrets
import config
from database import fetch_all, fetch_one, execute, utc_now_iso
from services.notifier import notify_targets, record_notification, _send_telegram
from core.security import verify_password, hash_password

worker_bp = Blueprint('worker_bp', __name__)


def normalize_phone(phone_str):
    if not phone_str:
        return ''
    cleaned = re.sub(r'\D', '', phone_str)
    return cleaned[-10:] if len(cleaned) >= 10 else cleaned



def employee_row(emp_key):
    if not emp_key:
        return None
    return fetch_one('SELECT * FROM employees WHERE emp_key = ?', (emp_key,))


@worker_bp.get('/api/workers')
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


@worker_bp.get('/api/workers/<emp_key>/dashboard')
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


@worker_bp.post('/api/tasks/confirm')
def confirm_task():
    data = request.get_json(force=True) if request.data else {}
    ward_name = (data.get('ward_name') or '').strip()
    employee_key = (data.get('employee_key') or '').strip().lower()
    notes = (data.get('notes') or 'Cleaning completed and ready for inspection.').strip()
    
    if not ward_name or not employee_key:
        return jsonify({'error': 'ward_name and employee_key are required'}), 400
        
    ward = fetch_one('SELECT * FROM wards WHERE name = ?', (ward_name,))
    if not ward:
        return jsonify({'error': 'Ward not found'}), 404

    employee = employee_row(employee_key)
    worker_name = employee.get('name') if employee else employee_key
        
    execute(
        'INSERT INTO task_confirmations (ward_name, employee_key, notes, created_at) VALUES (?, ?, ?, ?)',
        (ward_name, employee_key, notes, utc_now_iso())
    )

    admin_message = (
        f"✅ *Ward Cleaning Completed*\n"
        f"📍 Ward: *{ward_name}*\n"
        f"👤 Completed by: *{worker_name}* ({employee_key})\n"
        f"📝 Notes: {notes}\n"
        f"👉 Ready for AI Hygiene Inspection (Step 4)."
    )

    notifications = notify_targets(
        ward_name,
        admin_message,
        employee_phone=employee.get('phone') if employee else None,
        employee_chat_id=employee.get('telegram_chat_id') if employee else None
    )

    return jsonify({'status': 'confirmed', 'notifications': notifications})


@worker_bp.post('/api/worker/login')
def worker_login():
    data = request.get_json(force=True) if request.data else {}
    phone = (data.get('phone') or '').strip()
    password = (data.get('password') or '').strip()
    emp_key = (data.get('emp_key') or '').strip().lower()

    if not phone or not password:
        return jsonify({'error': 'Mobile number and password are required'}), 400

    clean_phone = normalize_phone(phone)
    employees = fetch_all('SELECT * FROM employees')
    matched_worker = None

    for emp in employees:
        emp_phone_clean = normalize_phone(emp.get('phone'))
        if clean_phone and emp_phone_clean and (emp_phone_clean == clean_phone):
            matched_worker = emp
            break
        # Also allow matching by explicit emp_key
        if emp_key and emp.get('emp_key') == emp_key:
            matched_worker = emp
            break

    if not matched_worker:
        return jsonify({'error': 'No worker found registered with this mobile number'}), 404

    stored_hash = matched_worker.get('password_hash')
    if not stored_hash:
        if password == 'worker123':
            pass
        else:
            return jsonify({'error': 'Default password required. Please use worker123 or reset via Forgot Password.'}), 401
    elif not verify_password(stored_hash, password):
        return jsonify({'error': 'Invalid mobile number or password'}), 401

    session['worker_emp_key'] = matched_worker['emp_key']
    return jsonify({
        'status': 'authenticated',
        'emp_key': matched_worker['emp_key'],
        'name': matched_worker['name'],
        'designation': matched_worker.get('designation', 'Sanitation Staff')
    })


@worker_bp.post('/api/worker/logout')
def worker_logout():
    session.pop('worker_emp_key', None)
    return jsonify({'status': 'logged_out'})


@worker_bp.post('/api/worker/forgot-password/request')
def worker_forgot_password_request():
    data = request.get_json(force=True) if request.data else {}
    phone = (data.get('phone') or '').strip()
    if not phone:
        return jsonify({'error': 'Mobile number is required'}), 400

    clean_phone = normalize_phone(phone)
    employees = fetch_all('SELECT * FROM employees')
    matched_worker = None
    for emp in employees:
        if normalize_phone(emp.get('phone')) == clean_phone:
            matched_worker = emp
            break

    if not matched_worker:
        return jsonify({'error': 'No worker found registered with this mobile number. Please contact your supervisor.'}), 404

    otp = f"{secrets.randbelow(900000) + 100000:06d}"
    expires_at = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()

    execute(
        'INSERT INTO password_resets (emp_key, otp_code, expires_at, created_at) VALUES (?, ?, ?, ?)',
        (matched_worker['emp_key'], otp, expires_at, utc_now_iso())
    )

    # Dispatch strictly to worker's private Telegram bot
    chat_id = matched_worker.get('telegram_chat_id')
    if not chat_id:
        return jsonify({
            'error': 'No Telegram account linked to this mobile number. Please link your Telegram with @SaniTrackBot first or contact your supervisor.'
        }), 400

    worker_msg = (
        f"🔐 *SaniTrack Password Reset*\n\n"
        f"Hello *{matched_worker['name']}*,\n"
        f"Your 6-digit password reset PIN is: *{otp}*\n\n"
        f"⏰ Valid for 10 minutes. Enter this code on the login page to set your new password."
    )
    _send_telegram(worker_msg, chat_id=chat_id)

    return jsonify({
        'status': 'otp_sent',
        'emp_key': matched_worker['emp_key'],
        'name': matched_worker['name'],
        'has_telegram': True,
        'message': 'Verification PIN sent to worker Telegram bot'
    })


@worker_bp.post('/api/worker/forgot-password/verify')
def worker_forgot_password_verify():
    data = request.get_json(force=True) if request.data else {}
    emp_key = (data.get('emp_key') or '').strip().lower()
    otp_code = (data.get('otp_code') or '').strip()
    new_password = (data.get('new_password') or '').strip()

    if not otp_code or not new_password:
        return jsonify({'error': 'OTP code and new password are required'}), 400

    if len(new_password) < 4:
        return jsonify({'error': 'New password must be at least 4 characters'}), 400

    now = utc_now_iso()
    reset_entry = fetch_one(
        'SELECT * FROM password_resets WHERE otp_code = ? AND expires_at > ? ORDER BY id DESC LIMIT 1',
        (otp_code, now)
    )
    if not reset_entry:
        return jsonify({'error': 'Invalid or expired 6-digit verification PIN. Please request a new code.'}), 400

    target_emp_key = reset_entry['emp_key']
    worker = employee_row(target_emp_key)
    if not worker:
        return jsonify({'error': 'Worker account not found'}), 404

    pwd_hash, _ = hash_password(new_password)

    execute('UPDATE employees SET password_hash = ? WHERE emp_key = ?', (pwd_hash, target_emp_key))
    execute('DELETE FROM password_resets WHERE emp_key = ?', (target_emp_key,))

    if config.EMPLOYEES_JSON.exists():
        try:
            metadata = json.loads(config.EMPLOYEES_JSON.read_text(encoding='utf-8'))
            if target_emp_key in metadata:
                metadata[target_emp_key]['password_hash'] = pwd_hash
                config.EMPLOYEES_JSON.write_text(json.dumps(metadata, indent=2), encoding='utf-8')
        except Exception:
            pass

    session['worker_emp_key'] = target_emp_key

    success_msg = f"✅ *Password Changed*: Your staff login password was updated successfully."
    if worker.get('telegram_chat_id'):
        _send_telegram(success_msg, chat_id=worker['telegram_chat_id'])

    return jsonify({
        'status': 'success',
        'emp_key': target_emp_key,
        'name': worker['name'],
        'message': 'Password updated successfully'
    })


