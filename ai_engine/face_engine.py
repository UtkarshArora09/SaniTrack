import json
from collections import Counter, defaultdict
from pathlib import Path
import cv2
import numpy as np

K_NEIGHBORS = 7
MIN_VOTE_SHARE = 0.55
MIN_MARGIN = 0.015


class FaceEngine:
    def __init__(self, cascade_path, dataset_dir, employees_json_path, distance_threshold=0.8):
        self.cascade_path = Path(cascade_path)
        self.dataset_dir = Path(dataset_dir)
        self.employees_json = Path(employees_json_path)
        self.distance_threshold = float(distance_threshold)
        
        self.cascade = cv2.CascadeClassifier(str(self.cascade_path))
        if self.cascade.empty():
            raise FileNotFoundError(f'Could not load Haar cascade from: {self.cascade_path}')
            
        self.employees = {}
        self.sample_matrix = np.empty((0, 10000), dtype=np.float32)
        self.sample_labels = []
        self.reload()

    def _load_employees(self):
        if not self.employees_json.exists():
            return {}
        try:
            return json.loads(self.employees_json.read_text(encoding='utf-8'))
        except Exception:
            return {}

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
        if not self.dataset_dir.exists():
            return np.empty((0, 10000), dtype=np.float32), []
            
        for file_path in self.dataset_dir.glob('*.npy'):
            try:
                data = np.load(file_path).astype(np.float32)
                if data.size == 0:
                    continue
                samples = data.reshape((-1, 100, 100, 3)).astype(np.uint8)
                processed = np.stack([self._preprocess_face(sample) for sample in samples], axis=0)
                matrices.append(processed)
                labels.extend([file_path.stem] * processed.shape[0])
            except Exception as e:
                continue
                
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
        rival_distance = min(
            (float(np.mean(values)) for key, values in class_mean_dist.items() if key != best_key),
            default=None
        )
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
            return {'matched': False, 'message': 'No face detected in the image.'}
        if len(self.sample_labels) == 0:
            return {'matched': False, 'message': 'No enrolled face samples available in database.'}

        faces = sorted(faces, key=lambda r: r[2] * r[3], reverse=True)
        x, y, w, h = faces[0]
        roi = frame[y:y + h, x:x + w]
        if roi.size == 0:
            return {'matched': False, 'message': 'Face crop extraction failed.'}

        probe = self._preprocess_face(roi)
        classification = self._classify_probe(probe)
        best_key = classification['best_key']
        vote_share = classification['vote_share']
        best_distance = classification['best_distance']
        margin = classification['margin']

        if best_distance > self.distance_threshold or vote_share < MIN_VOTE_SHARE or (margin is not None and margin < MIN_MARGIN):
            return {
                'matched': False,
                'message': 'Face detected but confidence below verification threshold.',
                'distance': round(best_distance, 4),
                'vote_share': round(vote_share, 4),
                'margin': round(margin, 4) if margin is not None else None,
            }

        employee_meta = self.employees.get(best_key, {})
        confidence = max(0.0, 1.0 - min(best_distance, 1.0)) * vote_share
        
        return {
            'matched': True,
            'employee_key': best_key,
            'name': employee_meta.get('name', best_key.capitalize()),
            'designation': employee_meta.get('designation', 'Sanitation Staff'),
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
        correct = 0
        total = len(self.sample_labels)
        
        # Leave-one-out cross validation
        for idx, label in enumerate(self.sample_labels):
            probe = self.sample_matrix[idx]
            mask = np.ones(len(self.sample_labels), dtype=bool)
            mask[idx] = False
            train_matrix = self.sample_matrix[mask]
            train_labels = [self.sample_labels[i] for i in range(len(self.sample_labels)) if i != idx]
            distances = np.linalg.norm(train_matrix - probe, axis=1)
            nearest_idx = np.argsort(distances)[:min(K_NEIGHBORS, len(train_labels))]
            predicted = Counter([train_labels[i] for i in nearest_idx]).most_common(1)[0][0]
            if predicted == label:
                correct += 1

        rows = []
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
                curr_dist = float(np.linalg.norm(same_vectors[:, None, :] - other_vectors[None, :, :], axis=2).mean())
                if rival_distance is None or curr_dist < rival_distance:
                    rival_distance = curr_dist
                    rival_label = other

            label_correct = sum(
                1 for idx in label_indices
                if Counter([
                    self.sample_labels[i] for i in np.argsort(np.linalg.norm(self.sample_matrix - self.sample_matrix[idx], axis=1))[1:K_NEIGHBORS + 1]
                ]).most_common(1)[0][0] == label
            )
            accuracy = label_correct / len(label_indices)
            
            if accuracy >= 0.9 and (rival_distance is None or rival_distance >= self.distance_threshold + 0.06):
                status = 'Strong'
            elif accuracy >= 0.75:
                status = 'Acceptable (More variety recommended)'
            else:
                status = 'Re-enrollment Recommended'
                
            rows.append({
                'employee_key': label,
                'sample_count': len(label_indices),
                'leave_one_out_accuracy': round(accuracy, 4),
                'closest_rival': rival_label,
                'closest_rival_distance': round(rival_distance, 4) if rival_distance is not None else None,
                'status': status,
            })
            
        return {'labels': rows, 'global_accuracy': round(correct / total, 4)}

    def enroll_samples(self, emp_key, face_crops):
        """Append normalized 100x100 BGR crops to dataset and reload engine."""
        if not face_crops:
            return 0
        new_data = np.stack(face_crops, axis=0).reshape((len(face_crops), -1))
        save_path = self.dataset_dir / f"{emp_key}.npy"
        if save_path.exists():
            try:
                existing = np.load(save_path)
                merged = np.concatenate([existing, new_data], axis=0)
            except Exception:
                merged = new_data
        else:
            merged = new_data
        np.save(save_path, merged)
        self.reload()
        return int(merged.shape[0])

    def delete_face(self, emp_key):
        """Delete face recording .npy file and reload engine."""
        save_path = self.dataset_dir / f"{emp_key}.npy"
        if save_path.exists():
            save_path.unlink()
            self.reload()
            return True
        return False


