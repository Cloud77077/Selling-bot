#!/usr/bin/env bash
set -euo pipefail
if [[ ! -f .env ]]; then echo "Create .env first" >&2; exit 1; fi
set -a; source .env; set +a
: "${PUBLIC_DOMAIN:?Set PUBLIC_DOMAIN in .env}"
: "${CERTBOT_EMAIL:?Set CERTBOT_EMAIL in .env}"

docker compose up -d nginx

docker compose run --rm certbot certonly \
  --webroot --webroot-path /var/www/certbot \
  --email "$CERTBOT_EMAIL" --agree-tos --no-eff-email \
  -d "$PUBLIC_DOMAIN"

python3 - <<'PYSSL'
import os
from pathlib import Path
template = Path('nginx/ssl.conf.template').read_text()
Path('nginx/default.conf').write_text(template.replace('${PUBLIC_DOMAIN}', os.environ['PUBLIC_DOMAIN']))
PYSSL
docker compose up -d nginx
