import os
import sys
import time
import requests
from dotenv import load_dotenv

# Load .env from project root
load_dotenv()

bot_token = os.getenv('TELEGRAM_BOT_TOKEN', '').strip()
chat_id = os.getenv('TELEGRAM_CHAT_ID', '').strip()

print("=" * 60)
print(" SaniTrack Telegram Notification Tester")
print("=" * 60)

if not bot_token:
    print("\n[!] TELEGRAM_BOT_TOKEN not found in .env")
    bot_token = input("Enter your Telegram Bot Token: ").strip()

if not bot_token:
    print("\n[ERROR] Bot Token is required.")
    sys.exit(1)

def send_alert(token, target_chat):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        'chat_id': target_chat,
        'text': "🏥 *SaniTrack Hospital Alert*\n\n✅ *Telegram Integration Successful!*\nReal-time sanitation notifications, dirty ward alerts, and staff attendance logs will now be delivered instantly to this chat.",
        'parse_mode': 'Markdown'
    }
    return requests.post(url, json=payload, timeout=10).json()

def check_updates(token):
    try:
        r = requests.get(f"https://api.telegram.org/bot{token}/getUpdates", timeout=10).json()
        if r.get('ok') and r.get('result'):
            for u in reversed(r['result']):
                msg = u.get('message') or u.get('channel_post') or u.get('my_chat_member', {}).get('chat')
                if msg:
                    cid = msg.get('chat', {}).get('id') or msg.get('id')
                    sender = msg.get('from', {}).get('first_name', 'User')
                    return str(cid), sender
    except Exception:
        pass
    return None, None

def update_env_file(cid):
    env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env')
    if os.path.exists(env_path):
        with open(env_path, 'r', encoding='utf-8') as f:
            content = f.read()
        import re
        if 'TELEGRAM_CHAT_ID=' in content:
            new_content = re.sub(r'TELEGRAM_CHAT_ID=.*', f'TELEGRAM_CHAT_ID={cid}', content)
        else:
            new_content = content + f'\nTELEGRAM_CHAT_ID={cid}\n'
        with open(env_path, 'w', encoding='utf-8') as f:
            f.write(new_content)

print(f"\n-> Checking bot status...")
r_me = requests.get(f"https://api.telegram.org/bot{bot_token}/getMe").json()
if not r_me.get('ok'):
    print(f"\n[ERROR] Invalid Telegram Bot Token: {r_me.get('description')}")
    sys.exit(1)

bot_username = r_me['result'].get('username')
print(f"   Bot Connected : @{bot_username}")

if chat_id:
    print(f"   Testing configured Chat ID : {chat_id}")
    data = send_alert(bot_token, chat_id)
    if data.get('ok'):
        print("\n" + "=" * 60)
        print(" [SUCCESS] Test message sent! Check your Telegram app.")
        print("=" * 60)
        sys.exit(0)
    else:
        print(f"\n[!] Configured Chat ID ({chat_id}) failed: {data.get('description')}")

print("\n" + "-" * 60)
print(f"ACTION REQUIRED: Telegram needs you to start the chat.")
print(f"1. Open: https://t.me/{bot_username}")
print(f"2. Tap the START button at the bottom (or send 'hi')")
print("-" * 60)
print("Listening for your message for 30 seconds...")

detected_id = None
detected_sender = None

for i in range(15):
    detected_id, detected_sender = check_updates(bot_token)
    if detected_id:
        break
    time.sleep(2)

if detected_id:
    print(f"\n-> Message detected from {detected_sender}! Detected Chat ID: {detected_id}")
    update_env_file(detected_id)
    print(f"   Updated .env with TELEGRAM_CHAT_ID={detected_id}")
    
    data = send_alert(bot_token, detected_id)
    if data.get('ok'):
        print("\n" + "=" * 60)
        print(" [SUCCESS] Test message sent! Check your Telegram app.")
        print("=" * 60)
    else:
        print(f"\n[ERROR] Failed to send: {data}")
else:
    print("\nNo message received yet. Please open https://t.me/" + str(bot_username) + " and tap START.")
