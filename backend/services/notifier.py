from datetime import datetime, timezone
import re
import collections
from twilio.rest import Client
import config
from database import execute

# In-memory circular buffer for real-time frontend toast notifications
LIVE_NOTIFICATION_FEED = collections.deque(maxlen=30)


def utc_now_iso():
    return datetime.now(timezone.utc).isoformat()


def _is_valid_e164(phone_number):
    return bool(phone_number and re.fullmatch(r'\+[1-9]\d{7,14}', phone_number))


def _send_twilio_whatsapp(phone_number, body):
    if not (config.TWILIO_ACCOUNT_SID and config.TWILIO_AUTH_TOKEN and config.TWILIO_WHATSAPP_FROM and phone_number):
        return {'sent': False, 'reason': 'twilio-not-configured'}
    try:
        client = Client(config.TWILIO_ACCOUNT_SID, config.TWILIO_AUTH_TOKEN)
        message = client.messages.create(
            from_=config.TWILIO_WHATSAPP_FROM,
            body=body,
            to=f'whatsapp:{phone_number}'
        )
        return {'sent': True, 'sid': message.sid}
    except Exception as exc:
        return {'sent': False, 'reason': str(exc)}


def record_notification(ward_name, message, channel='dashboard', delivery_status='queued'):
    execute(
        'INSERT INTO notifications (ward_name, channel, message, delivery_status, created_at) VALUES (?, ?, ?, ?, ?)',
        (ward_name, channel, message, delivery_status, utc_now_iso())
    )
    event = {
        'ward_name': ward_name,
        'message': message,
        'channel': channel,
        'delivery_status': delivery_status,
        'timestamp': utc_now_iso()
    }
    LIVE_NOTIFICATION_FEED.appendleft(event)
    return event


def notify_targets(ward_name, message, employee_phone=None):
    outcomes = []
    targets = []
    
    if _is_valid_e164(employee_phone):
        targets.append(('whatsapp-worker', employee_phone))
    if _is_valid_e164(config.ADMIN_WHATSAPP_TO):
        targets.append(('whatsapp-admin', config.ADMIN_WHATSAPP_TO))

    # If no valid phones found or Twilio unconfigured, record simulated alert so demo/audit never fails
    if not targets:
        outcomes.append(record_notification(
            ward_name,
            f"[Alert] {message}",
            channel='dashboard',
            delivery_status='logged-only'
        ))
        return outcomes

    for channel, phone in targets:
        result = _send_twilio_whatsapp(phone, message)
        if result.get('sent'):
            status = 'sent'
        else:
            # If Twilio credentials are blank, log as simulated delivery for evaluation/testing
            status = f"simulated ({result.get('reason', 'local')})"
        
        outcomes.append(record_notification(
            ward_name,
            f"[{channel.upper()}: {phone}] {message}",
            channel=channel,
            delivery_status=status
        ))

    return outcomes


def get_live_feed():
    return list(LIVE_NOTIFICATION_FEED)
