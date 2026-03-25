from __future__ import annotations

import io
from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse

from .auth import (
    authenticate_user,
    create_token,
    delete_user,
    get_auth_config,
    get_auth_mode,
    get_current_user,
    get_current_user_stream,
    list_users,
    register_user,
    require_admin,
    set_user_role,
)
from .docker_ops import (
    check_stack_updates,
    compose_available,
    create_backup_archive,
    create_network_resource,
    delete_health_config,
    delete_image,
    delete_network_resource,
    delete_stack,
    deploy_raw_stack,
    deploy_stack,
    docker_available,
    get_container_resources,
    get_disk_summary,
    get_stack,
    get_stack_category,
    get_stack_compose_content,
    get_stack_compose_dir,
    get_stack_disk_usage,
    get_stack_logs,
    get_stack_runtime_status,
    import_container,
    inspect_network,
    list_all_containers,
    list_categories,
    list_deployed_stacks,
    list_images,
    list_named_volumes,
    list_networks,
    pull_and_redeploy,
    restore_backup_archive,
    run_health_check,
    run_stack_action,
    save_health_config,
    set_stack_category,
    update_stack,
)
from .models import (
    NetworkCreateRequest,
    NotificationSettingsRequest,
    PluginGitInstallRequest,
    RawDeploymentRequest,
    StackActionRequest,
    StackCategoryRequest,
    StackDeploymentRequest,
    StackHealthConfigRequest,
    StackScheduleRequest,
    StackTemplateCreateRequest,
    TokenResponse,
    UserLoginRequest,
    UserRegisterRequest,
    UserRoleRequest,
)
from .resource_history import get_history as get_resource_history
from .templates import create_custom_template, get_templates
from .notifications import load_notification_settings, save_notification_settings, send_notification
from .scheduler import delete_schedule, get_schedule, list_schedules, set_schedule, start_scheduler
from .plugin_ops import (
    get_plugin_asset_path,
    install_plugin_from_git,
    install_plugin_from_zip,
    list_plugins,
    toggle_plugin,
    uninstall_plugin,
)

app = FastAPI(title='HomeStack API', version='0.4.0')


@app.on_event('startup')
def on_startup() -> None:
    start_scheduler()

app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_methods=['*'],
    allow_headers=['*'],
)


@app.get('/api/health')
def health() -> dict:
    return {
        'ok': True,
        'docker_available': docker_available(),
        'compose_available': compose_available(),
        'auth_mode': get_auth_mode(),
    }


@app.get('/api/auth/config')
def auth_config() -> dict:
    return {'ok': True, **get_auth_config()}


@app.post('/api/auth/register', response_model=TokenResponse)
def auth_register(request: UserRegisterRequest) -> TokenResponse:
    if get_auth_mode() != 'local':
        raise HTTPException(status_code=405, detail='Registration is disabled while Authelia proxy SSO is enabled')
    try:
        user = register_user(request.username, request.password)
        return TokenResponse(ok=True, token=create_token(user), user=user)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post('/api/auth/login', response_model=TokenResponse)
def auth_login(request: UserLoginRequest) -> TokenResponse:
    if get_auth_mode() != 'local':
        raise HTTPException(status_code=405, detail='Password login is disabled while Authelia proxy SSO is enabled')
    user = authenticate_user(request.username.strip().lower(), request.password)
    if user is None:
        raise HTTPException(status_code=401, detail='Invalid username or password')
    return TokenResponse(ok=True, token=create_token(user), user=user)


@app.get('/api/auth/me')
def auth_me(user=Depends(get_current_user)) -> dict:
    return {'ok': True, 'user': user.model_dump(), 'auth_mode': get_auth_mode()}


@app.get('/api/templates')
def templates(user=Depends(get_current_user)) -> list:
    return [template.model_dump() for template in get_templates()]


