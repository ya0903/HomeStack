services:
  nextcloud-db:
    image: mariadb:11
    container_name: {{STACK_NAME}}-db
    restart: unless-stopped
    command: --transaction-isolation=READ-COMMITTED --binlog-format=ROW
    environment:
      - MYSQL_DATABASE=nextcloud
      - MYSQL_USER=nextcloud
      - MYSQL_PASSWORD=nextcloud
      - MYSQL_ROOT_PASSWORD=nextcloud-root
    volumes:
      - {{NC_DB_PATH}}:/var/lib/mysql

  nextcloud-redis:
    image: redis:7-alpine
    container_name: {{STACK_NAME}}-redis
    restart: unless-stopped
    volumes:
      - {{NC_REDIS_PATH}}:/data

  nextcloud-app:
    image: nextcloud:stable-apache
    container_name: {{STACK_NAME}}
    restart: unless-stopped
    depends_on:
      - nextcloud-db
      - nextcloud-redis
    ports:
      - "8088:80"
    environment:
      - MYSQL_HOST=nextcloud-db
      - MYSQL_DATABASE=nextcloud
      - MYSQL_USER=nextcloud
      - MYSQL_PASSWORD=nextcloud
      - REDIS_HOST=nextcloud-redis
    volumes:
      - {{NC_APP_PATH}}:/var/www/html
      - {{NC_DATA_PATH}}:/var/www/html/data
