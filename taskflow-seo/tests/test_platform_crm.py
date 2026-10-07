"""Production API regression scenarios for platform identity, tenant isolation and CRM."""
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from tests.test_user_permissions import _make_user


def unique(prefix):
    return prefix + '_' + uuid.uuid4().hex[:10]


@pytest.fixture
def crm_space(sync_request, admin_cookies):
    space = sync_request('POST', '/api/workspaces', json={'name': unique('Sales'), 'preset': 'seo'}, cookies=admin_cookies)
    assert space.status_code == 201, space.text
    ident = space.json()['id']
    pipeline = sync_request('POST', f'/api/crm/pipelines?workspace_id={ident}', json={
        'name': 'Sales', 'stages': [{'id': 'new', 'label': 'Новая'}, {'id': 'won', 'label': 'Успешно', 'outcome': 'won'}]}, cookies=admin_cookies)
    assert pipeline.status_code == 201, pipeline.text
    return ident, pipeline.json()['id']


def make_deal(sync_request, cookies, space, **extra):
    wid, pid = space
    response = sync_request('POST', f'/api/crm/deals?workspace_id={wid}', json={
        'title': unique('Deal'), 'pipeline_id': pid, 'stage': 'new', **extra}, cookies=cookies)
    return response


def test_new_account_onboarding_and_session_revocation(sync_request, admin_cookies):
    name = unique('onboard')
    created = sync_request('POST', '/api/users', json={'username': name, 'password': 'temporary123', 'must_change_password': True}, cookies=admin_cookies)
    assert created.status_code == 201
    login = sync_request('POST', '/api/auth/login', json={'username': name, 'password': 'temporary123'})
    old = {'taskflow_user': login.cookies['taskflow_user']}
    assert sync_request('GET', '/api/auth/me', cookies=old).json()['user']['must_change_password'] is True
    assert sync_request('GET', '/api/workspaces', cookies=old).status_code == 403
    changed = sync_request('POST', '/api/users/change-password', json={'current_password': 'temporary123', 'new_password': 'permanent123'}, cookies=old)
    assert changed.status_code == 200
    assert sync_request('GET', '/api/auth/me', cookies=old).status_code == 401
    fresh = {'taskflow_user': changed.cookies['taskflow_user']}
    assert sync_request('GET', '/api/workspaces', cookies=fresh).json() == []
    assert sync_request('GET', '/api/auth/me', cookies=fresh).json()['user']['must_change_password'] is False


def test_block_unblock_does_not_restore_old_session(sync_request, admin_cookies):
    name = unique('block')
    uid, cookies = _make_user(sync_request, admin_cookies, name)
    for active in (False, True):
        assert sync_request('PATCH', f'/api/users/{uid}/status', json={'is_active': active}, cookies=admin_cookies).status_code == 200
        assert sync_request('GET', '/api/auth/me', cookies=cookies).status_code == 401
    assert sync_request('POST', '/api/auth/login', json={'username': name, 'password': 'pass1234'}).status_code == 200
    assert sync_request('PATCH', '/api/users/1/status', json={'is_active': False}, cookies=admin_cookies).status_code == 403


def test_study_space_has_no_crm_even_for_root(sync_request, admin_cookies):
    space = sync_request('POST', '/api/workspaces', json={'name': unique('Study'), 'preset': 'study'}, cookies=admin_cookies).json()
    assert 'crm' not in space['enabled_modules']
    for route in ('/api/clients', '/api/crm/deals'):
        assert sync_request('GET', f"{route}?workspace_id={space['id']}", cookies=admin_cookies).status_code == 403
    task = sync_request('POST', f"/api/tasks?workspace_id={space['id']}", json={'title': 'Учебная задача без клиента'}, cookies=admin_cookies)
    assert task.status_code == 201


