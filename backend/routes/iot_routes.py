import random
from flask import Blueprint, request, jsonify
from services.iot_service import IoTService
from services.notifier import notify_targets

iot_bp = Blueprint('iot_bp', __name__)
iot_service = IoTService(notify_fn=notify_targets)


@iot_bp.post('/api/iot/telemetry')
def receive_telemetry():
    data = request.get_json(force=True) if request.data else {}
    device_id = (data.get('device_id') or 'ESP32_DEV_01').strip()
    ward_name = (data.get('ward_name') or 'Emergency').strip()
    sensor_type = (data.get('sensor_type') or 'dustbin_level').strip().lower()
    
    try:
        metric_value = float(data.get('metric_value', 0.0))
    except (ValueError, TypeError):
        return jsonify({'error': 'metric_value must be a valid number'}), 400
        
    unit = data.get('unit')
    result = iot_service.record_telemetry(
        device_id=device_id,
        ward_name=ward_name,
        sensor_type=sensor_type,
        metric_value=metric_value,
        unit=unit
    )
    return jsonify({'status': 'recorded', 'telemetry': result})


@iot_bp.get('/api/iot/telemetry')
def get_telemetry():
    limit = int(request.args.get('limit', 20))
    telemetry = iot_service.get_latest_telemetry(limit=limit)
    return jsonify({'telemetry': telemetry})


@iot_bp.get('/api/iot/summary')
def get_summary():
    summary = iot_service.get_ward_sensor_summary()
    return jsonify({'summary': summary})


@iot_bp.post('/api/iot/simulate')
def simulate_sensor_reading():
    """Allows one-click demonstration of IoT hardware alerts during presentations."""
    data = request.get_json(force=True) if request.data else {}
    sensor_type = data.get('sensor_type', 'dustbin_level')
    ward_name = data.get('ward_name', 'Ward 1')

    if sensor_type == 'dustbin_level':
        # Simulate high fill level crossing 85%
        value = random.uniform(82.0, 96.0)
        unit = '%'
    elif sensor_type == 'uv_fluorescence':
        # Simulate blue-light contamination
        value = random.uniform(50.0, 85.0)
        unit = 'RFU'
    else:
        # Near-bed cleaning motion
        value = random.uniform(35.0, 60.0)
        unit = 'sec'

    result = iot_service.record_telemetry(
        device_id=f"SIM_{sensor_type.upper()}",
        ward_name=ward_name,
        sensor_type=sensor_type,
        metric_value=value,
        unit=unit
    )
    return jsonify({'status': 'simulated', 'telemetry': result})

