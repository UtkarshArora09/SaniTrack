import json
import re
from pathlib import Path

import cv2
import numpy as np

BASE_DIR = Path(__file__).resolve().parents[1] / 'backend'
CASCADE_PATH = BASE_DIR / 'data' / 'haarcascade_frontalface_alt.xml'
DATASET_DIR = BASE_DIR / 'data' / 'face_dataset'
EMPLOYEES_JSON = BASE_DIR / 'data' / 'employees.json'

face_cascade = cv2.CascadeClassifier(str(CASCADE_PATH))
if face_cascade.empty():
    raise FileNotFoundError(f'Could not load cascade from {CASCADE_PATH}')

DATASET_DIR.mkdir(parents=True, exist_ok=True)
raw_name = input('Enter the name of the person: ').strip()
designation = input('Enter the designation: ').strip() or 'Unknown'
phone = input('Enter the phone number (mandatory, with country code like +91...): ').strip()
if not phone:
    raise ValueError('Phone number is mandatory.')
    
file_key = re.sub(r'[^a-zA-Z0-9_]+', '_', raw_name.replace(' ', '_')).lower().strip('_')
if not file_key:
    raise ValueError('Invalid name provided.')

cap = cv2.VideoCapture(0)
if not cap.isOpened():
    raise RuntimeError('Could not open webcam.')

print('Move your face through different angles, distance, and lighting while capturing.')
max_new_samples = 80
sample_every = 6
skip = 0
face_data = []

gui_available = True

def safe_show(win_name, img):
    global gui_available
    if not gui_available:
        return
    try:
        cv2.imshow(win_name, img)
        return cv2.waitKey(1) & 0xFF
    except Exception:
        gui_available = False
        print("\nNote: Graphical window display unavailable. Capturing directly from webcam in terminal mode...")
        return 0

while True:
    ret, frame = cap.read()
    if not ret:
        continue
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    faces = face_cascade.detectMultiScale(gray, scaleFactor=1.2, minNeighbors=5, minSize=(60, 60))
    if len(faces) == 0:
        key = safe_show('SaniTrack Face Capture', frame)
        if key == ord('q'):
            break
        continue

    faces = sorted(faces, key=lambda r: r[2] * r[3], reverse=True)
    x, y, w, h = faces[0]
    face_roi = frame[y:y + h, x:x + w]
    if face_roi.size == 0:
        continue

    face_selection = cv2.resize(face_roi, (100, 100), interpolation=cv2.INTER_AREA)
    skip += 1
    if skip % sample_every == 0:
        face_data.append(face_selection)
        pct = int((len(face_data) / max_new_samples) * 100)
        print(f"\rCapturing biometric samples for {raw_name}: {len(face_data)}/{max_new_samples} [{pct}%]...", end="", flush=True)

    cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
    cv2.putText(frame, f'{raw_name} {len(face_data)}/{max_new_samples}', (x, max(y - 10, 20)), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
    key = safe_show('SaniTrack Face Capture', frame)

    if len(face_data) >= max_new_samples:
        break
    if key == ord('q'):
        break

cap.release()
if gui_available:
    try:
        cv2.destroyAllWindows()
    except Exception:
        pass
print()

if not face_data:
    raise SystemExit('No samples captured.')

new_array = np.array(face_data).reshape((len(face_data), -1))
save_path = DATASET_DIR / f'{file_key}.npy'
if save_path.exists():
    existing = np.load(save_path)
    merged = np.concatenate([existing, new_array], axis=0)
else:
    merged = new_array
np.save(save_path, merged)

employees = {}
if EMPLOYEES_JSON.exists():
    try:
        employees = json.loads(EMPLOYEES_JSON.read_text(encoding='utf-8'))
    except Exception:
        employees = {}
employees[file_key] = {'name': raw_name, 'designation': designation, 'phone': phone}
EMPLOYEES_JSON.write_text(json.dumps(employees, indent=2), encoding='utf-8')

# Synchronize directly with SQLite sanitrack.db
db_path = BASE_DIR / 'data' / 'sanitrack.db'
if db_path.exists():
    try:
        import sqlite3
        from datetime import datetime, timezone
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO employees (emp_key, name, designation, phone, created_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(emp_key) DO UPDATE SET
                name = excluded.name,
                designation = excluded.designation,
                phone = excluded.phone
            """,
            (file_key, raw_name, designation, phone, datetime.now(timezone.utc).isoformat())
        )
        conn.commit()
        conn.close()
        print(f'Synchronized "{raw_name}" into SQLite database (sanitrack.db).')
    except Exception as db_err:
        print(f'Warning: SQLite update error: {db_err}')

print(f'\nSUCCESS: Enrolled "{raw_name}" ({file_key})!')
print(f'Face vector samples: {merged.shape[0]} stored in {save_path.name}')
print('SaniTrack dashboard will immediately recognize this worker for attendance and shift assignment.')
