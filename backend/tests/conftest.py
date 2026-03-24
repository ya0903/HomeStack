import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def isolate_data(tmp_path, monkeypatch):
    """Redirect all mutable data paths to tmp_path for every test."""
    import app.auth as auth
    import app.docker_ops as docker_ops
    import app.templates as templates

    data_dir = tmp_path / 'data'
    data_dir.mkdir()

    # Patch auth data files
    monkeypatch.setattr(auth, 'DATA_DIR', data_dir)
    monkeypatch.setattr(auth, 'USERS_FILE', data_dir / 'users.json')
    monkeypatch.setattr(auth, 'SECRET_FILE', data_dir / 'secret.key')

    # Patch stacks dir
    monkeypatch.setattr(docker_ops, 'STACKS_DIR', data_dir / 'stacks')

    # Patch custom templates dir (builtin templates dir is NOT patched — tests use the real one)
    monkeypatch.setattr(templates, 'CUSTOM_TEMPLATES_DIR', data_dir / 'custom_templates')


@pytest.fixture
def client():
    from app.main import app
    return TestClient(app)


@pytest.fixture
def auth_token(client):
    client.post('/api/auth/register', json={'username': 'testuser', 'password': 'testpass123'})
    resp = client.post('/api/auth/login', json={'username': 'testuser', 'password': 'testpass123'})
    return resp.json()['token']


@pytest.fixture
def auth_headers(auth_token):
    return {'Authorization': f'Bearer {auth_token}'}
