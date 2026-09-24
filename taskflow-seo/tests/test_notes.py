import pytest


def _login_note_payload(**kw):
    payload = {
        'title': 'Тестовая заметка',
        'content': 'Привет, **мир**!\n\n[[Тестовая заметка]]',
        'format': 'markdown',
        'tags': ['seo', 'тест'],
        'is_public': False,
        'folder_id': None,
    }
    payload.update(kw)
    return payload


class TestNotesPage:

    def test_notes_page_admin(self, sync_request, admin_cookies):
        resp = sync_request('GET', '/notes', cookies=admin_cookies)
        assert resp.status_code == 200
        assert 'Доска заметок' in resp.text

    def test_notes_page_unauth_redirect(self, sync_request):
        resp = sync_request('GET', '/notes', cookies={})
        assert resp.status_code in (302, 307)


class TestNotesCrud:

    def test_create_note(self, sync_request, admin_cookies):
        resp = sync_request('POST', '/api/notes', json=_login_note_payload(title='CRUD note'), cookies=admin_cookies)
        assert resp.status_code == 201
        data = resp.json()
        assert data['title'] == 'CRUD note'
        assert data['is_owner'] is True
        assert data['tags'] == ['seo', 'тест']
        assert data['format'] == 'markdown'

    def test_list_notes(self, sync_request, admin_cookies):
        sync_request('POST', '/api/notes', json=_login_note_payload(title='Listed note'), cookies=admin_cookies)
        resp = sync_request('GET', '/api/notes', cookies=admin_cookies)
        assert resp.status_code == 200
        data = resp.json()
        assert 'notes' in data
        assert 'tags' in data
        assert any(n['title'] == 'Listed note' for n in data['notes'])

    def test_get_update_delete_note(self, sync_request, admin_cookies):
        created = sync_request('POST', '/api/notes', json=_login_note_payload(title='Temp note'), cookies=admin_cookies)
        note_id = created.json()['id']

        resp = sync_request('GET', f'/api/notes/{note_id}', cookies=admin_cookies)
        assert resp.status_code == 200
        assert resp.json()['title'] == 'Temp note'

        resp = sync_request('PUT', f'/api/notes/{note_id}', json={'title': 'Temp note v2', 'is_public': True}, cookies=admin_cookies)
        assert resp.status_code == 200
        assert resp.json()['title'] == 'Temp note v2'
        assert resp.json()['is_public'] is True

        resp = sync_request('DELETE', f'/api/notes/{note_id}', cookies=admin_cookies)
        assert resp.status_code == 200

        resp = sync_request('GET', f'/api/notes/{note_id}', cookies=admin_cookies)
        assert resp.status_code == 404

    def test_search_note(self, sync_request, admin_cookies):
        sync_request('POST', '/api/notes', json=_login_note_payload(title='Uniquemarker note'), cookies=admin_cookies)
        resp = sync_request('GET', '/api/notes?q=Uniquemarker', cookies=admin_cookies)
        assert resp.status_code == 200
        assert all('Uniquemarker' in n['title'] or 'Uniquemarker' in n['content'] for n in resp.json()['notes'])
        assert len(resp.json()['notes']) >= 1

    def test_invalid_format_rejected(self, sync_request, admin_cookies):
        resp = sync_request('POST', '/api/notes', json=_login_note_payload(format='excel'), cookies=admin_cookies)
        assert resp.status_code == 400

    def test_unauth_notes_rejected(self, sync_request):
        resp = sync_request('GET', '/api/notes', cookies={})
        assert resp.status_code == 401

    def test_duplicate_note(self, sync_request, admin_cookies):
        created = sync_request('POST', '/api/notes', json=_login_note_payload(title='Source note'), cookies=admin_cookies)
        note_id = created.json()['id']
        resp = sync_request('POST', f'/api/notes/{note_id}/duplicate', cookies=admin_cookies)
        assert resp.status_code == 201
        assert resp.json()['title'] == 'Source note (копия)'

    def test_archive_and_restore(self, sync_request, admin_cookies):
        created = sync_request('POST', '/api/notes', json=_login_note_payload(title='Archive me'), cookies=admin_cookies)
        note_id = created.json()['id']

        resp = sync_request('POST', f'/api/notes/{note_id}/archive', cookies=admin_cookies)
        assert resp.status_code == 200

        resp = sync_request('GET', f'/api/notes/{note_id}', cookies=admin_cookies)
        assert resp.status_code == 404

        resp = sync_request('GET', '/api/notes?archived=true', cookies=admin_cookies)
        assert resp.status_code == 200
        assert any(n['id'] == note_id for n in resp.json()['notes'])

        resp = sync_request('POST', f'/api/notes/{note_id}/restore', cookies=admin_cookies)
        assert resp.status_code == 200

        resp = sync_request('GET', f'/api/notes/{note_id}', cookies=admin_cookies)
        assert resp.status_code == 200


