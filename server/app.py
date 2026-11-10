"""Optional same-origin API for a Russian host. Disabled until configured.
Run behind a TLS reverse proxy. Never expose the data directory as static files.
"""
import os, json, re, sqlite3, secrets
import threading
from config import load_env
import telegram_bot
import cloud_queue
load_env()
from pathlib import Path
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

DATA = Path(os.environ.get('SG_DATA_DIR', str(Path(__file__).parent / 'private-data')))
ORIGIN = os.environ.get('SG_ORIGIN', '')
VERSION = os.environ.get('SG_CONSENT_VERSION', '')
ENABLED = os.environ.get('SG_ACCEPT_APPLICATIONS') == '1'
TOKEN = os.environ.get('SG_ADMIN_TOKEN', '')
BOT_TOKEN = os.environ.get('SG_TELEGRAM_BOT_TOKEN', '')
RUN_BOT = os.environ.get('SG_RUN_BOT') == '1' or ENABLED
FIELDS = {'nickname':40,'game':80,'steam':200,'level':40,'goal':50,'schedule':80,'timezone':80,'about':500}

def validate(data):
    if not isinstance(data, dict) or data.get('consent') is not True or data.get('adult') is not True or data.get('broadcastConsent') is not True:
        raise ValueError('Возраст и отдельное согласие обязательны')
    if data.get('consentVersion') != VERSION:
        raise ValueError('Обновите страницу: версия согласия изменилась')
    cleaned = {}
    for key, size in FIELDS.items():
        value = data.get(key, '')
        if not isinstance(value, str) or len(value) > size or ('\x00' in value):
            raise ValueError('Некорректное поле: ' + key)
        value = value.strip()
        if key != 'about' and not value:
            raise ValueError('Заполните поле: ' + key)
        cleaned[key] = value
    if len(cleaned['nickname']) < 2 or not re.fullmatch(r'https://steamcommunity\.com/(?:id/[A-Za-z0-9_-]+|profiles/\d{17})/?', cleaned['steam']):
        raise ValueError('Проверьте никнейм и ссылку Steam')
    return cleaned

class ClosingConnection(sqlite3.Connection):
    def __exit__(self, *args):
        try: return super().__exit__(*args)
        finally: self.close()

def connect():
    db = sqlite3.connect(DATA / 'applications.sqlite3', timeout=15, factory=ClosingConnection)
    db.execute('CREATE TABLE IF NOT EXISTS applications (id TEXT PRIMARY KEY, created TEXT NOT NULL, consent_version TEXT NOT NULL, payload TEXT NOT NULL)')
    telegram_bot.schema(db)
    return db

