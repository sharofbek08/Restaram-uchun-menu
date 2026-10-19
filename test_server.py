import http.client
import json
from pathlib import Path
import tempfile
import threading
import unittest
import server


class MenuTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory()
        server.DB = Path(cls.folder.name) / 'menu.sqlite3'
        server.UPLOADS = Path(cls.folder.name) / 'images'
        server.initialize()
        salt = '12' * 16
        with server.connect() as db:
            db.execute('INSERT INTO admin VALUES (1,?,?)', (salt, server.password_hash('test-password', salt)))
        cls.http = server.ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
        cls.thread = threading.Thread(target=cls.http.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.http.shutdown()
        cls.http.server_close()
        cls.thread.join()
        cls.folder.cleanup()

    def request(self, method, path, data=None, cookie='', csrf='', origin=None, length=None):
        conn = http.client.HTTPConnection('127.0.0.1', self.http.server_port)
        headers = {'Content-Type': 'application/json', 'Cookie': cookie, 'X-CSRF-Token': csrf}
        if origin:
            headers['Origin'] = origin
        if length is not None:
            headers['Content-Length'] = str(length)
        conn.request(method, path, data if isinstance(data, bytes) else json.dumps(data) if data is not None else None, headers)
        response = conn.getresponse()
        body = response.read()
        result = (response.status, json.loads(body) if response.getheader('Content-Type', '').startswith('application/json') else body, response.getheader('Set-Cookie', '').split(';')[0])
        conn.close()
        return result

    def test_admin_and_shared_menu(self):
        self.assertEqual(self.request('GET', '/admin')[0], 200)
        self.assertEqual(self.request('GET', '/data/safar.sqlite3')[0], 404)
        self.assertEqual(self.request('GET', '/server.py')[0], 404)
        original = self.request('GET', '/api/dishes')[1]
        self.assertEqual(len(original), 16)
        dish = dict(original[0], name='Test dish', price=12345)
        self.assertEqual(self.request('POST', '/api/dishes', dish)[0], 401)
        self.assertEqual(self.request('POST', '/api/login', {'password': 'wrong'})[0], 401)
        code, session, cookie = self.request('POST', '/api/login', {'password': 'test-password'})
        self.assertEqual(code, 200)
        csrf = session['csrf']
        self.assertEqual(self.request('POST', '/api/categories', {'name': 'Desserts'})[0], 401)
        self.assertEqual(self.request('POST', '/api/categories', {'name': 'Desserts'}, cookie)[0], 403)
        self.assertEqual(self.request('POST', '/api/categories', {'name': ' '}, cookie, csrf)[0], 400)
        self.assertEqual(self.request('POST', '/api/categories', {'name': 'Desserts'}, cookie, csrf)[0], 201)
        self.assertEqual(self.request('POST', '/api/categories', {'name': 'desserts'}, cookie, csrf)[0], 409)
        server.initialize()
        self.assertIn('Desserts', self.request('GET', '/api/categories')[1])
        photo = next((server.ROOT / 'images').glob('*.jpg')).read_bytes()
        self.assertEqual(self.request('POST', '/api/upload', photo)[0], 401)
        self.assertEqual(self.request('POST', '/api/upload', photo, cookie)[0], 403)
        self.assertEqual(self.request('POST', '/api/upload', b'<svg>invalid</svg>', cookie, csrf)[0], 400)
        self.assertEqual(self.request('POST', '/api/upload', b'', cookie, csrf, length=5 * 1024 * 1024 + 1)[0], 413)
        code, uploaded, _ = self.request('POST', '/api/upload', photo, cookie, csrf)
        self.assertEqual(code, 201)
        saved = server.UPLOADS / Path(uploaded['image']).name
        self.assertEqual(saved.read_bytes(), photo)
        dish['image'] = uploaded['image']
        self.assertEqual(self.request('POST', '/api/dishes', dish, cookie)[0], 403)
        self.assertEqual(self.request('POST', '/api/dishes', dish, cookie, csrf, 'https://foreign.test')[0], 403)
        self.assertEqual(self.request('POST', '/api/dishes', dict(dish, price=-1), cookie, csrf)[0], 400)
        self.assertEqual(self.request('POST', '/api/dishes', dict(dish, image='javascript:alert(1)'), cookie, csrf)[0], 400)
        code, created, _ = self.request('POST', '/api/dishes', dish, cookie, csrf)
        self.assertEqual(code, 201)
        path = '/api/dishes/' + str(created['id'])
        self.assertEqual(len(self.request('GET', '/api/dishes')[1]), 17)
        dish['price'] = 23000
        self.assertEqual(self.request('PUT', path, dish, cookie, csrf)[0], 200)
        server.initialize()
        with server.connect() as db:
            self.assertEqual(db.execute('SELECT price FROM dishes WHERE id=?', (created['id'],)).fetchone()[0], 23000)
        self.assertEqual(self.request('DELETE', path, {}, cookie, csrf)[0], 200)
        self.assertEqual(len(self.request('GET', '/api/dishes')[1]), 16)
        self.assertEqual(self.request('POST', '/api/logout', {}, cookie, csrf)[0], 200)
        self.assertEqual(self.request('POST', '/api/dishes', dish, cookie, csrf)[0], 401)
        for _ in range(5):
            self.assertEqual(self.request('POST', '/api/login', {'password': 'wrong'})[0], 401)
        self.assertEqual(self.request('POST', '/api/login', {'password': 'wrong'})[0], 429)


if __name__ == '__main__':
    unittest.main()
