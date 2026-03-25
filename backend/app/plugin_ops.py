from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

PLUGINS_DIR = Path('/app/data/plugins')


def _plugins_dir() -> Path:
    PLUGINS_DIR.mkdir(parents=True, exist_ok=True)
    return PLUGINS_DIR


def _safe_id(plugin_id: str) -> str:
    safe = ''.join(c for c in plugin_id if c.isalnum() or c in '-_')
    if not safe:
        raise ValueError('Invalid plugin ID')
    return safe


def _validate_manifest(manifest: dict) -> None:
    for key in ('name', 'version', 'entry'):
        if key not in manifest:
            raise ValueError(f'Plugin manifest missing required field: {key}')
    entry = manifest['entry']
    if '/' in entry or '\\' in entry or '..' in entry:
        raise ValueError('Plugin entry must be a filename, not a path')


def list_plugins() -> list[dict]:
    plugins = []
    for plugin_dir in sorted(_plugins_dir().iterdir()):
        if not plugin_dir.is_dir():
            continue
        manifest_path = plugin_dir / 'manifest.json'
        if not manifest_path.exists():
            continue
        try:
            manifest = json.loads(manifest_path.read_text())
            manifest['id'] = plugin_dir.name
            manifest['enabled'] = (plugin_dir / '.enabled').exists()
            plugins.append(manifest)
        except Exception:
            continue
    return plugins


def install_plugin_from_git(git_url: str) -> dict:
    if not git_url.startswith(('https://', 'http://', 'git@')):
        raise ValueError('git_url must start with https://, http://, or git@')

    raw_name = git_url.rstrip('/').split('/')[-1]
    if raw_name.endswith('.git'):
        raw_name = raw_name[:-4]
    plugin_id = ''.join(c for c in raw_name.lower() if c.isalnum() or c in '-_')
    if not plugin_id:
        raise ValueError('Could not derive a plugin ID from the git URL')

    plugin_dir = _plugins_dir() / plugin_id
    if plugin_dir.exists():
        result = subprocess.run(
            ['git', 'pull'],
            cwd=str(plugin_dir),
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode != 0:
            raise RuntimeError(f'git pull failed: {result.stderr.strip()}')
    else:
        result = subprocess.run(
            ['git', 'clone', '--depth=1', git_url, str(plugin_dir)],
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode != 0:
            raise RuntimeError(f'git clone failed: {result.stderr.strip()}')

    manifest_path = plugin_dir / 'manifest.json'
    if not manifest_path.exists():
        shutil.rmtree(plugin_dir, ignore_errors=True)
        raise ValueError('Repository is missing manifest.json — is this a HomeStack plugin?')

    manifest = json.loads(manifest_path.read_text())
    _validate_manifest(manifest)

    (plugin_dir / '.enabled').touch()
    manifest['id'] = plugin_id
    manifest['enabled'] = True
    return manifest


def install_plugin_from_zip(zip_bytes: bytes) -> dict:
    with tempfile.TemporaryDirectory() as tmpdir:
        zip_path = Path(tmpdir) / 'plugin.zip'
        zip_path.write_bytes(zip_bytes)

        with zipfile.ZipFile(zip_path) as zf:
            for name in zf.namelist():
                if '..' in name or name.startswith('/'):
                    raise ValueError('Zip contains unsafe paths')
            zf.extractall(tmpdir)

        manifests = list(Path(tmpdir).rglob('manifest.json'))
        if not manifests:
            raise ValueError('Zip is missing manifest.json')

        manifest_path = min(manifests, key=lambda p: len(p.parts))
        plugin_root = manifest_path.parent
        manifest = json.loads(manifest_path.read_text())
        _validate_manifest(manifest)

        raw_id = manifest.get('id', plugin_root.name)
        plugin_id = ''.join(c for c in str(raw_id).lower() if c.isalnum() or c in '-_')
        if not plugin_id:
            raise ValueError('Could not derive plugin ID from manifest')

        dest = _plugins_dir() / plugin_id
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(str(plugin_root), str(dest))

    (dest / '.enabled').touch()
    manifest['id'] = plugin_id
    manifest['enabled'] = True
    return manifest


def uninstall_plugin(plugin_id: str) -> None:
    plugin_dir = _plugins_dir() / _safe_id(plugin_id)
    if not plugin_dir.exists():
        raise FileNotFoundError(f'Plugin "{plugin_id}" not found')
    shutil.rmtree(plugin_dir)


def toggle_plugin(plugin_id: str) -> dict:
    plugin_dir = _plugins_dir() / _safe_id(plugin_id)
    if not plugin_dir.exists():
        raise FileNotFoundError(f'Plugin "{plugin_id}" not found')
    enabled_path = plugin_dir / '.enabled'
    if enabled_path.exists():
        enabled_path.unlink()
        enabled = False
    else:
        enabled_path.touch()
        enabled = True
    return {'ok': True, 'enabled': enabled}


def get_plugin_asset_path(plugin_id: str, filename: str) -> Path:
    plugin_dir = _plugins_dir() / _safe_id(plugin_id)
    if not plugin_dir.exists():
        raise FileNotFoundError(f'Plugin "{plugin_id}" not found')
    # Prevent path traversal — only allow bare filenames
    safe_name = Path(filename).name
    asset_path = plugin_dir / safe_name
    if not asset_path.exists() or not asset_path.is_file():
        raise FileNotFoundError(f'Asset "{filename}" not found in plugin "{plugin_id}"')
    return asset_path
