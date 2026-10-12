import socket
from app.core.favicons import public_host, fetch_icon


def test_reject_local_or_credentialed_hosts():
    for domain in ('localhost', '127.0.0.1', 'https://a:b@example.org', 'example.org:8080', 'local.local', 'file://example.org'):
        assert public_host(domain) is None
    assert public_host('https://example.org/path') == 'example.org'


def test_private_dns_address_never_opens_a_connection(monkeypatch):
    monkeypatch.setattr(socket, 'getaddrinfo', lambda *a, **k: [(2, 1, 6, '', ('127.0.0.1', 443))])
    monkeypatch.setattr(socket, 'create_connection', lambda *a, **k: (_ for _ in ()).throw(AssertionError('Private connection')))
    assert fetch_icon('example.org') is None


def test_mixed_public_private_dns_is_rejected(monkeypatch):
    monkeypatch.setattr(socket, 'getaddrinfo', lambda *a, **k: [(2, 1, 6, '', ('8.8.8.8', 443)), (2, 1, 6, '', ('192.168.1.2', 443))])
    monkeypatch.setattr(socket, 'create_connection', lambda *a, **k: (_ for _ in ()).throw(AssertionError('Mixed connection')))
    assert fetch_icon('example.org') is None


def test_pinned_tls_and_bounded_image_response(monkeypatch):
    import app.core.favicons as module
    seen = {}
    monkeypatch.setattr(socket, 'getaddrinfo', lambda *a, **k: [(2, 1, 6, '', ('8.8.8.8', 443))])
    class Raw:
        def close(self):
            pass
    def connect(address, timeout):
        seen['address'] = address
        return Raw()
    monkeypatch.setattr(socket, 'create_connection', connect)
    class Context:
        def wrap_socket(self, raw, server_hostname):
            seen['tls_host'] = server_hostname
            return raw
    monkeypatch.setattr(module.ssl, 'create_default_context', lambda: Context())
    class Response:
        status = 200
        def read(self, limit):
            assert limit == 65537
            return b'\x89PNG\r\n\x1a\nicon'
    class Connection:
        def __init__(self, host, timeout):
            assert host == 'example.org'
        def request(self, method, path, headers):
            assert method == 'GET' and path == '/favicon.ico'
            self.connect()
        def getresponse(self):
            return Response()
        def close(self):
            pass
    monkeypatch.setattr(module.http.client, 'HTTPSConnection', Connection)
    assert fetch_icon('example.org')[1] == 'image/png'
    assert seen == {'address': ('8.8.8.8', 443), 'tls_host': 'example.org'}
    Response.status = 302
    assert fetch_icon('example.org') is None
