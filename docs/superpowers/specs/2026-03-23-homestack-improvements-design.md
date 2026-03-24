# HomeStack Improvements Design

**Date:** 2026-03-23
**Scope:** Feature completeness (B) + Code quality & architecture (C)
**Approach:** Incremental layering — template engine first, then docker_ops, then frontend, then tests

---

## 1. Jinja2 Template Engine

### Problem
`_safe_replace` in `docker_ops.py` uses naive `str.replace` with `{{KEY}}` syntax. Missing placeholders silently leave `{{KEY}}` in rendered output. All 11 built-in templates are hardcoded as Python objects in `templates.py`, requiring code changes to add new templates.

Note: `jinja2==3.1.6` is already present in `requirements.txt`. No change needed there.

### Solution

**`docker_ops.py`**
- Replace `_safe_replace` with `jinja2.Environment(undefined=StrictUndefined).from_string(text).render(**placeholders)`
- Missing placeholders raise `UndefinedError` immediately with a clear message
- Auto-escaping must remain OFF (the default for non-HTML Jinja2 environments) — do not enable it
- All placeholder values are passed as plain Python strings; Jinja2 will not mutate them
- The existing `.tpl` files use `{{KEY}}` (no spaces). Jinja2 accepts this without modification — do not change `.tpl` file syntax unless a template breaks in testing.
- Extra context keys (e.g. `INSTALL_PATH` not referenced in a template) are silently ignored by Jinja2 — this is correct behaviour.

**`templates/*/template.json`** (new sidecar files per template directory)
- Each template directory gets a `template.json` with these fields: `id`, `name`, `description`, `required_placeholders`, `default_install_subdir`
- `compose_template_path` is NOT stored in `template.json`. The scanner derives it by convention: `TEMPLATES_DIR / id / 'docker-compose.yml.tpl'`
- `source` is NOT stored in `template.json`. The `StackTemplate` model already defaults `source` to `'builtin'`, so omitting it from the JSON and from the scanner constructor call is sufficient.

**`templates.py`**
- `get_builtin_templates()` becomes a directory scan: find all `templates/*/template.json`, load each, reconstruct `compose_template_path` as `TEMPLATES_DIR / id / 'docker-compose.yml.tpl'`, construct `StackTemplate` without passing `source` (model default handles it)
- `get_custom_templates()` is left completely unchanged — it already has a working storage format in `data/custom_templates/*.json`. Do not unify these two code paths.
- Adding a new built-in template = drop a folder with `template.json` + `docker-compose.yml.tpl`, no Python changes required

**Implementation atomicity:** The `get_builtin_templates()` rewrite and the creation of all 11 `template.json` files must be done together in a single step. Rewriting the function before the JSON files exist will crash the application.

**`frontend/app.js` — `templateExample()`**
- The hardcoded example uses `{{STACK_NAME}}` and `{{NC_CONFIG_PATH}}` — valid Jinja2 syntax without modification. Leave as-is.

### Result
Templates are self-describing, rendering fails loudly on bad input, and the template library is extensible without touching Python.

---

## 2. `docker_ops.py` Improvements

### Problem
- `list_named_volumes` calls `docker volume inspect` in a loop (N+1 subprocess calls)
- No delete/undeploy functionality
- `update_stack` re-deploys on top of old container state without tearing down first
- `run_stack_action` relies solely on Pydantic for action validation; the internal function has no guard if called directly from Python

### Solution

**Fix N+1 volume inspection**
- Call `docker volume ls --format {{json .}}` to get all volume names (1 subprocess)
- If there are zero volumes, return `[]` immediately — do NOT call `docker volume inspect` with no arguments (that errors)
- If there are one or more volumes, call `docker volume inspect name1 name2 ...` once (2nd subprocess), parse the returned JSON array
- Total: at most 2 subprocess calls for any number of volumes; 1 call for zero volumes

**Add `delete_stack(stack_name: str, delete_data: bool)` function**

