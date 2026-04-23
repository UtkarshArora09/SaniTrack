import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
BACKEND_DIR = BASE_DIR / 'backend'
sys.path.insert(0, str(BACKEND_DIR))

from services.face_service import FaceRecognitionService

svc = FaceRecognitionService()
report = svc.quality_report()
print('Global leave-one-out accuracy:', report['global_accuracy'])
for row in report['labels']:
    print(f"{row['employee_key']}: samples={row['sample_count']} accuracy={row['leave_one_out_accuracy']} rival={row['closest_rival']} status={row['status']}")
