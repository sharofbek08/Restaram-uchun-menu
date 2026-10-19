"""Safar menu server: python server.py --setup, then python server.py."""
import argparse
import getpass
import hashlib
import hmac
import json
import mimetypes
import re
import secrets
import sqlite3
import time
from contextlib import contextmanager
from html import unescape
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent
DB = ROOT / 'data' / 'safar.sqlite3'
UPLOADS = ROOT / 'images'
SESSIONS = {}
ATTEMPTS = {}

@contextmanager
def connect():
    db = sqlite3.connect(DB)
    db.row_factory = sqlite3.Row
    try:
        with db:
            yield db
    finally:
        db.close()

def initialize():
    DB.parent.mkdir(exist_ok=True)
    with connect() as db:
        db.execute('CREATE TABLE IF NOT EXISTS admin (id INTEGER PRIMARY KEY, salt TEXT, hash TEXT)')
        exists = db.execute("SELECT name FROM sqlite_master WHERE name='dishes'").fetchone()
        db.execute('CREATE TABLE IF NOT EXISTS dishes (id INTEGER PRIMARY KEY, name TEXT, category TEXT, portion TEXT, description TEXT, price INTEGER, image TEXT)')
        db.execute('CREATE TABLE IF NOT EXISTS categories (name TEXT PRIMARY KEY COLLATE NOCASE)')
        if not exists:
            for card in re.findall(r'<article class="card">(.*?)</article>', (ROOT / 'index.html').read_text(encoding='utf-8'), re.S):
                def read(pattern):
                    return unescape(re.search(pattern, card, re.S).group(1).strip())
                category, _, portion = read(r'class="dish-meta">(.*?)</div>').partition('·')
                db.execute('INSERT INTO dishes (name,category,portion,description,price,image) VALUES (?,?,?,?,?,?)', (
                    read(r'<h3>(.*?)</h3>'), category.strip(), portion.strip(), read(r'<p>(.*?)</p>'),
                    int(re.sub(r'\D', '', read(r'class="price">(.*?)<small>'))), read(r'<img src="([^"]+)"')))

def password_hash(password, salt):
    return hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), 600000).hex()

