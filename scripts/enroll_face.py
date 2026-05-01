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

while True:
    ret, frame = cap.read()
    if not ret:
        continue
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    faces = face_cascade.detectMultiScale(gray, scaleFactor=1.2, minNeighbors=5, minSize=(60, 60))
    if len(faces) == 0:
        cv2.imshow('SaniTrack Face Capture', frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
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

    cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
    cv2.putText(frame, f'{raw_name} {len(face_data)}/{max_new_samples}', (x, max(y - 10, 20)), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
    cv2.imshow('SaniTrack Face Capture', frame)

    if len(face_data) >= max_new_samples:
        break
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()

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
    employees = json.loads(EMPLOYEES_JSON.read_text(encoding='utf-8'))
employees[file_key] = {'name': raw_name, 'designation': designation, 'phone': phone}
EMPLOYEES_JSON.write_text(json.dumps(employees, indent=2), encoding='utf-8')

print(f'Added {len(face_data)} new samples to {save_path}')
print(f'Total samples for {file_key}: {merged.shape[0]}')
