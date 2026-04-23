# SaniTrack Final

Unified project folder for the SaniTrack hospital sanitation monitoring system.

## What is inside
- `backend/app.py`: Flask backend and dashboard routes
- `backend/services/face_service.py`: face recognition with preprocessing, KNN voting, and dataset diagnostics
- `backend/services/cleanliness_service.py`: YOLOv8 cleanliness detection service
- `backend/data/sanitrack.db`: SQLite database created automatically on first run
- `scripts/enroll_face.py`: webcam-based face registration utility that appends new samples
- `scripts/face_dataset_report.py`: prints face dataset quality metrics

## Main flow
1. Add wards and employees in the dashboard.
2. Use file upload or live webcam capture to verify that the assigned worker is present.
3. Use file upload or live webcam capture to inspect the ward floor.
4. If any object is detected, the backend marks the ward as `Not Clean`.
5. All activity is stored in SQLite for audit history.
6. If Twilio is configured, the app can send WhatsApp notifications for dirty-floor events.

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
1. Copy `.env.example` to `.env`.
2. Fill `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_WHATSAPP_FROM`, and `ADMIN_WHATSAPP_TO`.
3. Make sure the target phone has joined the Twilio WhatsApp sandbox.

## Notes
- The YOLO model is used as a cleanliness detector. The dashboard does not depend on the raw class name such as `bag`.
- The ward decision is binary: detection means `Not Clean`, no detection means `Clean`.
- Face-quality diagnostics are exposed in the dashboard and with the `face_dataset_report.py` script so you can see which workers need more varied samples.
