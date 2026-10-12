import pytest


class TestClients:

    def test_clients_require_auth(self, sync_request, client):
        assert sync_request('GET', '/api/clients', cookies={}).status_code == 401

    def test_client_detail(self, sync_request, client, admin_cookies):
        created = sync_request('POST', '/api/clients', json={'org_name': 'test_client_detail', 'status': 'active'}, cookies=admin_cookies)
        assert created.status_code == 201, created.text
        client_id = created.json()['id']
        detail = sync_request('GET', f'/api/clients/{client_id}', cookies=admin_cookies)
        assert detail.status_code == 200, detail.text
        assert detail.json()['org_name'] == 'test_client_detail'

    def test_client_create_readback(self, sync_request, client, admin_cookies):
        created = sync_request('POST', '/api/clients', json={'org_name': 'test_client_create_form', 'status': 'active'}, cookies=admin_cookies)
        assert created.status_code == 201, created.text
        client_id = created.json()['id']
        detail = sync_request('GET', f'/api/clients/{client_id}', cookies=admin_cookies)
        assert detail.status_code == 200, detail.text
        assert detail.json()['org_name'] == 'test_client_create_form'

    def test_client_create_api(self, sync_request, client, admin_cookies):
        resp = sync_request('POST', '/api/clients',
                           json={'org_name': 'API Org', 'status': 'active',
                                'contract_start': '2026-01-01',
                                'contract_end': '2027-12-31'},
                           cookies=admin_cookies)
        assert resp.status_code == 201
        assert 'id' in resp.json()

    def test_client_update(self, sync_request, client, admin_cookies):
        created = sync_request('POST', '/api/clients', json={'org_name': 'test_client_update', 'status': 'active'}, cookies=admin_cookies)
        assert created.status_code == 201, created.text
        client_id = created.json()['id']
        updated = sync_request('PUT', f'/api/clients/{client_id}', json={'org_name': 'Updated Org'}, cookies=admin_cookies)
        assert updated.status_code == 200, updated.text
        detail = sync_request('GET', f'/api/clients/{client_id}', cookies=admin_cookies)
        assert detail.status_code == 200, detail.text
        assert detail.json()['org_name'] == 'Updated Org'

    def test_client_status_change(self, sync_request, client, admin_cookies):
        created = sync_request('POST', '/api/clients', json={'org_name': 'test_client_status_change', 'status': 'active'}, cookies=admin_cookies)
        assert created.status_code == 201, created.text
        client_id = created.json()['id']
        updated = sync_request('PUT', f'/api/clients/{client_id}', json={'status': 'paused'}, cookies=admin_cookies)
        assert updated.status_code == 200, updated.text
        detail = sync_request('GET', f'/api/clients/{client_id}', cookies=admin_cookies)
        assert detail.status_code == 200, detail.text
        assert detail.json()['status'] == 'paused'

    def test_client_health(self, sync_request, client, admin_cookies):
        created = sync_request('POST', '/api/clients', json={'org_name': 'test_client_print', 'status': 'active'}, cookies=admin_cookies)
        assert created.status_code == 201, created.text
        client_id = created.json()['id']
        detail = sync_request('GET', f'/api/clients/{client_id}/health', cookies=admin_cookies)
        assert detail.status_code == 200, detail.text
        assert isinstance(detail.json(), dict)


    def test_client_api_get(self, sync_request, client, admin_cookies):
        resp = sync_request('GET', '/api/clients', cookies=admin_cookies)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_client_api_detail(self, sync_request, client, admin_cookies):
        sync_request('POST', '/api/clients',
                    json={'org_name': 'Detail API Org', 'status': 'active',
                         'contract_start': '2026-01-01',
                         'contract_end': '2027-12-31'},
                    cookies=admin_cookies)
        r = sync_request('GET', '/api/clients', cookies=admin_cookies)
        c = next((c for c in r.json() if c['org_name'] == 'Detail API Org'), None)
        assert c is not None
        resp = sync_request('GET', f'/api/clients/{c["id"]}',
                           cookies=admin_cookies)
        assert resp.status_code == 200
        assert resp.json()['org_name'] == 'Detail API Org'

    def test_client_not_found_404(self, sync_request, client, admin_cookies):
        resp = sync_request('GET', '/api/clients/99999',
                           cookies=admin_cookies)
        assert resp.status_code == 404

    def test_client_invalid_date_validation(self, sync_request, client, admin_cookies):
        resp = sync_request('POST', '/api/clients',
                           json={'org_name': 'Bad Dates Org',
                                'status': 'active',
                                'contract_start': '2027-01-01',
                                'contract_end': '2026-01-01'},
                           cookies=admin_cookies)
        assert resp.status_code == 400
