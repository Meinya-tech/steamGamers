"""Narrow public gateway. Only forwards form POST/OPTIONS to local API."""
import http.client
import json
import time
import threading
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from config import load_env
import os

load_env()
ORIGIN = os.environ.get('SG_ORIGIN','')
slots = threading.BoundedSemaphore(16)
lock = threading.Lock()
recent = deque()

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args): pass
    def setup(self):
        super().setup()
        self.connection.settimeout(10)
    def reply(self, status, body=b'{}', headers=None):
        self.send_response(status)
        self.send_header('Content-Type','application/json; charset=utf-8')
        self.send_header('Content-Length',str(len(body)))
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        if self.headers.get('Origin') == ORIGIN and ORIGIN:
            self.send_header('Access-Control-Allow-Origin',ORIGIN)
            self.send_header('Vary','Origin')
            self.send_header('Access-Control-Allow-Methods','POST, OPTIONS')
            self.send_header('Access-Control-Allow-Headers','Content-Type, Idempotency-Key')
        self.end_headers()
        self.wfile.write(body)
    def forward(self):
        if self.path != '/api/applications': return self.reply(404)
        if self.headers.get('Origin') != ORIGIN or not ORIGIN: return self.reply(403)
        if self.headers.get('Transfer-Encoding'): return self.reply(400)
        if not slots.acquire(blocking=False): return self.reply(429)
        try:
            with lock:
                now = time.monotonic()
                while recent and recent[0]<now-60: recent.popleft()
                if len(recent)>=120: return self.reply(429)
                recent.append(now)
            try: size = int(self.headers.get('Content-Length','0'))
            except ValueError: return self.reply(400)
            if size < 0 or size > 8192: return self.reply(413)
            if self.command == 'POST' and size == 0: return self.reply(400)
            body = self.rfile.read(size) if size else None
            if body is not None and len(body)!=size: return self.reply(400)
            headers = {key:self.headers[key] for key in ['Origin','Content-Type','Idempotency-Key'] if self.headers.get(key)}
            upstream = http.client.HTTPConnection('127.0.0.1',8081,timeout=12)
            try:
                upstream.request(self.command,'/api/applications',body=body,headers=headers)
                response = upstream.getresponse()
                self.reply(response.status,response.read(65536))
            finally: upstream.close()
        except (OSError, http.client.HTTPException):
            self.reply(503,json.dumps({'error':'Сервер временно недоступен'},ensure_ascii=False).encode())
        finally: slots.release()
    do_POST = forward
    do_OPTIONS = forward
    def do_GET(self): self.reply(404)
    def do_DELETE(self): self.reply(404)
    def do_PUT(self): self.reply(404)
    def do_PATCH(self): self.reply(404)
    def do_HEAD(self): self.send_response(404); self.end_headers()

if __name__=='__main__':
    server=ThreadingHTTPServer(('127.0.0.1',8082),Handler)
    print('Public form gateway listening on 127.0.0.1:8082',flush=True)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close()
