services:
  immich-server:
    image: ghcr.io/immich-app/immich-server:release
    container_name: {{STACK_NAME}}-server
    command: ["start.sh", "immich"]
    volumes:
      - {{IMMICH_UPLOAD_PATH}}:/usr/src/app/upload
    env_file:
      - .env
    ports:
      - "2283:2283"
    depends_on:
      - immich-db
    restart: unless-stopped

  immich-db:
    image: tensorchord/pgvecto-rs:pg14-v0.2.0
    container_name: {{STACK_NAME}}-db
    environment:
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
      POSTGRES_DB: immich
    volumes:
      - {{IMMICH_DB_DATA_PATH}}:/var/lib/postgresql/data
    restart: unless-stopped
