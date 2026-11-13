import time
import random
import requests

BASE_URL = 'http://127.0.0.1:5000'
WARDS = ['Emergency', 'ICU', 'Ward 1', 'Ward 2', 'Pediatrics']
SENSOR_TYPES = ['dustbin_level', 'uv_fluorescence', 'bed_proximity']


def emit_iot_telemetry():
    print('=' * 60)
    print('SaniTrack Hospital IoT Telemetry Simulator (Viva Demo)')
    print('=' * 60)

    for i in range(1, 10):
        ward = random.choice(WARDS)
        stype = random.choice(SENSOR_TYPES)

        if stype == 'dustbin_level':
            val = round(random.uniform(30.0, 95.0), 1)
            unit = '%'
        elif stype == 'uv_fluorescence':
            val = round(random.uniform(10.0, 75.0), 1)
            unit = 'RFU'
        else:
            val = round(random.uniform(15.0, 65.0), 1)
            unit = 'sec'

        payload = {
            'device_id': f'ESP32_{ward.replace(" ", "_").upper()}',
            'ward_name': ward,
            'sensor_type': stype,
            'metric_value': val,
            'unit': unit
        }

        try:
            res = requests.post(f'{BASE_URL}/api/iot/telemetry', json=payload, timeout=5)
            if res.status_code == 200:
                data = res.json().get('telemetry', {})
                alert = '🚨 [ALARM TRIGGERED]' if data.get('alert_triggered') else '✅ [NORMAL]'
                print(f"[{i}] Sent {stype:16} for {ward:12} = {val:5.1f} {unit:4} {alert} -> Status: {data.get('status')}")
            else:
                print(f"[{i}] HTTP {res.status_code}: {res.text}")
        except Exception as e:
            print(f"[{i}] Connection failed (Is backend running?): {e}")

        time.sleep(2)

    print("\nIoT telemetry streaming cycle finished.")


if __name__ == '__main__':
    emit_iot_telemetry()

