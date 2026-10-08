import pytest

@pytest.mark.parametrize('url', ['/static/files/internal-notes.txt', '/download?file=internal-notes.txt'])
def test_internal_notes_are_not_public(shop, url):
    response = shop.client.get(url)
    assert response.status_code != 200, 'Anonymous caller received the internal notes asset'
