from __future__ import annotations

from typing import Dict, List, Optional
from pydantic import BaseModel, Field, field_validator


class VolumeOption(BaseModel):
    id: str
    name: str
    driver: Optional[str] = None
    mountpoint: Optional[str] = None


class StackTemplate(BaseModel):
    id: str
    name: str
    description: str
    compose_template_path: str
    default_install_subdir: str
    required_placeholders: List[str] = Field(default_factory=list)
    source: str = 'builtin'


class StackTemplateCreateRequest(BaseModel):
    id: str
    name: str
    description: str = ''
    default_install_subdir: str
    required_placeholders: List[str] = Field(default_factory=list)
    compose_template_text: str

    @field_validator('id')
    @classmethod
    def validate_template_id(cls, value: str) -> str:
        value = value.strip().lower()
        if not value:
            raise ValueError('Template id cannot be empty')
        allowed = set('abcdefghijklmnopqrstuvwxyz0123456789-_')
        if any(ch not in allowed for ch in value):
            raise ValueError('Template id may only contain lowercase letters, numbers, hyphens and underscores')
        return value


class StackDeploymentRequest(BaseModel):
    template_id: str
    stack_name: str
    install_path: str
    placeholders: Dict[str, str] = Field(default_factory=dict)
    named_volume_bindings: Dict[str, str] = Field(default_factory=dict)

    @field_validator('stack_name')
    @classmethod
    def validate_stack_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError('stack_name cannot be empty')
        invalid = set('/\\ ')
        if any(ch in invalid for ch in value):
            raise ValueError('stack_name must not contain spaces or path separators')
        return value

    @field_validator('install_path')
    @classmethod
    def validate_install_path(cls, value: str) -> str:
        value = value.strip()
        if not value.startswith('/'):
            raise ValueError('install_path must be an absolute Linux path')
        return value


class StackDeploymentResponse(BaseModel):
    ok: bool
    stack_name: str
    install_path: str
    compose_path: str
    message: str


class StackActionRequest(BaseModel):
    action: str

    @field_validator('action')
    @classmethod
    def validate_action(cls, value: str) -> str:
        value = value.strip().lower()
        if value not in {'start', 'stop', 'restart'}:
            raise ValueError('Action must be start, stop or restart')
        return value


class UserRegisterRequest(BaseModel):
    username: str
    password: str

    @field_validator('username')
    @classmethod
    def validate_username(cls, value: str) -> str:
        value = value.strip().lower()
        if not value:
            raise ValueError('Username cannot be empty')
        allowed = set('abcdefghijklmnopqrstuvwxyz0123456789-_.')
        if any(ch not in allowed for ch in value):
            raise ValueError('Username contains unsupported characters')
        return value

    @field_validator('password')
    @classmethod
    def validate_password(cls, value: str) -> str:
        if len(value) < 8:
            raise ValueError('Password must be at least 8 characters long')
        return value


class UserLoginRequest(BaseModel):
    username: str
    password: str


class UserResponse(BaseModel):
    username: str
    role: str


class TokenResponse(BaseModel):
    ok: bool
    token: str
    user: UserResponse
