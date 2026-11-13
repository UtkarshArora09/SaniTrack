from flask import Blueprint, request, jsonify
from database import fetch_all, fetch_one, execute, utc_now_iso
from services.notifier import record_notification

worker_bp = Blueprint('worker_bp', __name__)


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
        
    execute(
        'INSERT INTO task_confirmations (ward_name, employee_key, notes, created_at) VALUES (?, ?, ?, ?)',
        (ward_name, employee_key, notes, utc_now_iso())
    )
    record_notification(
        ward_name,
        f"{employee_key} marked task complete: {notes}",
        channel='worker-confirmation',
        delivery_status='logged'
    )
    return jsonify({'status': 'confirmed'})

