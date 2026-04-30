# SaniTrack Final

Unified project folder for the SaniTrack hospital sanitation monitoring system.

## What is inside
- `backend/app.py`: Flask backend and dashboard routes
- `backend/services/face_service.py`: face recognition with preprocessing, KNN voting, and dataset diagnostics
- `backend/services/cleanliness_service.py`: YOLOv8 cleanliness detection service
- `backend/services/notifier.py`: dashboard logging plus WhatsApp notifications via Twilio
- `backend/data/sanitrack.db`: SQLite database created automatically on first run
- `scripts/enroll_face.py`: webcam-based face registration utility that appends new samples
- `scripts/face_dataset_report.py`: prints face dataset quality metrics

## Current workflow
1. Admin registers cleaners and phone numbers.
2. Admin assigns or reassigns wards to workers.
3. Workers can open a direct page at `/worker/<emp_key>` to see assigned tasks.
4. Attendance is verified from upload or live webcam capture.
5. Attendance mismatch can trigger an admin/worker alert.
6. Worker can confirm cleaning completion from the dashboard or worker page.
7. Ward floor image is analyzed by YOLOv8.
8. If waste is detected, the ward is marked `Not Clean` and WhatsApp alerts can be sent.
9. Admin can override inspection decisions and all actions are stored in audit history.

## Worker task delivery
Workers can know their tasks in two ways:
- Worker page: `http://127.0.0.1:5000/worker/<emp_key>`
- WhatsApp notification on assignment/reassignment and failure alerts

If a worker phone number is a placeholder or invalid, the system will still log the notification attempt in the database, but WhatsApp delivery will fail until a real number is configured.

## Run
```powershell
cd "D:\SANITRACK FINAL"
python -m pip install -r requirements.txt
python backend\app.py
```

Open `http://127.0.0.1:5000`.

## Face registration
```powershell
cd "D:\SANITRACK FINAL"
python scripts\enroll_face.py
python scripts\face_dataset_report.py
```

## WhatsApp setup
1. Copy `.env.example` to `.env` if needed.
2. Fill `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_WHATSAPP_FROM`, and `ADMIN_WHATSAPP_TO`.
3. Make sure the target phone has joined the Twilio WhatsApp sandbox.
4. Do not commit real credentials into GitHub.

## Notes
- The YOLO model is used as a cleanliness detector. The dashboard does not depend on the raw class name such as `bag`.
- The ward decision is binary: detection means `Not Clean`, no detection means `Clean`.
- Face-quality diagnostics are exposed in the dashboard and with `face_dataset_report.py` so you can see which workers need more varied samples.
- For best face-recognition results, append 2-3 enrollment sessions per worker under different lighting and angles.