class TestNotesPermissions:

    def test_private_note_hidden_from_others(self, sync_request, admin_cookies, executor_cookies):
        created = sync_request('POST', '/api/notes', json=_login_note_payload(title='Private admin note'), cookies=admin_cookies)
        note_id = created.json()['id']

        resp = sync_request('GET', f'/api/notes/{note_id}', cookies=executor_cookies)
        assert resp.status_code == 404

        resp = sync_request('GET', '/api/notes?q=Private admin note', cookies=executor_cookies)
        assert resp.status_code == 200
        assert all(n['id'] != note_id for n in resp.json()['notes'])

    def test_public_note_visible_to_others(self, sync_request, admin_cookies, executor_cookies):
        created = sync_request('POST', '/api/notes', json=_login_note_payload(title='Public admin note', is_public=True), cookies=admin_cookies)
        note_id = created.json()['id']

        resp = sync_request('GET', f'/api/notes/{note_id}', cookies=executor_cookies)
        assert resp.status_code == 200
        assert resp.json()['is_owner'] is False

    def test_public_note_not_editable_by_others(self, sync_request, admin_cookies, executor_cookies):
        created = sync_request('POST', '/api/notes', json=_login_note_payload(title='Shared note', is_public=True), cookies=admin_cookies)
        note_id = created.json()['id']

        resp = sync_request('PUT', f'/api/notes/{note_id}', json={'title': 'Hacked'}, cookies=executor_cookies)
        assert resp.status_code == 403

        resp = sync_request('DELETE', f'/api/notes/{note_id}', cookies=executor_cookies)
        assert resp.status_code == 404

    def test_scope_shared_lists_only_others_public(self, sync_request, admin_cookies, executor_cookies):
        sync_request('POST', '/api/notes', json=_login_note_payload(title='Admin shared for scope', is_public=True), cookies=admin_cookies)
        resp = sync_request('GET', '/api/notes?scope=shared', cookies=executor_cookies)
        assert resp.status_code == 200
        for n in resp.json()['notes']:
            assert n['is_public'] is True
            assert n['is_owner'] is False


class TestNoteFolders:

    def test_folder_crud(self, sync_request, admin_cookies):
        resp = sync_request('POST', '/api/notes/folders', json={'name': 'SEO'}, cookies=admin_cookies)
        assert resp.status_code == 201
        folder_id = resp.json()['id']

        resp = sync_request('POST', '/api/notes/folders', json={'name': 'Кластеры', 'parent_id': folder_id}, cookies=admin_cookies)
        assert resp.status_code == 201
        child_id = resp.json()['id']
        assert resp.json()['parent_id'] == folder_id

        resp = sync_request('PUT', f'/api/notes/folders/{folder_id}', json={'name': 'SEO продвижение'}, cookies=admin_cookies)
        assert resp.status_code == 200
        assert resp.json()['name'] == 'SEO продвижение'

        resp = sync_request('GET', '/api/notes/folders', cookies=admin_cookies)
        assert resp.status_code == 200
        names = [f['name'] for f in resp.json()]
        assert 'SEO продвижение' in names
        assert 'Кластеры' in names

        resp = sync_request('DELETE', f'/api/notes/folders/{child_id}', cookies=admin_cookies)
        assert resp.status_code == 200

    def test_folder_cycle_rejected(self, sync_request, admin_cookies):
        parent = sync_request('POST', '/api/notes/folders', json={'name': 'Cycle parent'}, cookies=admin_cookies).json()
        child = sync_request('POST', '/api/notes/folders', json={'name': 'Cycle child', 'parent_id': parent['id']}, cookies=admin_cookies).json()
        resp = sync_request('PUT', f"/api/notes/folders/{parent['id']}", json={'parent_id': child['id']}, cookies=admin_cookies)
        assert resp.status_code == 400

    def test_note_move_between_folders(self, sync_request, admin_cookies):
        folder = sync_request('POST', '/api/notes/folders', json={'name': 'Move target'}, cookies=admin_cookies).json()
        note = sync_request('POST', '/api/notes', json=_login_note_payload(title='Movable note'), cookies=admin_cookies).json()

        resp = sync_request('PUT', f"/api/notes/{note['id']}", json={'folder_id': folder['id']}, cookies=admin_cookies)
        assert resp.status_code == 200
        assert resp.json()['folder_id'] == folder['id']
        assert resp.json()['folder_name'] == 'Move target'

        resp = sync_request('GET', f"/api/notes?folder_id={folder['id']}", cookies=admin_cookies)
        assert resp.status_code == 200
        assert any(n['id'] == note['id'] for n in resp.json()['notes'])

    def test_foreign_folder_rejected(self, sync_request, admin_cookies, executor_cookies):
        folder = sync_request('POST', '/api/notes/folders', json={'name': 'Admin folder'}, cookies=admin_cookies).json()
        note = sync_request('POST', '/api/notes', json=_login_note_payload(title='Folder bound note'), cookies=executor_cookies)
        if note.status_code != 201:
            pytest.skip(note.text)
        resp = sync_request('PUT', f"/api/notes/{note.json()['id']}", json={'folder_id': folder['id']}, cookies=executor_cookies)
        assert resp.status_code == 400

    def test_delete_folder_keeps_notes(self, sync_request, admin_cookies):
        folder = sync_request('POST', '/api/notes/folders', json={'name': 'Doomed folder'}, cookies=admin_cookies).json()
        note = sync_request('POST', '/api/notes', json=_login_note_payload(title='Survives folder', folder_id=folder['id']), cookies=admin_cookies).json()

        resp = sync_request('DELETE', f"/api/notes/folders/{folder['id']}", cookies=admin_cookies)
        assert resp.status_code == 200
        assert resp.json()['moved_notes'] == 1

        resp = sync_request('GET', f"/api/notes/{note['id']}", cookies=admin_cookies)
        assert resp.status_code == 200
        assert resp.json()['folder_id'] is None