def test_module_off_preserves_data(sync_request, admin_cookies, crm_space):
    wid, _ = crm_space
    deal = make_deal(sync_request, admin_cookies, crm_space).json()
    assert sync_request('PUT', f'/api/workspaces/{wid}/modules', json={'enabled': ['tasks', 'notes']}, cookies=admin_cookies).status_code == 200
    assert sync_request('GET', f'/api/crm/deals?workspace_id={wid}', cookies=admin_cookies).status_code == 403
    assert sync_request('PUT', f'/api/workspaces/{wid}/modules', json={'enabled': ['tasks', 'notes', 'crm']}, cookies=admin_cookies).status_code == 200
    assert any(d['id'] == deal['id'] for d in sync_request('GET', f'/api/crm/deals?workspace_id={wid}', cookies=admin_cookies).json())


def test_platform_admin_does_not_read_unjoined_space(sync_request, admin_cookies, crm_space):
    uid, cookies = _make_user(sync_request, admin_cookies, unique('appadmin'))
    role = next(r for r in sync_request('GET', '/api/roles', cookies=admin_cookies).json() if r['name'] == 'admin')
    assert sync_request('PUT', f'/api/users/{uid}/role', json={'role_id': role['id']}, cookies=admin_cookies).status_code == 200
    assert sync_request('GET', f'/api/crm/deals?workspace_id={crm_space[0]}', cookies=cookies).status_code == 403
    assert sync_request('POST', '/api/roles', json={'name': unique('escalation'), 'permissions': {'all': True}}, cookies=cookies).status_code == 403
    assert sync_request('PUT', f'/api/workspaces/{crm_space[0]}/modules', json={'enabled': []}, cookies=cookies).status_code == 403


@pytest.mark.parametrize('visibility,can_join,in_directory', [('open', 200, True), ('closed', 403, True), ('hidden', 404, False)])
def test_space_directory_visibility(sync_request, admin_cookies, visibility, can_join, in_directory):
    _, cookies = _make_user(sync_request, admin_cookies, unique('visitor'))
    ws = sync_request('POST', '/api/workspaces', json={'name': unique('Space'), 'visibility': visibility}, cookies=admin_cookies).json()
    listing = sync_request('GET', '/api/workspaces/directory/list', cookies=cookies).json()
    assert any(w['id'] == ws['id'] for w in listing) == in_directory
    assert sync_request('POST', f"/api/workspaces/{ws['id']}/join", cookies=cookies).status_code == can_join
    assert sync_request('GET', f"/api/workspaces/{ws['id']}", cookies=cookies).status_code == (200 if visibility == 'open' else 403)


def test_new_crm_permissions_are_not_implicitly_granted(sync_request, admin_cookies, crm_space):
    uid, cookies = _make_user(sync_request, admin_cookies, unique('manager'))
    wid, _ = crm_space
    assert sync_request('POST', f'/api/workspaces/{wid}/members', json={'user_id': uid, 'role': 'admin'}, cookies=admin_cookies).status_code == 201
    assert sync_request('GET', f'/api/crm/deals?workspace_id={wid}', cookies=cookies).status_code == 403
    role = sync_request('POST', f'/api/workspaces/{wid}/roles', json={'name': 'Sales viewer', 'permissions': {'crm': True}}, cookies=admin_cookies)
    assert role.status_code == 201, role.text
    assert sync_request('PUT', f'/api/workspaces/{wid}/members/{uid}/custom-role', json={'role_id': role.json()['id']}, cookies=admin_cookies).status_code == 200
    assert sync_request('GET', f'/api/crm/deals?workspace_id={wid}', cookies=cookies).status_code == 200
    assert make_deal(sync_request, cookies, crm_space).status_code == 403


def test_deal_archive_trash_restore_and_purge(sync_request, admin_cookies, crm_space):
    wid, _ = crm_space
    deal = make_deal(sync_request, admin_cookies, crm_space)
    assert deal.status_code == 201, deal.text
    ident = deal.json()['id']
    url = f'/api/crm/deals/{ident}?workspace_id={wid}'
    assert sync_request('PATCH', url, json={'archived': True}, cookies=admin_cookies).status_code == 200
    assert not sync_request('GET', f'/api/crm/deals?workspace_id={wid}', cookies=admin_cookies).json()
    assert len(sync_request('GET', f'/api/crm/deals?workspace_id={wid}&archived=true', cookies=admin_cookies).json()) == 1
    assert sync_request('PATCH', url, json={'archived': False}, cookies=admin_cookies).status_code == 200
    assert sync_request('DELETE', url, cookies=admin_cookies).status_code == 200
    assert sync_request('PATCH', url, json={'title': 'Cannot edit trash'}, cookies=admin_cookies).status_code == 409
    assert sync_request('POST', f'/api/crm/deals/{ident}/restore?workspace_id={wid}', cookies=admin_cookies).status_code == 200
    assert sync_request('DELETE', url + '&permanent=true', cookies=admin_cookies).status_code == 200
    assert sync_request('POST', f'/api/crm/deals/{ident}/restore?workspace_id={wid}', cookies=admin_cookies).status_code == 404


