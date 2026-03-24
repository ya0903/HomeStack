services:
  sonarr:
    image: lscr.io/linuxserver/sonarr:latest
    container_name: {{STACK_NAME}}
    restart: unless-stopped
    ports:
      - "8989:8989"
    environment:
      - PUID=1000
      - PGID=1000
      - TZ=Europe/London
    volumes:
      - {{SONARR_CONFIG_PATH}}:/config
      - {{SONARR_TV_PATH}}:/tv
      - {{SONARR_DOWNLOADS_PATH}}:/downloads
