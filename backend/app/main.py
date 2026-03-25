from __future__ import annotations

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .auth import (
    authenticate_user,
    create_token,
    get_auth_config,
    get_auth_mode,
    get_current_user,
    register_user,
)
from .docker_ops import (
    compose_available,
    delete_stack,
    deploy_raw_stack,
    deploy_stack,
    docker_available,
    get_stack,
    get_stack_disk_usage,
    get_stack_logs,
    get_stack_runtime_status,
    import_container,
    list_all_containers,
    list_deployed_stacks,
    list_named_volumes,
    pull_and_redeploy,
    run_stack_action,
    update_stack,
)
from .models import (
    RawDeploymentRequest,
    StackActionRequest,
    StackDeploymentRequest,
    StackTemplateCreateRequest,
    TokenResponse,
    UserLoginRequest,
    UserRegisterRequest,
)
from .templates import create_custom_template, get_templates

app = FastAPI(title='HomeStack API', version='0.3.0')

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
def deploy_raw(request: RawDeploymentRequest, user=Depends(get_current_user)) -> dict:
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
def create_stack(request: StackDeploymentRequest, user=Depends(get_current_user)) -> dict:
    try:
        response = deploy_stack(request)
        return response.model_dump()
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.put('/api/stacks/{stack_name}')
def edit_stack(stack_name: str, request: StackDeploymentRequest, user=Depends(get_current_user)) -> dict:
    try:
        response = update_stack(stack_name, request)
        return response.model_dump()
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post('/api/stacks/{stack_name}/action')
def stack_action(stack_name: str, request: StackActionRequest, user=Depends(get_current_user)) -> dict:
    try:
        return run_stack_action(stack_name, request.action)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post('/api/stacks/{stack_name}/pull')
def pull_stack(stack_name: str, user=Depends(get_current_user)) -> dict:
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
    user=Depends(get_current_user),
) -> dict:
    try:
        return delete_stack(stack_name, delete_data)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
