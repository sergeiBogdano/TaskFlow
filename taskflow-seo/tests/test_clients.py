import pytest


class TestClients:

    def test_clients_page(self, sync_request, client, admin_cookies):
        resp = sync_request('GET', '/clients', cookies=admin_cookies)
        assert resp.status_code == 200

    def test_client_detail(self, sync_request, client, admin_cookies):
        resp = sync_request('POST', '/clients/create',
                           data={'org_name': 'Detail Test Org',
                                'contract_end': '2027-12-31',
                                'status': 'active'},
                           cookies=admin_cookies, follow_redirects=False)
        assert resp.status_code == 302
        r = sync_request('GET', '/api/clients', cookies=admin_cookies)
        clients = r.json()
        c = next((c for c in clients if c['org_name'] == 'Detail Test Org'), None)
        assert c is not None
        resp = sync_request('GET', f'/clients/{c["id"]}', cookies=admin_cookies)
        assert resp.status_code == 200

    def test_client_create_form(self, sync_request, client, admin_cookies):
        resp = sync_request('POST', '/clients/create',
                           data={'org_name': 'New Org', 'contract_end': '2027-06-30',
                                'status': 'active'},
                           cookies=admin_cookies, follow_redirects=False)
        assert resp.status_code == 302
        assert '/clients' in resp.headers['location']

    def test_client_create_api(self, sync_request, client, admin_cookies):
        resp = sync_request('POST', '/api/clients',
                           json={'org_name': 'API Org', 'status': 'active',
                                'contract_start': '2026-01-01',
                                'contract_end': '2027-12-31'},
                           cookies=admin_cookies)
        assert resp.status_code == 201
        assert 'id' in resp.json()

    def test_client_update(self, sync_request, client, admin_cookies):
        sync_request('POST', '/clients/create',
                    data={'org_name': 'Update Test Org',
                         'contract_end': '2027-12-31', 'status': 'active'},
                    cookies=admin_cookies, follow_redirects=False)
        r = sync_request('GET', '/api/clients', cookies=admin_cookies)
        c = next((c for c in r.json() if c['org_name'] == 'Update Test Org'), None)
        assert c is not None
        resp = sync_request('POST', f'/clients/{c["id"]}/update',
                           data={'org_name': 'Updated Org', 'contract_end': '2027-12-31'},
                           cookies=admin_cookies, follow_redirects=False)
        assert resp.status_code == 302

    def test_client_status_change(self, sync_request, client, admin_cookies):
        sync_request('POST', '/clients/create',
                    data={'org_name': 'Status Test Org',
                         'contract_end': '2027-12-31', 'status': 'active'},
                    cookies=admin_cookies, follow_redirects=False)
        r = sync_request('GET', '/api/clients', cookies=admin_cookies)
        c = next((c for c in r.json() if c['org_name'] == 'Status Test Org'), None)
        assert c is not None
        resp = sync_request('POST', f'/clients/{c["id"]}/status',
                           data={'status': 'paused'}, cookies=admin_cookies, follow_redirects=False)
        assert resp.status_code == 302

    def test_client_print(self, sync_request, client, admin_cookies):
        sync_request('POST', '/clients/create',
                    data={'org_name': 'Print Test Org',
                         'contract_end': '2027-12-31', 'status': 'active'},
                    cookies=admin_cookies, follow_redirects=False)
        r = sync_request('GET', '/api/clients', cookies=admin_cookies)
        c = next((c for c in r.json() if c['org_name'] == 'Print Test Org'), None)
        assert c is not None
        resp = sync_request('GET', f'/clients/{c["id"]}/print',
                           cookies=admin_cookies)
        assert resp.status_code == 200


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
