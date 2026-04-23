from pathlib import Path
import os

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR.parent / '.env')

DATA_DIR = BASE_DIR / 'data'
MODEL_PATH = DATA_DIR / 'models' / 'waste_detector.pt'
FACE_DATASET_DIR = DATA_DIR / 'face_dataset'
EMPLOYEES_JSON = DATA_DIR / 'employees.json'
HAAR_CASCADE_PATH = DATA_DIR / 'haarcascade_frontalface_alt.xml'
UPLOADS_DIR = DATA_DIR / 'uploads'
INSPECTIONS_DIR = DATA_DIR / 'inspections'
DB_PATH = DATA_DIR / 'sanitrack.db'

SECRET_KEY = os.getenv('SANITRACK_SECRET_KEY', 'sanitrack-dev-secret')
DEFAULT_WARDS = ['Emergency', 'ICU', 'Ward 1', 'Ward 2', 'Pediatrics']
CONFIDENCE_THRESHOLD = float(os.getenv('SANITRACK_CONFIDENCE', '0.5'))
FACE_DISTANCE_THRESHOLD = float(os.getenv('SANITRACK_FACE_THRESHOLD', '0.8'))

TWILIO_ACCOUNT_SID = os.getenv('TWILIO_ACCOUNT_SID')
TWILIO_AUTH_TOKEN = os.getenv('TWILIO_AUTH_TOKEN')
TWILIO_WHATSAPP_FROM = os.getenv('TWILIO_WHATSAPP_FROM')
ADMIN_WHATSAPP_TO = os.getenv('ADMIN_WHATSAPP_TO')


def notification_config():
    return {
        'twilio_configured': bool(TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN and TWILIO_WHATSAPP_FROM),
        'admin_whatsapp_configured': bool(ADMIN_WHATSAPP_TO),
        'from_number': TWILIO_WHATSAPP_FROM,
    }
