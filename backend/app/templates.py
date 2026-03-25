from __future__ import annotations

import json
import os
from pathlib import Path
from typing import List

from .models import StackTemplate, StackTemplateCreateRequest

ROOT = Path(os.environ.get('APP_ROOT', str(Path(__file__).resolve().parents[2])))
TEMPLATES_DIR = ROOT / 'templates'
CUSTOM_TEMPLATES_DIR = ROOT / 'data' / 'custom_templates'


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


def get_custom_templates() -> List[StackTemplate]:
    CUSTOM_TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
    templates: List[StackTemplate] = []
    for file in sorted(CUSTOM_TEMPLATES_DIR.glob('*.json')):
        try:
            raw = json.loads(file.read_text(encoding='utf-8'))
            templates.append(StackTemplate(**raw))
        except Exception:
            continue
    return templates


def get_templates() -> List[StackTemplate]:
    return get_builtin_templates() + get_custom_templates()


def get_template_by_id(template_id: str) -> StackTemplate | None:
    for template in get_templates():
        if template.id == template_id:
            return template
    return None


def create_custom_template(request: StackTemplateCreateRequest) -> StackTemplate:
    CUSTOM_TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
    if get_template_by_id(request.id) is not None:
        raise ValueError(f'A template with id {request.id} already exists')

    compose_dir = CUSTOM_TEMPLATES_DIR / request.id
    compose_dir.mkdir(parents=True, exist_ok=True)
    compose_path = compose_dir / 'docker-compose.yml.tpl'
    compose_path.write_text(request.compose_template_text.rstrip() + '\n', encoding='utf-8')

    template = StackTemplate(
        id=request.id,
        name=request.name,
        description=request.description,
        compose_template_path=str(compose_path),
        default_install_subdir=request.default_install_subdir.strip('/'),
        required_placeholders=request.required_placeholders,
        source='custom',
    )
    metadata_path = CUSTOM_TEMPLATES_DIR / f'{request.id}.json'
    metadata_path.write_text(json.dumps(template.model_dump(), indent=2) + '\n', encoding='utf-8')
    return template
