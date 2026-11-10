import json
import tempfile
import unittest
from pathlib import Path
import app
import telegram_bot as bot

class FakeTelegram:
    def __init__(self, error=None): self.calls, self.error = [], error
    def call(self, method, **data):
        self.calls.append((method,data))
        if self.error: raise self.error
        return {'message_id':123}

class BroadcastTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.original_data, self.original_version = app.DATA, app.VERSION
        app.DATA, app.VERSION = Path(self.temp.name), 'test-v1'
        self.data = dict(nickname='Demo',game='CS2',steam='https://steamcommunity.com/id/demo',level='Новичок',goal='Общение',schedule='Вечер',timezone='МСК',about='<test>')
        with app.connect() as db:
            bot.subscribe(db,11,True)
            bot.subscribe(db,22,True)
            bot.subscribe(db,33,False)
    def tearDown(self):
        app.DATA, app.VERSION = self.original_data, self.original_version
        self.temp.cleanup()
    def submit(self): return app.save_application(self.data,'a'*20)
    def test_snapshot_and_idempotence(self):
        uid = self.submit()
        self.assertEqual(uid,self.submit())
        with app.connect() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM applications').fetchone()[0],1)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM outbox').fetchone()[0],2)
            bot.subscribe(db,44,True)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM outbox').fetchone()[0],2)
    def test_idempotency_rejects_other_content(self):
        self.submit()
        with self.assertRaises(ValueError): app.save_application({**self.data,'nickname':'Other'},'a'*20)
    def test_success_and_unsubscribe(self):
        self.submit()
        with app.connect() as db: bot.subscribe(db,22,False)
        client = FakeTelegram()
        self.assertTrue(bot.deliver_one(app.connect,client))
        self.assertFalse(bot.deliver_one(app.connect,client))
        self.assertEqual(client.calls[0][1]['chat_id'],11)
        self.assertNotIn('parse_mode',client.calls[0][1])
        with app.connect() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM outbox WHERE status='sent'").fetchone()[0],1)
    def test_retry_after_and_restart(self):
        self.submit()
        bot.deliver_one(app.connect,FakeTelegram(bot.TelegramError(429,60)),now=100)
        self.assertFalse(bot.deliver_one(app.connect,FakeTelegram(),now=159))
        self.assertTrue(bot.deliver_one(app.connect,FakeTelegram(),now=161))
    def test_block_disables_subscriber(self):
        self.submit()
        bot.deliver_one(app.connect,FakeTelegram(bot.TelegramError(403)),now=100)
        with app.connect() as db:
            self.assertEqual(db.execute('SELECT active FROM subscribers WHERE chat_id=11').fetchone()[0],0)
    def test_start_does_not_subscribe_and_delete(self):
        def update(command): return {'message':{'chat':{'id':55,'type':'private'},'text':command}}
        with app.connect() as db:
            bot.handle_update(db,update('/start'))
            self.assertIsNone(db.execute('SELECT * FROM subscribers WHERE chat_id=55').fetchone())
            bot.handle_update(db,update('/subscribe'))
            self.assertEqual(db.execute('SELECT active FROM subscribers WHERE chat_id=55').fetchone()[0],1)
            bot.handle_update(db,update('/delete_me'))
            self.assertIsNone(db.execute('SELECT * FROM subscribers WHERE chat_id=55').fetchone())
    def test_same_profile_rate_limit(self):
        self.submit()
        with self.assertRaises(ValueError): app.save_application(self.data,'b'*20)

if __name__ == '__main__': unittest.main()
