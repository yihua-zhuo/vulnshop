"""Isolated integration fixtures; application sources are never modified."""
import importlib
import io
import re
import shutil
import sqlite3
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from werkzeug.security import generate_password_hash


@pytest.fixture
def shop(tmp_path, monkeypatch):
    root = Path(__file__).resolve().parents[2]
    isolated = tmp_path / 'shop'
    isolated.mkdir()
    for name in ('app.py', 'db.py', 'services', 'templates', 'static'):
        source = root / name
        if source.is_dir():
            shutil.copytree(source, isolated / name)
        else:
            shutil.copy2(source, isolated / name)
    monkeypatch.setenv('SHOP_DB_PATH', str(isolated / 'data' / 'shop.db'))
    monkeypatch.setenv('SHOP_ADMIN_PASSWORD', 'test-admin-only')
    monkeypatch.syspath_prepend(str(isolated))
    names = [n for n in sys.modules if n in ('app', 'db', 'services') or n.startswith('services.')]
    previous = {n: sys.modules.pop(n) for n in names}
    try:
        db = importlib.import_module('db')
        db.init_db()
        application = importlib.import_module('app').app
        application.config.update(TESTING=True)
        path = isolated / 'data' / 'shop.db'

        def sql(statement, args=()):
            with sqlite3.connect(path) as conn:
                cursor = conn.execute(statement, args)
                return cursor.fetchall() if cursor.description else cursor.lastrowid

        def user(name, admin=False):
            uid = sql('INSERT INTO users (username,password_hash,email,is_admin) VALUES (?,?,?,?)',
                      (name, generate_password_hash('test-only-password'), name + '@example.test', int(admin)))
            client = application.test_client()
            client.post('/login', data={'username': name, 'password': 'test-only-password'})
            return client, uid

        def post(client, route, data=None, page='/profile', **kwargs):
            # Read the actual rendered control so CSRF fixes do not mask other tests.
            html = client.get(page).get_data(as_text=True)
            fields = dict(data or {})
            token = re.search(r'name=["\']csrf_token["\'][^>]*value=["\']([^"\']+)', html)
            if token:
                fields['csrf_token'] = token.group(1)
            return client.post(route, data=fields, **kwargs)

        yield SimpleNamespace(app=application, sql=sql, user=user, post=post, root=isolated,
                              client=application.test_client())
    finally:
        for name in list(sys.modules):
            if name in ('app', 'db', 'services') or name.startswith('services.'):
                del sys.modules[name]
        sys.modules.update(previous)


def png(color):
    """A valid one-pixel RGB PNG, with distinct pixels for ownership tests."""
    import struct
    import zlib
    def chunk(kind, data):
        return struct.pack('!I', len(data)) + kind + data + struct.pack('!I', zlib.crc32(kind + data))
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('!2I5B', 1, 1, 8, 2, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(b'\0' + bytes(color))) + chunk(b'IEND', b''))
