"""Pull hosted queue over outbound HTTPS; commit locally before acknowledging."""
import json
import os
import sqlite3
from urllib.request import Request,urlopen

def remote(method,path,data=None):
    origin=os.environ['SG_QUEUE_ORIGIN'].rstrip('/')
    if not origin.startswith('https://'): raise ValueError('Queue requires HTTPS')
    request=Request(origin+path,method=method,data=None if data is None else json.dumps(data).encode(),headers={
        'Authorization':'Bearer '+os.environ['SG_QUEUE_SECRET'],'Content-Type':'application/json'})
    with urlopen(request,timeout=25) as response: return json.load(response)

def ingest(connect, application, enqueue):
    uid=application['id']
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        found=db.execute('SELECT id FROM applications WHERE id=?',(uid,)).fetchone()
        if not found:
            db.execute('INSERT INTO applications VALUES (?,?,?,?)',(uid,application['created'],application['consentVersion'],json.dumps(application['data'],ensure_ascii=False)))
            db.execute('INSERT INTO publication_consents VALUES (?,?)',(uid,application['consentVersion']))
            enqueue(db,uid)
    return uid

def run(connect, enqueue, stop):
    while not stop.is_set():
        try:
            records=remote('GET','/api/queue/pending')['applications']
            saved=[ingest(connect,row,enqueue) for row in records]
            if saved: remote('POST','/api/queue/ack',{'ids':saved})
        except Exception:
            print('Hosted queue unavailable; retrying. No credentials or form data logged.',flush=True)
        stop.wait(8)
