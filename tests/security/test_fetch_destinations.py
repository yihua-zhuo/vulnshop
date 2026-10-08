def test_fetch_cannot_return_local_files(shop, tmp_path):
    client, _ = shop.user('fetch-admin', admin=True)
    marker = tmp_path / 'fetch.txt'
    marker.write_text('LOCAL_FETCH_MARKER_832')
    response = shop.post(client, '/admin/fetch', {'url': marker.as_uri()}, page='/admin')
    assert b'LOCAL_FETCH_MARKER_832' not in response.data


import io
import socket
import urllib.request
import pytest


@pytest.mark.parametrize('url', [
    'http://127.0.0.1/', 'http://10.0.0.1/', 'http://169.254.169.254/',
    'http://[::1]/', 'http://internal.example/',
])
def test_fetch_does_not_contact_private_destinations(shop, monkeypatch, url):
    calls = []
    def transport(self, address):
        calls.append(address)
        raise OSError('Network disabled by regression test')
    def resolve(host, port, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, '', ('127.0.0.1', port or 80))]
    monkeypatch.setattr(socket.socket, 'connect', transport)
    monkeypatch.setattr(socket, 'getaddrinfo', resolve)
    client, _ = shop.user('network-admin', admin=True)
    shop.post(client, '/admin/fetch', {'url':url}, page='/admin')
    assert not calls, 'Private destination reached the HTTP transport'
