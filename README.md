# Selling Bot

A beginner-friendly Telegram digital goods selling system with an aiogram v3 bot, FastAPI admin panel, shared SQLAlchemy database layer, Alembic migrations, PostgreSQL/SQLite support, Docker Compose, nginx, backups, and tests.

## Features
- Product catalogue with images, descriptions, stock indicators, and pagination.
- Manual-confirm UPI and Binance payment flows with buyer “I’ve Paid” action.
- Admin Telegram callbacks to confirm or reject payment claims.
- Atomic deliverable-code assignment so each code is sold once.
- Human-readable orders like `ORD-2026-0001` and unique UPI amounts.
- Web admin login, dashboard, product CRUD, stock management, order actions, and settings.

## Project layout
- `bot/` Telegram bot.
- `admin_panel/` FastAPI app and Bootstrap templates.
- `shared/` config, database models, and services.
- `migrations/` Alembic migration environment.
- `nginx/` reverse proxy template.
- `scripts/` maintenance utilities.
- `tests/` pytest service tests.

## Configuration
Copy `.env.example` to `.env` and fill every value:

```bash
cp .env.example .env
```

Important variables:
- `DATABASE_URL`: PostgreSQL URL in Docker or `sqlite:///./selling_bot.db` for local testing.
- `BOT_TOKEN`: token from BotFather.
- `ADMIN_IDS`: comma-separated Telegram numeric user IDs.
- `SECRET_KEY`: long random value for web sessions.
- `UPLOAD_DIR`: product image upload directory.

## Docker setup
```bash
docker compose up --build -d postgres
docker compose run --rm admin_panel alembic -c migrations/alembic.ini upgrade head
docker compose up --build -d
```

Open the admin panel through nginx on `http://YOUR_SERVER/`.

## Create an admin user
Run inside the admin container or locally with dependencies installed:

```bash
python - <<'PY'
from passlib.context import CryptContext
from shared.database import SessionLocal
from shared.models import AdminUser
pwd=CryptContext(schemes=['bcrypt'], deprecated='auto')
with SessionLocal() as db:
    db.add(AdminUser(username='admin', password_hash=pwd.hash('change-me')))
    db.commit()
PY
```

## VPS setup
1. Point your domain A record to the VPS IP.
2. Install Docker and the Compose plugin.
3. Clone the repository, create `.env`, and run the Docker commands above.
4. Restrict firewall ports to SSH, HTTP, and HTTPS.

## UPI and Binance setup
In the admin panel settings page, set:
- UPI ID shown to buyers.
- Binance QR or payment instructions.
- Low-stock threshold.
- Pending order expiry timeout.

Payments are manual-confirm: buyers press “I’ve Paid”, admins verify externally, then confirm/reject.

## SSL
Use Certbot on the host or place a TLS-enabled reverse proxy in front of this nginx service. After issuing certificates, extend `nginx/default.conf` with a `listen 443 ssl;` server and certificate paths.

## Maintenance
- Backups: `DATABASE_URL=... scripts/backup_db.sh`.
- Migrations: `alembic -c migrations/alembic.ini upgrade head`.
- Tests: `pytest`.
- Logs: `docker compose logs -f bot admin_panel nginx`.

## Troubleshooting
- Bot not responding: verify `BOT_TOKEN`, container logs, and that only one poller is running.
- Admin login fails: create an `admin_users` row and verify `SECRET_KEY` remains stable.
- No stock on confirm: restock product before confirming or reject/refund manually.
- Upload issues: verify `UPLOAD_DIR` exists and nginx/admin container can serve `/static/uploads`.

## Future automatic payment integration
Add provider webhook endpoints in `admin_panel/`, verify signed callbacks, locate the pending order by unique amount/order number, and call `confirm_payment`. Keep manual review as a fallback for mismatches.