def test_invalid_pipeline_changes_and_money(sync_request, admin_cookies, crm_space):
    wid, pid = crm_space
    assert make_deal(sync_request, admin_cookies, crm_space, amount='-1').status_code == 422
    assert make_deal(sync_request, admin_cookies, crm_space, amount='100.123').status_code == 422
    assert make_deal(sync_request, admin_cookies, crm_space, stage='foreign').status_code == 400
    assert make_deal(sync_request, admin_cookies, crm_space).status_code == 201
    response = sync_request('PATCH', f'/api/crm/pipelines/{pid}?workspace_id={wid}', json={'stages': [{'id': 'won', 'label': 'Успех'}]}, cookies=admin_cookies)
    assert response.status_code == 409
    assert sync_request('DELETE', f'/api/crm/pipelines/{pid}?workspace_id={wid}', cookies=admin_cookies).status_code == 409


def test_custom_fields_types_required_order(sync_request, admin_cookies, crm_space):
    wid, _ = crm_space
    field = sync_request('POST', f'/api/crm/fields?workspace_id={wid}', json={'key': 'source', 'label': 'Источник', 'required': True}, cookies=admin_cookies)
    assert field.status_code == 201
    assert make_deal(sync_request, admin_cookies, crm_space).status_code == 400
    assert make_deal(sync_request, admin_cookies, crm_space, custom_fields={'source': 3}).status_code == 400
    valid = make_deal(sync_request, admin_cookies, crm_space, custom_fields={'source': 'Рекомендация'})
    assert valid.status_code == 201
    assert sync_request('PATCH', f"/api/crm/fields/{field.json()['id']}?workspace_id={wid}", json={'position': 10}, cookies=admin_cookies).status_code == 200
    assert sync_request('PATCH', f"/api/crm/fields/{field.json()['id']}?workspace_id={wid}", json={'kind': 'number'}, cookies=admin_cookies).status_code == 400


def test_cross_space_references_and_object_updates(sync_request, admin_cookies, crm_space):
    other = sync_request('POST', '/api/workspaces', json={'name': unique('Other'), 'preset': 'seo'}, cookies=admin_cookies).json()['id']
    contact = sync_request('POST', f'/api/crm/contacts?workspace_id={other}', json={'name': 'Foreign'}, cookies=admin_cookies).json()
    assert make_deal(sync_request, admin_cookies, crm_space, contact_id=contact['id']).status_code == 404
    deal = make_deal(sync_request, admin_cookies, crm_space).json()
    assert sync_request('PATCH', f"/api/crm/deals/{deal['id']}?workspace_id={other}", json={'title': 'Leaked'}, cookies=admin_cookies).status_code == 404
    task = sync_request('POST', f'/api/tasks?workspace_id={other}', json={'title': 'Other task'}, cookies=admin_cookies).json()
    assert make_deal(sync_request, admin_cookies, crm_space, task_id=task['id']).status_code == 404


