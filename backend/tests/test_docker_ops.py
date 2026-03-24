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
