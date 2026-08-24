import os
import dotenv

dotenv.load_dotenv()

from telegram_client import send_message

test_msg = 'Test message from Reddit bot - if you receive this, Telegram integration is working!'

result = send_message(test_msg)
if result:
    print('Telegram message sent successfully!')
else:
    print('Telegram message failed to send')
    print('Checking env vars:')
    print(f'  TELEGRAM_BOT_TOKEN: {os.environ.get("TELEGRAM_BOT_TOKEN", "NOT SET")}')
    print(f'  TELEGRAM_CHAT_ID: {os.environ.get("TELEGRAM_CHAT_ID", "NOT SET")}')