services:
  bazarr:
    image: lscr.io/linuxserver/bazarr:latest
    container_name: {{STACK_NAME}}
    restart: unless-stopped
    ports:
      - "6767:6767"
    environment:
      - PUID=1000
      - PGID=1000
      - TZ=Europe/London
    volumes:
      - {{BAZARR_CONFIG_PATH}}:/config
      - {{BAZARR_MOVIES_PATH}}:/movies
      - {{BAZARR_TV_PATH}}:/tv
