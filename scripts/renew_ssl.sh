#!/usr/bin/env bash
set -euo pipefail
docker compose run --rm certbot renew --webroot --webroot-path /var/www/certbot
docker compose exec nginx nginx -s reload
