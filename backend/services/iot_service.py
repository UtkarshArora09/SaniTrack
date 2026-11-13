import logging
from database import execute, fetch_all, fetch_one, utc_now_iso

logger = logging.getLogger('SaniTrack.IoT')

DUSTBIN_ALERT_THRESHOLD = 80.0  # Percentage
UV_STAIN_THRESHOLD = 45.0       # Fluorescence index
BED_CLEANING_MOTION_MIN_SEC = 30 # Interaction time in seconds


class IoTService:
    def __init__(self, notify_fn):
        self.notify = notify_fn

    def record_telemetry(self, device_id: str, ward_name: str, sensor_type: str, metric_value: float, unit: str = None):
        """
        Processes and stores an incoming IoT sensor reading.
        Applies automated threshold triggers and hospital workflow alerts.
        """
        unit = unit or ('%' if 'level' in sensor_type or 'fill' in sensor_type else 'index')
        metric_value = float(metric_value)
        status = 'Normal'
        alert_msg = None

        # 1. Smart Dustbin Fill Level
        if sensor_type in ('dustbin_level', 'bin_fill'):
            if metric_value >= DUSTBIN_ALERT_THRESHOLD:
                status = 'Critical'
                alert_msg = f"IoT Alert: Dustbin in {ward_name} is at {metric_value:.1f}% capacity. Emptying required immediately."
            elif metric_value >= 60.0:
                status = 'Warning'

        # 2. Blue-Light / UV Micro-Contamination Sensor
        elif sensor_type in ('uv_fluorescence', 'micro_stain'):
            if metric_value >= UV_STAIN_THRESHOLD:
                status = 'Contaminated'
                alert_msg = f"IoT Micro-Stain Alert: High biological residue detected in {ward_name} (Index: {metric_value:.1f})."
            else:
                status = 'Sanitized'

        # 3. Near-Bed Motion / Cleaning Sensor
        elif sensor_type in ('bed_proximity', 'cleaning_motion'):
            if metric_value >= BED_CLEANING_MOTION_MIN_SEC:
                status = 'Bed Sanitized'
            else:
                status = 'Incomplete'

        # Insert telemetry log
        execute(
            '''INSERT INTO iot_telemetry (device_id, ward_name, sensor_type, metric_value, unit, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)''',
            (device_id, ward_name, sensor_type, metric_value, unit, status, utc_now_iso())
        )

        # Trigger notification if anomalous
        if alert_msg:
            self.notify(ward_name, alert_msg)

        return {
            'device_id': device_id,
            'ward_name': ward_name,
            'sensor_type': sensor_type,
            'metric_value': metric_value,
            'unit': unit,
            'status': status,
            'alert_triggered': bool(alert_msg)
        }

    def get_latest_telemetry(self, limit=20):
        return fetch_all(
            '''SELECT * FROM iot_telemetry ORDER BY created_at DESC LIMIT ?''',
            (limit,)
        )

    def get_ward_sensor_summary(self):
        """Returns the latest sensor status grouped by ward and sensor type."""
        rows = fetch_all(
            '''SELECT t1.* FROM iot_telemetry t1
               JOIN (
                   SELECT ward_name, sensor_type, MAX(created_at) as max_time
                   FROM iot_telemetry
                   GROUP BY ward_name, sensor_type
               ) t2 ON t1.ward_name = t2.ward_name AND t1.sensor_type = t2.sensor_type AND t1.created_at = t2.max_time
               ORDER BY t1.ward_name'''
        )
        return rows

