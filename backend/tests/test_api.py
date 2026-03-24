import json
import pytest
from unittest.mock import patch, MagicMock


def test_health(client):
    resp = client.get('/api/health')
    assert resp.status_code == 200
    data = resp.json()
    assert 'ok' in data
    assert 'docker_available' in data
    assert 'compose_available' in data
    assert 'auth_mode' in data


def test_unauthenticated_returns_401(client):
    resp = client.get('/api/templates')
    assert resp.status_code == 401


def test_delete_unknown_stack_returns_404(client, auth_headers):
    resp = client.delete('/api/stacks/nonexistent', headers=auth_headers)
    assert resp.status_code == 404


def test_delete_stack_success(client, auth_headers, tmp_path, monkeypatch):
    import app.docker_ops as dops
    stacks_dir = tmp_path / 'stacks2'
    monkeypatch.setattr(dops, 'STACKS_DIR', stacks_dir)

    # Seed a fake stack
    stack_dir = stacks_dir / 'mystack'
    stack_dir.mkdir(parents=True)
    (stack_dir / 'docker-compose.yml').write_text('services: {}')
    meta = {
        'stack_name': 'mystack',
        'install_path': str(tmp_path / 'install'),
        'placeholders': {},
        'named_volume_bindings': {},
    }
    (stack_dir / 'stack.json').write_text(json.dumps(meta))

    with patch('app.docker_ops._run_command', return_value=MagicMock(returncode=0, stdout='', stderr='')):
        with patch('app.docker_ops.compose_available', return_value=True):
            resp = client.delete('/api/stacks/mystack', headers=auth_headers)

    assert resp.status_code == 200
    assert resp.json()['ok'] is True
    assert not stack_dir.exists()


def test_delete_stack_unauthenticated(client):
    resp = client.delete('/api/stacks/mystack')
    assert resp.status_code == 401


def test_register_and_login(client):
    resp = client.post('/api/auth/register', json={'username': 'newuser', 'password': 'password123'})
    assert resp.status_code == 200
    assert resp.json()['ok'] is True
    assert 'token' in resp.json()

    resp = client.post('/api/auth/login', json={'username': 'newuser', 'password': 'password123'})
    assert resp.status_code == 200
    assert 'token' in resp.json()


def test_login_wrong_password_returns_401(client):
    client.post('/api/auth/register', json={'username': 'user1', 'password': 'password123'})
    resp = client.post('/api/auth/login', json={'username': 'user1', 'password': 'wrongpass'})
    assert resp.status_code == 401


def test_auth_me(client, auth_headers):
    resp = client.get('/api/auth/me', headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()['user']['username'] == 'testuser'


def test_templates_returns_all_builtins(client, auth_headers):
    resp = client.get('/api/templates', headers=auth_headers)
    assert resp.status_code == 200
    ids = {t['id'] for t in resp.json()}
    assert ids == {
        'jellyfin', 'immich', 'komga', 'nextcloud', 'vaultwarden',
        'sonarr', 'radarr', 'prowlarr', 'qbittorrent', 'bazarr', 'arr-stack',
    }


def test_stack_action_invalid_returns_422(client, auth_headers, tmp_path, monkeypatch):
    import app.docker_ops as dops
    stacks_dir = tmp_path / 'stacks3'
    monkeypatch.setattr(dops, 'STACKS_DIR', stacks_dir)
    stack_dir = stacks_dir / 'mystack'
    stack_dir.mkdir(parents=True)
    (stack_dir / 'docker-compose.yml').write_text('services: {}')

    with patch('app.docker_ops.compose_available', return_value=True):
        resp = client.post(
            '/api/stacks/mystack/action',
            headers=auth_headers,
            json={'action': 'explode'},
        )
    assert resp.status_code == 422  # Pydantic rejects at HTTP layer


def test_stacks_list(client, auth_headers):
    resp = client.get('/api/stacks', headers=auth_headers)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_delete_stack_with_data(client, auth_headers, tmp_path, monkeypatch):
    import app.docker_ops as dops
    stacks_dir = tmp_path / 'stacks4'
    monkeypatch.setattr(dops, 'STACKS_DIR', stacks_dir)
    install = tmp_path / 'install4'
    install.mkdir()

    stack_dir = stacks_dir / 'mystack'
    stack_dir.mkdir(parents=True)
    (stack_dir / 'docker-compose.yml').write_text('services: {}')
    meta = {
        'stack_name': 'mystack',
        'install_path': str(install),
        'placeholders': {},
        'named_volume_bindings': {},
    }
    (stack_dir / 'stack.json').write_text(json.dumps(meta))

    with patch('app.docker_ops._run_command', return_value=MagicMock(returncode=0, stdout='', stderr='')):
        with patch('app.docker_ops.compose_available', return_value=True):
            resp = client.delete(
                '/api/stacks/mystack?delete_data=true',
                headers=auth_headers,
            )

    assert resp.status_code == 200
    assert not install.exists()