def test_contract_renewal_links_task_and_preserves_identity(sync_request, admin_cookies, crm_space):
    wid, _ = crm_space
    client = sync_request('POST', f'/api/clients?workspace_id={wid}', json={'org_name': unique('Org'), 'contracts': [{'contract_type': 'SEO', 'start_date': '2026-01-01', 'end_date': '2026-12-31'}]}, cookies=admin_cookies)
    assert client.status_code == 201, client.text
    cid = client.json()['id']
    full = sync_request('GET', f'/api/clients/{cid}?workspace_id={wid}', cookies=admin_cookies).json()
    contract = full['contracts'][0]
    deal = make_deal(sync_request, admin_cookies, crm_space, client_id=cid, contract_id=contract['id']).json()
    response = sync_request('POST', f"/api/crm/contracts/{contract['id']}/renew?workspace_id={wid}", json={'end_date': '2027-12-31T12:00:00Z'}, cookies=admin_cookies)
    assert response.status_code == 200, response.text
    assert response.json()['task_id']
    task = sync_request('GET', f"/api/tasks/{response.json()['task_id']}?workspace_id={wid}", cookies=admin_cookies).json()
    assert task['contract_id'] == contract['id']
    listing = sync_request('GET', f'/api/crm/deals?workspace_id={wid}', cookies=admin_cookies).json()
    assert next(d for d in listing if d['id'] == deal['id'])['task_id'] == response.json()['task_id']
    assert sync_request('PUT', f'/api/clients/{cid}?workspace_id={wid}', json={'contracts': []}, cookies=admin_cookies).status_code == 409


def test_space_purge_removes_crm(sync_request, admin_cookies, crm_space, event_loop):
    from app.core.database import async_session
    from app.core.models import CrmActivity, CrmContact, CrmDeal, CrmField, CrmPipeline
    from sqlalchemy import func, select
    wid, _ = crm_space
    deal = make_deal(sync_request, admin_cookies, crm_space).json()
    assert sync_request('POST', f'/api/crm/activities?workspace_id={wid}', json={'deal_id': deal['id'], 'title': 'Call'}, cookies=admin_cookies).status_code == 201
    assert sync_request('DELETE', f'/api/workspaces/{wid}?permanent=true', cookies=admin_cookies).status_code == 200
    async def check():
        async with async_session() as session:
            for model in (CrmActivity, CrmContact, CrmDeal, CrmField, CrmPipeline):
                assert (await session.execute(select(func.count()).select_from(model).where(model.workspace_id == wid))).scalar() == 0
    event_loop.run_until_complete(check())


def test_search_and_activity_never_leak_other_space(sync_request, admin_cookies, crm_space):
    from tests.test_user_permissions import _make_workspace
    _, cookies = _make_user(sync_request, admin_cookies, unique('searcher'))
    own = _make_workspace(sync_request, cookies, unique('Own'), 'study')
    wid = crm_space[0]
    title = unique('Secret')
    assert sync_request('POST', f'/api/tasks?workspace_id={wid}', json={'title': title}, cookies=admin_cookies).status_code == 201
    result = sync_request('GET', f"/api/search?q={title}&workspace_id={own['id']}", cookies=cookies)
    assert result.status_code == 200, result.text
    assert result.json() == {'tasks': [], 'clients': []}
    logs = sync_request('GET', f"/api/activity?workspace_id={own['id']}", cookies=cookies)
    assert logs.status_code == 200
    assert title not in logs.text


def test_module_restore_requires_explicit_feature_opt_in(sync_request, admin_cookies, crm_space):
    wid, _ = crm_space
    uid, cookies = _make_user(sync_request, admin_cookies, unique('restore_user'))
    sync_request('POST', f'/api/workspaces/{wid}/members', json={'user_id': uid, 'role': 'member'}, cookies=admin_cookies)
    role = sync_request('POST', f'/api/workspaces/{wid}/roles', json={'name': unique('Viewer'), 'permissions': {'crm': True}}, cookies=admin_cookies).json()
    sync_request('PUT', f'/api/workspaces/{wid}/members/{uid}/custom-role', json={'role_id': role['id']}, cookies=admin_cookies)
    assert sync_request('GET', f'/api/crm/deals?workspace_id={wid}', cookies=cookies).status_code == 200
    for modules in (['tasks', 'notes'], ['tasks', 'notes', 'crm']):
        assert sync_request('PUT', f'/api/workspaces/{wid}/modules', json={'enabled': modules}, cookies=admin_cookies).status_code == 200
        assert sync_request('GET', f'/api/crm/deals?workspace_id={wid}', cookies=cookies).status_code == 403
    assert sync_request('PUT', '/api/features', json={'scope': 'workspace', 'target_id': wid, 'key': 'crm', 'enabled': True}, cookies=admin_cookies).status_code == 200
    assert sync_request('GET', f'/api/crm/deals?workspace_id={wid}', cookies=cookies).status_code == 200


