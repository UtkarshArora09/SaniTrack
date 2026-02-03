🚀 SaniTrack
Intelligent Hospital Sanitation Monitoring & Workforce Management System

SaniTrack is an AI-powered desktop application designed to automate hospital sanitation monitoring. It verifies cleaner attendance using face recognition and validates ward cleanliness using deep learning-based trash detection.

🧠 Why SaniTrack?

Hospitals often rely on manual attendance registers and visual inspections to monitor cleaning tasks. This creates problems such as:

❌ Proxy attendance

❌ Missed cleaning schedules

❌ Incomplete sanitation

❌ Lack of accountability

❌ Increased infection risks

SaniTrack solves these issues using computer vision and automated alert mechanisms.

🔍 How It Works
1️⃣ Cleaner Attendance Verification

Admin registers cleaning staff (face data fed only by admin).

Camera detects faces using Haarcascade (OpenCV).

Identity verified using KNN-based face recognition.

Attendance automatically marked when assigned worker is detected.

If absent → WhatsApp alert triggered (placeholder integration).

2️⃣ Ward Cleaning Verification

After cleaning, ward images are analyzed.

YOLOv8 model detects trash such as plastics, metals, cardboard, bottles, etc.

If trash/dirt detected → Ward marked Not Cleaned.

WhatsApp alert sent to worker and admin.

Admin can reassign tasks instantly.

👨‍💼 Admin Capabilities

Register & manage cleaners

Assign/Reassign cleaning tasks

Monitor real-time ward status

View alert logs with timestamps

Override decisions if needed

👷 Worker Capabilities

View assigned wards

See attendance status

Get notified if cleaning fails

Confirm task completion

📊 System Pipeline

Face Detection → Face Recognition → Attendance Marked
↓
Cleaning Performed
↓
YOLOv8 Trash Detection
↓
Cleaned / Not Cleaned
↓
Alert + Log + Reassignment

🛠️ Tech Stack

Backend / AI Models

Python

OpenCV (Haarcascade)

KNN Classifier

YOLOv8

Frontend

React (Vite)

TailwindCSS

Notifications

WhatsApp API (Integration Placeholder)

🔮 Future Enhancements

Near-bed IoT cleaning sensors

Bedsheet-change detection

Blue-light contamination scanning

Mobile application support

Cloud-based deployment

🎯 Project Objective

To build a scalable, automated, and accountable sanitation monitoring framework that enhances hospital hygiene compliance and reduces infection risks using AI-driven validation.

📌 Status

🚧 Active Development – Models Completed | Frontend Integration in Progress
