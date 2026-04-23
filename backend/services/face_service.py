import json
from collections import Counter, defaultdict
from pathlib import Path

import cv2
import numpy as np

from config import EMPLOYEES_JSON, FACE_DATASET_DIR, FACE_DISTANCE_THRESHOLD, HAAR_CASCADE_PATH

K_NEIGHBORS = 7
MIN_VOTE_SHARE = 0.55
MIN_MARGIN = 0.015


class FaceRecognitionService:
    def __init__(self):
        self.cascade = cv2.CascadeClassifier(str(HAAR_CASCADE_PATH))
        if self.cascade.empty():
            raise FileNotFoundError(f'Could not load Haar cascade from {HAAR_CASCADE_PATH}')
        self.employees = {}
        self.sample_matrix = np.empty((0, 10000), dtype=np.float32)
        self.sample_labels = []
        self.reload()

    def _load_employees(self):
        if not EMPLOYEES_JSON.exists():
            return {}
        return json.loads(EMPLOYEES_JSON.read_text(encoding='utf-8'))

    def _preprocess_face(self, face_bgr):
        resized = cv2.resize(face_bgr, (100, 100), interpolation=cv2.INTER_AREA)
        gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)
        gray = cv2.equalizeHist(gray)
        blurred = cv2.GaussianBlur(gray, (3, 3), 0)
        vector = blurred.flatten().astype(np.float32)
        norm = np.linalg.norm(vector)
        return vector / (norm if norm else 1.0)

    def _load_samples(self):
        matrices = []
        labels = []
        for file_path in Path(FACE_DATASET_DIR).glob('*.npy'):
            data = np.load(file_path).astype(np.float32)
            if data.size == 0:
                continue
            samples = data.reshape((-1, 100, 100, 3)).astype(np.uint8)
            processed = np.stack([self._preprocess_face(sample) for sample in samples], axis=0)
            matrices.append(processed)
            labels.extend([file_path.stem] * processed.shape[0])
        if not matrices:
            return np.empty((0, 10000), dtype=np.float32), []
        return np.concatenate(matrices, axis=0), labels

    def reload(self):
        self.employees = self._load_employees()
        self.sample_matrix, self.sample_labels = self._load_samples()

    def _classify_probe(self, probe):
        distances = np.linalg.norm(self.sample_matrix - probe, axis=1)
        neighbor_count = min(K_NEIGHBORS, len(self.sample_labels))
        nearest_idx = np.argsort(distances)[:neighbor_count]
        nearest_labels = [self.sample_labels[i] for i in nearest_idx]
        vote_counts = Counter(nearest_labels)
        best_key, best_votes = vote_counts.most_common(1)[0]
        vote_share = best_votes / neighbor_count
        class_mean_dist = defaultdict(list)
        for idx in nearest_idx:
            class_mean_dist[self.sample_labels[idx]].append(float(distances[idx]))
        best_distance = float(np.mean(class_mean_dist[best_key]))
        rival_distance = min((float(np.mean(values)) for key, values in class_mean_dist.items() if key != best_key), default=None)
        margin = (rival_distance - best_distance) if rival_distance is not None else None
        return {
            'best_key': best_key,
            'vote_share': vote_share,
            'best_distance': best_distance,
            'rival_distance': rival_distance,
            'margin': margin,
        }

    def recognize(self, image_path):
        frame = cv2.imread(str(image_path))
        if frame is None:
            return {'matched': False, 'message': 'Unable to read image file.'}
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = self.cascade.detectMultiScale(gray, scaleFactor=1.2, minNeighbors=5, minSize=(60, 60))
        if len(faces) == 0:
            return {'matched': False, 'message': 'No face detected in the uploaded image.'}
        if len(self.sample_labels) == 0:
            return {'matched': False, 'message': 'No enrolled face samples available.'}

        faces = sorted(faces, key=lambda r: r[2] * r[3], reverse=True)
        x, y, w, h = faces[0]
        roi = frame[y:y + h, x:x + w]
        if roi.size == 0:
            return {'matched': False, 'message': 'Face crop failed.'}

        probe = self._preprocess_face(roi)
        classification = self._classify_probe(probe)
        best_key = classification['best_key']
        vote_share = classification['vote_share']
        best_distance = classification['best_distance']
        margin = classification['margin']

        if best_distance > FACE_DISTANCE_THRESHOLD or vote_share < MIN_VOTE_SHARE or (margin is not None and margin < MIN_MARGIN):
            return {
                'matched': False,
                'message': 'Face not recognized confidently enough.',
                'distance': round(best_distance, 4),
                'vote_share': round(vote_share, 4),
                'margin': round(margin, 4) if margin is not None else None,
            }

        employee_meta = self.employees.get(best_key, {})
        confidence = max(0.0, 1.0 - min(best_distance, 1.0)) * vote_share
        return {
            'matched': True,
            'employee_key': best_key,
            'name': employee_meta.get('name', best_key),
            'designation': employee_meta.get('designation', 'Unknown'),
            'distance': round(best_distance, 4),
            'vote_share': round(vote_share, 4),
            'margin': round(margin, 4) if margin is not None else None,
            'confidence': round(confidence, 4),
            'bbox': [int(x), int(y), int(w), int(h)],
        }

    def quality_report(self):
        if len(self.sample_labels) == 0:
            return {'labels': [], 'global_accuracy': 0.0}
        labels = sorted(set(self.sample_labels))
        rows = []
        correct = 0
        total = len(self.sample_labels)
        for idx, label in enumerate(self.sample_labels):
            probe = self.sample_matrix[idx]
            mask = np.ones(len(self.sample_labels), dtype=bool)
            mask[idx] = False
            train_matrix = self.sample_matrix[mask]
            train_labels = [self.sample_labels[i] for i in range(len(self.sample_labels)) if i != idx]
            distances = np.linalg.norm(train_matrix - probe, axis=1)
            nearest_idx = np.argsort(distances)[:min(K_NEIGHBORS, len(train_labels))]
            nearest_labels = [train_labels[i] for i in nearest_idx]
            predicted = Counter(nearest_labels).most_common(1)[0][0]
            if predicted == label:
                correct += 1

        for label in labels:
            label_indices = [i for i, current in enumerate(self.sample_labels) if current == label]
            same_vectors = self.sample_matrix[label_indices]
            rival_distance = None
            rival_label = None
            for other in labels:
                if other == label:
                    continue
                other_indices = [i for i, current in enumerate(self.sample_labels) if current == other]
                other_vectors = self.sample_matrix[other_indices]
                current_distance = float(np.linalg.norm(same_vectors[:, None, :] - other_vectors[None, :, :], axis=2).mean())
                if rival_distance is None or current_distance < rival_distance:
                    rival_distance = current_distance
                    rival_label = other

            label_correct = 0
            for idx in label_indices:
                probe = self.sample_matrix[idx]
                mask = np.ones(len(self.sample_labels), dtype=bool)
                mask[idx] = False
                train_matrix = self.sample_matrix[mask]
                train_labels = [self.sample_labels[i] for i in range(len(self.sample_labels)) if i != idx]
                distances = np.linalg.norm(train_matrix - probe, axis=1)
                nearest_idx = np.argsort(distances)[:min(K_NEIGHBORS, len(train_labels))]
                predicted = Counter([train_labels[i] for i in nearest_idx]).most_common(1)[0][0]
                if predicted == label:
                    label_correct += 1

            accuracy = label_correct / len(label_indices)
            if accuracy >= 0.9 and (rival_distance is None or rival_distance >= FACE_DISTANCE_THRESHOLD + 0.06):
                status = 'Strong'
            elif accuracy >= 0.75:
                status = 'Needs more variety'
            else:
                status = 'Re-enroll recommended'
            rows.append({
                'employee_key': label,
                'sample_count': len(label_indices),
                'leave_one_out_accuracy': round(accuracy, 4),
                'closest_rival': rival_label,
                'closest_rival_distance': round(rival_distance, 4) if rival_distance is not None else None,
                'status': status,
            })
        return {'labels': rows, 'global_accuracy': round(correct / total, 4)}