def test_custom_role_stays_exact_after_restart(sync_request, admin_cookies, crm_space, event_loop):
    from app.core.database import _migrate_custom_roles_exact, _ensure_workspaces
    wid, _ = crm_space
    uid, cookies = _make_user(sync_request, admin_cookies, unique('restart_role'))
    sync_request('POST', f'/api/workspaces/{wid}/members', json={'user_id': uid, 'role': 'admin'}, cookies=admin_cookies)
    role = sync_request('POST', f'/api/workspaces/{wid}/roles', json={'name': unique('OnlyCRM'), 'permissions': {'crm': True}}, cookies=admin_cookies).json()
    sync_request('PUT', f'/api/workspaces/{wid}/members/{uid}/custom-role', json={'role_id': role['id']}, cookies=admin_cookies)
    for _ in range(2):
        event_loop.run_until_complete(_migrate_custom_roles_exact())
        event_loop.run_until_complete(_ensure_workspaces())
        permissions = sync_request('GET', f'/api/auth/me?workspace_id={wid}', cookies=cookies).json()['user']['permissions']
        assert permissions.get('crm') is True
        assert not permissions.get('tasks')
        assert not permissions.get('client_delete')


def test_global_restore_does_not_revive_user_access(sync_request, admin_cookies, crm_space):
    wid, _ = crm_space
    uid, cookies = _make_user(sync_request, admin_cookies, unique('globalrestore'))
    sync_request('POST', f'/api/workspaces/{wid}/members', json={'user_id': uid, 'role': 'member'}, cookies=admin_cookies)
    role = sync_request('POST', f'/api/workspaces/{wid}/roles', json={'name': unique('CRM'), 'permissions': {'crm': True}}, cookies=admin_cookies).json()
    sync_request('PUT', f'/api/workspaces/{wid}/members/{uid}/custom-role', json={'role_id': role['id']}, cookies=admin_cookies)
    try:
        for enabled in (False, True):
            assert sync_request('PUT', '/api/features', json={'scope': 'global', 'key': 'crm', 'enabled': enabled}, cookies=admin_cookies).status_code == 200
            assert sync_request('GET', f'/api/crm/deals?workspace_id={wid}', cookies=cookies).status_code == 403
        sync_request('PUT', '/api/features', json={'scope': 'user', 'target_id': uid, 'key': 'crm', 'enabled': True}, cookies=admin_cookies)
        assert sync_request('GET', f'/api/crm/deals?workspace_id={wid}', cookies=cookies).status_code == 200
    finally:
        sync_request('PUT', '/api/features', json={'scope': 'global', 'key': 'crm', 'enabled': True}, cookies=admin_cookies)


def test_archived_deal_visible_in_trash_and_restores_to_archive(sync_request, admin_cookies, crm_space):
    wid, _ = crm_space
    deal = make_deal(sync_request, admin_cookies, crm_space, archived=True).json()
    url = f"/api/crm/deals/{deal['id']}?workspace_id={wid}"
    assert sync_request('DELETE', url, cookies=admin_cookies).status_code == 200
    trash = sync_request('GET', f'/api/crm/deals?workspace_id={wid}&deleted=true', cookies=admin_cookies).json()
    assert any(item['id'] == deal['id'] for item in trash)
    assert sync_request('POST', f"/api/crm/deals/{deal['id']}/restore?workspace_id={wid}", cookies=admin_cookies).status_code == 200
    archive = sync_request('GET', f'/api/crm/deals?workspace_id={wid}&archived=true', cookies=admin_cookies).json()
    assert any(item['id'] == deal['id'] for item in archive)


