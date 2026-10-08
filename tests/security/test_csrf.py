import io
import subprocess
import urllib.request
import pytest
from conftest import png

@pytest.mark.parametrize('route,data', [
    ('/comment', {'product_id':'1','content':'CSRF_MARKER'}),
    ('/profile/update', {'bio':'CSRF_MARKER'}),
    ('/transfer', {'to':'1','amount':'1'}),
    ('/upload-avatar', {}),
    ('/admin/ping', {'host':'localhost'}),
    ('/admin/fetch', {'url':'http://localhost/'}),
    ('/admin/import-xml', {'xml':'<order>CSRF_MARKER</order>'}),
    ('/admin/restore', {'blob':'7d942e'}),
])
def test_session_post_without_csrf_is_refused(shop, route, data, monkeypatch):
    monkeypatch.setattr(subprocess, 'run', lambda *a, **k: subprocess.CompletedProcess(a, 0, '', ''))
    monkeypatch.setattr(urllib.request.OpenerDirector, 'open', lambda *a, **k: io.BytesIO(b'LOCAL_STUB'))
    client, _ = shop.user('csrf-admin', admin=True)
    client.get('/admin')
    fields = dict(data)
    if route == '/upload-avatar':
        fields['avatar'] = (io.BytesIO(png((0,0,0))), 'csrf.png')
    response = client.post(route, data=fields, headers={'Origin':'https://untrusted.example'})
    assert response.status_code in (400, 403), 'Cross-origin POST without token was accepted'
