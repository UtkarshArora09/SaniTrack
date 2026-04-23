import json
import sqlite3
from datetime import datetime, timezone

from config import DB_PATH, DEFAULT_WARDS, EMPLOYEES_JSON


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def utc_now_iso():
    return datetime.now(timezone.utc).isoformat()


def init_db():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute('CREATE TABLE IF NOT EXISTS employees (id INTEGER PRIMARY KEY AUTOINCREMENT, emp_key TEXT UNIQUE NOT NULL, name TEXT NOT NULL, designation TEXT, phone TEXT, created_at TEXT NOT NULL)')
    cur.execute('CREATE TABLE IF NOT EXISTS wards (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL, location TEXT, assigned_employee_key TEXT, created_at TEXT NOT NULL)')
    cur.execute('CREATE TABLE IF NOT EXISTS attendance_logs (id INTEGER PRIMARY KEY AUTOINCREMENT, employee_key TEXT NOT NULL, ward_name TEXT NOT NULL, confidence REAL, source_image TEXT, created_at TEXT NOT NULL)')
    cur.execute('CREATE TABLE IF NOT EXISTS inspection_logs (id INTEGER PRIMARY KEY AUTOINCREMENT, ward_name TEXT NOT NULL, employee_key TEXT, status TEXT NOT NULL, object_found INTEGER NOT NULL, confidence REAL, object_count INTEGER NOT NULL, raw_label TEXT, source_image TEXT, annotated_image TEXT, notes TEXT, created_at TEXT NOT NULL)')
    cur.execute('CREATE TABLE IF NOT EXISTS notifications (id INTEGER PRIMARY KEY AUTOINCREMENT, ward_name TEXT NOT NULL, channel TEXT NOT NULL, message TEXT NOT NULL, delivery_status TEXT NOT NULL, created_at TEXT NOT NULL)')

    for ward in DEFAULT_WARDS:
        cur.execute('INSERT OR IGNORE INTO wards (name, location, assigned_employee_key, created_at) VALUES (?, ?, ?, ?)', (ward, ward, None, utc_now_iso()))

    if EMPLOYEES_JSON.exists():
        metadata = json.loads(EMPLOYEES_JSON.read_text(encoding='utf-8'))
        for emp_key, info in metadata.items():
            cur.execute(
                'INSERT OR IGNORE INTO employees (emp_key, name, designation, phone, created_at) VALUES (?, ?, ?, ?, ?)',
                (emp_key, info.get('name', emp_key), info.get('designation'), info.get('phone'), utc_now_iso()),
            )

    conn.commit()
    conn.close()


def fetch_all(query, params=()):
    conn = get_conn()
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def fetch_one(query, params=()):
    conn = get_conn()
    row = conn.execute(query, params).fetchone()
    conn.close()
    return dict(row) if row else None


def execute(query, params=()):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(query, params)
    conn.commit()
    lastrowid = cur.lastrowid
    conn.close()
    return lastrowid