@app.post('/api/templates')
def create_template(request: StackTemplateCreateRequest, user=Depends(get_current_user)) -> dict:
    try:
        template = create_custom_template(request)
        return {'ok': True, 'template': template.model_dump()}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get('/api/volumes')
def volumes(user=Depends(get_current_user)) -> list:
    return [volume.model_dump() for volume in list_named_volumes()]


@app.get('/api/containers')
def containers(user=Depends(get_current_user)) -> list:
    return list_all_containers()


@app.post('/api/deploy/raw')
def deploy_raw(request: RawDeploymentRequest, user=Depends(require_admin)) -> dict:
    try:
        response = deploy_raw_stack(request)
        return response.model_dump()
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get('/api/stacks')
def stacks(user=Depends(get_current_user)) -> list:
    return list_deployed_stacks()


@app.get('/api/stacks/{stack_name}')
def stack_detail(stack_name: str, user=Depends(get_current_user)) -> dict:
    try:
        return get_stack(stack_name)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get('/api/stacks/{stack_name}/status')
def stack_status(stack_name: str, user=Depends(get_current_user)) -> dict:
    return get_stack_runtime_status(stack_name)


@app.get('/api/stacks/{stack_name}/logs')
def stack_logs(stack_name: str, user=Depends(get_current_user)) -> dict:
    return {'stack_name': stack_name, 'logs': get_stack_logs(stack_name)}


@app.post('/api/deploy')
def create_stack(request: StackDeploymentRequest, user=Depends(require_admin)) -> dict:
    try:
        response = deploy_stack(request)
        send_notification('stack_deployed', 'Stack deployed', f'{request.stack_name} deployed successfully')
        return response.model_dump()
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.put('/api/stacks/{stack_name}')
def edit_stack(stack_name: str, request: StackDeploymentRequest, user=Depends(require_admin)) -> dict:
    try:
        response = update_stack(stack_name, request)
        return response.model_dump()
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post('/api/stacks/{stack_name}/action')
def stack_action(stack_name: str, request: StackActionRequest, user=Depends(require_admin)) -> dict:
    try:
        return run_stack_action(stack_name, request.action)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post('/api/stacks/{stack_name}/pull')
def pull_stack(stack_name: str, user=Depends(require_admin)) -> dict:
    try:
        return pull_and_redeploy(stack_name)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get('/api/stacks/{stack_name}/diskusage')
def stack_disk_usage(stack_name: str, user=Depends(get_current_user)) -> dict:
    try:
        return get_stack_disk_usage(stack_name)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post('/api/containers/{container_name}/import')
