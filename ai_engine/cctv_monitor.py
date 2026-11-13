import threading
import time
import logging
from pathlib import Path
import cv2

logger = logging.getLogger('SaniTrack.CCTV')


class CCTVStreamMonitor:
    """
    Automated background CCTV ingestion and auditing worker.
    Continuously monitors camera streams for assigned wards and performs automated inspections.
    """
    def __init__(self, yolo_engine, db_execute_fn, notify_fn, uploads_dir):
        self.yolo = yolo_engine
        self.execute = db_execute_fn
        self.notify = notify_fn
        self.uploads_dir = Path(uploads_dir)
        self.active_monitors = {}  # ward_name -> thread
        self.running_flags = {}    # ward_name -> bool

    def start_monitoring(self, ward_name, source=0, interval_seconds=15):
        if ward_name in self.running_flags and self.running_flags[ward_name]:
            return {'status': 'already_running', 'ward': ward_name}

        self.running_flags[ward_name] = True
        worker = threading.Thread(
            target=self._monitor_loop,
            args=(ward_name, source, interval_seconds),
            daemon=True,
            name=f'CCTV_{ward_name}'
        )
        self.active_monitors[ward_name] = worker
        worker.start()
        logger.info(f'Started automated CCTV monitoring for {ward_name} (interval={interval_seconds}s)')
        return {'status': 'started', 'ward': ward_name, 'interval': interval_seconds}

    def stop_monitoring(self, ward_name):
        if ward_name in self.running_flags:
            self.running_flags[ward_name] = False
            return {'status': 'stopped', 'ward': ward_name}
        return {'status': 'not_running', 'ward': ward_name}

    def is_monitoring(self, ward_name):
        return self.running_flags.get(ward_name, False)

    def _monitor_loop(self, ward_name, source, interval):
        self.uploads_dir.mkdir(parents=True, exist_ok=True)
        # Attempt to open video capture (camera index 0/1 or video file or simulated loop)
        cap = None
        try:
            # If source is integer or string representing integer
            src_val = int(source) if str(source).isdigit() else source
            cap = cv2.VideoCapture(src_val)
        except Exception:
            cap = None

        while self.running_flags.get(ward_name, False):
            try:
                frame = None
                if cap and cap.isOpened():
                    ret, raw_frame = cap.read()
                    if ret and raw_frame is not None:
                        frame = raw_frame

                if frame is None:
                    # If live camera isn't attached, create a mock test capture or read last uploaded image
                    # to keep the monitoring pipeline robust during testing/demonstration
                    frame_path = self.uploads_dir / f'cctv_auto_{ward_name.lower().replace(" ", "_")}.jpg'
                    if frame_path.exists():
                        frame = cv2.imread(str(frame_path))

                if frame is not None:
                    timestamp_str = time.strftime('%Y%m%d_%H%M%S')
                    snapshot_path = self.uploads_dir / f'cctv_{ward_name}_{timestamp_str}.jpg'
                    cv2.imwrite(str(snapshot_path), frame)

                    # Insert inspection record
                    from datetime import datetime, timezone
                    now_iso = datetime.now(timezone.utc).isoformat()
                    inspection_id = self.execute(
                        '''INSERT INTO inspection_logs 
                           (ward_name, employee_key, status, object_found, confidence, object_count, raw_label, source_image, annotated_image, notes, created_at)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                        (ward_name, 'cctv_auto', 'Processing', 0, None, 0, None, str(snapshot_path), None, 'Automated CCTV surveillance frame', now_iso)
                    )

                    analysis = self.yolo.analyze(snapshot_path, inspection_id=inspection_id)

                    self.execute(
                        '''UPDATE inspection_logs 
                           SET status = ?, object_found = ?, confidence = ?, object_count = ?, raw_label = ?, annotated_image = ?, notes = ? 
                           WHERE id = ?''',
                        (
                            analysis['status'],
                            1 if analysis['object_found'] else 0,
                            analysis['confidence'],
                            analysis['object_count'],
                            analysis['raw_label'],
                            analysis['annotated_image'],
                            'Automated CCTV inspection completed',
                            inspection_id
                        )
                    )

                    if analysis['object_found']:
                        msg = f"CCTV Alert: {ward_name} flagged Not Clean. Waste detected in automated video sweep."
                        self.notify(ward_name, msg)

            except Exception as e:
                logger.error(f'Error in CCTV monitor loop for {ward_name}: {e}')

            # Sleep interval
            for _ in range(interval):
                if not self.running_flags.get(ward_name, False):
                    break
                time.sleep(1)

        if cap and cap.isOpened():
            cap.release()
        logger.info(f'CCTV monitoring stopped for {ward_name}')

