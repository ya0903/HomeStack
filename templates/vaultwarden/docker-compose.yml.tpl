services:
  vaultwarden:
    image: vaultwarden/server:latest
    container_name: {{STACK_NAME}}
    restart: unless-stopped
    ports:
      - "8222:80"
    environment:
      - TZ=Europe/London
      - SIGNUPS_ALLOWED=false
    volumes:
      - {{VW_DATA_PATH}}:/data
