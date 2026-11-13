from datetime import datetime, timezone
import re
import collections
import urllib.parse
import requests
from twilio.rest import Client
import config
from database import execute

# In-memory circular buffer for real-time frontend toast notifications
LIVE_NOTIFICATION_FEED = collections.deque(maxlen=30)


def utc_now_iso():
    return datetime.now(timezone.utc).isoformat()


def _is_valid_e164(phone_number):
    return bool(phone_number and re.fullmatch(r'\+[1-9]\d{7,14}', phone_number))


# 1. Telegram Bot (100% Free Forever)
def _send_telegram(message, chat_id=None):
    target_chat = chat_id or config.TELEGRAM_CHAT_ID
    if not (config.TELEGRAM_BOT_TOKEN and target_chat):
        return {'sent': False, 'reason': 'telegram-not-configured'}
    try:
        url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            'chat_id': target_chat,
            'text': f"🏥 *SaniTrack Hospital Alert*\n{message}",
            'parse_mode': 'Markdown'
        }
        res = requests.post(url, json=payload, timeout=8)
        data = res.json()
        return {'sent': data.get('ok', False), 'data': data}
    except Exception as exc:
        return {'sent': False, 'reason': str(exc)}


# 2. Discord Webhook (100% Free Forever)
def _send_discord(message):
    if not config.DISCORD_WEBHOOK_URL:
        return {'sent': False, 'reason': 'discord-not-configured'}
    try:
        payload = {'content': f"🚨 **SaniTrack Hospital Alert**\n{message}"}
        res = requests.post(config.DISCORD_WEBHOOK_URL, json=payload, timeout=8)
        return {'sent': 200 <= res.status_code < 300, 'status_code': res.status_code}
    except Exception as exc:
        return {'sent': False, 'reason': str(exc)}


# 3. CallMeBot Free WhatsApp Gateway (Free)
def _send_callmebot_whatsapp(phone, message):
    phone_to_use = phone or config.CALLMEBOT_PHONE
    if not (phone_to_use and config.CALLMEBOT_API_KEY):
        return {'sent': False, 'reason': 'callmebot-not-configured'}
    try:
        clean_phone = phone_to_use.replace('+', '').replace(' ', '')
        encoded_text = urllib.parse.quote_plus(f"🏥 SaniTrack: {message}")
        url = f"https://api.callmebot.com/whatsapp.php?phone={clean_phone}&text={encoded_text}&apikey={config.CALLMEBOT_API_KEY}"
        res = requests.get(url, timeout=10)
        return {'sent': res.status_code == 200, 'response': res.text[:100]}
    except Exception as exc:
        return {'sent': False, 'reason': str(exc)}


# 4. Twilio WhatsApp
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


def notify_targets(ward_name, message, employee_phone=None, employee_chat_id=None):
    outcomes = []
    dispatched_any = False

    # 1. Telegram (Admin + Assigned Worker)
    if config.TELEGRAM_BOT_TOKEN:
        # 1a. Admin / Supervisor Alert
        if config.TELEGRAM_CHAT_ID:
            tg_res = _send_telegram(f"[{ward_name}] {message}", chat_id=config.TELEGRAM_CHAT_ID)
            status = 'sent' if tg_res.get('sent') else f"failed ({tg_res.get('reason')})"
            outcomes.append(record_notification(ward_name, message, channel='telegram', delivery_status=status))
            dispatched_any = True

        # 1b. Worker Personal Alert (if configured)
        target_worker_chat = employee_chat_id or config.WORKER_TELEGRAM_CHAT_ID
        if not target_worker_chat and employee_phone:
            try:
                from database import fetch_one
                emp = fetch_one('SELECT telegram_chat_id FROM employees WHERE phone = ?', (employee_phone,))
                if emp and emp.get('telegram_chat_id'):
                    target_worker_chat = emp['telegram_chat_id']
            except Exception:
                pass

        if target_worker_chat and str(target_worker_chat) != str(config.TELEGRAM_CHAT_ID):
            worker_msg = f"🔔 *Ward Task Dispatch*\nWard: *{ward_name}*\n{message}"
            tg_w_res = _send_telegram(worker_msg, chat_id=target_worker_chat)
            w_status = 'sent' if tg_w_res.get('sent') else f"failed ({tg_w_res.get('reason')})"
            outcomes.append(record_notification(ward_name, f"[WORKER DISPATCH] {message}", channel='telegram-worker', delivery_status=w_status))
            dispatched_any = True


    # 2. Try Discord Webhook (Free)
    if config.DISCORD_WEBHOOK_URL:
        dc_res = _send_discord(f"[{ward_name}] {message}")
        status = 'sent' if dc_res.get('sent') else f"failed ({dc_res.get('reason')})"
        outcomes.append(record_notification(ward_name, message, channel='discord', delivery_status=status))
        dispatched_any = True

    # 3. Try CallMeBot Free WhatsApp
    if config.CALLMEBOT_PHONE and config.CALLMEBOT_API_KEY:
        cmb_res = _send_callmebot_whatsapp(employee_phone or config.CALLMEBOT_PHONE, message)
        status = 'sent' if cmb_res.get('sent') else f"failed ({cmb_res.get('reason')})"
        outcomes.append(record_notification(ward_name, message, channel='whatsapp-free', delivery_status=status))
        dispatched_any = True

    # 4. Try Twilio WhatsApp (if configured)
    targets = []
    if _is_valid_e164(employee_phone):
        targets.append(('whatsapp-worker', employee_phone))
    if _is_valid_e164(config.ADMIN_WHATSAPP_TO):
        targets.append(('whatsapp-admin', config.ADMIN_WHATSAPP_TO))

    for channel, phone in targets:
        result = _send_twilio_whatsapp(phone, message)
        if result.get('sent'):
            status = 'sent'
            dispatched_any = True
        else:
            status = f"simulated ({result.get('reason', 'local')})"
        
        outcomes.append(record_notification(
            ward_name,
            f"[{channel.upper()}: {phone}] {message}",
            channel=channel,
            delivery_status=status
        ))

    # Always ensure at least dashboard toast is recorded
    if not dispatched_any:
        outcomes.append(record_notification(
            ward_name,
            f"[Live Toast] {message}",
            channel='dashboard',
            delivery_status='logged-only'
        ))

    return outcomes


def get_live_feed():
    return list(LIVE_NOTIFICATION_FEED)