Deletion sequence:
1. Read `data/stacks/{stack_name}/stack.json` — raise `FileNotFoundError` if missing
2. Attempt `docker compose down`: call `_compose_command_for_stack(stack_name, ['down'])`. If the compose file is missing (`FileNotFoundError` from `_compose_command_for_stack`), skip this step and proceed — the stack isn't running. If the compose file exists but `compose down` returns non-zero, raise `RuntimeError`.
3. Delete `data/stacks/{stack_name}/` (compose file, `.env`, `stack.json`)
4. If `delete_data=True`: delete `install_path` (top-level field in `stack.json`) AND each value in `stack.json["placeholders"]` that starts with `/`. Values not starting with `/` (e.g. named volume references) are skipped. Shared paths are the user's responsibility — HomeStack does not check whether another stack references the same directory.
5. Return `{ "ok": True, "deleted": [list_of_paths_removed] }` (plain dict, no new Pydantic model needed)

**New endpoint in `main.py`**
- `DELETE /api/stacks/{stack_name}?delete_data=false`
- Add `delete_stack` to the `from .docker_ops import (...)` block in `main.py`
- Error handling follows the existing pattern:
  - `FileNotFoundError` (stack metadata not found) → HTTP 404
  - `RuntimeError` (compose down failed) → HTTP 500
- Returns `{ ok: true, deleted: [...paths] }` on success

**`run_stack_action` guard**
- Add `if action not in command_map: raise ValueError(f"Unknown action: {action}")` before the dict lookup
- This is a defensive internal API guard for callers bypassing HTTP/Pydantic (e.g. direct Python calls in tests)

**`update_stack` safe teardown**
Proposed order to avoid leaving the stack undeployed if file-writing fails:
1. Validate and write new files (call `_write_stack_files`) — if this fails, old containers remain running (safe)
2. Run `docker compose down` — if it returns non-zero, raise `RuntimeError` (leave new file on disk, old containers still running — acceptable for a home lab tool)
3. Run `docker compose up -d`

---

## 3. Frontend Improvements

### Problem
- Stack cards built with `innerHTML` and unescaped user data (XSS)
- Inline `onclick` handlers embed stack names as JS string literals — exploitable if name contains `'` or `">`
- No delete UI
- API base URL detection uses fragile `includes('5500')` / `includes('8080')` check
- Stack action results shown as raw JSON in `<pre>` elements
- `window.editStack`, `window.stackAction`, `window.viewLogs` are global functions (anti-pattern)

### Solution

**Delete button + confirm dialog**
- Each stack card gets a "Delete" button
- Click triggers two sequential `confirm()` calls (no custom modal state required):
  1. `confirm("Delete stack [name]? This will stop its containers.")` — Cancel aborts
  2. `confirm("Also delete data directories from disk? This cannot be undone.")` — OK = `delete_data=true`, Cancel = `delete_data=false`
- Calls `DELETE /api/stacks/{name}?delete_data=true/false`, then refreshes stack list on success

**XSS fix — `escapeHtml` + data attributes**
- Add `escapeHtml(str)` utility that replaces `&`, `<`, `>`, `"`, `'` with HTML entities
- All user-sourced values passed into `innerHTML` must go through `escapeHtml()`
- All action buttons (start, stop, restart, logs, edit, delete) must use `data-stack-name="${escapeHtml(name)}"` and `data-action="..."` attributes, NOT inline `onclick` attributes with embedded stack names. This applies to `editStack` as well — it is also converted to data-attribute + delegated listener
- A single delegated listener on `#stacksList` reads `dataset.action` and `dataset.stackName` and dispatches to the appropriate handler function
- `editStack`, `stackAction`, `viewLogs` are all module-level named functions (not on `window`). `editStack` calls `switchView('deploy')` from within the delegated handler

**Fix API base URL**
- Replace the `includes('5500')` / `includes('8080')` detection with `const API_BASE = ''` (empty string = same origin)
- Leave a comment: `// For local dev with separate servers, set API_BASE = 'http://localhost:8000'`

**Action feedback**
- Show human-readable message as primary text (e.g. "Stack restarted successfully")
- Wrap raw JSON in `<details><summary>Details</summary><pre>...</pre></details>`