class TestNotesTrash:

    def test_soft_delete_moves_to_archive(self, sync_request, admin_cookies):
        note_id = sync_request('POST', '/api/notes', json=_login_note_payload(title='Trash me'), cookies=admin_cookies).json()['id']

        resp = sync_request('DELETE', f'/api/notes/{note_id}', cookies=admin_cookies)
        assert resp.status_code == 200
        assert resp.json() == {'ok': True, 'permanent': False}

        resp = sync_request('GET', f'/api/notes/{note_id}', cookies=admin_cookies)
        assert resp.status_code == 404

        resp = sync_request('GET', '/api/notes', cookies=admin_cookies)
        assert all(n['id'] != note_id for n in resp.json()['notes'])

        resp = sync_request('GET', '/api/notes?archived=true', cookies=admin_cookies)
        assert resp.status_code == 200
        assert any(n['id'] == note_id for n in resp.json()['notes'])

    def test_restore_after_soft_delete(self, sync_request, admin_cookies):
        note_id = sync_request('POST', '/api/notes', json=_login_note_payload(title='Restore me'), cookies=admin_cookies).json()['id']
        sync_request('DELETE', f'/api/notes/{note_id}', cookies=admin_cookies)

        resp = sync_request('POST', f'/api/notes/{note_id}/restore', cookies=admin_cookies)
        assert resp.status_code == 200
        assert resp.json()['id'] == note_id

        resp = sync_request('GET', '/api/notes?archived=true', cookies=admin_cookies)
        assert all(n['id'] != note_id for n in resp.json()['notes'])

    def test_permanent_delete_removes_everywhere(self, sync_request, admin_cookies):
        note_id = sync_request('POST', '/api/notes', json=_login_note_payload(title='Nuke me'), cookies=admin_cookies).json()['id']

        resp = sync_request('DELETE', f'/api/notes/{note_id}?permanent=true', cookies=admin_cookies)
        assert resp.status_code == 200
        assert resp.json() == {'ok': True, 'permanent': True}

        assert sync_request('GET', f'/api/notes/{note_id}', cookies=admin_cookies).status_code == 404
        resp = sync_request('GET', '/api/notes?archived=true', cookies=admin_cookies)
        assert all(n['id'] != note_id for n in resp.json()['notes'])

    def test_restore_foreign_archived_rejected(self, sync_request, admin_cookies, executor_cookies):
        note_id = sync_request('POST', '/api/notes', json=_login_note_payload(title=' чужой архив'.strip()), cookies=admin_cookies).json()['id']
        sync_request('DELETE', f'/api/notes/{note_id}', cookies=admin_cookies)

        resp = sync_request('POST', f'/api/notes/{note_id}/restore', cookies=executor_cookies)
        assert resp.status_code == 404


