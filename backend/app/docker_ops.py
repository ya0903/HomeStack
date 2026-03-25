from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Dict, List

import jinja2

from .models import RawDeploymentRequest, StackDeploymentRequest, StackDeploymentResponse, VolumeOption
from .templates import get_template_by_id

import os
ROOT = Path(os.environ.get('APP_ROOT', str(Path(__file__).resolve().parents[2])))
STACKS_DIR = ROOT / 'data' / 'stacks'


def _run_command(command: List[str], cwd: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(command, cwd=cwd, text=True, capture_output=True, check=False)


def docker_available() -> bool:
    return shutil.which('docker') is not None


def compose_available() -> bool:
    if not docker_available():
        return False
    result = _run_command(['docker', 'compose', 'version'])
    return result.returncode == 0


def list_all_containers() -> List[Dict[str, object]]:
    if not docker_available():
        return []
    result = _run_command(['docker', 'ps', '-a', '--format', '{{json .}}'])
    if result.returncode != 0:
        return []
    containers = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            containers.append(json.loads(line))
        except Exception:
            continue
    return containers


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


def _render_template(template_text: str, placeholders: Dict[str, str]) -> str:
    """Render a Jinja2 template. Raises jinja2.UndefinedError on missing placeholders."""
    env = jinja2.Environment(undefined=jinja2.StrictUndefined)
    return env.from_string(template_text).render(**placeholders)


def _stack_root(stack_name: str) -> Path:
    return STACKS_DIR / stack_name


def _stack_compose_path(stack_name: str) -> Path:
    return _stack_root(stack_name) / 'docker-compose.yml'


def _stack_meta_path(stack_name: str) -> Path:
    return _stack_root(stack_name) / 'stack.json'


def _read_stack_metadata(stack_name: str) -> Dict:
    meta_path = _stack_meta_path(stack_name)
    if not meta_path.exists():
        raise FileNotFoundError(f'Stack metadata not found for {stack_name}')
    return json.loads(meta_path.read_text(encoding='utf-8'))


def _compose_command_for_stack(stack_name: str, args: List[str]) -> subprocess.CompletedProcess:
    compose_path = _stack_compose_path(stack_name)
    if not compose_path.exists():
        raise FileNotFoundError(f'Compose file not found for stack {stack_name}')
    return _run_command(['docker', 'compose', '-f', str(compose_path), *args])


def _write_stack_files(request: StackDeploymentRequest) -> StackDeploymentResponse:
    template = get_template_by_id(request.template_id)
    if template is None:
        raise ValueError(f'Unknown template_id: {request.template_id}')

    template_path = Path(template.compose_template_path)
    if not template_path.exists():
        raise FileNotFoundError(f'Template not found: {template_path}')

    stack_root = _stack_root(request.stack_name)
    install_path = Path(request.install_path)
    install_path.mkdir(parents=True, exist_ok=True)
    stack_root.mkdir(parents=True, exist_ok=True)

    placeholders = dict(request.placeholders)
    placeholders['STACK_NAME'] = request.stack_name
    placeholders['INSTALL_PATH'] = str(install_path)

    for required in template.required_placeholders:
        if required not in placeholders or not placeholders[required].strip():
            raise ValueError(f'Missing placeholder value: {required}')
        path_value = placeholders[required]
        if path_value.startswith('/'):
            Path(path_value).mkdir(parents=True, exist_ok=True)

    for template_volume_name, existing_volume_name in request.named_volume_bindings.items():
        placeholders[template_volume_name] = existing_volume_name

    compose_text = template_path.read_text(encoding='utf-8')
    try:
        rendered = _render_template(compose_text, placeholders)
    except jinja2.UndefinedError as exc:
        raise ValueError(str(exc)) from exc

    compose_path = stack_root / 'docker-compose.yml'
    compose_path.write_text(rendered, encoding='utf-8')

    env_path = stack_root / '.env'
    env_lines = [f'{k}={v}' for k, v in sorted(placeholders.items())]
    env_path.write_text('\n'.join(env_lines) + '\n', encoding='utf-8')

    metadata = {
        'stack_name': request.stack_name,
        'template_id': request.template_id,
        'install_path': str(install_path),
        'placeholders': request.placeholders,
        'named_volume_bindings': request.named_volume_bindings,
        'compose_path': str(compose_path),
    }
    _stack_meta_path(request.stack_name).write_text(json.dumps(metadata, indent=2) + '\n', encoding='utf-8')

    return StackDeploymentResponse(
        ok=True,
        stack_name=request.stack_name,
        install_path=str(install_path),
        compose_path=str(compose_path),
        message='Stack files saved successfully',
    )


def deploy_raw_stack(request: RawDeploymentRequest) -> StackDeploymentResponse:
    stack_root = _stack_root(request.stack_name)
    install_path = Path(request.install_path)
    install_path.mkdir(parents=True, exist_ok=True)
    stack_root.mkdir(parents=True, exist_ok=True)

    compose_path = stack_root / 'docker-compose.yml'
    compose_path.write_text(request.compose_content, encoding='utf-8')

    metadata = {
        'stack_name': request.stack_name,
        'template_id': '__custom__',
        'install_path': str(install_path),
        'placeholders': {},
        'named_volume_bindings': {},
        'compose_path': str(compose_path),
    }
    _stack_meta_path(request.stack_name).write_text(json.dumps(metadata, indent=2) + '\n', encoding='utf-8')

    response = StackDeploymentResponse(
        ok=True,
        stack_name=request.stack_name,
        install_path=str(install_path),
        compose_path=str(compose_path),
        message='Stack files saved successfully',
    )
    if compose_available():
        result = _compose_command_for_stack(request.stack_name, ['up', '-d'])
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or result.stdout.strip() or 'docker compose failed')
        response.message = 'Stack deployed successfully with docker compose up -d'
    else:
        response.message = 'Compose file generated, but Docker Compose was not available on this system'
    return response


