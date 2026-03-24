services:
  qbittorrent:
    image: lscr.io/linuxserver/qbittorrent:latest
    container_name: {{STACK_NAME}}-qbittorrent
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
      - {{ARR_CONFIG_ROOT}}/qbittorrent:/config
      - {{ARR_DOWNLOADS_PATH}}:/downloads

  prowlarr:
    image: lscr.io/linuxserver/prowlarr:latest
    container_name: {{STACK_NAME}}-prowlarr
    restart: unless-stopped
    ports:
      - "9696:9696"
    environment:
      - PUID=1000
      - PGID=1000
      - TZ=Europe/London
    volumes:
      - {{ARR_CONFIG_ROOT}}/prowlarr:/config

  sonarr:
    image: lscr.io/linuxserver/sonarr:latest
    container_name: {{STACK_NAME}}-sonarr
    restart: unless-stopped
    ports:
      - "8989:8989"
    environment:
      - PUID=1000
      - PGID=1000
      - TZ=Europe/London
    volumes:
      - {{ARR_CONFIG_ROOT}}/sonarr:/config
      - {{ARR_TV_PATH}}:/tv
      - {{ARR_DOWNLOADS_PATH}}:/downloads

  radarr:
    image: lscr.io/linuxserver/radarr:latest
    container_name: {{STACK_NAME}}-radarr
    restart: unless-stopped
    ports:
      - "7878:7878"
    environment:
      - PUID=1000
      - PGID=1000
      - TZ=Europe/London
    volumes:
      - {{ARR_CONFIG_ROOT}}/radarr:/config
      - {{ARR_MOVIES_PATH}}:/movies
      - {{ARR_DOWNLOADS_PATH}}:/downloads

  bazarr:
    image: lscr.io/linuxserver/bazarr:latest
    container_name: {{STACK_NAME}}-bazarr
    restart: unless-stopped
    ports:
      - "6767:6767"
    environment:
      - PUID=1000
      - PGID=1000
      - TZ=Europe/London
    volumes:
      - {{ARR_CONFIG_ROOT}}/bazarr:/config
      - {{ARR_MOVIES_PATH}}:/movies
      - {{ARR_TV_PATH}}:/tv