def import_container_endpoint(container_name: str, user=Depends(get_current_user)) -> dict:
    try:
        return import_container(container_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.delete('/api/stacks/{stack_name}')
def remove_stack(
    stack_name: str,
    delete_data: bool = False,
    user=Depends(require_admin),
) -> dict:
    try:
        result = delete_stack(stack_name, delete_data)
        send_notification('stack_deleted', 'Stack deleted', f'{stack_name} was deleted')
        return result
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ── Plugin endpoints ──────────────────────────────────────────────────────────

@app.get('/api/plugins')
def get_plugins(user=Depends(get_current_user)) -> list:
    return list_plugins()


@app.post('/api/plugins/install/git')
def plugin_install_git(request: PluginGitInstallRequest, user=Depends(require_admin)) -> dict:
    try:
        return install_plugin_from_git(request.git_url)
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post('/api/plugins/install/zip')
async def plugin_install_zip(file: UploadFile = File(...), user=Depends(require_admin)) -> dict:
    try:
        content = await file.read()
        return install_plugin_from_zip(content)
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post('/api/plugins/{plugin_id}/toggle')
def plugin_toggle(plugin_id: str, user=Depends(require_admin)) -> dict:
    try:
        return toggle_plugin(plugin_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.delete('/api/plugins/{plugin_id}')
def plugin_uninstall(plugin_id: str, user=Depends(require_admin)) -> dict:
    try:
        uninstall_plugin(plugin_id)
        return {'ok': True}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get('/api/plugins/{plugin_id}/assets/{filename}')
def plugin_asset(plugin_id: str, filename: str, user=Depends(get_current_user)):
    try:
        path = get_plugin_asset_path(plugin_id, filename)
        return FileResponse(str(path))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


# ── Categories ────────────────────────────────────────────────────────────────

@app.get('/api/categories')
def categories(user=Depends(get_current_user)) -> list:
    return list_categories()


@app.get('/api/categories/map')
def categories_map(user=Depends(get_current_user)) -> dict:
    from .docker_ops import _load_categories
    return _load_categories()


@app.put('/api/stacks/{stack_name}/category')
def set_category(stack_name: str, request: StackCategoryRequest, user=Depends(require_admin)) -> dict:
    set_stack_category(stack_name, request.category)
    return {'ok': True, 'stack_name': stack_name, 'category': request.category}


# ── Health checks ─────────────────────────────────────────────────────────────

@app.get('/api/stacks/{stack_name}/health')
def stack_health(stack_name: str, user=Depends(get_current_user)) -> dict:
    return run_health_check(stack_name)


@app.put('/api/stacks/{stack_name}/health')
def set_stack_health(stack_name: str, request: StackHealthConfigRequest, user=Depends(require_admin)) -> dict:
    save_health_config(stack_name, request.url, request.expected_status)
    return {'ok': True, 'stack_name': stack_name, 'url': request.url}


@app.delete('/api/stacks/{stack_name}/health')
def remove_stack_health(stack_name: str, user=Depends(require_admin)) -> dict:
    delete_health_config(stack_name)
    return {'ok': True}


# ── Resource usage ────────────────────────────────────────────────────────────

@app.get('/api/resources')
def container_resources(user=Depends(get_current_user)) -> list:
    return get_container_resources()


# ── Schedules ─────────────────────────────────────────────────────────────────

@app.get('/api/schedules')
def schedules(user=Depends(get_current_user)) -> dict:
    return list_schedules()


@app.put('/api/stacks/{stack_name}/schedule')
def set_stack_schedule(stack_name: str, request: StackScheduleRequest, user=Depends(require_admin)) -> dict:
    try:
        result = set_schedule(stack_name, request.cron, request.enabled)
        return {'ok': True, 'stack_name': stack_name, **result}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.delete('/api/stacks/{stack_name}/schedule')
def remove_stack_schedule(stack_name: str, user=Depends(require_admin)) -> dict:
    delete_schedule(stack_name)
    return {'ok': True}


@app.get('/api/stacks/{stack_name}/schedule')
def get_stack_schedule_endpoint(stack_name: str, user=Depends(get_current_user)) -> dict:
    schedule = get_schedule(stack_name)
    return schedule or {}


# ── Notifications ─────────────────────────────────────────────────────────────

@app.get('/api/settings/notifications')
def get_notifications(user=Depends(get_current_user)) -> dict:
    return load_notification_settings()


@app.put('/api/settings/notifications')
def update_notifications(request: NotificationSettingsRequest, user=Depends(require_admin)) -> dict:
    save_notification_settings(request.model_dump())
    return {'ok': True}


@app.post('/api/settings/notifications/test')
def test_notification(user=Depends(get_current_user)) -> dict:
    send_notification('test', 'HomeStack test', 'Your notification settings are working.')
    return {'ok': True, 'message': 'Test notification sent'}


# ── Backup / Restore ──────────────────────────────────────────────────────────

@app.get('/api/backup')
def backup(user=Depends(require_admin)):
    data = create_backup_archive()
    return StreamingResponse(
        io.BytesIO(data),
        media_type='application/gzip',
        headers={'Content-Disposition': 'attachment; filename="homestack-backup.tar.gz"'},
    )


@app.post('/api/restore')
async def restore(file: UploadFile = File(...), user=Depends(require_admin)) -> dict:
    try:
        content = await file.read()
        restore_backup_archive(content)
        return {'ok': True, 'message': 'Backup restored successfully. Restart HomeStack to apply.'}
    except (ValueError, Exception) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# ── Image management ───────────────────────────────────────────────────────────

@app.get('/api/images')
def images(user=Depends(get_current_user)) -> list:
    return list_images()


@app.delete('/api/images')
def remove_image(ref: str, user=Depends(require_admin)) -> dict:
    try:
        return delete_image(ref)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ── Update checks ──────────────────────────────────────────────────────────────

@app.get('/api/stacks/{stack_name}/update-check')
def stack_update_check(stack_name: str, user=Depends(get_current_user)) -> dict:
    try:
        return check_stack_updates(stack_name)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


# ── Resource history ───────────────────────────────────────────────────────────

@app.get('/api/resources/history')
def resource_history(user=Depends(get_current_user)) -> list:
    return get_resource_history()


# ── Live log streaming (SSE) ───────────────────────────────────────────────────

@app.get('/api/stacks/{stack_name}/logs/stream')
async def stream_stack_logs(stack_name: str, user=Depends(get_current_user_stream)):
    import asyncio
    stack_dir = get_stack_compose_dir(stack_name)
    compose_file = stack_dir / 'docker-compose.yml'
    if not compose_file.exists():
        raise HTTPException(status_code=404, detail=f'Stack {stack_name!r} not found')

    async def generate():
        proc = await asyncio.create_subprocess_exec(
            'docker', 'compose', '-f', str(compose_file), 'logs', '-f', '--tail=100', '--no-color',
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        try:
            while True:
                try:
                    line = await asyncio.wait_for(proc.stdout.readline(), timeout=25.0)
                except asyncio.TimeoutError:
                    yield 'data: [heartbeat]\n\n'
                    continue
                if not line:
                    break
                text = line.decode('utf-8', errors='replace').rstrip()
                yield f'data: {text}\n\n'
        finally:
            try:
                proc.kill()
                await proc.wait()
            except Exception:
                pass

    return StreamingResponse(
        generate(),
        media_type='text/event-stream',
        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'},
    )


# ── User management ────────────────────────────────────────────────────────────

@app.get('/api/users')
def get_users(user=Depends(require_admin)) -> list:
    return list_users()


@app.put('/api/users/{username}/role')
def set_role(username: str, request: UserRoleRequest, user=Depends(require_admin)) -> dict:
    try:
        set_user_role(username, request.role)
        return {'ok': True, 'username': username, 'role': request.role}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.delete('/api/users/{username}')
def remove_user(username: str, user=Depends(require_admin)) -> dict:
    try:
        delete_user(username, user.username)
        return {'ok': True}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# ── Stack compose content ──────────────────────────────────────────────────────

@app.get('/api/stacks/{stack_name}/compose')
def stack_compose_content(stack_name: str, user=Depends(get_current_user)) -> dict:
    try:
        return {'stack_name': stack_name, 'content': get_stack_compose_content(stack_name)}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


# ── Network management ─────────────────────────────────────────────────────────

@app.get('/api/networks')
def networks_list(user=Depends(get_current_user)) -> list:
    return list_networks()


@app.get('/api/networks/{network_id}')
def network_detail(network_id: str, user=Depends(get_current_user)) -> dict:
    try:
        return inspect_network(network_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post('/api/networks')
def create_network(request: NetworkCreateRequest, user=Depends(require_admin)) -> dict:
    try:
        return create_network_resource(request.name, request.driver)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.delete('/api/networks/{network_id}')
def remove_network(network_id: str, user=Depends(require_admin)) -> dict:
    try:
        return delete_network_resource(network_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ── Disk usage ─────────────────────────────────────────────────────────────────

@app.get('/api/disk')
def disk_usage(user=Depends(get_current_user)) -> dict:
    return get_disk_summary()
