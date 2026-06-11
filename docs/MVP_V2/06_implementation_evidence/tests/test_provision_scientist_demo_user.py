from pathlib import Path
from unittest.mock import patch

from backend.scripts.provision_scientist_demo_user import (
    SupabaseConnection,
    provision_scientist_demo_user,
    resolve_supabase_connection,
)


def test_resolve_connection_prefers_local_service_role_key(monkeypatch):
    monkeypatch.setenv('SUPABASE_URL', 'https://exampleprojectref.supabase.co')
    monkeypatch.setenv('SUPABASE_SERVICE_ROLE_KEY', 'service-role-fixture')
    monkeypatch.delenv('SUPABASE_ACCESS_TOKEN', raising=False)

    connection = resolve_supabase_connection(env_files=())

    assert connection.project_ref == 'exampleprojectref'
    assert connection.admin_key == 'service-role-fixture'
    assert connection.admin_key_source == 'local_env'


@patch('backend.scripts.provision_scientist_demo_user._create_or_update_user')
@patch('backend.scripts.provision_scientist_demo_user.resolve_supabase_connection')
def test_provision_writes_scientist_only_credentials_without_printing_password(
    resolve_connection_mock,
    create_or_update_mock,
    tmp_path: Path,
):
    resolve_connection_mock.return_value = SupabaseConnection(
        url='https://exampleprojectref.supabase.co',
        project_ref='exampleprojectref',
        admin_key='service-role-fixture',
        admin_key_source='local_env',
    )
    create_or_update_mock.return_value = ('scientist-user-id', True)
    env_path = tmp_path / '.env.scientist.local'

    result = provision_scientist_demo_user(
        email='scientist@insight-hub.local',
        password='REDACTED_TEST_PASSWORD',
        env_output=env_path,
    )

    assert result.email == 'scientist@insight-hub.local'
    assert result.user_id == 'scientist-user-id'
    assert result.safe_summary()['password_printed'] is False
    create_or_update_mock.assert_called_once()
    _, kwargs = create_or_update_mock.call_args
    assert kwargs['email'] == 'scientist@insight-hub.local'
    assert kwargs['password'] == 'REDACTED_TEST_PASSWORD'
    content = env_path.read_text(encoding='utf-8')
    assert 'SCIENTIST_DEMO_PASSWORD=REDACTED_TEST_PASSWORD' in content
    assert 'SUPABASE_SERVICE_ROLE_KEY' not in content
    assert 'SUPABASE_SECRET_KEY' not in content


@patch('backend.scripts.provision_scientist_demo_user.requests.post')
@patch('backend.scripts.provision_scientist_demo_user._find_user_by_email')
def test_create_or_update_payload_never_assigns_admin_role(find_user_mock, post_mock, monkeypatch):
    from backend.scripts.provision_scientist_demo_user import _create_or_update_user

    find_user_mock.return_value = None
    post_mock.return_value.ok = True
    post_mock.return_value.json.return_value = {'id': 'scientist-user-id'}
    connection = SupabaseConnection(
        url='https://exampleprojectref.supabase.co',
        project_ref='exampleprojectref',
        admin_key='service-role-fixture',
        admin_key_source='local_env',
    )

    user_id, created = _create_or_update_user(
        connection,
        email='scientist@insight-hub.local',
        password='REDACTED_TEST_PASSWORD',
    )

    assert user_id == 'scientist-user-id'
    assert created is True
    payload = post_mock.call_args.kwargs['json']
    assert payload['email_confirm'] is True
    assert payload['app_metadata'] == {'roles': ['scientist']}
    assert 'admin' not in payload['app_metadata']['roles']
