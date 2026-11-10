import http.client
import threading
import unittest
import public_gateway as gateway
from http.server import ThreadingHTTPServer

class GatewayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original = gateway.ORIGIN
        gateway.ORIGIN = 'https://example.test'
        cls.server = ThreadingHTTPServer(('127.0.0.1',0), gateway.Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever,daemon=True)
        cls.thread.start()
    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown(); cls.server.server_close(); cls.thread.join()
        gateway.ORIGIN=cls.original
    def request(self, method, path, body=None, headers=None):
        client=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=3)
        try:
            client.request(method,path,body=body,headers=headers or {})
            response=client.getresponse(); response.read()
            return response.status
        finally: client.close()
    def test_private_paths_never_forward(self):
        for path in ['/api/admin/applications','/.env','/private-data/applications.sqlite3','/api/applications?x=1','/api/applications/../admin/applications']:
            for method in ['GET','POST','DELETE','OPTIONS']:
                self.assertEqual(self.request(method,path,headers={'Origin':gateway.ORIGIN}),404)
    def test_foreign_origin(self):
        self.assertEqual(self.request('POST','/api/applications','{}',{'Origin':'https://other.test'}),403)
    def test_large_body(self):
        self.assertEqual(self.request('POST','/api/applications','x'*8193,{'Origin':gateway.ORIGIN}),413)
    def test_read_method_blocked(self):
        self.assertEqual(self.request('GET','/api/applications'),404)

if __name__=='__main__': unittest.main()
