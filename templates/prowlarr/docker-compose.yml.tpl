services:
  prowlarr:
    image: lscr.io/linuxserver/prowlarr:latest
    container_name: {{STACK_NAME}}
    restart: unless-stopped
    ports:
      - "9696:9696"
    environment:
      - PUID=1000
      - PGID=1000
      - TZ=Europe/London
    volumes:
      - {{PROWLARR_CONFIG_PATH}}:/config
