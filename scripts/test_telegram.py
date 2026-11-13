import os
import sys
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

if not chat_id:
    print("\n[!] TELEGRAM_CHAT_ID not found in .env")
    print("Tip: Start a chat with @userinfobot on Telegram to get your numeric ID.")
    chat_id = input("Enter your Telegram Chat ID: ").strip()

if not bot_token or not chat_id:
    print("\n[ERROR] Both Bot Token and Chat ID are required to send notifications.")
    sys.exit(1)

print(f"\n-> Attempting to send test message...")
print(f"   Bot Token : {bot_token[:10]}...{bot_token[-5:]}")
print(f"   Chat ID   : {chat_id}")

url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
payload = {
    'chat_id': chat_id,
    'text': "🏥 *SaniTrack Hospital Alert*\n\n✅ *Telegram Integration Successful!*\nReal-time sanitation notifications, dirty ward alerts, and staff attendance logs will now be delivered instantly to this chat.",
    'parse_mode': 'Markdown'
}

try:
    response = requests.post(url, json=payload, timeout=10)
    data = response.json()
    if data.get('ok'):
        print("\n" + "=" * 60)
        print(" [SUCCESS] Test message sent! Check your Telegram app.")
        print("=" * 60)
        print("\nMake sure your .env has:")
        print(f"TELEGRAM_BOT_TOKEN={bot_token}")
        print(f"TELEGRAM_CHAT_ID={chat_id}")
    else:
        print("\n[FAILED] Telegram API returned error:")
        print(f"  Error Code  : {data.get('error_code')}")
        print(f"  Description : {data.get('description')}")
        if data.get('error_code') == 400:
            print("\nTip: Did you press 'Start' or send /start to your bot in Telegram first?")
        elif data.get('error_code') == 401:
            print("\nTip: Invalid bot token. Double check the token from @BotFather.")
except Exception as e:
    print(f"\n[NETWORK ERROR] Could not connect to Telegram API: {e}")
