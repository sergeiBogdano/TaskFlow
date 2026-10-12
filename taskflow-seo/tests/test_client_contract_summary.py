from app.core.models import Client, Contract
from app.web.api.clients import _client_to_dict


def test_summary_does_not_disclose_contract_existence_without_tab_permission():
    client = Client(id=1, org_name='Restricted')
    data = _client_to_dict(client, [], [], [], [], permissions={})
    assert data['has_contract'] is None


def test_authorized_empty_contracts_are_missing_despite_legacy_dates():
    from datetime import datetime
    client = Client(id=1, org_name='No contract', contract_end=datetime(2030, 1, 1))
    data = _client_to_dict(client, [], [], [], [], permissions={'client_tab_contracts': True})
    assert data['has_contract'] is False


def test_archived_and_closed_contracts_do_not_count_as_current():
    client = Client(id=1, org_name='Archive')
    contracts = [Contract(id=1, status='archived'), Contract(id=2, status='closed')]
    data = _client_to_dict(client, [], contracts, [], [], permissions={'client_tab_contracts': True})
    assert data['has_contract'] is False


def test_contract_check_uses_actual_contracts(sync_request, admin_cookies):
    response = sync_request('POST', '/api/clients', cookies=admin_cookies, json={'org_name': 'Contract summary regression', 'contracts': []})
    assert response.status_code == 201, response.text
    client_id = response.json()['id']
    url = f'/api/clients/{client_id}/contract-check'
    response = sync_request('GET', url, cookies=admin_cookies)
    assert response.status_code == 200
    assert response.json()['has_contract'] is False
    assert response.json()['contract_end'] == ''
    response = sync_request('PUT', f'/api/clients/{client_id}', cookies=admin_cookies, json={'contracts': [{'contract_type': 'Support', 'start_date': '2026-01-01', 'end_date': '2027-12-31', 'status': 'active'}]})
    assert response.status_code == 200, response.text
    response = sync_request('GET', url+'?deadline=2028-01-01T12:00:00', cookies=admin_cookies)
    assert response.status_code == 200, response.text
    assert response.json()['has_contract'] is True
    assert response.json()['contract_end'] == '2027-12-31'
    assert response.json()['valid'] is False


def test_client_without_domain_has_no_favicon(sync_request, admin_cookies):
    response = sync_request('POST', '/api/clients', cookies=admin_cookies, json={'org_name': 'Initials fallback'})
    client_id = response.json()['id']
    response = sync_request('GET', f'/api/clients/{client_id}/favicon', cookies=admin_cookies)
    assert response.status_code == 404
    response = sync_request('GET', f'/api/clients/{client_id}/favicon', cookies={})
    assert response.status_code == 401