---

## 4. Tests

### Problem
Zero tests exist. No `tests/` directory, no test dependencies.

### Dependencies
Test dependencies go in `backend/requirements-dev.txt` (new file, NOT added to the production `requirements.txt`):
```
pytest
httpx
pytest-mock
```

### Structure

```
backend/tests/
  conftest.py          # shared fixtures: tmp dirs, test app client, mock env vars
  test_auth.py         # unit tests for auth.py
  test_templates.py    # unit tests for template discovery + Jinja2 rendering
  test_docker_ops.py   # unit tests with mocked subprocess
  test_api.py          # integration tests via FastAPI TestClient
```

### Coverage

**`test_auth.py`**
- Register user succeeds, creates admin role for first user
- Duplicate username raises ValueError
- Login with correct credentials returns token
- Login with bad password returns None
- Token validates and returns correct user
- Expired token is rejected

**`test_templates.py`**
- Built-in template discovery scans real `templates/` dir and returns exactly these IDs: `{'jellyfin', 'immich', 'komga', 'nextcloud', 'vaultwarden', 'sonarr', 'radarr', 'prowlarr', 'qbittorrent', 'bazarr', 'arr-stack'}` (assert set equality, not just count)
- Jinja2 rendering with all placeholders provided succeeds
- Jinja2 rendering with a missing placeholder raises `UndefinedError` (not silently passes through `{{KEY}}`)
- Custom template creation writes JSON and `.tpl` file
- Duplicate template id raises ValueError
- `get_custom_templates()` reads from `data/custom_templates/` independently of the builtin scan

**`test_docker_ops.py`** (subprocess mocked via `pytest-mock`)
- Deploy writes compose file and metadata to correct paths
- Jinja2 renders placeholder values correctly into compose file content
- Delete removes stack dir; with `delete_data=True` also removes paths starting with `/` in placeholders
- Delete raises `FileNotFoundError` for unknown stack (missing `stack.json`)
- Delete proceeds without error when compose file is missing (skips `compose down`)
- Volume list with N>0 volumes calls subprocess exactly twice (not N+1)
- Volume list with 0 volumes calls subprocess exactly once (no inspect call)
- `run_stack_action` with invalid action string raises `ValueError` when called directly (bypassing Pydantic)
- `update_stack` writes files before running `compose down` (assert write happens first in call order)

**`test_api.py`** (FastAPI TestClient)
- `GET /api/health` returns dict with keys `ok`, `docker_available`, `compose_available`, `auth_mode`
- Register + login flow returns token
- Authenticated requests succeed; unauthenticated return 401
- `GET /api/templates` returns all 11 built-in templates
- `POST /api/deploy` creates stack files (mocked compose)
- `DELETE /api/stacks/{name}` returns 404 for unknown stack
- `DELETE /api/stacks/{name}` returns 200 and removes stack on success
- `DELETE /api/stacks/{name}?delete_data=true` removes stack and data paths
- `POST /api/stacks/{name}/action` with valid action succeeds (mocked compose)
- `GET /api/stacks/{name}/logs` returns dict with `logs` key

---

## Implementation Order

1. Add `template.json` sidecars to all 11 `templates/*/` directories AND rewrite `get_builtin_templates()` in `templates.py` to directory scan (these two sub-steps must be done atomically in the same commit)
2. Replace `_safe_replace` with Jinja2 in `docker_ops.py`
3. Fix N+1 in `list_named_volumes` (with zero-volume guard)
4. Add `delete_stack`; fix `update_stack` teardown order; add internal guard to `run_stack_action`
5. Add `DELETE /api/stacks/{stack_name}` endpoint and `delete_stack` import to `main.py`
6. Update frontend: `escapeHtml`, data-attribute delegation for all action buttons including `editStack`, delete button + two-confirm dialog, API base fix, action feedback with `<details>`
7. Create `backend/requirements-dev.txt` with test dependencies
8. Add `backend/tests/` with conftest and all four test files
9. Run `pytest`, fix failures
