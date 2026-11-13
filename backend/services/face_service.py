import config
from ai_engine.face_engine import FaceEngine


class FaceRecognitionService:
    def __init__(self):
        self.engine = FaceEngine(
            cascade_path=config.HAAR_CASCADE_PATH,
            dataset_dir=config.FACE_DATASET_DIR,
            employees_json_path=config.EMPLOYEES_JSON,
            distance_threshold=config.FACE_DISTANCE_THRESHOLD
        )

    def reload(self):
        self.engine.reload()

    def recognize(self, image_path):
        return self.engine.recognize(image_path)

    def quality_report(self):
        return self.engine.quality_report()

    def enroll_samples(self, emp_key, face_crops):
        return self.engine.enroll_samples(emp_key, face_crops)

    def delete_face(self, emp_key):
        return self.engine.delete_face(emp_key)

