class TestPermissionCatalog:
    def test_requires_auth(self, sync_request):
        resp = sync_request('GET', '/api/permissions/catalog')
        assert resp.status_code == 401

    def test_catalog_structure(self, sync_request, admin_cookies):
        resp = sync_request('GET', '/api/permissions/catalog', cookies=admin_cookies)
        assert resp.status_code == 200, resp.text
        data = resp.json()

        groups = data['groups']
        keys = [item['key'] for group in groups for item in group['items']]
        assert len(keys) == len(set(keys)), 'ключи прав не должны дублироваться'
        assert {'navigation', 'tasks', 'clients', 'system'} <= {group['id'] for group in groups}
        assert all(group['scope'] in ('app', 'work') for group in groups)

        scopes = data['scopes']
        assert scopes['users'] == 'app'
        assert scopes['settings'] == 'app'
        for key in ('dashboard', 'tasks', 'kanban', 'clients', 'notes', 'ai', 'workspace', 'tasks_view_all', 'client_delete'):
            assert scopes[key] == 'work', f'{key} должна быть областью work'

        presets = data['presets']
        known = set(keys)
        for name, preset in presets.items():
            assert set(preset) <= known, f'пресет {name} ссылается на неизвестные ключи'
        assert {'users', 'notes', 'ai', 'workspace'} <= set(presets['admin'])
        assert {'notes', 'workspace'} <= set(presets['executor'])
        assert {'notes', 'ai', 'workspace'} <= set(presets['manager'])

    def test_roles_migrated_with_new_keys(self, sync_request, admin_cookies):
        resp = sync_request('GET', '/api/roles', cookies=admin_cookies)
        assert resp.status_code == 200, resp.text
        by_name = {role['name']: role['permissions'] for role in resp.json()}

        for key in ('users', 'notes', 'ai', 'workspace'):
            assert by_name['admin'].get(key) is True, f'admin должен получить {key}'
        for key in ('notes', 'ai', 'workspace'):
            assert by_name['manager'].get(key) is True, f'manager должен получить {key}'
        for key in ('notes', 'workspace'):
            assert by_name['executor'].get(key) is True, f'executor должен получить {key}'

        assert by_name['superadmin'].get('all') is True

    def test_migration_is_idempotent(self, sync_request, admin_cookies, event_loop):
        """Повторная миграция не меняет роли и не удаляет старые ключи."""
        from app.core.database import _migrate_role_permissions

        def snapshot():
            roles = sync_request('GET', '/api/roles', cookies=admin_cookies).json()
            return {role['name']: dict(role['permissions']) for role in roles}

        before = snapshot()
        event_loop.run_until_complete(_migrate_role_permissions())
        after = snapshot()

        assert after == before, 'повторная миграция не должна менять роли'
        assert 'dashboard' in after['executor'], 'старые ключи не должны удаляться'
        assert 'client_delete' in after['admin'], 'старые ключи не должны удаляться'
        assert 'all' in after['superadmin'], 'superadmin не должен мигрироваться'
