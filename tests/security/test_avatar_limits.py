import io


def test_large_nonimage_upload_is_not_persisted(shop):
    client, uid = shop.user('upload-limit')
    # Finite 16 MiB probe: never fills a disk, even on vulnerable code.
    payload = b'not-an-image\n' + b'x' * (16 * 1024 * 1024)
    before = sum(p.stat().st_size for p in (shop.root / 'static').rglob('*') if p.is_file())
    shop.post(client, '/upload-avatar', {'avatar': (io.BytesIO(payload), 'large.png')})
    after = sum(p.stat().st_size for p in (shop.root / 'static').rglob('*') if p.is_file())
    assert after - before < len(payload), 'Entire oversized non-image persisted as an avatar'