def test_deal_tasks_history_is_scoped_and_survives_deal_removal(sync_request, admin_cookies, crm_space):
    wid, _ = crm_space
    deal = make_deal(sync_request, admin_cookies, crm_space).json()
    url = f"/api/crm/deals/{deal['id']}/tasks?workspace_id={wid}"
    tasks = []
    for title in ('Подготовить предложение', 'Проверить результат'):
        response = sync_request('POST', url, json={'title': title}, cookies=admin_cookies)
        assert response.status_code == 201, response.text
        tasks.append(response.json()['id'])
    assert {t['id'] for t in sync_request('GET', url, cookies=admin_cookies).json()} == set(tasks)
    other = sync_request('POST', '/api/workspaces', json={'name': unique('ForeignTasks'), 'preset': 'seo'}, cookies=admin_cookies).json()['id']
    assert sync_request('GET', f"/api/crm/deals/{deal['id']}/tasks?workspace_id={other}", cookies=admin_cookies).status_code == 404
    uid, _ = _make_user(sync_request, admin_cookies, unique('outsider'))
    assert sync_request('POST', url, json={'title': 'Wrong assignee', 'assignee_id': uid}, cookies=admin_cookies).status_code == 400
    assert sync_request('PATCH', f"/api/crm/deals/{deal['id']}?workspace_id={wid}", json={'archived': True}, cookies=admin_cookies).status_code == 200
    assert sync_request('POST', url, json={'title': 'Archived'}, cookies=admin_cookies).status_code == 409
    assert sync_request('DELETE', f"/api/crm/deals/{deal['id']}?workspace_id={wid}&permanent=true", cookies=admin_cookies).status_code == 200
    for tid in tasks:
        task = sync_request('GET', f'/api/tasks/{tid}?workspace_id={wid}', cookies=admin_cookies)
        assert task.status_code == 200
        assert task.json()['crm_deal_id'] is None


def test_deal_task_contract_limits_and_module_switch(sync_request, admin_cookies, crm_space):
    wid, _ = crm_space
    client = sync_request('POST', f'/api/clients?workspace_id={wid}', json={'org_name': unique('Bound'), 'contracts': [{'contract_type': 'Support', 'start_date': '2026-01-01', 'end_date': '2026-12-31'}]}, cookies=admin_cookies).json()
    full = sync_request('GET', f"/api/clients/{client['id']}?workspace_id={wid}", cookies=admin_cookies).json()
    contract = full['contracts'][0]['id']
    deal = make_deal(sync_request, admin_cookies, crm_space, client_id=client['id'], contract_id=contract).json()
    url = f"/api/crm/deals/{deal['id']}/tasks?workspace_id={wid}"
    assert sync_request('POST', url, json={'title': 'Too late', 'deadline': '2027-01-01T12:00:00Z'}, cookies=admin_cookies).status_code == 400
    created = sync_request('POST', url, json={'title': 'Delivery', 'deadline': '2026-12-01T12:00:00Z'}, cookies=admin_cookies)
    assert created.status_code == 201, created.text
    assert created.json()['contract_id'] == contract
    switched = sync_request('PUT', f'/api/workspaces/{wid}/modules', json={'enabled': ['crm', 'notes']}, cookies=admin_cookies)
    assert switched.status_code == 200, switched.text
    assert sync_request('POST', url, json={'title': 'Disabled'}, cookies=admin_cookies).status_code == 403
    assert sync_request('GET', url, cookies=admin_cookies).status_code == 403


