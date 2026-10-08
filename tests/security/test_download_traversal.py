def test_encoded_download_cannot_escape_root(shop):
    marker = shop.root / 'static' / 'outside.txt'
    marker.write_text('OUTSIDE_DOWNLOAD_MARKER')
    response = shop.client.get('/download', query_string={'file':'%2e%2e%2foutside.txt'})
    assert b'OUTSIDE_DOWNLOAD_MARKER' not in response.data
