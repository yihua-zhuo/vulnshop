import io
from conftest import png


def test_same_basename_cannot_overwrite_other_avatar(shop):
    first, uid = shop.user('avatar-first')
    second, _ = shop.user('avatar-second')
    shop.post(first, '/upload-avatar', {'avatar': (io.BytesIO(png((255,0,0))), 'portrait.png')})
    saved = shop.sql('SELECT avatar_path FROM users WHERE id=?', (uid,))[0][0]
    assert saved, 'Valid initial avatar must be accepted'
    files = list((shop.root / 'static').rglob('*'))
    candidates = [p for p in files if p.is_file() and (str(p).endswith(saved) or p.name == saved)]
    assert candidates, 'Initial avatar must have a persistent file'
    path = candidates[0]
    original = path.read_bytes()
    shop.post(second, '/upload-avatar', {'avatar': (io.BytesIO(png((0,0,255))), 'portrait.png')})
    assert path.read_bytes() == original, 'Another customer replaced the first avatar'
