from urllib.parse import urlsplit
import pytest

@pytest.mark.parametrize('target', ['https://untrusted.example/path', '//untrusted.example/path'])
def test_redirect_stays_local(shop, target):
    response = shop.client.get('/redirect', query_string={'url':target})
    location = response.headers.get('Location', '')
    assert not urlsplit(location).netloc or urlsplit(location).netloc == 'localhost'
