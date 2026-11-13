import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BACKEND_DIR = ROOT / 'backend'
for p in [str(ROOT), str(BACKEND_DIR)]:
    if p not in sys.path:
        sys.path.insert(0, p)

from app import app

if __name__ == '__main__':
    app.run(host=os.getenv('SANITRACK_HOST', '0.0.0.0'), port=int(os.getenv('PORT', os.getenv('SANITRACK_PORT', '5050'))))