def deploy_stack(request: StackDeploymentRequest) -> StackDeploymentResponse:
    response = _write_stack_files(request)

    if compose_available():
        result = _compose_command_for_stack(request.stack_name, ['up', '-d'])
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or result.stdout.strip() or 'docker compose failed')
        response.message = 'Stack deployed successfully with docker compose up -d'
    else:
        response.message = 'Compose file generated, but Docker Compose was not available on this system'
    return response


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
            if isinstance(value, str) and Path(value).is_absolute() and Path(value).exists():
                shutil.rmtree(value)
                deleted.append(value)

    return {'ok': True, 'deleted': deleted}


def list_deployed_stacks() -> List[Dict[str, object]]:
    STACKS_DIR.mkdir(parents=True, exist_ok=True)
    stacks = []
    for child in sorted(STACKS_DIR.iterdir()):
        if not child.is_dir():
            continue
        compose_file = child / 'docker-compose.yml'
        metadata = {}
        if _stack_meta_path(child.name).exists():
            try:
                metadata = json.loads(_stack_meta_path(child.name).read_text(encoding='utf-8'))
            except Exception:
                metadata = {}
        status = get_stack_runtime_status(child.name)
        stacks.append(
            {
                'stack_name': child.name,
                'compose_path': str(compose_file),
                'exists': compose_file.exists(),
                'template_id': metadata.get('template_id'),
                'install_path': metadata.get('install_path'),
                'runtime': status,
            }
        )
    return stacks



def get_stack(stack_name: str) -> Dict[str, object]:
    metadata = _read_stack_metadata(stack_name)
    metadata['runtime'] = get_stack_runtime_status(stack_name)
    metadata['logs'] = get_stack_logs(stack_name, tail=80)
    return metadata



def parse_compose_ps_output(stdout: str) -> List[Dict[str, object]]:
    stdout = stdout.strip()
    if not stdout:
        return []
    try:
        raw = json.loads(stdout)
        if isinstance(raw, list):
            return raw
    except Exception:
        pass

    rows: List[Dict[str, object]] = []
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except Exception:
            continue
    return rows



def get_stack_runtime_status(stack_name: str) -> Dict[str, object]:
    if not compose_available():
        return {
            'available': False,
            'running': False,
            'containers': [],
            'summary': 'Docker Compose not available',
        }
    try:
        result = _compose_command_for_stack(stack_name, ['ps', '--format', 'json'])
    except FileNotFoundError:
        return {
            'available': False,
            'running': False,
            'containers': [],
            'summary': 'Compose file not found',
        }
    if result.returncode != 0:
        return {
            'available': True,
            'running': False,
            'containers': [],
            'summary': result.stderr.strip() or result.stdout.strip() or 'Unable to fetch status',
        }
    containers = parse_compose_ps_output(result.stdout)

    # For imported stacks, compose ps returns nothing because the container
    # wasn't started with this compose project. Fall back to docker ps by name.
    if not containers:
        meta_path = _stack_meta_path(stack_name)
        is_imported = False
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text(encoding='utf-8'))
                is_imported = meta.get('template_id') == '__imported__'
            except Exception:
                pass
        if is_imported:
            fallback = _run_command([
                'docker', 'ps', '-a',
                '--filter', f'name=^/{stack_name}$',
                '--format', '{{json .}}',
            ])
            for line in fallback.stdout.splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    c = json.loads(line)
                    containers.append({
                        'Name': c.get('Names', stack_name),
                        'Service': stack_name,
                        'State': c.get('State', 'unknown'),
                        'Status': c.get('Status', ''),
                        'Ports': c.get('Ports', ''),
                    })
                except Exception:
                    continue

    running = any(str(c.get('State', '')).lower() == 'running' for c in containers)
    summary = 'Running' if running else 'Stopped'
    if not containers:
        summary = 'No containers yet'
    return {
        'available': True,
        'running': running,
        'containers': containers,
        'summary': summary,
    }