class TestNotesFilters:

    def test_scope_mine_only_own(self, sync_request, admin_cookies, executor_cookies):
        sync_request('POST', '/api/notes', json=_login_note_payload(title='Admin mine note', is_public=True), cookies=admin_cookies)
        sync_request('POST', '/api/notes', json=_login_note_payload(title='Executor mine note', is_public=True), cookies=executor_cookies)

        resp = sync_request('GET', '/api/notes?scope=mine', cookies=executor_cookies)
        assert resp.status_code == 200
        assert len(resp.json()['notes']) >= 1
        assert all(n['is_owner'] is True for n in resp.json()['notes'])

    def test_folder_root(self, sync_request, admin_cookies):
        folder = sync_request('POST', '/api/notes/folders', json={'name': 'Root filter folder'}, cookies=admin_cookies).json()
        root_note = sync_request('POST', '/api/notes', json=_login_note_payload(title='Root note'), cookies=admin_cookies).json()
        boxed_note = sync_request('POST', '/api/notes', json=_login_note_payload(title='Boxed note', folder_id=folder['id']), cookies=admin_cookies).json()

        resp = sync_request('GET', '/api/notes?folder_id=root', cookies=admin_cookies)
        ids = [n['id'] for n in resp.json()['notes']]
        assert root_note['id'] in ids
        assert boxed_note['id'] not in ids

    def test_fmt_filter(self, sync_request, admin_cookies):
        code_note = sync_request('POST', '/api/notes', json=_login_note_payload(title='Code fmt note', format='code'), cookies=admin_cookies).json()

        resp = sync_request('GET', '/api/notes?fmt=code', cookies=admin_cookies)
        assert any(n['id'] == code_note['id'] for n in resp.json()['notes'])

        resp = sync_request('GET', '/api/notes?fmt=text', cookies=admin_cookies)
        assert all(n['id'] != code_note['id'] for n in resp.json()['notes'])

    def test_tag_filter(self, sync_request, admin_cookies):
        tagged = sync_request('POST', '/api/notes', json=_login_note_payload(title='Tagged note', tags=['unique-tag-xyz']), cookies=admin_cookies).json()

        resp = sync_request('GET', '/api/notes?tag=unique-tag-xyz', cookies=admin_cookies)
        assert any(n['id'] == tagged['id'] for n in resp.json()['notes'])

        resp = sync_request('GET', '/api/notes', cookies=admin_cookies)
        assert 'unique-tag-xyz' in resp.json()['tags']


class TestNotesValidation:

    def test_empty_title_rejected_on_update(self, sync_request, admin_cookies):
        note_id = sync_request('POST', '/api/notes', json=_login_note_payload(title='Title check'), cookies=admin_cookies).json()['id']
        resp = sync_request('PUT', f'/api/notes/{note_id}', json={'title': '   '}, cookies=admin_cookies)
        assert resp.status_code == 400

    def test_bad_format_rejected_on_update(self, sync_request, admin_cookies):
        note_id = sync_request('POST', '/api/notes', json=_login_note_payload(title='Format check'), cookies=admin_cookies).json()['id']
        resp = sync_request('PUT', f'/api/notes/{note_id}', json={'format': 'excel'}, cookies=admin_cookies)
        assert resp.status_code == 400

    def test_long_title_rejected(self, sync_request, admin_cookies):
        resp = sync_request('POST', '/api/notes', json=_login_note_payload(title='x' * 201), cookies=admin_cookies)
        assert resp.status_code == 400

    def test_empty_folder_name_rejected(self, sync_request, admin_cookies):
        resp = sync_request('POST', '/api/notes/folders', json={'name': '   '}, cookies=admin_cookies)
        assert resp.status_code == 400

    def test_folder_self_parent_rejected(self, sync_request, admin_cookies):
        folder = sync_request('POST', '/api/notes/folders', json={'name': 'Self parent'}, cookies=admin_cookies).json()
        resp = sync_request('PUT', f"/api/notes/folders/{folder['id']}", json={'parent_id': folder['id']}, cookies=admin_cookies)
        assert resp.status_code == 400

    def test_duplicate_private_by_other_rejected(self, sync_request, admin_cookies, executor_cookies):
        note_id = sync_request('POST', '/api/notes', json=_login_note_payload(title='Private source'), cookies=admin_cookies).json()['id']
        resp = sync_request('POST', f'/api/notes/{note_id}/duplicate', cookies=executor_cookies)
        assert resp.status_code == 404

    def test_duplicate_public_by_other_creates_private_copy(self, sync_request, admin_cookies, executor_cookies):
        note_id = sync_request('POST', '/api/notes', json=_login_note_payload(title='Public source', is_public=True), cookies=admin_cookies).json()['id']
        resp = sync_request('POST', f'/api/notes/{note_id}/duplicate', cookies=executor_cookies)
        assert resp.status_code == 201
        data = resp.json()
        assert data['title'] == 'Public source (копия)'
        assert data['is_owner'] is True
        assert data['is_public'] is False
