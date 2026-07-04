#!/usr/bin/env bash
set -euo pipefail
if [[ ! -f .env ]]; then echo "Create .env first"; exit 1; fi
set -a; source .env; set +a
: "${DOMAIN_NAME:?Set DOMAIN_NAME in .env}"
: "${CERTBOT_EMAIL:?Set CERTBOT_EMAIL in .env}"
mkdir -p certbot/conf/live/${DOMAIN_NAME} certbot/www
if [[ ! -f certbot/conf/live/${DOMAIN_NAME}/fullchain.pem ]]; then
  echo "Creating temporary self-signed certificate so nginx can start..."
  docker compose run --rm --entrypoint sh certbot -c "apk add --no-cache openssl >/dev/null 2>&1 || true; openssl req -x509 -nodes -newkey rsa:2048 -days 1 -keyout /etc/letsencrypt/live/${DOMAIN_NAME}/privkey.pem -out /etc/letsencrypt/live/${DOMAIN_NAME}/fullchain.pem -subj '/CN=${DOMAIN_NAME}'"
fi
docker compose up -d nginx

echo "Requesting Let's Encrypt certificate for ${DOMAIN_NAME}..."
docker compose run --rm certbot certonly --webroot -w /var/www/certbot -d "${DOMAIN_NAME}" --email "${CERTBOT_EMAIL}" --agree-tos --no-eff-email --force-renewal
docker compose exec nginx nginx -s reload
cat <<MSG
SSL is installed. To renew later, run:
  docker compose run --rm certbot renew --webroot -w /var/www/certbot && docker compose exec nginx nginx -s reload
MSG