class Handler(BaseHTTPRequestHandler):
    def reply(self, status, data, cookie=None):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        if cookie:
            self.send_header('Set-Cookie', cookie)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def session(self):
        cookie = SimpleCookie()
        try:
            cookie.load(self.headers.get('Cookie', ''))
        except Exception:
            return None
        token = cookie.get('safar_session')
        token = token.value if token else ''
        session = SESSIONS.get(token)
        if session and session['expires'] > time.time():
            return token, session
        SESSIONS.pop(token, None)
        return None

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == '/api/categories':
            with connect() as db:
                return self.reply(200, [row[0] for row in db.execute('SELECT name FROM categories UNION SELECT category FROM dishes ORDER BY 1')])
        if path == '/api/dishes':
            with connect() as db:
                return self.reply(200, [dict(row) for row in db.execute('SELECT * FROM dishes ORDER BY id')])
        if path == '/api/session':
            session = self.session()
            return self.reply(200, {'csrf': session[1]['csrf']} if session else {'csrf': None})
        allowed = {'/': 'index.html', '/index.html': 'index.html', '/app.js': 'app.js', '/styles.css': 'styles.css', '/admin': 'admin/index.html', '/admin/': 'admin/index.html', '/admin/app.js': 'admin/app.js', '/admin/style.css': 'admin/style.css'}
        filename = allowed.get(path)
        if re.fullmatch(r'/images/[A-Za-z0-9_.-]+\.(jpg|jpeg|png|webp)', path):
            filename = path.lstrip('/')
        target = (ROOT / filename).resolve() if filename else None
        if not target or not target.is_relative_to(ROOT) or not target.is_file():
            return self.reply(404, {'error': 'Topilmadi'})
        body = target.read_bytes()
        self.send_response(200)
        self.send_header('Content-Type', mimetypes.guess_type(str(target))[0] or 'application/octet-stream')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Cache-Control', 'no-cache')
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        self.mutate()

    def do_PUT(self):
        self.mutate()

    def do_DELETE(self):
        self.mutate()

    def mutate(self):
        path = urlsplit(self.path).path
        origin = self.headers.get('Origin')
        if origin and urlsplit(origin).netloc != self.headers.get('Host'):
            return self.reply(403, {'error': 'Ruxsat yoq'})
        if path == '/api/upload' and self.command == 'POST':
            return self.upload()
        if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
            return self.reply(415, {'error': 'JSON kerak'})
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 16000:
                raise ValueError()
            data = json.loads(self.rfile.read(length))
            if not isinstance(data, dict):
                raise ValueError()
        except (ValueError, UnicodeDecodeError):
            return self.reply(400, {'error': 'Malumot formati xato'})
        if path == '/api/login' and self.command == 'POST':
            ip = self.client_address[0]
            attempts = [t for t in ATTEMPTS.get(ip, []) if t > time.time() - 300]
            ATTEMPTS[ip] = attempts
            if len(attempts) >= 5:
                return self.reply(429, {'error': '5 daqiqadan keyin qayta urining'})
            with connect() as db:
                admin = db.execute('SELECT * FROM admin WHERE id=1').fetchone()
            if not admin:
                return self.reply(503, {'error': 'Avval terminalda python server.py --setup buyrugini bajaring'})
            password = data.get('password', '')
            if not isinstance(password, str) or not hmac.compare_digest(password_hash(password, admin['salt']), admin['hash']):
                attempts.append(time.time())
                return self.reply(401, {'error': 'Parol xato'})
            ATTEMPTS.pop(ip, None)
            token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
            SESSIONS[token] = {'csrf': csrf, 'expires': time.time() + 28800}
            return self.reply(200, {'csrf': csrf}, f'safar_session={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age=28800')
        session = self.session()
        if not session:
            return self.reply(401, {'error': 'Avval tizimga kiring'})
        if not hmac.compare_digest(self.headers.get('X-CSRF-Token', ''), session[1]['csrf']):
            return self.reply(403, {'error': 'Sahifani yangilab qayta urining'})
        if path == '/api/logout' and self.command == 'POST':
            SESSIONS.pop(session[0], None)
            return self.reply(200, {'ok': True}, 'safar_session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0')
        if path == '/api/categories' and self.command == 'POST':
            name = data.get('name')
            if not isinstance(name, str) or not 1 <= len(name.strip()) <= 100 or name.strip().casefold() == 'barchasi':
                return self.reply(400, {'error': 'Kategoriya nomi 1–100 belgidan iborat bo‘lsin. Barchasi nomi band.'})
            name = name.strip()
            with connect() as db:
                names = [row[0] for row in db.execute('SELECT name FROM categories UNION SELECT category FROM dishes')]
                if any(item.casefold() == name.casefold() for item in names):
                    return self.reply(409, {'error': 'Bu kategoriya allaqachon mavjud'})
                try:
                    db.execute('INSERT INTO categories (name) VALUES (?)', (name,))
                except sqlite3.IntegrityError:
                    return self.reply(409, {'error': 'Bu kategoriya allaqachon mavjud'})
            return self.reply(201, {'name': name})
        match = re.fullmatch(r'/api/dishes/(\d+)', path)
        if not ((path == '/api/dishes' and self.command == 'POST') or (match and self.command in ('PUT', 'DELETE'))):
            return self.reply(404, {'error': 'Topilmadi'})
        if self.command != 'DELETE':
            fields = ('name', 'category', 'portion', 'description', 'price', 'image')
            for field in ('name', 'category', 'portion', 'description', 'image'):
                if not isinstance(data.get(field), str) or len(data[field]) > (1000 if field in ('description', 'image') else 100):
                    return self.reply(400, {'error': 'Maydonlar xato yoki juda uzun'})
                data[field] = data[field].strip()
            image = data['image']
            valid_image = re.fullmatch(r'images/[A-Za-z0-9_.-]+\.(jpg|jpeg|png|webp)', image) or (urlsplit(image).scheme == 'https' and urlsplit(image).netloc)
            if not data['name'] or not data['category'] or type(data.get('price')) is not int or not 0 <= data['price'] <= 100000000 or not valid_image:
                return self.reply(400, {'error': 'Nom, kategoriya, narx yoki rasm manzili xato'})
        with connect() as db:
            if self.command == 'POST':
                cursor = db.execute('INSERT INTO dishes (name,category,portion,description,price,image) VALUES (?,?,?,?,?,?)', [data[f] for f in fields])
                db.commit()
                return self.reply(201, {'id': cursor.lastrowid})
            dish_id = int(match[1])
            if not db.execute('SELECT id FROM dishes WHERE id=?', (dish_id,)).fetchone():
                return self.reply(404, {'error': 'Taom topilmadi'})
            if self.command == 'DELETE':
                db.execute('DELETE FROM dishes WHERE id=?', (dish_id,))
            else:
                db.execute('UPDATE dishes SET name=?,category=?,portion=?,description=?,price=?,image=? WHERE id=?', [data[f] for f in fields] + [dish_id])
        self.reply(200, {'ok': True})

    def upload(self):
        session = self.session()
        if not session:
            return self.reply(401, {'error': 'Avval tizimga kiring'})
        if not hmac.compare_digest(self.headers.get('X-CSRF-Token', ''), session[1]['csrf']):
            return self.reply(403, {'error': 'Sahifani yangilab qayta urining'})
        try:
            length = int(self.headers.get('Content-Length', '0'))
        except ValueError:
            length = 0
        if not 0 < length <= 5 * 1024 * 1024:
            return self.reply(413, {'error': 'Rasm hajmi 5 MB dan oshmasin'})
        body = self.rfile.read(length)
        extension = None
        if body.startswith(b'\xff\xd8\xff') and body.endswith(b'\xff\xd9'):
            extension = 'jpg'
        elif body.startswith(b'\x89PNG\r\n\x1a\n') and body[12:16] == b'IHDR' and body.endswith(b'IEND\xaeB`\x82'):
            extension = 'png'
        elif body.startswith(b'RIFF') and body[8:12] == b'WEBP' and body[12:16] in (b'VP8 ', b'VP8L', b'VP8X') and int.from_bytes(body[4:8], 'little') == len(body) - 8:
            extension = 'webp'
        if not extension or len(body) != length:
            return self.reply(400, {'error': 'JPG, PNG yoki WebP rasm tanlang'})
        UPLOADS.mkdir(exist_ok=True)
        filename = 'upload-' + secrets.token_hex(16) + '.' + extension
        (UPLOADS / filename).write_bytes(body)
        self.reply(201, {'image': 'images/' + filename})

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--setup', action='store_true')
    parser.add_argument('--port', type=int, default=8000)
    parser.add_argument('--host', default='127.0.0.1')
    args = parser.parse_args()
    initialize()
    if args.setup:
        password = getpass.getpass('Yangi admin paroli (kamida 10 belgi): ')
        if len(password) < 10 or password != getpass.getpass('Parolni takrorlang: '):
            raise SystemExit('Parol qisqa yoki mos kelmadi.')
        salt = secrets.token_hex(16)
        with connect() as db:
            db.execute('INSERT OR REPLACE INTO admin VALUES (1,?,?)', (salt, password_hash(password, salt)))
        print('Admin paroli saqlandi.')
    else:
        print(f'Safar: http://{args.host}:{args.port} | Admin: /admin', flush=True)
        ThreadingHTTPServer((args.host, args.port), Handler).serve_forever()
