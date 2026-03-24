# HomeStack Improvements Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add dynamic template discovery, Jinja2 rendering, N+1 fix, delete/undeploy stacks, and a hardened frontend with full pytest test coverage.

**Architecture:** Backend changes layer in order: template metadata files → Jinja2 rendering → docker_ops improvements → new DELETE endpoint. Frontend is updated independently. Tests are written alongside each backend change using TDD. Run pytest from `backend/` throughout.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic, Jinja2 (already in requirements), pytest, httpx, pytest-mock, vanilla JS frontend

---

## File Map

**Create:**
- `templates/jellyfin/template.json`
- `templates/immich/template.json`
- `templates/komga/template.json`
- `templates/nextcloud/template.json`
- `templates/vaultwarden/template.json`
- `templates/sonarr/template.json`
- `templates/radarr/template.json`
- `templates/prowlarr/template.json`
- `templates/qbittorrent/template.json`
- `templates/bazarr/template.json`
- `templates/arr-stack/template.json`
- `backend/requirements-dev.txt`
- `backend/tests/__init__.py` (empty)
- `backend/tests/conftest.py`
- `backend/tests/test_auth.py`
- `backend/tests/test_templates.py`
- `backend/tests/test_docker_ops.py`
- `backend/tests/test_api.py`

**Modify:**
- `backend/app/templates.py` — rewrite `get_builtin_templates()`
- `backend/app/docker_ops.py` — Jinja2 rendering, N+1 fix, delete_stack, update_stack, run_stack_action guard
- `backend/app/main.py` — import delete_stack, add DELETE endpoint
- `frontend/app.js` — escapeHtml, data-attribute delegation, delete button, API base fix, action feedback

---

## Chunk 1: Test Infrastructure + Template System

### Task 1: Set up test infrastructure

**Files:**
- Create: `backend/requirements-dev.txt`
- Create: `backend/tests/__init__.py`
- Create: `backend/tests/conftest.py`

- [ ] **Step 1: Create `backend/requirements-dev.txt`**

```
pytest>=8.0
httpx>=0.27
pytest-mock>=3.14
```

- [ ] **Step 2: Create `backend/tests/__init__.py`**

Empty file — makes `tests/` a package so pytest can discover it.

```python
```

- [ ] **Step 3: Create `backend/tests/conftest.py`**

```python
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
```

- [ ] **Step 4: Install test dependencies**

Run from `G:/Claude/Homestack/backend/`:
```bash
pip install -r requirements-dev.txt
```

- [ ] **Step 5: Verify pytest discovers tests**

```bash
cd G:/Claude/Homestack/backend
pytest tests/ --collect-only
```

