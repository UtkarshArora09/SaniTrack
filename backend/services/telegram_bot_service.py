import threading
import time
import logging
import requests
import config
from database import execute, fetch_one, fetch_all

logger = logging.getLogger('SaniTrack.TelegramBot')


class TelegramBotDaemon(threading.Thread):
    def __init__(self, interval_seconds=4):
        super().__init__(daemon=True, name="TelegramBotDaemon")
        self.interval = interval_seconds
        self.running = False
        self.last_update_id = 0

    def send_reply(self, chat_id, text):
        if not config.TELEGRAM_BOT_TOKEN:
            return
        url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"
        try:
            requests.post(url, json={
                'chat_id': chat_id,
                'text': text,
                'parse_mode': 'Markdown'
            }, timeout=8)
        except Exception as e:
            logger.error(f"Failed to send Telegram reply to {chat_id}: {e}")

    def handle_message(self, message):
        chat = message.get('chat', {})
        chat_id = chat.get('id')
        text = (message.get('text') or '').strip()
        first_name = message.get('from', {}).get('first_name') or 'Staff Member'

        if not chat_id or not text:
            return

        # 1. Deep-link connection: /start emp_<key>
        if text.startswith('/start emp_') or text.startswith('/connect '):
            if text.startswith('/start emp_'):
                emp_key = text[11:].strip().lower()
            else:
                emp_key = text[9:].strip().lower()

            worker = fetch_one('SELECT * FROM employees WHERE emp_key = ?', (emp_key,))
            if not worker:
                self.send_reply(
                    chat_id,
                    f"⚠️ *Staff Key Not Found*\nCould not find employee matching `{emp_key}`.\nPlease check your staff key on the SaniTrack portal."
                )
                return

            execute('UPDATE employees SET telegram_chat_id = ? WHERE emp_key = ?', (str(chat_id), emp_key))
            self.send_reply(
                chat_id,
                f"🏥 *SaniTrack Staff Linked Successfully!*\n\n"
                f"Hello *{worker['name']}*, your Telegram account has been linked to your SaniTrack profile (`{emp_key}`).\n\n"
                f"✅ You will now receive real-time cleaning task assignments and urgent alerts directly in this chat.\n\n"
                f"💡 Send `/tasks` anytime to see your current ward duties."
            )
            logger.info(f"Linked Telegram chat {chat_id} to employee {emp_key}")
            return

        # 2. General /start command
        if text == '/start':
            worker = fetch_one('SELECT * FROM employees WHERE telegram_chat_id = ?', (str(chat_id),))
            if worker:
                self.send_reply(
                    chat_id,
                    f"🏥 *Welcome Back, {worker['name']}!*\n\n"
                    f"Your account is connected to staff key `{worker['emp_key']}`.\n\n"
                    f"Commands:\n"
                    f"• `/tasks` — View your assigned wards\n"
                    f"• `/status` — View your shift summary"
                )
            else:
                self.send_reply(
                    chat_id,
                    f"🏥 *Welcome to SaniTrack Hospital Bot!*\n\n"
                    f"To connect your Telegram account to your cleaning duties, open your worker mobile portal and tap *Connect Telegram Alerts*, or reply with:\n\n"
                    f"`/connect <your_staff_key>`\n\n"
                    f"*(e.g. `/connect utkarsh_arora`)*"
                )
            return

        # 3. /tasks command
        if text in ('/tasks', '/status'):
            worker = fetch_one('SELECT * FROM employees WHERE telegram_chat_id = ?', (str(chat_id),))
            if not worker:
                self.send_reply(
                    chat_id,
                    "⚠️ Your Telegram account is not linked to a staff profile yet.\nReply with `/connect <your_staff_key>` to link."
                )
                return

            wards = fetch_all('SELECT name, location, worker_presence FROM wards WHERE assigned_employee_key = ?', (worker['emp_key'],))
            if not wards:
                self.send_reply(chat_id, f"📋 *No active wards assigned* to your shift right now, {worker['name']}.")
            else:
                ward_lines = "\n".join([f"• *{w['name']}* ({w['location'] or 'General'}) — Status: {w.get('worker_presence') or 'Assigned'}" for w in wards])
                self.send_reply(
                    chat_id,
                    f"📋 *Your Current Assigned Wards ({worker['name']})*:\n\n{ward_lines}\n\n"
                    f"Tap 'Mark Cleaning Complete' on your portal when done."
                )
            return

    def poll_updates(self):
        if not config.TELEGRAM_BOT_TOKEN:
            return
        url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/getUpdates"
        params = {'offset': self.last_update_id + 1, 'timeout': 5}
        try:
            res = requests.get(url, params=params, timeout=10)
            if not res.ok:
                return
            data = res.json()
            if not data.get('ok'):
                return
            for update in data.get('result', []):
                self.last_update_id = max(self.last_update_id, update['update_id'])
                if 'message' in update:
                    self.handle_message(update['message'])
        except Exception as e:
            logger.debug(f"Telegram polling exception: {e}")

    def run(self):
        logger.info("TelegramBotDaemon started.")
        self.running = True
        while self.running:
            try:
                self.poll_updates()
            except Exception as exc:
                logger.error(f"Error in TelegramBotDaemon: {exc}")
            time.sleep(self.interval)

    def stop(self):
        self.running = False

