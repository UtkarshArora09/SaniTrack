# 🚀 SaniTrack
# 🏥 Intelligent Hospital Sanitation Monitoring & Workforce Management System

---

## 💡 Transforming Hospital Hygiene with AI

SaniTrack is an AI-powered desktop application designed to automate hospital sanitation monitoring.  
It verifies cleaner attendance using face recognition and validates ward cleanliness using deep learning-based trash detection — ensuring accountability, transparency, and hygiene compliance.

---

## 🧠 Why SaniTrack?

Hospitals often rely on manual registers and visual inspections, which result in:

- Proxy attendance  
- Missed cleaning schedules  
- Incomplete sanitation  
- Lack of accountability  
- Increased infection risks  

SaniTrack replaces manual supervision with AI-driven validation and automated alert mechanisms.

---

## 🔍 How It Works

### 1️⃣ Cleaner Attendance Verification

- Admin registers cleaning staff (face data fed only by admin)
- Face detected using Haarcascade (OpenCV)
- Identity verified using KNN-based face recognition
- Attendance automatically marked when assigned worker is detected
- If absent → WhatsApp alert triggered (integration placeholder)

---

### 2️⃣ Ward Cleaning Verification

- Ward images analyzed after cleaning
- YOLOv8 model detects trash (plastics, metals, cardboard, bottles, etc.)
- If trash/dirt detected → Ward marked Not Cleaned
- WhatsApp alert sent to worker & admin
- Admin can instantly reassign tasks

---

## 👨‍💼 Admin Capabilities

- Register and manage cleaners
- Assign and reassign cleaning tasks
- Monitor real-time ward status
- View timestamped alert logs
- Override cleaning decisions if needed

---

## 👷 Worker Capabilities

- View assigned wards
- Check attendance status
- Receive cleaning failure notifications
- Confirm validated task completion

---

## 📊 System Pipeline

Face Detection  
↓  
Face Recognition  
↓  
Attendance Marked  
↓  
Cleaning Performed  
↓  
YOLOv8 Trash Detection  
↓  
Cleaned / Not Cleaned  
↓  
Alert + Log + Reassignment  

---

## 🛠️ Tech Stack

### Backend / AI Models
- Python
- OpenCV (Haarcascade)
- KNN Classifier
- YOLOv8

### Frontend
- React (Vite)
- TailwindCSS

### Notifications
- WhatsApp API (Integration Placeholder)

---

## 🔮 Future Enhancements

- Near-bed IoT cleaning sensors
- Bedsheet-change detection
- Blue-light contamination scanning
- Mobile application support
- Cloud-based deployment

---

## 🎯 Project Objective

To build a scalable, automated, and accountable hospital sanitation monitoring framework that enhances hygiene compliance and reduces infection risks using AI-driven validation.

---

## 📌 Current Status

Active Development  
AI Models Completed  
Frontend Integration in Progress