def test_contract_files_need_tab_permission_and_writes_need_edit(sync_request, admin_cookies, crm_space):
    from io import BytesIO
    wid, _ = crm_space
    client = sync_request('POST', f'/api/clients?workspace_id={wid}', json={'org_name': unique('Files'), 'contracts': [{'contract_type': 'Private', 'start_date': '2026-01-01', 'end_date': '2026-12-31'}]}, cookies=admin_cookies).json()
    cid = client['id']
    full = sync_request('GET', f'/api/clients/{cid}?workspace_id={wid}', cookies=admin_cookies).json()
    contract = full['contracts'][0]['id']
    uploaded = sync_request('POST', f'/api/clients/{cid}/contracts/{contract}/upload?workspace_id={wid}', files={'file': ('contract.txt', BytesIO(b'confidential'), 'text/plain')}, cookies=admin_cookies)
    assert uploaded.status_code == 200, uploaded.text
    fid = uploaded.json()['id']
    uid, cookies = _make_user(sync_request, admin_cookies, unique('file_reader'))
    assert sync_request('POST', f'/api/workspaces/{wid}/members', json={'user_id': uid}, cookies=admin_cookies).status_code == 201
    role = sync_request('POST', f'/api/workspaces/{wid}/roles', json={'name': unique('Reader'), 'permissions': {'clients': True}}, cookies=admin_cookies)
    assert role.status_code == 201, role.text
    assert sync_request('PUT', f'/api/workspaces/{wid}/members/{uid}/custom-role', json={'role_id': role.json()['id']}, cookies=admin_cookies).status_code == 200
    for url in (f'/api/clients/{cid}/contracts/{contract}/files', f'/api/clients/{cid}/files/{fid}/download', f'/api/files/{fid}/download'):
        assert sync_request('GET', url+f'?workspace_id={wid}', cookies=cookies).status_code == 403
    assert sync_request('DELETE', f'/api/clients/{cid}/files/{fid}?workspace_id={wid}', cookies=cookies).status_code == 403
    assert sync_request('POST', f'/api/clients/{cid}/upload?workspace_id={wid}', files={'file': ('new.txt', BytesIO(b'new'), 'text/plain')}, cookies=cookies).status_code == 403


def test_orphan_file_is_not_downloadable(sync_request, admin_cookies, event_loop):
    from app.core.database import async_session
    from app.core.models import FileAttachment
    async def seed():
        async with async_session() as session:
            row = FileAttachment(filename='orphan.txt', original_name='orphan.txt', data=b'secret')
            session.add(row)
            await session.commit()
            return row.id
    fid = event_loop.run_until_complete(seed())
    assert sync_request('GET', f'/api/files/{fid}/download', cookies=admin_cookies).status_code == 404
    assert sync_request('DELETE', f'/api/files/{fid}', cookies=admin_cookies).status_code == 404


def test_disabled_edit_feature_blocks_writes_even_when_role_grants_it(sync_request, admin_cookies, crm_space):
    wid, _ = crm_space
    uid, cookies = _make_user(sync_request, admin_cookies, unique('edit_switch'))
    assert sync_request('POST', f'/api/workspaces/{wid}/members', json={'user_id': uid}, cookies=admin_cookies).status_code == 201
    role = sync_request('POST', f'/api/workspaces/{wid}/roles', json={'name': unique('Editor'), 'permissions': {'crm': True, 'crm_edit': True}}, cookies=admin_cookies)
    assert role.status_code == 201, role.text
    assert sync_request('PUT', f'/api/workspaces/{wid}/members/{uid}/custom-role', json={'role_id': role.json()['id']}, cookies=admin_cookies).status_code == 200
    assert make_deal(sync_request, cookies, crm_space).status_code == 201
    assert sync_request('PUT', '/api/features', json={'scope': 'user', 'target_id': uid, 'key': 'crm_edit', 'enabled': False}, cookies=admin_cookies).status_code == 200
    assert sync_request('GET', f'/api/crm/deals?workspace_id={wid}', cookies=cookies).status_code == 200
    assert make_deal(sync_request, cookies, crm_space).status_code == 403


def test_recreated_account_does_not_inherit_session_or_browser_identity(sync_request, admin_cookies):
    name = unique('recreated')
    uid, old_cookie = _make_user(sync_request, admin_cookies, name)
    old_key = sync_request('GET', '/api/auth/me', cookies=old_cookie).json()['user']['account_key']
    assert sync_request('PUT', '/api/features', json={'scope':'user', 'target_id':uid, 'key':'users_password_own', 'enabled':False}, cookies=admin_cookies).status_code == 200
    assert sync_request('DELETE', f'/api/users/{uid}', cookies=admin_cookies).status_code == 200
    _, new_cookie = _make_user(sync_request, admin_cookies, name)
    assert sync_request('GET', '/api/auth/me', cookies=old_cookie).status_code == 401
    new_user = sync_request('GET', '/api/auth/me', cookies=new_cookie).json()['user']
    assert new_user['account_key'] != old_key
    assert new_user['features']['users_password_own'] is True
