"""Persistent subscriber list and outbox. No network calls at import time."""
import json
import time
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError


class TelegramError(Exception):
    def __init__(self, code=0, retry_after=30):
        self.code, self.retry_after = code, retry_after
        super().__init__('Telegram request failed (%s)' % code)  # Never include token/URL.


class Telegram:
    def __init__(self, token):
        self.token = token

    def call(self, method, **data):
        request = Request('https://api.telegram.org/bot' + self.token + '/' + method,
                          data=json.dumps(data).encode(), headers={'Content-Type':'application/json'})
        try:
            with urlopen(request, timeout=40) as response:
                result = json.load(response)
        except HTTPError as error:
            try: result = json.load(error)
            except (ValueError, OSError): result = {}
            raise TelegramError(error.code, result.get('parameters', {}).get('retry_after', 30)) from None
        except (URLError, OSError, ValueError):
            raise TelegramError() from None
        if not result.get('ok'):
            raise TelegramError(result.get('error_code', 0), result.get('parameters', {}).get('retry_after', 30))
        return result.get('result')


def schema(db):
    db.executescript('''
    CREATE TABLE IF NOT EXISTS subscribers(chat_id INTEGER PRIMARY KEY, active INTEGER NOT NULL);
    CREATE TABLE IF NOT EXISTS bot_state(key TEXT PRIMARY KEY, value INTEGER NOT NULL);
    CREATE TABLE IF NOT EXISTS outbox(application_id TEXT NOT NULL, chat_id INTEGER NOT NULL,
      status TEXT NOT NULL DEFAULT 'pending', attempts INTEGER NOT NULL DEFAULT 0,
      next_at REAL NOT NULL DEFAULT 0, message_id INTEGER,
      PRIMARY KEY(application_id, chat_id));
    CREATE TABLE IF NOT EXISTS requests(key TEXT PRIMARY KEY, application_id TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS publication_consents(application_id TEXT PRIMARY KEY, version TEXT NOT NULL);
    ''')


def subscribe(db, chat_id, active):
    db.execute('INSERT INTO subscribers VALUES (?,?) ON CONFLICT(chat_id) DO UPDATE SET active=excluded.active', (chat_id, int(active)))
    if not active:
        db.execute("UPDATE outbox SET status='cancelled' WHERE chat_id=? AND status='pending'", (chat_id,))


def enqueue(db, application_id):
    db.execute("INSERT OR IGNORE INTO outbox(application_id,chat_id) SELECT ?,chat_id FROM subscribers WHERE active=1", (application_id,))


def handle_update(db, update):
    message = update.get('message', {})
    chat = message.get('chat', {})
    if chat.get('type') != 'private' or message.get('from', {}).get('is_bot'):
        return None
    chat_id = chat.get('id')
    if not isinstance(chat_id, int): return None
    command = message.get('text', '').split(' ', 1)[0].split('@', 1)[0]
    if command == '/subscribe':
        subscribe(db, chat_id, True)
        text = 'Подписка включена. Будут приходить новые анкеты SteamGamers: игра, никнейм, профиль Steam, расписание и описание. Отписаться: /stop.'
    elif command == '/stop':
        subscribe(db, chat_id, False)
        text = 'Рассылка отключена. Новые анкеты приходить не будут. Вернуться: /subscribe.'
    elif command == '/delete_me':
        db.execute('DELETE FROM outbox WHERE chat_id=?', (chat_id,))
        db.execute('DELETE FROM subscribers WHERE chat_id=?', (chat_id,))
        text = 'Ваш chat_id и записи доставки удалены из локальной базы. Уже полученные сообщения остаются в Telegram.'
    elif command == '/status':
        row = db.execute('SELECT active FROM subscribers WHERE chat_id=?', (chat_id,)).fetchone()
        text = 'Подписка включена. /stop — отписаться.' if row and row[0] else 'Подписка выключена. /subscribe — подписаться.'
    elif command in ('/start', '/help'):
        text = ('SteamGamers — поиск напарников, 18+. Подписка добровольная: /subscribe. '
                'Бот хранит ваш Telegram chat_id на компьютере организатора, чтобы доставлять новые анкеты. '
                '/stop — отписаться; /status — статус; /delete_me — удалить данные подписки. '
                'Никому не передавайте пароль и коды Steam Guard.')
    else:
        return None
    return chat_id, text


def format_application(uid, data):
    labels = {'nickname':'Никнейм','game':'Игра','steam':'Steam','level':'Уровень','goal':'Цель',
              'schedule':'Время','timezone':'Часовой пояс','about':'О себе'}
    return ('Новая заявка SteamGamers #' + uid[:8] + '\n\n' +
            '\n'.join(label + ': ' + data.get(key, '') for key, label in labels.items()) +
            '\n\nСвязаться: откройте профиль Steam выше.\n/stop — отключить рассылку.')


def deliver_one(connect, client, now=None):
    now = time.time() if now is None else now
    with connect() as db:
        row = db.execute("""SELECT o.application_id,o.chat_id,o.attempts,a.payload FROM outbox o
            JOIN applications a ON a.id=o.application_id JOIN subscribers s ON s.chat_id=o.chat_id
            WHERE o.status='pending' AND s.active=1 AND o.next_at<=? ORDER BY a.created,o.chat_id LIMIT 1""", (now,)).fetchone()
    if not row: return False
    uid, chat_id, attempts, payload = row
    try:
        sent = client.call('sendMessage', chat_id=chat_id, text=format_application(uid, json.loads(payload)),
                           link_preview_options={'is_disabled':True})
    except TelegramError as error:
        with connect() as db:
            if error.code == 403:
                subscribe(db, chat_id, False)
            elif error.code in (400, 401, 404) or attempts >= 9:
                db.execute("UPDATE outbox SET status='failed',attempts=attempts+1 WHERE application_id=? AND chat_id=?", (uid,chat_id))
            else:
                delay = max(error.retry_after, min(3600, 2 ** (attempts + 4)))
                db.execute('UPDATE outbox SET attempts=attempts+1,next_at=? WHERE application_id=? AND chat_id=?', (now+delay,uid,chat_id))
                if error.code == 429:
                    db.execute("UPDATE outbox SET next_at=MAX(next_at,?) WHERE status='pending'", (now+delay,))
        return True
    with connect() as db:
        db.execute("UPDATE outbox SET status='sent',message_id=?,attempts=attempts+1 WHERE application_id=? AND chat_id=?", (sent['message_id'],uid,chat_id))
    return True


def poll(connect, client, stop):
    while not stop.is_set():
        try:
            with connect() as db:
                row = db.execute("SELECT value FROM bot_state WHERE key='offset'").fetchone()
            updates = client.call('getUpdates', offset=row[0] if row else 0, timeout=25, allowed_updates=['message'])
            for update in updates:
                with connect() as db:
                    reply = handle_update(db, update)
                    db.execute("INSERT INTO bot_state VALUES ('offset',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (update['update_id']+1,))
                if reply:
                    try: client.call('sendMessage', chat_id=reply[0], text=reply[1])
                    except TelegramError: pass
                if stop.is_set(): break
        except TelegramError as error:
            print('Telegram temporarily unavailable; code:', error.code, flush=True)
            stop.wait(max(5, error.retry_after))


def dispatch(connect, client, stop):
    while not stop.is_set():
        try: deliver_one(connect, client)
        except Exception:
            # Keep private payloads, paths and credentials out of console logs.
            print('Outbox unavailable; will retry.', flush=True)
            stop.wait(5)
        stop.wait(1.1)  # Conservative free delivery rate, also protects a single chat.
