"""Bounded favicon downloads: public DNS addresses, pinned TLS, no redirects."""
import asyncio
import http.client
import ipaddress
import socket
import ssl
import time
from urllib.parse import urlsplit

_cache = {}
_gate = asyncio.Semaphore(2)


def public_host(domain):
    value = domain.strip()
    url = urlsplit(value if '://' in value else 'https://' + value)
    if url.scheme not in ('http', 'https') or url.username or url.password or url.port:
        return None
    host = (url.hostname or '').encode('idna').decode('ascii')
    if '.' not in host or host.endswith(('.local', '.localhost')):
        return None
    try:
        ipaddress.ip_address(host)
        return None
    except ValueError:
        return host


def fetch_icon(domain):
    host = public_host(domain)
    if not host:
        return None
    addresses = list(dict.fromkeys(row[4][0] for row in socket.getaddrinfo(host, 443, family=socket.AF_INET, type=socket.SOCK_STREAM)))
    if not addresses or any(not ipaddress.ip_address(address).is_global for address in addresses):
        return None
    # Resolve once and connect to the checked address, while verifying TLS for host.
    class PinnedTLS(http.client.HTTPSConnection):
        def connect(self):
            raw = socket.create_connection((addresses[0], 443), timeout=3)
            try:
                self.sock = ssl.create_default_context().wrap_socket(raw, server_hostname=host)
            except Exception:
                raw.close()
                raise
    connection = PinnedTLS(host, timeout=3)
    try:
        connection.request('GET', '/favicon.ico', headers={'User-Agent': 'TaskFlow-Favicon/1.0', 'Accept': 'image/*'})
        response = connection.getresponse()
        if response.status != 200:
            return None
        data = response.read(65537)
        if not data or len(data) > 65536:
            return None
        if data.startswith(b'\x89PNG\r\n\x1a\n'):
            mime = 'image/png'
        elif data.startswith(b'\x00\x00\x01\x00'):
            mime = 'image/x-icon'
        elif data.startswith(b'\xff\xd8\xff'):
            mime = 'image/jpeg'
        elif data.startswith((b'GIF87a', b'GIF89a')):
            mime = 'image/gif'
        elif data.startswith(b'RIFF') and data[8:12] == b'WEBP':
            mime = 'image/webp'
        else:
            return None
        return data, mime
    finally:
        connection.close()


async def favicon(domain):
    if not domain:
        return None
    cached = _cache.get(domain)
    if cached and cached[0] > time.monotonic():
        return cached[1]
    async with _gate:
        cached = _cache.get(domain)
        if cached and cached[0] > time.monotonic():
            return cached[1]
        try:
            value = await asyncio.wait_for(asyncio.to_thread(fetch_icon, domain), timeout=8)
        except Exception:
            value = None
        if len(_cache) >= 256:
            _cache.pop(next(iter(_cache)))
        _cache[domain] = (time.monotonic() + (86400 if value else 900), value)
        return value
