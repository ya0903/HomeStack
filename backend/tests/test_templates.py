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
