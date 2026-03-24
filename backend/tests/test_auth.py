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
