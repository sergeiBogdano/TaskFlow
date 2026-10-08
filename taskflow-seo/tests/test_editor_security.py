import uuid

import pytest
from fastapi import HTTPException

from app.core.rich_text import clean_html, clean_payload
from app.web.security import _failed_logins, check_login_limit, record_login_failure, login_succeeded


def test_rich_text_removes_active_content_but_keeps_formatting():
    cleaned = clean_html('<script>alert(1)</script><p onclick="x()"><u>Hello</u><a href="javascript:alert(1)">link</a></p><img src="x" onerror="x()">')
    assert '<u>Hello</u>' in cleaned
    assert all(token not in cleaned for token in ('script', 'onclick', 'javascript:', 'onerror', '<img'))
    with pytest.raises(HTTPException) as error:
        clean_html('x' * 100001)
    assert error.value.status_code == 400
    assert clean_payload({'format': 'code', 'content': '<script>example</script>'})['content'] == '<script>example</script>'


def test_login_throttling_can_be_cleared_after_success():
    name = 'rate_' + uuid.uuid4().hex
    for _ in range(10):
        record_login_failure(name)
    with pytest.raises(HTTPException) as error:
        check_login_limit(name.upper())
    assert error.value.status_code == 429
    login_succeeded(name)
    check_login_limit(name)
    assert name not in _failed_logins


@pytest.mark.asyncio
async def test_nonroot_startup_uses_console_for_old_root_owned_logs(monkeypatch):
    from unittest.mock import AsyncMock
    from app.web import app as web
    configured = {}

    def denied(*args, **kwargs):
        raise PermissionError('test-only old volume')

    monkeypatch.setattr(web, 'RotatingFileHandler', denied)
    monkeypatch.setattr(web.logging, 'basicConfig', lambda **kwargs: configured.update(kwargs))
    for name in ('init_db', 'close_db', 'start_scheduler', 'stop_scheduler'):
        monkeypatch.setattr(web, name, AsyncMock())
    async with web.lifespan(web.app):
        assert len(configured['handlers']) == 1
        assert isinstance(configured['handlers'][0], web.logging.StreamHandler)


def test_foreign_browser_origin_cannot_modify_data(sync_request, admin_cookies):
    response = sync_request('POST', '/api/tasks', cookies=admin_cookies,
                            headers={'Origin': 'https://attacker.example'}, json={'title': 'forged'})
    assert response.status_code == 403


def test_logout_revokes_the_old_cookie(sync_request, admin_cookies):
    username = 'logout_' + uuid.uuid4().hex[:8]
    assert sync_request('POST', '/api/users', cookies=admin_cookies,
                        json={'username': username, 'password': 'pass1234'}).status_code == 201
    login = sync_request('POST', '/api/auth/login', json={'username': username, 'password': 'pass1234'})
    assert 'token' not in login.json()
    cookies = {'taskflow_user': login.cookies['taskflow_user']}
    assert sync_request('POST', '/api/auth/logout', cookies=cookies).status_code == 200
    assert sync_request('GET', '/api/auth/me', cookies=cookies).status_code == 401


def test_oversize_request_rejected_before_parsing(sync_request, admin_cookies):
    response = sync_request('POST', '/api/tasks', cookies=admin_cookies,
                            headers={'Content-Length': str(2 * 1024 * 1024)}, json={'title': 'oversize'})
    assert response.status_code == 413


@pytest.mark.asyncio
async def test_upload_checks_actual_image_and_stops_at_limit(monkeypatch):
    from io import BytesIO
    from starlette.datastructures import UploadFile
    from PIL import Image
    from app.core.uploads import read_upload
    from app.core.config import settings
    content = BytesIO()
    Image.new('RGB', (4, 4)).save(content, format='PNG')
    data, name, mime = await read_upload(UploadFile(BytesIO(content.getvalue()), filename='test.png'))
    assert data and name == 'test.png' and mime == 'image/png'
    for filename, raw in [('fake.png', b'not an image'), ('script.svg', b'<svg/>'), ('bad.pdf', b'not a PDF')]:
        with pytest.raises(HTTPException) as error:
            await read_upload(UploadFile(BytesIO(raw), filename=filename))
        assert error.value.status_code == 415
    monkeypatch.setattr(settings, 'MAX_UPLOAD_SIZE_MB', 1)
    file = UploadFile(BytesIO(b'x' * (2 * 1024 * 1024)), filename='large.txt')
    with pytest.raises(HTTPException) as error:
        await read_upload(file)
    assert error.value.status_code == 413
    assert file.file.tell() <= 1024 * 1024 + 65536