Expected: `no tests ran` (no test files yet — that's correct at this point)

- [ ] **Step 6: Commit**

```bash
cd G:/Claude/Homestack
git add backend/requirements-dev.txt backend/tests/__init__.py backend/tests/conftest.py
git commit -m "test: add test infrastructure (conftest, requirements-dev)"
```

---

### Task 2: Dynamic template discovery (TDD)

**Files:**
- Create: `templates/*/template.json` (11 files)
- Modify: `backend/app/templates.py`
- Create: `backend/tests/test_templates.py` (partial — discovery tests only)

- [ ] **Step 1: Write the failing discovery test**

Create `backend/tests/test_templates.py`:

```python
import pytest
from app.templates import get_builtin_templates, get_template_by_id

EXPECTED_IDS = {
    'jellyfin', 'immich', 'komga', 'nextcloud', 'vaultwarden',
    'sonarr', 'radarr', 'prowlarr', 'qbittorrent', 'bazarr', 'arr-stack',
}


def test_builtin_template_discovery():
    templates = get_builtin_templates()
    assert {t.id for t in templates} == EXPECTED_IDS


def test_builtin_templates_have_required_fields():
    from pathlib import Path
    for t in get_builtin_templates():
        assert t.name, f'{t.id} missing name'
        assert t.description, f'{t.id} missing description'
        assert t.required_placeholders, f'{t.id} missing required_placeholders'
        assert t.default_install_subdir, f'{t.id} missing default_install_subdir'
        assert Path(t.compose_template_path).exists(), f'.tpl missing for {t.id}'
        assert t.source == 'builtin', f'{t.id} source should be builtin'


def test_get_template_by_id():
    t = get_template_by_id('jellyfin')
    assert t is not None
    assert t.id == 'jellyfin'


def test_get_template_by_id_unknown():
    assert get_template_by_id('does-not-exist') is None
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd G:/Claude/Homestack/backend
pytest tests/test_templates.py::test_builtin_template_discovery -v
```

Expected: FAIL — `get_builtin_templates()` returns hardcoded list, not from JSON files (and JSON files don't exist yet).

- [ ] **Step 3: Create `templates/jellyfin/template.json`**

```json
{
  "id": "jellyfin",
  "name": "Jellyfin",
  "description": "Deploy Jellyfin with configurable config, cache and media mappings.",
  "default_install_subdir": "media/jellyfin",
  "required_placeholders": ["JF_CONFIG_PATH", "JF_CACHE_PATH", "JF_MEDIA_PATH"]
}
```

- [ ] **Step 4: Create `templates/immich/template.json`**

```json
{
  "id": "immich",
  "name": "Immich",
  "description": "Deploy Immich with library and Postgres data mappings.",
  "default_install_subdir": "photos/immich",
  "required_placeholders": ["IMMICH_UPLOAD_PATH", "IMMICH_DB_DATA_PATH"]
}
```

- [ ] **Step 5: Create `templates/komga/template.json`**

```json
{
  "id": "komga",
  "name": "Komga",
  "description": "Deploy Komga for manga, comics and ebooks with a dedicated config path and library mount.",
  "default_install_subdir": "media/komga",
  "required_placeholders": ["KOMGA_CONFIG_PATH", "KOMGA_LIBRARY_PATH"]
}
```

- [ ] **Step 6: Create `templates/nextcloud/template.json`**

```json
{
  "id": "nextcloud",
  "name": "Nextcloud",
  "description": "Deploy Nextcloud with MariaDB and Redis using Linux bind mounts you can place anywhere.",
  "default_install_subdir": "cloud/nextcloud",
  "required_placeholders": ["NC_APP_PATH", "NC_DATA_PATH", "NC_DB_PATH", "NC_REDIS_PATH"]
}
```

- [ ] **Step 7: Create `templates/vaultwarden/template.json`**

```json
{
  "id": "vaultwarden",
  "name": "Vaultwarden",
  "description": "Deploy Vaultwarden with a dedicated persistent data path for lightweight self-hosted password management.",
  "default_install_subdir": "security/vaultwarden",
  "required_placeholders": ["VW_DATA_PATH"]
}
```

- [ ] **Step 8: Create `templates/sonarr/template.json`**

```json
{
  "id": "sonarr",
  "name": "Sonarr",
  "description": "Deploy Sonarr on its own with separate config, downloads and TV library paths.",
  "default_install_subdir": "media/sonarr",
  "required_placeholders": ["SONARR_CONFIG_PATH", "SONARR_DOWNLOADS_PATH", "SONARR_TV_PATH"]
}
```

- [ ] **Step 9: Create `templates/radarr/template.json`**

```json
{
  "id": "radarr",
  "name": "Radarr",
  "description": "Deploy Radarr on its own with separate config, downloads and movie library paths.",
  "default_install_subdir": "media/radarr",
  "required_placeholders": ["RADARR_CONFIG_PATH", "RADARR_DOWNLOADS_PATH", "RADARR_MOVIES_PATH"]
}
```

- [ ] **Step 10: Create `templates/prowlarr/template.json`**

```json
{
  "id": "prowlarr",
  "name": "Prowlarr",
  "description": "Deploy Prowlarr on its own with a dedicated config path.",
  "default_install_subdir": "media/prowlarr",
  "required_placeholders": ["PROWLARR_CONFIG_PATH"]
}
```

- [ ] **Step 11: Create `templates/qbittorrent/template.json`**

```json
{
  "id": "qbittorrent",
  "name": "qBittorrent",
  "description": "Deploy qBittorrent on its own with separate config and downloads paths.",
  "default_install_subdir": "media/qbittorrent",
  "required_placeholders": ["QBITTORRENT_CONFIG_PATH", "QBITTORRENT_DOWNLOADS_PATH"]
}
```

- [ ] **Step 12: Create `templates/bazarr/template.json`**

```json
{
  "id": "bazarr",
  "name": "Bazarr",
  "description": "Deploy Bazarr on its own with separate config, movies and TV library paths.",
  "default_install_subdir": "media/bazarr",
  "required_placeholders": ["BAZARR_CONFIG_PATH", "BAZARR_MOVIES_PATH", "BAZARR_TV_PATH"]
}
```

- [ ] **Step 13: Create `templates/arr-stack/template.json`**

```json
{
  "id": "arr-stack",
  "name": "Arr Stack Combined",
  "description": "Deploy Sonarr, Radarr, Prowlarr, qBittorrent and Bazarr together with shared downloads and media mounts.",
  "default_install_subdir": "media/arr-stack",
  "required_placeholders": ["ARR_CONFIG_ROOT", "ARR_DOWNLOADS_PATH", "ARR_MOVIES_PATH", "ARR_TV_PATH"]
}
```

- [ ] **Step 14: Rewrite `get_builtin_templates()` in `backend/app/templates.py`**

Replace the entire `get_builtin_templates()` function (the hardcoded list). Leave `get_custom_templates()`, `get_templates()`, `get_template_by_id()`, and `create_custom_template()` completely unchanged.

```python
def get_builtin_templates() -> List[StackTemplate]:
    templates: List[StackTemplate] = []
    for json_path in sorted(TEMPLATES_DIR.glob('*/template.json')):
        try:
            raw = json.loads(json_path.read_text(encoding='utf-8'))
            templates.append(StackTemplate(
                id=raw['id'],
                name=raw['name'],
                description=raw['description'],
                compose_template_path=str(json_path.parent / 'docker-compose.yml.tpl'),
                default_install_subdir=raw['default_install_subdir'],
                required_placeholders=raw['required_placeholders'],
                source='builtin',
            ))
        except Exception:
            continue
    return templates
```

- [ ] **Step 15: Run tests to verify they pass**

```bash
cd G:/Claude/Homestack/backend
pytest tests/test_templates.py -v
```

Expected: all 4 tests PASS

- [ ] **Step 16: Commit**

```bash
cd G:/Claude/Homestack
git add templates/*/template.json backend/app/templates.py backend/tests/test_templates.py
git commit -m "feat: dynamic template discovery from template.json sidecars"
```

---

### Task 3: Jinja2 rendering (TDD)

**Files:**
- Modify: `backend/app/docker_ops.py` — add `_render_template`, replace `_safe_replace`
- Modify: `backend/tests/test_templates.py` — add rendering tests

- [ ] **Step 1: Add rendering tests to `backend/tests/test_templates.py`**

Append to the existing file:

```python
import jinja2
from app.docker_ops import _render_template


def test_render_template_success():
    result = _render_template('path: {{INSTALL_PATH}}', {'INSTALL_PATH': '/opt/test'})
    assert result == 'path: /opt/test'


def test_render_template_extra_keys_ignored():
    # Extra placeholders not used in template are fine
    result = _render_template('name: {{NAME}}', {'NAME': 'myapp', 'UNUSED': 'value'})
    assert result == 'name: myapp'


def test_render_template_missing_placeholder_raises():
    with pytest.raises(jinja2.UndefinedError):
        _render_template('path: {{INSTALL_PATH}}', {})
```

- [ ] **Step 2: Run to verify they fail**

```bash
cd G:/Claude/Homestack/backend
pytest tests/test_templates.py::test_render_template_success -v
```

Expected: FAIL — `cannot import name '_render_template' from 'app.docker_ops'`

- [ ] **Step 3: Update `backend/app/docker_ops.py`**

Add `import jinja2` at the top (after the existing imports):

```python
import jinja2
```

Add `_render_template` function directly below the imports section, replacing the `_safe_replace` function entirely:

```python
def _render_template(template_text: str, placeholders: Dict[str, str]) -> str:
    """Render a Jinja2 template. Raises jinja2.UndefinedError on missing placeholders."""
    env = jinja2.Environment(undefined=jinja2.StrictUndefined)
    return env.from_string(template_text).render(**placeholders)
```

In `_write_stack_files`, find:
```python
rendered = _safe_replace(compose_text, placeholders)
```
Replace with:
```python
try:
    rendered = _render_template(compose_text, placeholders)
except jinja2.UndefinedError as exc:
    raise ValueError(str(exc)) from exc
```

Delete the `_safe_replace` function entirely.

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd G:/Claude/Homestack/backend
pytest tests/test_templates.py -v
```

Expected: all 7 tests PASS

- [ ] **Step 5: Commit**

```bash
cd G:/Claude/Homestack
git add backend/app/docker_ops.py backend/tests/test_templates.py
git commit -m "feat: replace _safe_replace with Jinja2 StrictUndefined rendering"
```

---

## Chunk 2: docker_ops Improvements

### Task 4: Fix N+1 in `list_named_volumes` (TDD)

**Files:**
- Modify: `backend/app/docker_ops.py`
- Create: `backend/tests/test_docker_ops.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_docker_ops.py`:

```python
import json
import pytest
from unittest.mock import MagicMock, patch
from app.docker_ops import list_named_volumes


def test_list_named_volumes_two_subprocess_calls():
    """With N volumes, must use exactly 2 subprocess calls — no N+1."""
    ls_output = (
        json.dumps({'Name': 'vol1'}) + '\n' +
        json.dumps({'Name': 'vol2'})
    )
    inspect_output = json.dumps([
        {'Name': 'vol1', 'Driver': 'local', 'Mountpoint': '/volumes/vol1/_data'},
        {'Name': 'vol2', 'Driver': 'local', 'Mountpoint': '/volumes/vol2/_data'},
    ])
    ls_result = MagicMock(returncode=0, stdout=ls_output, stderr='')
    inspect_result = MagicMock(returncode=0, stdout=inspect_output, stderr='')

    with patch('app.docker_ops.docker_available', return_value=True):
        with patch('app.docker_ops._run_command', side_effect=[ls_result, inspect_result]) as mock_run:
            volumes = list_named_volumes()

    assert mock_run.call_count == 2
    assert len(volumes) == 2
    assert volumes[0].name == 'vol1'
    assert volumes[1].name == 'vol2'
    assert volumes[0].driver == 'local'
    assert volumes[0].mountpoint == '/volumes/vol1/_data'


def test_list_named_volumes_zero_volumes_one_call():
    """With zero volumes, only the ls call is made — no inspect call."""
    ls_result = MagicMock(returncode=0, stdout='', stderr='')

    with patch('app.docker_ops.docker_available', return_value=True):
        with patch('app.docker_ops._run_command', return_value=ls_result) as mock_run:
            volumes = list_named_volumes()

    assert mock_run.call_count == 1
    assert volumes == []
```

- [ ] **Step 2: Run to verify they fail**

```bash
cd G:/Claude/Homestack/backend
pytest tests/test_docker_ops.py::test_list_named_volumes_two_subprocess_calls -v
```

Expected: FAIL — current code calls `_run_command` N+1 times

- [ ] **Step 3: Rewrite `list_named_volumes` in `backend/app/docker_ops.py`**

Replace the entire `list_named_volumes` function:

```python
def list_named_volumes() -> List[VolumeOption]:
    if not docker_available():
        return []

    ls_result = _run_command(['docker', 'volume', 'ls', '--format', '{{json .}}'])
    if ls_result.returncode != 0:
        return []

    names: List[str] = []
    for line in ls_result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            raw = json.loads(line)
            name = raw.get('Name')
            if name:
                names.append(name)
        except Exception:
            continue

    if not names:
        return []

    inspect = _run_command(['docker', 'volume', 'inspect'] + names)
    if inspect.returncode != 0:
        return [VolumeOption(id=n, name=n) for n in names]

    try:
        details_list = json.loads(inspect.stdout)
    except Exception:
        return [VolumeOption(id=n, name=n) for n in names]

    volumes: List[VolumeOption] = []
    for details in details_list:
        name = details.get('Name')
        if not name:
            continue
        volumes.append(VolumeOption(
            id=name,
            name=name,
            driver=details.get('Driver'),
            mountpoint=details.get('Mountpoint'),
        ))
    return volumes
```

- [ ] **Step 4: Run tests**

```bash
cd G:/Claude/Homestack/backend
pytest tests/test_docker_ops.py -v
```

Expected: all 2 tests PASS

- [ ] **Step 5: Commit**

```bash
cd G:/Claude/Homestack
git add backend/app/docker_ops.py backend/tests/test_docker_ops.py
git commit -m "perf: fix N+1 subprocess calls in list_named_volumes"
```

---

### Task 5: Add `delete_stack` (TDD)

**Files:**
- Modify: `backend/app/docker_ops.py`
- Modify: `backend/tests/test_docker_ops.py`

- [ ] **Step 1: Add failing tests to `backend/tests/test_docker_ops.py`**

Append:

```python
from app.docker_ops import delete_stack
import app.docker_ops as dops


def _make_stack(stacks_dir, stack_name, install_path, placeholders=None, with_compose=True):
    """Helper: create a fake deployed stack on disk."""
    stack_dir = stacks_dir / stack_name
    stack_dir.mkdir(parents=True)
    if with_compose:
        (stack_dir / 'docker-compose.yml').write_text('services: {}')
    meta = {
        'stack_name': stack_name,
        'install_path': str(install_path),
        'placeholders': placeholders or {},
        'named_volume_bindings': {},
    }
    (stack_dir / 'stack.json').write_text(json.dumps(meta))
    return stack_dir


def test_delete_stack_raises_for_unknown_stack(tmp_path, monkeypatch):
    monkeypatch.setattr(dops, 'STACKS_DIR', tmp_path / 'stacks')
    with pytest.raises(FileNotFoundError, match='mystack'):
        delete_stack('mystack', delete_data=False)


def test_delete_stack_removes_stack_dir(tmp_path, monkeypatch):
    stacks_dir = tmp_path / 'stacks'
    monkeypatch.setattr(dops, 'STACKS_DIR', stacks_dir)
    install = tmp_path / 'install'
    install.mkdir()
    stack_dir = _make_stack(stacks_dir, 'mystack', install)

    with patch('app.docker_ops._run_command', return_value=MagicMock(returncode=0, stdout='', stderr='')):
        with patch('app.docker_ops.compose_available', return_value=True):
            result = delete_stack('mystack', delete_data=False)

    assert not stack_dir.exists()
    assert result['ok'] is True
    assert install.exists()  # data kept


def test_delete_stack_with_data_removes_paths(tmp_path, monkeypatch):
    stacks_dir = tmp_path / 'stacks'
    monkeypatch.setattr(dops, 'STACKS_DIR', stacks_dir)
    install = tmp_path / 'install'
    install.mkdir()
    data_dir = tmp_path / 'appdata'
    data_dir.mkdir()

    _make_stack(stacks_dir, 'mystack', install, placeholders={'DATA_PATH': str(data_dir)})

    with patch('app.docker_ops._run_command', return_value=MagicMock(returncode=0, stdout='', stderr='')):
        with patch('app.docker_ops.compose_available', return_value=True):
            result = delete_stack('mystack', delete_data=True)

    assert not install.exists()
    assert not data_dir.exists()
    assert str(install) in result['deleted']
    assert str(data_dir) in result['deleted']


def test_delete_stack_skips_non_path_placeholders(tmp_path, monkeypatch):
    """Placeholder values not starting with '/' are not deleted."""
    stacks_dir = tmp_path / 'stacks'
    monkeypatch.setattr(dops, 'STACKS_DIR', stacks_dir)
    install = tmp_path / 'install'
    install.mkdir()

    _make_stack(stacks_dir, 'mystack', install, placeholders={'VOL_NAME': 'myvolume'})

    with patch('app.docker_ops._run_command', return_value=MagicMock(returncode=0, stdout='', stderr='')):
        with patch('app.docker_ops.compose_available', return_value=True):
            result = delete_stack('mystack', delete_data=True)

    assert result['ok'] is True  # no error for non-path placeholder
    assert 'myvolume' not in result['deleted']  # non-path value not deleted


def test_delete_stack_skips_compose_down_if_no_compose_file(tmp_path, monkeypatch):
    """If the compose file is missing, deletion proceeds without running compose down."""
    stacks_dir = tmp_path / 'stacks'
    monkeypatch.setattr(dops, 'STACKS_DIR', stacks_dir)
    _make_stack(stacks_dir, 'mystack', tmp_path / 'install', with_compose=False)

    with patch('app.docker_ops.compose_available', return_value=True):
        with patch('app.docker_ops._run_command') as mock_run:
            result = delete_stack('mystack', delete_data=False)

    mock_run.assert_not_called()  # compose down was skipped
    assert result['ok'] is True
```

- [ ] **Step 2: Run to verify they fail**

```bash
cd G:/Claude/Homestack/backend
pytest tests/test_docker_ops.py::test_delete_stack_raises_for_unknown_stack -v
```

Expected: FAIL — `ImportError: cannot import name 'delete_stack'`

- [ ] **Step 3: Add `delete_stack` to `backend/app/docker_ops.py`**

Add after the `update_stack` function:

```python
def delete_stack(stack_name: str, delete_data: bool) -> Dict[str, object]:
    meta_path = _stack_meta_path(stack_name)
    if not meta_path.exists():
        raise FileNotFoundError(f'Stack not found: {stack_name}')

    metadata = json.loads(meta_path.read_text(encoding='utf-8'))
    deleted: List[str] = []

    # Stop containers — skip if compose unavailable or compose file is missing
    if compose_available():
        try:
            result = _compose_command_for_stack(stack_name, ['down'])
            if result.returncode != 0:
                raise RuntimeError(result.stderr.strip() or result.stdout.strip() or 'docker compose down failed')
        except FileNotFoundError:
            pass  # compose file absent — proceed with cleanup

    # Remove stack tracking directory
    stack_dir = _stack_root(stack_name)
    if stack_dir.exists():
        shutil.rmtree(stack_dir)
        deleted.append(str(stack_dir))

    # Optionally remove data directories
    if delete_data:
        install_path = metadata.get('install_path')
        if install_path and Path(install_path).exists():
            shutil.rmtree(install_path)
            deleted.append(install_path)

        for value in metadata.get('placeholders', {}).values():
            if isinstance(value, str) and value.startswith('/') and Path(value).exists():
                shutil.rmtree(value)
                deleted.append(value)

    return {'ok': True, 'deleted': deleted}
```

- [ ] **Step 4: Run tests**

```bash
cd G:/Claude/Homestack/backend
pytest tests/test_docker_ops.py -v
```

Expected: all tests PASS

- [ ] **Step 5: Commit**

```bash
cd G:/Claude/Homestack
git add backend/app/docker_ops.py backend/tests/test_docker_ops.py
git commit -m "feat: add delete_stack with optional data directory removal"
```

---

### Task 6: Fix `update_stack` + guard `run_stack_action` (TDD)

**Files:**
- Modify: `backend/app/docker_ops.py`
- Modify: `backend/tests/test_docker_ops.py`

- [ ] **Step 1: Add failing tests**

Append to `backend/tests/test_docker_ops.py`:

```python
from app.docker_ops import run_stack_action, update_stack
from app.models import StackDeploymentRequest, StackDeploymentResponse


def test_run_stack_action_invalid_raises_value_error(tmp_path, monkeypatch):
    stacks_dir = tmp_path / 'stacks'
    monkeypatch.setattr(dops, 'STACKS_DIR', stacks_dir)
    stack_dir = stacks_dir / 'mystack'
    stack_dir.mkdir(parents=True)
    (stack_dir / 'docker-compose.yml').write_text('services: {}')

    with patch('app.docker_ops.compose_available', return_value=True):
        with pytest.raises(ValueError, match='Unknown action'):
            run_stack_action('mystack', 'explode')


def test_update_stack_write_before_compose_down(tmp_path, monkeypatch):
    """_write_stack_files must be called before compose down."""
    stacks_dir = tmp_path / 'stacks'
    monkeypatch.setattr(dops, 'STACKS_DIR', stacks_dir)

    call_order = []

    def fake_write(req):
        call_order.append('write')
        stack_dir = stacks_dir / req.stack_name
        stack_dir.mkdir(parents=True, exist_ok=True)
        (stack_dir / 'docker-compose.yml').write_text('services: {}')
        meta = {
            'stack_name': req.stack_name,
            'install_path': str(tmp_path / 'install'),
            'placeholders': {},
            'named_volume_bindings': {},
        }
        (stack_dir / 'stack.json').write_text(json.dumps(meta))
        return StackDeploymentResponse(
            ok=True,
            stack_name=req.stack_name,
            install_path=str(tmp_path / 'install'),
            compose_path=str(stack_dir / 'docker-compose.yml'),
            message='ok',
        )

    def fake_run(cmd, cwd=None):
        if 'down' in cmd:
            call_order.append('down')
        elif 'up' in cmd:
            call_order.append('up')
        return MagicMock(returncode=0, stdout='', stderr='')

    monkeypatch.setattr(dops, '_write_stack_files', fake_write)
    monkeypatch.setattr(dops, '_run_command', fake_run)

    with patch('app.docker_ops.compose_available', return_value=True):
        req = StackDeploymentRequest(
            template_id='jellyfin',
            stack_name='mystack',
            install_path='/opt/homestack/test/install',  # must start with / to pass Pydantic validator on Windows
            placeholders={
                'JF_CONFIG_PATH': '/p/config',
                'JF_CACHE_PATH': '/p/cache',
                'JF_MEDIA_PATH': '/p/media',
            },
            named_volume_bindings={},
        )
        update_stack('mystack', req)

    assert call_order == ['write', 'down', 'up'], f'Wrong order: {call_order}'
```

- [ ] **Step 2: Run to verify they fail**

```bash
cd G:/Claude/Homestack/backend
pytest tests/test_docker_ops.py::test_run_stack_action_invalid_raises_value_error tests/test_docker_ops.py::test_update_stack_write_before_compose_down -v
```

Expected: both FAIL

- [ ] **Step 3: Update `run_stack_action` in `backend/app/docker_ops.py`**

Find:
```python
def run_stack_action(stack_name: str, action: str) -> Dict[str, object]:
    if not compose_available():
        raise RuntimeError('Docker Compose not available')
    command_map = {
```

Add guard before the `command_map` lookup:
```python
def run_stack_action(stack_name: str, action: str) -> Dict[str, object]:
    if not compose_available():
        raise RuntimeError('Docker Compose not available')
    command_map = {
        'start': ['up', '-d'],
        'stop': ['stop'],
        'restart': ['restart'],
    }
    if action not in command_map:
        raise ValueError(f'Unknown action: {action}')
    result = _compose_command_for_stack(stack_name, command_map[action])
    ...  # rest unchanged
```

- [ ] **Step 4: Rewrite `update_stack` in `backend/app/docker_ops.py`**

Replace the current `update_stack` function:

```python
def update_stack(stack_name: str, request: StackDeploymentRequest) -> StackDeploymentResponse:
    if stack_name != request.stack_name:
        raise ValueError('Stack name in URL must match stack_name in request body')

    # 1. Write files first — if this fails, old containers keep running (safe)
    response = _write_stack_files(request)

    if compose_available():
        # 2. Tear down old containers
        down_result = _compose_command_for_stack(request.stack_name, ['down'])
        if down_result.returncode != 0:
            raise RuntimeError(down_result.stderr.strip() or down_result.stdout.strip() or 'docker compose down failed')

        # 3. Re-deploy with new config
        up_result = _compose_command_for_stack(request.stack_name, ['up', '-d'])
        if up_result.returncode != 0:
            raise RuntimeError(up_result.stderr.strip() or up_result.stdout.strip() or 'docker compose up failed')

        response.message = 'Stack updated and redeployed successfully'
    else:
        response.message = 'Compose file updated, but Docker Compose was not available'

    return response
```

- [ ] **Step 5: Run all docker_ops tests**

```bash
cd G:/Claude/Homestack/backend
pytest tests/test_docker_ops.py -v
```

Expected: all tests PASS

- [ ] **Step 6: Commit**

```bash
cd G:/Claude/Homestack
git add backend/app/docker_ops.py backend/tests/test_docker_ops.py
git commit -m "feat: fix update_stack teardown order and guard run_stack_action"
```

---

### Task 7: Add DELETE endpoint (TDD)

**Files:**
- Modify: `backend/app/main.py`
- Create: `backend/tests/test_api.py` (partial — delete endpoint tests)

- [ ] **Step 1: Write failing integration tests**

Create `backend/tests/test_api.py`:

```python
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
```

- [ ] **Step 2: Run to verify delete tests fail**

```bash
cd G:/Claude/Homestack/backend
pytest tests/test_api.py::test_delete_unknown_stack_returns_404 -v
```

Expected: FAIL — 405 Method Not Allowed (endpoint doesn't exist)

- [ ] **Step 3: Update `backend/app/main.py`**

Add `delete_stack` to the `from .docker_ops import (...)` block:

```python
from .docker_ops import (
    compose_available,
    delete_stack,
    deploy_stack,
    docker_available,
    get_stack,
    get_stack_logs,
    get_stack_runtime_status,
    list_deployed_stacks,
    list_named_volumes,
    run_stack_action,
    update_stack,
)
```

Add the DELETE endpoint after the existing `stack_action` endpoint:

```python
@app.delete('/api/stacks/{stack_name}')
def remove_stack(
    stack_name: str,
    delete_data: bool = False,
    user=Depends(get_current_user),
) -> dict:
    try:
        return delete_stack(stack_name, delete_data)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
```

- [ ] **Step 4: Run API tests**

```bash
cd G:/Claude/Homestack/backend
pytest tests/test_api.py -v
```

Expected: all 5 tests PASS

- [ ] **Step 5: Run full test suite to check no regressions**

```bash
cd G:/Claude/Homestack/backend
pytest tests/ -v
```

Expected: all tests PASS

- [ ] **Step 6: Commit**

```bash
cd G:/Claude/Homestack
git add backend/app/main.py backend/tests/test_api.py
git commit -m "feat: add DELETE /api/stacks/{stack_name} endpoint"
```

---

## Chunk 3: Frontend

### Task 8: All frontend changes

**Files:**
- Modify: `frontend/app.js`

This task has no automated tests (frontend). Use the manual checklist in Step 6.

- [ ] **Step 1: Add `escapeHtml` utility and fix `API_BASE`**

Replace the first 4 lines of `frontend/app.js`:
```javascript
const apiBase = window.location.origin.includes('5500') || window.location.origin.includes('8080')
  ? 'http://localhost:8000'
  : '';
```
With:
```javascript
const API_BASE = '';
// For local dev with separate servers, set API_BASE = 'http://localhost:8000'

function escapeHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}
```

In the `api()` function, replace `${apiBase}${path}` with `${API_BASE}${path}`.

- [ ] **Step 2: Rewrite `refreshStacks` with `escapeHtml` + data-attribute buttons + delete button + action feedback**

Replace the entire `refreshStacks` function:

```javascript
async function refreshStacks() {
  const stacks = await api('/api/stacks');
  if (!stacks.length) {
    els.stacksList.innerHTML = '<div class="card">No stacks deployed yet.</div>';
    return;
  }

  els.stacksList.innerHTML = stacks.map(stack => {
    const containers = stack.runtime?.containers || [];
    const runningClass = stack.runtime?.running ? 'ok' : 'danger';
    const name = escapeHtml(stack.stack_name);
    return `
      <div class="card card-grid">
        <div>
          <h3>${name}</h3>
          <div class="kv">
            <strong>Template</strong><span>${escapeHtml(stack.template_id || 'Unknown')}</span>
            <strong>Install path</strong><span>${escapeHtml(stack.install_path || 'Unknown')}</span>
            <strong>Status</strong><span class="${runningClass}">${escapeHtml(stack.runtime?.summary || 'Unknown')}</span>
            <strong>Compose</strong><span>${escapeHtml(stack.compose_path || '')}</span>
          </div>
          <div>
            ${containers.map(c => `<span class="tag">${escapeHtml(c.Service || c.Name || 'container')}: ${escapeHtml(String(c.State || 'unknown'))}</span>`).join('') || '<span class="hint">No container status yet.</span>'}
          </div>
        </div>
        <div>
          <div class="button-row">
            <button data-action="edit" data-stack-name="${escapeHtml(stack.stack_name)}">Edit</button>
            <button data-action="start" data-stack-name="${escapeHtml(stack.stack_name)}">Start</button>
            <button data-action="stop" data-stack-name="${escapeHtml(stack.stack_name)}">Stop</button>
            <button data-action="restart" data-stack-name="${escapeHtml(stack.stack_name)}">Restart</button>
            <button data-action="logs" data-stack-name="${escapeHtml(stack.stack_name)}">Logs</button>
            <button data-action="delete" data-stack-name="${escapeHtml(stack.stack_name)}">Delete</button>
          </div>
          <details>
            <summary>Last action output</summary>
            <pre id="logs-${name}">Logs appear here.</pre>
          </details>
        </div>
      </div>
    `;
  }).join('');
}
```

- [ ] **Step 3: Add delegated event listener on `#stacksList`**

Add this block after `refreshStacks` (before `renderSystemStatus`):

```javascript
els.stacksList.addEventListener('click', async (e) => {
  const btn = e.target.closest('button[data-action]');
  if (!btn) return;
  const action = btn.dataset.action;
  const stackName = btn.dataset.stackName;
  if (action === 'edit') await editStack(stackName);
  else if (action === 'logs') await viewLogs(stackName);
  else if (action === 'delete') await deleteStack(stackName);
  else await stackAction(stackName, action);
});
```

- [ ] **Step 4: Add `deleteStack` function**

Add after `viewLogs`:

```javascript
async function deleteStack(stackName) {
  if (!confirm(`Delete stack "${stackName}"? This will stop its containers.`)) return;
  const deleteData = confirm('Also delete data directories from disk? This cannot be undone.');
  try {
    await api(`/api/stacks/${stackName}?delete_data=${deleteData}`, { method: 'DELETE' });
    els.statusBox.textContent = `Stack "${stackName}" deleted.`;
    await refreshStacks();
  } catch (err) {
    els.statusBox.textContent = `Delete failed: ${err.message}`;
  }
}
```

- [ ] **Step 5: Update `stackAction` for human-readable feedback**

Replace the `stackAction` function:

```javascript
async function stackAction(stackName, action) {
  try {
    const data = await api(`/api/stacks/${stackName}/action`, {
      method: 'POST',
      body: JSON.stringify({ action }),
    });
    const msg = data.message || `Stack ${action} completed.`;
    els.statusBox.textContent = msg;
    const logBox = document.getElementById(`logs-${stackName}`);
    if (logBox) logBox.textContent = JSON.stringify(data, null, 2);  // raw JSON in the <details> block
    await refreshStacks();
  } catch (err) {
    els.statusBox.textContent = `Action failed: ${err.message}`;
    const logBox = document.getElementById(`logs-${stackName}`);
    if (logBox) logBox.textContent = `Action failed: ${err.message}`;
  }
}
```

- [ ] **Step 6: Remove `window.*` global assignments**

Delete these three lines (they appear near the bottom of `app.js`):
```javascript
window.editStack = editStack;
window.stackAction = stackAction;
window.viewLogs = viewLogs;
```

- [ ] **Step 7: Manual verification checklist**

Start the app:
```bash
cd G:/Claude/Homestack
docker compose up -d --build
```
Then open `http://localhost:8080` and verify:
- [ ] Login works
- [ ] Stack list renders without console errors
- [ ] Start / Stop / Restart buttons work via data-attribute delegation
- [ ] Logs button shows logs in `<details>` section
- [ ] Edit button loads stack into deploy form
- [ ] Delete button shows two confirm dialogs then removes the stack
- [ ] Stack names with special characters (if any) don't break the UI

- [ ] **Step 8: Commit**

```bash
cd G:/Claude/Homestack
git add frontend/app.js
git commit -m "feat: escapeHtml XSS fix, data-attribute delegation, delete button, API base fix"
```

---

## Chunk 4: Full Test Coverage

### Task 9: Complete `test_auth.py`

**Files:**
- Create: `backend/tests/test_auth.py`

- [ ] **Step 1: Create `backend/tests/test_auth.py`**

```python
import pytest
from fastapi import HTTPException
from app.auth import (
    register_user,
    authenticate_user,
    create_token,
    decode_token,
)


def test_register_first_user_is_admin():
    user = register_user('admin', 'password123')
    assert user.username == 'admin'
    assert user.role == 'admin'


def test_register_second_user_is_not_admin():
    register_user('admin', 'password123')
    user = register_user('other', 'password456')
    assert user.role == 'user'


def test_register_duplicate_username_raises():
    register_user('admin', 'password123')
    with pytest.raises(ValueError, match='already exists'):
        register_user('admin', 'differentpass')


def test_authenticate_correct_password():
    register_user('testuser', 'mypassword')
    user = authenticate_user('testuser', 'mypassword')
    assert user is not None
    assert user.username == 'testuser'


def test_authenticate_wrong_password_returns_none():
    register_user('testuser', 'mypassword')
    result = authenticate_user('testuser', 'wrongpassword')
    assert result is None


def test_authenticate_unknown_user_returns_none():
    result = authenticate_user('nobody', 'somepassword')
    assert result is None


def test_create_and_decode_token():
    user = register_user('tokenuser', 'pass123456')
    token = create_token(user)
    assert '.' in token
    decoded = decode_token(token)
    assert decoded.username == 'tokenuser'
    assert decoded.role == 'admin'


def test_expired_token_raises_401(monkeypatch):
    import app.auth as auth
    monkeypatch.setattr(auth, 'TOKEN_TTL_SECONDS', -1)
    user = register_user('expuser', 'pass123456')
    token = create_token(user)
    with pytest.raises(HTTPException) as exc_info:
        decode_token(token)
    assert exc_info.value.status_code == 401
    assert 'expired' in exc_info.value.detail.lower()


def test_tampered_token_raises_401():
    with pytest.raises(HTTPException) as exc_info:
        decode_token('fakepayload.fakesignature')
    assert exc_info.value.status_code == 401
```

- [ ] **Step 2: Run auth tests**

```bash
cd G:/Claude/Homestack/backend
pytest tests/test_auth.py -v
```

Expected: all 9 tests PASS

- [ ] **Step 3: Commit**

```bash
cd G:/Claude/Homestack
git add backend/tests/test_auth.py
git commit -m "test: add full test_auth.py coverage"
```

---

### Task 10: Complete `test_templates.py` and `test_docker_ops.py`

**Files:**
- Modify: `backend/tests/test_templates.py`
- Modify: `backend/tests/test_docker_ops.py`

- [ ] **Step 1: Add custom template tests to `backend/tests/test_templates.py`**

Append:

```python
from app.templates import get_custom_templates, create_custom_template
from app.models import StackTemplateCreateRequest
import app.templates as tmpl


def _make_create_request(template_id='myapp'):
    return StackTemplateCreateRequest(
        id=template_id,
        name='My App',
        description='Test template',
        default_install_subdir='apps/myapp',
        required_placeholders=['MYAPP_DATA'],
        compose_template_text='services:\n  app:\n    image: myapp\n    volumes:\n      - {{MYAPP_DATA}}:/data',
    )


def test_custom_templates_empty_by_default():
    assert get_custom_templates() == []


def test_create_custom_template(tmp_path, monkeypatch):
    monkeypatch.setattr(tmpl, 'CUSTOM_TEMPLATES_DIR', tmp_path / 'custom')
    t = create_custom_template(_make_create_request())
    assert t.id == 'myapp'
    assert t.source == 'custom'
    assert t.required_placeholders == ['MYAPP_DATA']


def test_create_duplicate_custom_template_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(tmpl, 'CUSTOM_TEMPLATES_DIR', tmp_path / 'custom')
    create_custom_template(_make_create_request())
    with pytest.raises(ValueError, match='already exists'):
        create_custom_template(_make_create_request())


def test_custom_template_appears_in_get_templates(tmp_path, monkeypatch):
    monkeypatch.setattr(tmpl, 'CUSTOM_TEMPLATES_DIR', tmp_path / 'custom')
    create_custom_template(_make_create_request())
    from app.templates import get_templates
    ids = {t.id for t in get_templates()}
    assert 'myapp' in ids
    assert 'jellyfin' in ids  # builtins still present
```

- [ ] **Step 2: Add remaining `run_stack_action` tests to `backend/tests/test_docker_ops.py`**

Append:

```python
def test_run_stack_action_valid_actions_do_not_raise_value_error(tmp_path, monkeypatch):
    """Valid actions should not raise ValueError."""
    stacks_dir = tmp_path / 'stacks'
    monkeypatch.setattr(dops, 'STACKS_DIR', stacks_dir)
    stack_dir = stacks_dir / 'mystack'
    stack_dir.mkdir(parents=True)
    (stack_dir / 'docker-compose.yml').write_text('services: {}')

    mock_result = MagicMock(returncode=0, stdout='done', stderr='')
    with patch('app.docker_ops.compose_available', return_value=True):
        with patch('app.docker_ops._run_command', return_value=mock_result):
            for action in ['start', 'stop', 'restart']:
                result = run_stack_action('mystack', action)
                assert result['ok'] is True
                assert result['action'] == action
```

- [ ] **Step 3: Run all tests**

```bash
cd G:/Claude/Homestack/backend
pytest tests/test_templates.py tests/test_docker_ops.py -v
```

Expected: all tests PASS

- [ ] **Step 4: Commit**

```bash
cd G:/Claude/Homestack
git add backend/tests/test_templates.py backend/tests/test_docker_ops.py
git commit -m "test: complete test_templates and test_docker_ops coverage"
```

---

### Task 11: Complete `test_api.py`

**Files:**
- Modify: `backend/tests/test_api.py`

- [ ] **Step 1: Append remaining API tests to `backend/tests/test_api.py`**

```python
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
```

- [ ] **Step 2: Run full test suite**

```bash
cd G:/Claude/Homestack/backend
pytest tests/ -v
```

Expected: all tests PASS. If any fail, read the error carefully and fix the failing test or implementation before proceeding.

- [ ] **Step 3: Commit**

```bash
cd G:/Claude/Homestack
git add backend/tests/test_api.py
git commit -m "test: complete test_api.py coverage including delete endpoint"
```

---

### Task 12: Final verification

- [ ] **Step 1: Run complete test suite with coverage summary**

```bash
cd G:/Claude/Homestack/backend
pytest tests/ -v --tb=short
```

Expected: all tests PASS, zero failures.

- [ ] **Step 2: Verify the app still builds**

```bash
cd G:/Claude/Homestack
docker compose build
```

Expected: build succeeds (no import errors, no syntax errors).

- [ ] **Step 3: Final commit if any fixes were needed**

If any tests required fixes to implementation code, commit those fixes:
```bash
cd G:/Claude/Homestack
git add -p  # stage only what changed
git commit -m "fix: address test failures found during final verification"
```
