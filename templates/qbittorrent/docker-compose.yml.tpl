services:
  qbittorrent:
    image: lscr.io/linuxserver/qbittorrent:latest
    container_name: {{STACK_NAME}}
    restart: unless-stopped
    ports:
      - "8081:8080"
      - "6881:6881"
      - "6881:6881/udp"
    environment:
      - PUID=1000
      - PGID=1000
      - TZ=Europe/London
      - WEBUI_PORT=8080
    volumes:
      - {{QBITTORRENT_CONFIG_PATH}}:/config
      - {{QBITTORRENT_DOWNLOADS_PATH}}:/downloads
