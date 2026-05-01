# SaniTrack Deployment Guide

Your project is completely ready for deployment on **Render** using Docker! Based on the analysis of your codebase, all necessary configuration files (`Dockerfile`, `render.yaml`, `wsgi.py`) are properly set up and you have successfully pushed them to your GitHub repository.

Here is the step-by-step guide to get your application live:

## Step 1: Connect to Render using Blueprint
Since your repository includes a `render.yaml` file, we can use Render's Blueprint feature to automatically configure your service.

1. Log in to your [Render Dashboard](https://dashboard.render.com/).
2. Click the **New** button in the top right corner and select **Blueprint**.
3. Connect your GitHub account (if you haven't already).
4. Search for and select your repository: `UtkarshArora09/SaniTrack`.
5. Click **Connect**.
6. Render will read your `render.yaml` file and prompt you to create a Web Service named `sanitrack`. Click **Apply**.

## Step 2: Configure Environment Variables
In your `render.yaml`, several sensitive environment variables are configured with `sync: false`. This means you need to manually provide their values in the Render dashboard for security reasons.

1. Once the service is created, click on your **`sanitrack`** Web Service in the Render dashboard.
2. Navigate to the **Environment** tab on the left menu.
3. You will see several empty environment variables. Fill in the values for:
   - `TWILIO_ACCOUNT_SID`
   - `TWILIO_AUTH_TOKEN`
   - `TWILIO_WHATSAPP_FROM`
   - `ADMIN_WHATSAPP_TO`
4. Click **Save Changes**.

## Step 3: Monitor Deployment
1. Navigate to the **Events** or **Logs** tab of your `sanitrack` service on Render.
2. You will see Render building your Docker image (installing system dependencies like `libgl1` for OpenCV and installing your Python packages).
3. Once the build finishes, Render will start the application using Gunicorn.
4. When you see the message indicating the service is live, click the **URL** provided by Render at the top of the dashboard (e.g., `https://sanitrack.onrender.com`) to access your live application.

> [!NOTE]
> **Data Persistence:** Because you are deploying on the Free tier, Render provides an ephemeral file system. This means any newly uploaded images (`data/uploads`), generated inspections (`data/inspections`), or updates to the SQLite database (`data/sanitrack.db`) will be reset every time the application restarts or redeploys. For a fully production-ready environment, you may want to consider using a persistent PostgreSQL database and cloud storage (like AWS S3) in the future.
