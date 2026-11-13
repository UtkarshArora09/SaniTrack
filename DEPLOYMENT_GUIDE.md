# SaniTrack — Production Deployment Guide

This guide covers deploying SaniTrack using **Render**, **Railway**, or **Docker Compose (Local/VPS)**.

---

## 1. Quick Deploy on Render (Recommended)

Since the repository includes a [`render.yaml`](./render.yaml) blueprint and [`Dockerfile`](./Dockerfile), Render deploys the entire stack automatically.

### Steps:
1. Push your latest code to GitHub (`https://github.com/UtkarshArora09/SaniTrack`).
2. Log in to [Render Dashboard](https://dashboard.render.com/).
3. Click **New +** &rarr; **Blueprint**.
4. Select your repository: `UtkarshArora09/SaniTrack`.
5. Render reads `render.yaml` and auto-configures:
   * **Runtime**: Docker (Python 3.12 + OpenCV + PyTorch/YOLO)
   * **Health Check**: `/api/health`
   * **Port**: Dynamic (`$PORT`)
6. Click **Apply**.
7. In the **Environment** tab on Render, optionally set your Twilio telephony keys:
   * `TWILIO_ACCOUNT_SID`
   * `TWILIO_AUTH_TOKEN`
   * `TWILIO_WHATSAPP_FROM`
   * `ADMIN_WHATSAPP_TO`
8. Once built, click your live URL (e.g., `https://sanitrack.onrender.com`).

---

## 2. Deploy on Railway

1. Log in to [Railway.app](https://railway.app/).
2. Click **New Project** &rarr; **Deploy from GitHub Repo**.
3. Select `UtkarshArora09/SaniTrack`.
4. Railway detects the `Dockerfile` automatically.
5. In **Variables**, add:
   * `SANITRACK_SECRET_KEY`: (generate a random string)
   * `SANITRACK_PORT`: `5050`
6. Click **Deploy**. Railway will generate a public domain (e.g. `https://sanitrack.up.railway.app`).

---

## 3. Deploy with Docker Compose (Local / Cloud VPS)

Run the containerized stack locally or on any cloud server (AWS, GCP, DigitalOcean):

```bash
# 1. Clone repository
git clone https://github.com/UtkarshArora09/SaniTrack.git
cd SaniTrack

# 2. Configure environment
cp .env.example .env

# 3. Start containers
docker compose up -d --build
```
Access the application at: `http://localhost:5050`

---

## 4. Environment Variables Reference

| Variable | Default | Purpose |
| :--- | :--- | :--- |
| `PORT` / `SANITRACK_PORT` | `5050` | HTTP port for the web server |
| `SANITRACK_SECRET_KEY` | `sanitrack-dev-secret` | Session and token encryption key |
| `SANITRACK_CONFIDENCE` | `0.5` | YOLOv8 minimum detection threshold |
| `SANITRACK_FACE_THRESHOLD` | `0.8` | Face biometric distance verification threshold |
| `TWILIO_ACCOUNT_SID` | *Optional* | Twilio API Account SID for WhatsApp alerts |
| `TWILIO_AUTH_TOKEN` | *Optional* | Twilio API Auth Token |
| `TWILIO_WHATSAPP_FROM` | *Optional* | Twilio WhatsApp sender number |
| `ADMIN_WHATSAPP_TO` | *Optional* | Hospital Director/Admin phone number |
