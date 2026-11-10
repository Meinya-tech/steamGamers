import unittest, app

class ValidationTests(unittest.TestCase):
    def setUp(self):
        app.VERSION = 'test-v1'
        self.data = dict(nickname='Demo', game='CS2', steam='https://steamcommunity.com/id/demo-player', level='Новичок', goal='Общение', schedule='Вечер', timezone='МСК', about='', consent=True, adult=True, broadcastConsent=True, consentVersion='test-v1')
    def test_valid(self):
        self.assertEqual(app.validate(self.data)['game'], 'CS2')
    def test_consent_and_age_required(self):
        for field in ['consent','adult','broadcastConsent']:
            with self.assertRaises(ValueError): app.validate({**self.data,field:False})
    def test_fake_steam_hosts(self):
        for url in ['https://steamcommunity.com.evil.test/id/demo','https://steamcommunity.com@evil.test/id/demo','http://steamcommunity.com/id/demo']:
            with self.assertRaises(ValueError): app.validate({**self.data,'steam':url})
    def test_old_consent(self):
        with self.assertRaises(ValueError): app.validate({**self.data,'consentVersion':'old'})
    def test_oversize(self):
        with self.assertRaises(ValueError): app.validate({**self.data,'about':'a'*501})

if __name__ == '__main__': unittest.main()