def save_application(data, key):
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        existing = db.execute('SELECT application_id FROM requests WHERE key=?',(key,)).fetchone()
        if existing:
            previous = db.execute('SELECT payload FROM applications WHERE id=?',(existing[0],)).fetchone()
            if not previous or json.loads(previous[0]) != data:
                raise ValueError('Ключ отправки уже использован для другой анкеты')
            return existing[0]
        count = db.execute("SELECT COUNT(*) FROM applications WHERE julianday(created)>julianday('now','-1 minute')").fetchone()[0]
        if count >= 30: raise ValueError('Слишком много заявок, повторите позже')
        recent = db.execute("SELECT 1 FROM applications WHERE json_extract(payload,'$.steam')=? AND julianday(created)>julianday('now','-1 minute')",(data['steam'],)).fetchone()
        if recent: raise ValueError('Подождите минуту перед новой заявкой')
        uid = secrets.token_hex(12)
        db.execute('INSERT INTO applications VALUES (?,?,?,?)',(uid,datetime.now(timezone.utc).isoformat(),VERSION,json.dumps(data,ensure_ascii=False)))
        db.execute('INSERT INTO publication_consents VALUES (?,?)',(uid,VERSION))
        db.execute('INSERT INTO requests VALUES (?,?)',(key,uid))
        telegram_bot.enqueue(db,uid)
        return uid

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass  # Do not log submitted values or authorization headers.

    def reply(self, status, data):
        body = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type','application/json; charset=utf-8')
        self.send_header('Cache-Control','no-store')
        if self.headers.get('Origin') == ORIGIN and ORIGIN:
            self.send_header('Access-Control-Allow-Origin',ORIGIN)
            self.send_header('Vary','Origin')
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Content-Length',str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def authorized(self):
        return len(TOKEN) >= 32 and secrets.compare_digest(self.headers.get('Authorization',''), 'Bearer ' + TOKEN)

    def do_OPTIONS(self):
        if self.path != '/api/applications' or self.headers.get('Origin') != ORIGIN:
            return self.reply(403, {'error':'Forbidden'})
        self.send_response(204)
        self.send_header('Access-Control-Allow-Origin',ORIGIN)
        self.send_header('Vary','Origin')
        self.send_header('Access-Control-Allow-Methods','POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers','Content-Type, Idempotency-Key')
        self.end_headers()

    def do_POST(self):
        if self.path != '/api/applications':
            return self.reply(404, {'error':'Not found'})
        if not ENABLED:
            return self.reply(503, {'error':'Приём заявок не запущен'})
        if self.headers.get('Origin') != ORIGIN:
            return self.reply(403, {'error':'Недопустимый источник запроса'})
        if self.headers.get('Content-Type','').split(';')[0] != 'application/json':
            return self.reply(415, {'error':'Ожидается JSON'})
        try:
            size = int(self.headers.get('Content-Length','0'))
            if not 0 < size <= 8192:
                return self.reply(413, {'error':'Слишком большой запрос'})
            self.connection.settimeout(10)
            data = validate(json.loads(self.rfile.read(size)))
            key = self.headers.get('Idempotency-Key','')
            if not re.fullmatch(r'[A-Za-z0-9-]{16,80}',key):
                return self.reply(400, {'error':'Требуется ключ отправки'})
            uid = save_application(data,key)
            return self.reply(201, {'id':uid,'message':'Заявка сохранена и поставлена в очередь рассылки. Доставка ещё не подтверждена.'})
        except (ValueError, UnicodeDecodeError):
            return self.reply(400, {'error':'Проверьте поля, возраст и согласие'})
        except (sqlite3.Error, OSError):
            return self.reply(503, {'error':'Не удалось сохранить заявку. Повторите позже'})

    def do_GET(self):
        if self.path != '/api/admin/applications':
            return self.reply(404, {'error':'Not found'})
        if not self.authorized():
            return self.reply(401, {'error':'Unauthorized'})
        if not ENABLED:
            return self.reply(503, {'error':'Приём не запущен'})
        with connect() as db:
            rows = db.execute('SELECT id,created,consent_version,payload FROM applications ORDER BY created DESC LIMIT 500').fetchall()
        return self.reply(200, {'applications':[dict(id=r[0],created=r[1],consentVersion=r[2],data=json.loads(r[3])) for r in rows]})

    def do_DELETE(self):
        if not self.authorized():
            return self.reply(401, {'error':'Unauthorized'})
        match = re.fullmatch(r'/api/admin/applications/([a-f0-9]{24})', self.path)
        if not match or not ENABLED:
            return self.reply(404, {'error':'Not found'})
        with connect() as db:
            db.execute('DELETE FROM outbox WHERE application_id=?',(match[1],))
            db.execute('DELETE FROM requests WHERE application_id=?',(match[1],))
            db.execute('DELETE FROM publication_consents WHERE application_id=?',(match[1],))
            changed = db.execute('DELETE FROM applications WHERE id=?',(match[1],)).rowcount
        return self.reply(200 if changed else 404, {'deleted':bool(changed)})

if __name__ == '__main__':
    if RUN_BOT and not BOT_TOKEN:
        raise SystemExit('Set SG_TELEGRAM_BOT_TOKEN before starting the bot')
    if ENABLED and (not ORIGIN.startswith('https://') or not VERSION or len(TOKEN)<32 or not BOT_TOKEN):
        raise SystemExit('Configure HTTPS SG_ORIGIN, SG_CONSENT_VERSION, SG_ADMIN_TOKEN (32+ chars), SG_TELEGRAM_BOT_TOKEN before enabling')
    if ENABLED or RUN_BOT:
        DATA.mkdir(parents=True, exist_ok=True)
        if os.name != 'nt': DATA.chmod(0o700)
    server = ThreadingHTTPServer(('127.0.0.1', int(os.environ.get('PORT','8081'))), Handler)
    stop = threading.Event()
    if RUN_BOT:
        client = telegram_bot.Telegram(BOT_TOKEN)
        try:
            client.call('getMe')
            if client.call('getWebhookInfo').get('url'):
                raise SystemExit('This bot has a webhook. Use a separate bot or remove its webhook intentionally before starting.')
        except telegram_bot.TelegramError as error:
            raise SystemExit('Telegram startup check failed, code: ' + str(error.code)) from None
        with connect() as db: pass
        for work in (telegram_bot.poll, telegram_bot.dispatch):
            threading.Thread(target=work,args=(connect,client,stop),daemon=True).start()
        if os.environ.get('SG_QUEUE_ORIGIN') and os.environ.get('SG_QUEUE_SECRET'):
            threading.Thread(target=cloud_queue.run,args=(connect,telegram_bot.enqueue,stop),daemon=True).start()
    print('SteamGamers listening on 127.0.0.1:' + str(server.server_port), flush=True)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally:
        stop.set()
        server.server_close()
