from test_telegram import BroadcastTests
import cloud_queue,app,telegram_bot

class QueueImportTests(BroadcastTests):
    def test_replayed_download_does_not_reenqueue(self):
        item={'id':'f'*24,'created':'2026-11-10T20:00:00Z','consentVersion':'telegram-queue-v1','data':self.data}
        cloud_queue.ingest(app.connect,item,telegram_bot.enqueue)
        with app.connect() as db:
            db.execute("UPDATE outbox SET status='sent'")
        cloud_queue.ingest(app.connect,item,telegram_bot.enqueue)
        with app.connect() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM applications').fetchone()[0],1)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM outbox WHERE status='sent'").fetchone()[0],2)
