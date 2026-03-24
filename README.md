# HomeStack *UNTESTED*

HomeStack is a Linux compatible web app for deploying and managing Docker Compose stacks with per stack install paths, reusable Docker volume selection, local auth or Authelia SSO, runtime controls and a built in template builder.

## Included features

- Local auth with user accounts and bearer token login
- Optional Authelia SSO mode through a reverse proxy
- Edit existing stack definitions from the UI
- Container logs and live runtime status per stack
- Start, stop and restart controls
- Template builder in the UI for custom Docker Compose templates
- Linux friendly path validation and stack file generation

## Built in templates

- Jellyfin
- Immich
- Komga
- Nextcloud
- Vaultwarden
- Arr Stack Combined
- Sonarr
- Radarr
- Prowlarr
- qBittorrent
- Bazarr
- Any custom templates you create from the Template builder view

## What it does

- Lists built in and custom stack templates
- Lets you pick an absolute Linux install path for each stack
- Lets you choose placeholder paths for config, cache, uploads and other bind mounts
- Detects existing Docker named volumes and lets you map them into a deployment
- Generates a per stack `docker-compose.yml` and `stack.json`
- Runs `docker compose up -d` automatically when Docker Compose is available
- Reads `docker compose ps` and `docker compose logs` for runtime insight

## Linux compatibility

This project is designed around Linux style absolute paths and uses the Docker CLI on the host. It expects:

- Docker installed
- Docker Compose plugin installed, `docker compose`
- The backend to have access to `/var/run/docker.sock`

## Quick start

```bash
cd homestack
docker compose up -d --build
```

Then open:

- Frontend: `http://localhost:8080`
- API health: `http://localhost:8000/api/health`

## Local auth mode

By default the app uses local auth.

When you first open the UI there will be no accounts. Create the first account from the register tab. The first account becomes `admin`.

## Authelia SSO mode

This app can also trust Authelia through a reverse proxy. Set the following environment variables for the backend service:

```env
AUTH_MODE=authelia_proxy
AUTHELIA_LOGIN_URL=https://your-domain.example
AUTHELIA_USER_HEADER=Remote-User
```

An example Caddy configuration is included at `examples/caddy/Caddyfile.authelia`.

## Suggested Git ignore

The project includes a sensible `.gitignore` for Python, Docker and generated stack data. Keep generated runtime data and secrets out of Git.

## Notes

This is an MVP foundation for a larger homelab control plane. Before exposing it publicly you should add stronger session handling, HTTPS everywhere, rate limiting and role based access control.
