services:
  komga:
    image: gotson/komga:latest
    container_name: {{STACK_NAME}}
    restart: unless-stopped
    ports:
      - "25600:25600"
    environment:
      - TZ=Europe/London
    volumes:
      - {{KOMGA_CONFIG_PATH}}:/config
      - {{KOMGA_LIBRARY_PATH}}:/data
