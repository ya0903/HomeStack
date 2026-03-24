services:
  radarr:
    image: lscr.io/linuxserver/radarr:latest
    container_name: {{STACK_NAME}}
    restart: unless-stopped
    ports:
      - "7878:7878"
    environment:
      - PUID=1000
      - PGID=1000
      - TZ=Europe/London
    volumes:
      - {{RADARR_CONFIG_PATH}}:/config
      - {{RADARR_MOVIES_PATH}}:/movies
      - {{RADARR_DOWNLOADS_PATH}}:/downloads
