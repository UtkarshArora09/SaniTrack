from datetime import datetime, timezone
import re

from twilio.rest import Client

from config import ADMIN_WHATSAPP_TO, TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_WHATSAPP_FROM
from database import execute


def utc_now_iso():
    return datetime.now(timezone.utc).isoformat()


def _is_valid_e164(phone_number):
    return bool(phone_number and re.fullmatch(r'\+[1-9]\d{7,14}', phone_number))


def _send_twilio_whatsapp(phone_number, body):
    if not (TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN and TWILIO_WHATSAPP_FROM and phone_number):
        return {'sent': False, 'reason': 'twilio-not-configured'}
    client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
    message = client.messages.create(from_=TWILIO_WHATSAPP_FROM, body=body, to=f'whatsapp:{phone_number}')
    return {'sent': True, 'sid': message.sid}


def record_notification(ward_name, message, channel='dashboard', delivery_status='queued'):
    execute('INSERT INTO notifications (ward_name, channel, message, delivery_status, created_at) VALUES (?, ?, ?, ?, ?)', (ward_name, channel, message, delivery_status, utc_now_iso()))
    return {'ward_name': ward_name, 'message': message, 'channel': channel, 'delivery_status': delivery_status}


def notify_targets(ward_name, message, employee_phone=None):
    outcomes = []
    targets = []
    if _is_valid_e164(employee_phone):
        targets.append(('whatsapp-worker', employee_phone))
    if _is_valid_e164(ADMIN_WHATSAPP_TO):
        targets.append(('whatsapp-admin', ADMIN_WHATSAPP_TO))

    if not targets:
        outcomes.append(record_notification(ward_name, message, channel='dashboard', delivery_status='logged-only'))
        return outcomes

    for channel, phone in targets:
        try:
            result = _send_twilio_whatsapp(phone, message)
            status = 'sent' if result.get('sent') else result.get('reason', 'not-sent')
        except Exception as exc:
            status = f'error: {exc}'
        outcomes.append(record_notification(ward_name, message, channel=channel, delivery_status=status))
    return outcomes