def get_stack_logs(stack_name: str, tail: int = 200) -> str:
    if not compose_available():
        return 'Docker Compose not available'
    result = _compose_command_for_stack(stack_name, ['logs', '--no-color', '--tail', str(tail)])
    if result.returncode != 0:
        return result.stderr.strip() or result.stdout.strip() or 'Unable to read logs'
    return result.stdout.strip() or 'No logs yet'



def import_container(container_name: str) -> Dict[str, object]:
    if not docker_available():
        raise ValueError('Docker is not available')
    result = _run_command(['docker', 'inspect', container_name])
    if result.returncode != 0:
        raise ValueError(f'Container not found: {container_name}')
    try:
        data = json.loads(result.stdout)
    except Exception as exc:
        raise ValueError('Failed to parse docker inspect output') from exc
    if not data:
        raise ValueError(f'No inspect data for: {container_name}')

    inspect = data[0]
    config = inspect.get('Config') or {}
    host_config = inspect.get('HostConfig') or {}

    name = inspect.get('Name', '').lstrip('/')
    image = config.get('Image', 'unknown')
    restart = (host_config.get('RestartPolicy') or {}).get('Name', 'unless-stopped')
    if not restart or restart == 'no':
        restart = 'unless-stopped'

    lines = [
        'services:',
        f'  {name}:',
        f'    image: {image}',
        f'    container_name: {name}',
        f'    restart: {restart}',
    ]

    port_bindings = host_config.get('PortBindings') or {}
    if port_bindings:
        lines.append('    ports:')
        for cport_proto, host_bindings in port_bindings.items():
            cport = cport_proto.split('/')[0]
            for binding in (host_bindings or []):
                hport = binding.get('HostPort', '')
                if hport:
                    lines.append(f'      - "{hport}:{cport}"')

    binds = host_config.get('Binds') or []
    if binds:
        lines.append('    volumes:')
        for bind in binds:
            lines.append(f'      - {bind}')

    skip_prefixes = ('PATH=', 'HOME=', 'HOSTNAME=', 'TERM=', 'SHLVL=', 'PWD=')
    filtered_env = [e for e in (config.get('Env') or []) if not any(e.startswith(p) for p in skip_prefixes)]
    if filtered_env:
        lines.append('    environment:')
        for env in filtered_env:
            lines.append(f'      - {env}')

    compose_content = '\n'.join(lines) + '\n'

    if _stack_meta_path(name).exists():
        raise ValueError(f'Stack "{name}" already exists in HomeStack')

    STACKS_DIR.mkdir(parents=True, exist_ok=True)
    stack_root = _stack_root(name)
    stack_root.mkdir(parents=True, exist_ok=True)
    compose_path = stack_root / 'docker-compose.yml'
    compose_path.write_text(compose_content, encoding='utf-8')

    metadata = {
        'stack_name': name,
        'template_id': '__imported__',
        'install_path': str(stack_root),
        'placeholders': {},
        'named_volume_bindings': {},
        'compose_path': str(compose_path),
    }
    _stack_meta_path(name).write_text(json.dumps(metadata, indent=2) + '\n', encoding='utf-8')
    return {'ok': True, 'stack_name': name, 'compose_path': str(compose_path)}


def pull_and_redeploy(stack_name: str) -> Dict[str, object]:
    if not compose_available():
        raise RuntimeError('Docker Compose not available')
    pull = _compose_command_for_stack(stack_name, ['pull'])
    if pull.returncode != 0:
        raise RuntimeError(pull.stderr.strip() or pull.stdout.strip() or 'docker compose pull failed')
    up = _compose_command_for_stack(stack_name, ['up', '-d'])
    if up.returncode != 0:
        raise RuntimeError(up.stderr.strip() or up.stdout.strip() or 'docker compose up failed')
    return {
        'ok': True,
        'stack_name': stack_name,
        'message': 'Images pulled and stack redeployed',
        'runtime': get_stack_runtime_status(stack_name),
    }


def get_stack_disk_usage(stack_name: str) -> Dict[str, object]:
    metadata = _read_stack_metadata(stack_name)
    install_path = metadata.get('install_path', '')
    size_str = 'N/A'
    if install_path and Path(install_path).exists():
        try:
            result = subprocess.run(
                ['du', '-sh', '--apparent-size', install_path],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0:
                size_str = result.stdout.split()[0]
        except Exception:
            size_str = 'N/A'
    return {'stack_name': stack_name, 'install_path': install_path, 'disk_usage': size_str}


def run_stack_action(stack_name: str, action: str) -> Dict[str, object]:
    if not compose_available():
        raise RuntimeError('Docker Compose not available')
    command_map = {
        'start': ['up', '-d', '--no-recreate'],
        'stop': ['stop'],
        'restart': ['restart'],
    }
    if action not in command_map:
        raise ValueError(f'Unknown action: {action}')
    result = _compose_command_for_stack(stack_name, command_map[action])
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or f'Failed to {action} stack')
    return {
        'ok': True,
        'action': action,
        'stack_name': stack_name,
        'message': result.stdout.strip() or f'Stack {action} command completed',
        'runtime': get_stack_runtime_status(stack_name),
    }
