import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BACKEND_DIR = ROOT / 'backend'
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app import app

if __name__ == '__main__':
    app.run(host=os.getenv('SANITRACK_HOST', '0.0.0.0'), port=int(os.getenv('PORT', '5000')))
