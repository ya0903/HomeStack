from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import Header, HTTPException, Request

from .models import UserResponse

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / 'data'
USERS_FILE = DATA_DIR / 'users.json'
SECRET_FILE = DATA_DIR / 'secret.key'
TOKEN_TTL_SECONDS = 60 * 60 * 24 * 7


def get_auth_mode() -> str:
    mode = os.getenv('AUTH_MODE', 'local').strip().lower()
    return mode if mode in {'local', 'authelia_proxy'} else 'local'


def get_authelia_login_url() -> str:
    return os.getenv('AUTHELIA_LOGIN_URL', '/').strip() or '/'


def get_authelia_header_name() -> str:
    return os.getenv('AUTHELIA_USER_HEADER', 'Remote-User').strip() or 'Remote-User'


def _normalise_header_lookup(name: str) -> str:
    return name.lower().replace('_', '-')


def _ensure_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def _load_secret() -> bytes:
    _ensure_data_dir()
    if not SECRET_FILE.exists():
        SECRET_FILE.write_text(secrets.token_hex(32), encoding='utf-8')
    return SECRET_FILE.read_text(encoding='utf-8').strip().encode('utf-8')


def _load_users() -> List[Dict[str, str]]:
    _ensure_data_dir()
    if not USERS_FILE.exists():
        USERS_FILE.write_text('[]\n', encoding='utf-8')
    return json.loads(USERS_FILE.read_text(encoding='utf-8'))


def _save_users(users: List[Dict[str, str]]) -> None:
    USERS_FILE.write_text(json.dumps(users, indent=2) + '\n', encoding='utf-8')


def _hash_password(password: str, salt: str) -> str:
    return hashlib.sha256(f'{salt}:{password}'.encode('utf-8')).hexdigest()


def register_user(username: str, password: str) -> UserResponse:
    if get_auth_mode() != 'local':
        raise ValueError('Local registration is disabled while Authelia proxy SSO is enabled')
    users = _load_users()
    if any(user['username'] == username for user in users):
        raise ValueError('That username already exists')
    salt = secrets.token_hex(16)
    role = 'admin' if not users else 'user'
    users.append(
        {
            'username': username,
            'password_salt': salt,
            'password_hash': _hash_password(password, salt),
            'role': role,
        }
    )
    _save_users(users)
    return UserResponse(username=username, role=role)


def authenticate_user(username: str, password: str) -> Optional[UserResponse]:
    if get_auth_mode() != 'local':
        return None
    users = _load_users()
    for user in users:
        if user['username'] != username:
            continue
        if hmac.compare_digest(user['password_hash'], _hash_password(password, user['password_salt'])):
            return UserResponse(username=user['username'], role=user['role'])
    return None


def create_token(user: UserResponse) -> str:
    payload = {
        'sub': user.username,
        'role': user.role,
        'exp': int(time.time()) + TOKEN_TTL_SECONDS,
    }
    payload_bytes = json.dumps(payload, separators=(',', ':')).encode('utf-8')
    payload_b64 = base64.urlsafe_b64encode(payload_bytes).decode('utf-8').rstrip('=')
    signature = hmac.new(_load_secret(), payload_b64.encode('utf-8'), hashlib.sha256).hexdigest()
    return f'{payload_b64}.{signature}'


def decode_token(token: str) -> UserResponse:
    try:
        payload_b64, signature = token.split('.', 1)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail='Invalid token format') from exc
    expected = hmac.new(_load_secret(), payload_b64.encode('utf-8'), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        raise HTTPException(status_code=401, detail='Invalid token signature')
    padded = payload_b64 + '=' * (-len(payload_b64) % 4)
    payload = json.loads(base64.urlsafe_b64decode(padded.encode('utf-8')).decode('utf-8'))
    if int(payload.get('exp', 0)) < int(time.time()):
        raise HTTPException(status_code=401, detail='Token expired')
    return UserResponse(username=payload['sub'], role=payload['role'])


def _authelia_user_from_request(request: Request) -> UserResponse:
    header_name = get_authelia_header_name()
    header_value = request.headers.get(header_name)
    if header_value is None:
        header_value = request.headers.get(_normalise_header_lookup(header_name))
    username = (header_value or '').strip().lower()
    if not username:
        raise HTTPException(status_code=401, detail='Authelia authenticated user header missing')
    return UserResponse(username=username, role='admin')


def get_auth_config() -> Dict[str, object]:
    return {
        'mode': get_auth_mode(),
        'login_url': get_authelia_login_url(),
        'authelia_user_header': get_authelia_header_name(),
        'local_auth_enabled': get_auth_mode() == 'local',
    }


def get_current_user(request: Request, authorization: str | None = Header(default=None)) -> UserResponse:
    if get_auth_mode() == 'authelia_proxy':
        return _authelia_user_from_request(request)
    if not authorization or not authorization.startswith('Bearer '):
        raise HTTPException(status_code=401, detail='Missing bearer token')
    token = authorization.split(' ', 1)[1].strip()
    return decode_token(token)
