"""Accept the bot token on hidden stdin; never print credentials."""
import getpass
import secrets
from pathlib import Path
from telegram_bot import Telegram, TelegramError

if __name__ == '__main__':
    token = getpass.getpass('Telegram token (hidden): ').strip()
    if not token or ':' not in token:
        raise SystemExit('Invalid token format')
    try:
        client = Telegram(token)
        identity = client.call('getMe')
        webhook = client.call('getWebhookInfo')
    except TelegramError as error:
        raise SystemExit('Connection check failed, code: ' + str(error.code)) from None
    path = Path(__file__).with_name('.env')
    values = {}
    if path.exists():
        for line in path.read_text(encoding='utf-8-sig').splitlines():
            key, sep, value = line.partition('=')
            if sep and not key.lstrip().startswith('#'): values[key.strip()] = value.strip()
    values['SG_TELEGRAM_BOT_TOKEN'] = token
    values.setdefault('SG_ADMIN_TOKEN', secrets.token_urlsafe(36))
    values.setdefault('SG_ACCEPT_APPLICATIONS', '0')
    values.setdefault('SG_ORIGIN', 'https://steamgamers-squad-roost.roostamsevbyanov.chatgpt.site')
    values.setdefault('SG_CONSENT_VERSION', 'telegram-v1')
    values.setdefault('PORT', '8081')
    path.write_text('\n'.join(key+'='+value for key,value in values.items())+'\n', encoding='utf-8')
    print('Token saved locally. Bot: @' + identity.get('username','unknown'))
    print('Existing webhook: ' + ('yes; left unchanged' if webhook.get('url') else 'none'))
    print('Application intake: ' + values['SG_ACCEPT_APPLICATIONS'])
