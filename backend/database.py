import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
import config
from core.security import hash_password


def get_conn():
    conn = sqlite3.connect(config.DB_PATH, timeout=20.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def utc_now_iso():
    return datetime.now(timezone.utc).isoformat()


def _ensure_column(cur, table_name, column_name, definition):
    columns = [row[1] for row in cur.execute(f"PRAGMA table_info({table_name})").fetchall()]
    if column_name not in columns:
        cur.execute(f'ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}')


def init_db():
    conn = get_conn()
    cur = conn.cursor()

    # 1. RBAC Users Table
    cur.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'supervisor',
        name TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    ''')

    # 2. Staff Employees Table
    cur.execute('''
    CREATE TABLE IF NOT EXISTS employees (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        emp_key TEXT UNIQUE NOT NULL,
        name TEXT NOT NULL,
        designation TEXT,
        phone TEXT,
        password_hash TEXT,
        telegram_chat_id TEXT,
        created_at TEXT NOT NULL
    )
    ''')
    _ensure_column(cur, 'employees', 'password_hash', 'TEXT')
    _ensure_column(cur, 'employees', 'telegram_chat_id', 'TEXT')

    # Password Reset Tokens Table (for Worker Forgot Password)
    cur.execute('''
    CREATE TABLE IF NOT EXISTS password_resets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        emp_key TEXT NOT NULL,
        otp_code TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    ''')


    # 3. Wards Table
    cur.execute('''
    CREATE TABLE IF NOT EXISTS wards (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
        location TEXT,
        assigned_employee_key TEXT,
        auto_monitor INTEGER DEFAULT 0,
        cctv_stream_url TEXT,
        worker_presence TEXT DEFAULT 'Inactive',
        last_presence_at TEXT,
        created_at TEXT NOT NULL
    )
    ''')
    _ensure_column(cur, 'wards', 'auto_monitor', 'INTEGER DEFAULT 0')
    _ensure_column(cur, 'wards', 'cctv_stream_url', 'TEXT')
    _ensure_column(cur, 'wards', 'worker_presence', "TEXT DEFAULT 'Inactive'")
    _ensure_column(cur, 'wards', 'last_presence_at', 'TEXT')

    # 4. Shift Schedules Table (For Automated Absence & Shift Monitoring)
    cur.execute('''
    CREATE TABLE IF NOT EXISTS shift_schedules (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ward_name TEXT NOT NULL,
        shift_name TEXT NOT NULL,
        start_time TEXT NOT NULL,
        end_time TEXT NOT NULL,
        assigned_employee_key TEXT,
        is_active INTEGER DEFAULT 1,
        created_at TEXT NOT NULL
    )
    ''')

    # 5. Attendance Logs Table
    cur.execute('''
    CREATE TABLE IF NOT EXISTS attendance_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        employee_key TEXT NOT NULL,
        ward_name TEXT NOT NULL,
        confidence REAL,
        source_image TEXT,
        assigned_match INTEGER DEFAULT 1,
        created_at TEXT NOT NULL
    )
    ''')
    _ensure_column(cur, 'attendance_logs', 'assigned_match', 'INTEGER DEFAULT 1')

    # 6. Inspection Logs Table
    cur.execute('''
    CREATE TABLE IF NOT EXISTS inspection_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ward_name TEXT NOT NULL,
        employee_key TEXT,
        status TEXT NOT NULL,
        object_found INTEGER NOT NULL,
        confidence REAL,
        object_count INTEGER NOT NULL,
        raw_label TEXT,
        source_image TEXT,
        annotated_image TEXT,
        notes TEXT,
        overridden_status TEXT,
        overridden_by TEXT,
        override_reason TEXT,
        overridden_at TEXT,
        created_at TEXT NOT NULL
    )
    ''')
    _ensure_column(cur, 'inspection_logs', 'overridden_status', 'TEXT')
    _ensure_column(cur, 'inspection_logs', 'overridden_by', 'TEXT')
    _ensure_column(cur, 'inspection_logs', 'override_reason', 'TEXT')
    _ensure_column(cur, 'inspection_logs', 'overridden_at', 'TEXT')

    # 7. Notifications Audit Table
    cur.execute('''
    CREATE TABLE IF NOT EXISTS notifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ward_name TEXT NOT NULL,
        channel TEXT NOT NULL,
        message TEXT NOT NULL,
        delivery_status TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    ''')

    # 8. Task Confirmations Table
    cur.execute('''
    CREATE TABLE IF NOT EXISTS task_confirmations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ward_name TEXT NOT NULL,
        employee_key TEXT NOT NULL,
        notes TEXT,
        created_at TEXT NOT NULL
    )
    ''')

    # 9. IoT Telemetry Table (Bed Proximity, Dustbin Level, UV Micro-Stain)
    cur.execute('''
    CREATE TABLE IF NOT EXISTS iot_telemetry (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        device_id TEXT NOT NULL,
        ward_name TEXT NOT NULL,
        sensor_type TEXT NOT NULL,
        metric_value REAL NOT NULL,
        unit TEXT NOT NULL,
        status TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    ''')

    # Seed Default Wards if not present
    for ward in config.DEFAULT_WARDS:
        cur.execute(
            'INSERT OR IGNORE INTO wards (name, location, assigned_employee_key, created_at) VALUES (?, ?, ?, ?)',
            (ward, ward, None, utc_now_iso()),
        )

    # Seed Employees from employees.json
    if config.EMPLOYEES_JSON.exists():
        try:
            metadata = json.loads(config.EMPLOYEES_JSON.read_text(encoding='utf-8'))
            for emp_key, info in metadata.items():
                pwd_hash = info.get('password_hash')
                if not pwd_hash:
                    pwd_hash, _ = hash_password('worker123')
                    info['password_hash'] = pwd_hash
                    try:
                        config.EMPLOYEES_JSON.write_text(json.dumps(metadata, indent=2), encoding='utf-8')
                    except Exception:
                        pass

                cur.execute(
                    '''INSERT INTO employees (emp_key, name, designation, phone, password_hash, telegram_chat_id, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?)
                       ON CONFLICT(emp_key) DO UPDATE SET
                           name=excluded.name,
                           designation=excluded.designation,
                           phone=excluded.phone,
                           password_hash=COALESCE(excluded.password_hash, employees.password_hash),
                           telegram_chat_id=COALESCE(excluded.telegram_chat_id, employees.telegram_chat_id)''',
                    (emp_key, info.get('name', emp_key), info.get('designation'), info.get('phone'), pwd_hash, info.get('telegram_chat_id'), utc_now_iso()),
                )
        except Exception:
            pass


    # Seed Default Users for Role-Based Access Control
    pwd_admin, _ = hash_password('admin123')
    pwd_super, _ = hash_password('super123')
    cur.execute(
        'INSERT OR IGNORE INTO users (username, password_hash, role, name, created_at) VALUES (?, ?, ?, ?, ?)',
        ('admin', pwd_admin, 'admin', 'Hospital Sanitation Director', utc_now_iso()),
    )
    cur.execute(
        'INSERT OR IGNORE INTO users (username, password_hash, role, name, created_at) VALUES (?, ?, ?, ?, ?)',
        ('supervisor', pwd_super, 'supervisor', 'Floor Shift Supervisor', utc_now_iso()),
    )

    # Seed Sample Shift Schedules
    cur.execute('''
    INSERT OR IGNORE INTO shift_schedules (id, ward_name, shift_name, start_time, end_time, assigned_employee_key, is_active, created_at)
    VALUES 
        (1, 'Emergency', 'Morning Shift', '08:00', '14:00', NULL, 1, ?),
        (2, 'ICU', 'Morning Shift', '08:00', '14:00', NULL, 1, ?),
        (3, 'Ward 1', 'Morning Shift', '08:00', '14:00', NULL, 1, ?)
    ''', (utc_now_iso(), utc_now_iso(), utc_now_iso()))

    conn.commit()
    conn.close()


def fetch_all(query, params=()):
    conn = get_conn()
    try:
        rows = conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def fetch_one(query, params=()):
    conn = get_conn()
    try:
        row = conn.execute(query, params).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def execute(query, params=()):
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(query, params)
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()
