import concurrent.futures
import gc
import logging
from pathlib import Path
import cv2

logger = logging.getLogger('SaniTrack.YOLO')


class YOLOInferenceEngine:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, model_path=None, confidence_threshold=0.5, inspections_dir=None):
        if self._initialized:
            return
        self.model_path = Path(model_path) if model_path else None
        self.confidence_threshold = float(confidence_threshold)
        self.inspections_dir = Path(inspections_dir) if inspections_dir else None
        self._model = None
        # Single worker queue prevents simultaneous CPU tensor memory peaks on Render Free Tier (512MB RAM)
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix='YOLO_Worker')
        self._initialized = True

    def _ensure_model(self):
        if self._model is not None:
            return self._model
        try:
            import os
            os.environ['YOLO_VERBOSE'] = 'False'
            import torch
            torch.set_num_threads(1)
            try:
                torch.set_num_interop_threads(1)
            except Exception:
                pass
            from ultralytics import YOLO
        except ImportError:
            raise RuntimeError('Ultralytics package is not installed. Please install requirements.txt.')

        if not self.model_path or not self.model_path.exists():
            possible_paths = [
                Path(__file__).resolve().parents[1] / 'backend' / 'data' / 'models' / 'waste_detector.pt',
                Path(__file__).resolve().parent / 'models' / 'waste_detector.pt',
            ]
            for p in possible_paths:
                if p.exists():
                    self.model_path = p
                    break

        if not self.model_path or not self.model_path.exists():
            raise FileNotFoundError(f'Could not find trained YOLO model weights at: {self.model_path}')

        logger.info(f'Loading YOLOv8 weights from: {self.model_path}')
        self._model = YOLO(str(self.model_path))
        return self._model

    def analyze(self, image_path, inspection_id=None):
        """
        Synchronous forward pass on an image with memory safeguards for cloud hosting.
        """
        import torch
        gc.collect()
        model = self._ensure_model()

        # Downscale large images to max 640px to keep RAM usage within Render's 512MB ceiling
        try:
            img = cv2.imread(str(image_path))
            if img is not None:
                h, w = img.shape[:2]
                if max(h, w) > 640:
                    scale = 640 / max(h, w)
                    resized = cv2.resize(img, (int(w * scale), int(h * scale)))
                    cv2.imwrite(str(image_path), resized)
                    del resized
                del img
        except Exception as e:
            logger.warning(f"Could not pre-scale image {image_path}: {e}")

        try:
            with torch.inference_mode():
                results = model.predict(
                    source=str(image_path),
                    conf=self.confidence_threshold,
                    imgsz=640,
                    device='cpu',
                    max_det=10,
                    save=False,
                    verbose=False
                )
        except Exception as pred_err:
            logger.error(f"YOLO forward pass exception: {pred_err}", exc_info=True)
            gc.collect()
            raise pred_err

        result = results[0]
        boxes = result.boxes
        object_found = boxes is not None and len(boxes) > 0
        top_conf = None
        raw_label = None
        object_count = 0
        detections = []


        # Friendly label mapping so the hospital admin never sees confusing internal labels like "bag"
        FRIENDLY_CLASS_NAMES = {
            0: 'Floor Waste / Debris',
            1: 'Floor Debris / Refuse',
            2: 'Metal / Sharp Waste',
            3: 'Plastic Contaminant',
            4: 'Floor Trash'
        }
        if hasattr(result, 'names'):
            result.names = {k: FRIENDLY_CLASS_NAMES.get(k, 'Waste Detected') for k in result.names.keys()}

        if object_found:
            object_count = len(boxes)
            for box in boxes:
                conf = float(box.conf[0])
                class_id = int(box.cls[0]) if box.cls is not None else 0
                label = FRIENDLY_CLASS_NAMES.get(class_id, 'Floor Waste / Debris')
                xyxy = [round(float(v), 2) for v in box.xyxy[0].tolist()]
                detections.append({'label': label, 'confidence': round(conf, 4), 'bbox': xyxy})
                if top_conf is None or conf > top_conf:
                    top_conf = conf
                    raw_label = label

        annotated_path = None
        plotted = result.plot()
        if plotted is not None and self.inspections_dir:
            self.inspections_dir.mkdir(parents=True, exist_ok=True)
            output_name = f'inspection_{inspection_id}.jpg' if inspection_id else f'{Path(image_path).stem}_annotated.jpg'
            annotated_path = self.inspections_dir / output_name
            cv2.imwrite(str(annotated_path), plotted)
            del plotted

        del result
        del results
        gc.collect()

        return {
            'status': 'Not Clean' if object_found else 'Clean',
            'object_found': object_found,
            'object_count': object_count,
            'confidence': round(top_conf, 4) if top_conf is not None else None,
            'raw_label': raw_label,
            'detections': detections,
            'annotated_image': str(annotated_path) if annotated_path else None,
            'message': f"{object_count} waste item(s) localized ({raw_label}). Re-cleaning required." if object_found else 'Floor verified clean and sanitary. No contaminants detected.',
        }

    def submit_async(self, image_path, inspection_id, callback_fn):
        """
        Submits inspection inference to the background ThreadPoolExecutor.
        Calls callback_fn(result, error) upon completion.
        """
        def _task():
            try:
                res = self.analyze(image_path, inspection_id=inspection_id)
                callback_fn(res, None)
            except Exception as err:
                logger.error(f'Background inference failed: {err}', exc_info=True)
                callback_fn(None, err)

        return self.executor.submit(_task)

