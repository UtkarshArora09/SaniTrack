from pathlib import Path
import os
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent
load_dotenv(PROJECT_ROOT / '.env')

DATA_DIR = BASE_DIR / 'data'
MODEL_PATH = DATA_DIR / 'models' / 'waste_detector.pt'
FACE_DATASET_DIR = DATA_DIR / 'face_dataset'
EMPLOYEES_JSON = DATA_DIR / 'employees.json'
HAAR_CASCADE_PATH = DATA_DIR / 'haarcascade_frontalface_alt.xml'
UPLOADS_DIR = DATA_DIR / 'uploads'
INSPECTIONS_DIR = DATA_DIR / 'inspections'
DB_PATH = DATA_DIR / 'sanitrack.db'

SECRET_KEY = os.getenv('SANITRACK_SECRET_KEY', 'sanitrack-dev-secret-2026')
DEFAULT_WARDS = ['Emergency', 'ICU', 'Ward 1', 'Ward 2', 'Pediatrics']
CONFIDENCE_THRESHOLD = float(os.getenv('SANITRACK_CONFIDENCE', '0.5'))
FACE_DISTANCE_THRESHOLD = float(os.getenv('SANITRACK_FACE_THRESHOLD', '0.8'))
APP_HOST = os.getenv('SANITRACK_HOST', '0.0.0.0')
APP_PORT = int(os.getenv('PORT', os.getenv('SANITRACK_PORT', '5050')))
APP_DEBUG = os.getenv('SANITRACK_DEBUG', 'false').lower() == 'true'

# Twilio WhatsApp Config
TWILIO_ACCOUNT_SID = os.getenv('TWILIO_ACCOUNT_SID')
TWILIO_AUTH_TOKEN = os.getenv('TWILIO_AUTH_TOKEN')
TWILIO_WHATSAPP_FROM = os.getenv('TWILIO_WHATSAPP_FROM')
ADMIN_WHATSAPP_TO = os.getenv('ADMIN_WHATSAPP_TO')

# IoT & Scheduler Settings
SHIFT_GRACE_PERIOD_MINUTES = int(os.getenv('SHIFT_GRACE_MINUTES', '15'))
CCTV_POLL_INTERVAL_SECONDS = int(os.getenv('CCTV_INTERVAL', '15'))


def notification_config():
    return {
        'twilio_configured': bool(TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN and TWILIO_WHATSAPP_FROM),
        'admin_whatsapp_configured': bool(ADMIN_WHATSAPP_TO),
        'from_number': TWILIO_WHATSAPP_FROM or 'Not configured (Simulation Active)',
        'mode': 'live' if bool(TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN) else 'simulation'
    }
