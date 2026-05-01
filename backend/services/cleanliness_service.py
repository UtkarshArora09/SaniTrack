from pathlib import Path

import cv2

from config import CONFIDENCE_THRESHOLD, INSPECTIONS_DIR, MODEL_PATH

class CleanlinessService:
    def __init__(self):
        self._model = None

    def _ensure_model(self):
        try:
            from ultralytics import YOLO
        except ImportError:
            raise RuntimeError('Ultralytics is not installed. Install requirements first.')
            
        if self._model is None:
            self._model = YOLO(str(MODEL_PATH))
        return self._model

    def analyze(self, image_path, inspection_id=None):
        model = self._ensure_model()
        results = model.predict(source=str(image_path), conf=CONFIDENCE_THRESHOLD, save=False, verbose=False)
        result = results[0]
        boxes = result.boxes
        object_found = boxes is not None and len(boxes) > 0
        top_conf = None
        raw_label = None
        object_count = 0
        detections = []

        if object_found:
            object_count = len(boxes)
            for box in boxes:
                conf = float(box.conf[0])
                class_id = int(box.cls[0]) if box.cls is not None else 0
                label = result.names.get(class_id, str(class_id)) if hasattr(result, 'names') else str(class_id)
                xyxy = [round(float(v), 2) for v in box.xyxy[0].tolist()]
                detections.append({'label': label, 'confidence': round(conf, 4), 'bbox': xyxy})
                if top_conf is None or conf > top_conf:
                    top_conf = conf
                    raw_label = label

        annotated_path = None
        plotted = result.plot()
        if plotted is not None:
            output_name = f'inspection_{inspection_id}.jpg' if inspection_id else f'{Path(image_path).stem}_annotated.jpg'
            annotated_path = INSPECTIONS_DIR / output_name
            cv2.imwrite(str(annotated_path), plotted)

        return {
            'status': 'Not Clean' if object_found else 'Clean',
            'object_found': object_found,
            'object_count': object_count,
            'confidence': round(top_conf, 4) if top_conf is not None else None,
            'raw_label': raw_label,
            'detections': detections,
            'annotated_image': str(annotated_path) if annotated_path else None,
            'message': 'Waste/object detected on floor' if object_found else 'No visible waste detected on floor',
        }
