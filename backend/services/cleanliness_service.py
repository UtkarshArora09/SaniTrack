from pathlib import Path
import config
from ai_engine.yolo_service import YOLOInferenceEngine


class CleanlinessService:
    def __init__(self):
        self.engine = YOLOInferenceEngine(
            model_path=config.MODEL_PATH,
            confidence_threshold=config.CONFIDENCE_THRESHOLD,
            inspections_dir=config.INSPECTIONS_DIR
        )

    def analyze(self, image_path, inspection_id=None):
        return self.engine.analyze(image_path, inspection_id=inspection_id)

    def submit_async(self, image_path, inspection_id, callback_fn):
        return self.engine.submit_async(image_path, inspection_id, callback_fn)
