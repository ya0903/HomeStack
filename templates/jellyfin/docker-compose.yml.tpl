services:
  jellyfin:
    image: jellyfin/jellyfin:latest
    container_name: {{STACK_NAME}}
    network_mode: host
    environment:
      - TZ=Europe/London
    volumes:
      - {{JF_CONFIG_PATH}}:/config
      - {{JF_CACHE_PATH}}:/cache
      - {{JF_MEDIA_PATH}}:/media
    restart: unless-stopped
