# Selling Bot — beginner VPS setup guide

Selling Bot is a self-hosted Telegram shop for digital goods such as coupon codes, license keys, vouchers, or account details. Buyers browse products in Telegram, choose UPI or Binance payment instructions, press **I've Paid**, and an admin manually confirms the payment before the bot delivers one unused code. The project includes an aiogram bot, a FastAPI admin panel, shared SQLAlchemy models/services, PostgreSQL in Docker, nginx, Certbot SSL automation, migrations, backups, and tests.

> ⚠️ Important: v1 uses manual payment confirmation. The bot does **not** read your bank, UPI, or Binance account automatically. This avoids PSP/KYC complexity, but you must verify payments yourself.

## 1. What you need

1. A VPS (a small Ubuntu server). Cheap examples include Hetzner, DigitalOcean, Vultr, Linode/Akamai, or any local VPS provider.
2. A Telegram account.
3. Optional but strongly recommended: a domain name, such as `yourshop.com`, for HTTPS.
4. A UPI account and/or Binance account if you want to accept those payment methods.

## 2. Create your Telegram bot with @BotFather

1. Open Telegram and search for **@BotFather**.
2. Send `/newbot`.
3. BotFather asks for a display name. Example: `My Digital Shop`.
4. BotFather asks for a username ending in `bot`. Example: `my_digital_shop_bot`.
5. BotFather replies with a token that looks like `123456789:AA...`.
6. Put that token in `.env` as `BOT_TOKEN=...`.

## 3. Get your Telegram numeric admin ID

1. Open Telegram and search for **@userinfobot**.
2. Press Start or send `/start`.
3. It replies with your numeric ID, such as `123456789`.
4. Put one or more admin IDs in `.env` as `ADMIN_IDS=123456789,987654321`.

`ADMIN_IDS` controls who can use `/addproduct`, `/restock`, `/manualsale`, and `/stats`, and who receives payment and low-stock alerts.

## 4. Connect to a fresh VPS with SSH

SSH is the terminal connection from your computer to the VPS. Your provider shows the VPS IP address after creation.

```bash
ssh root@your_vps_ip
```

Type `yes` if asked to trust the host key. Then enter the root password or use the SSH key configured at your VPS provider.

## 5. Update Ubuntu and install Docker

Copy and paste these commands on the VPS:

```bash
apt update
apt upgrade -y
apt install -y ca-certificates curl gnupg git python3
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
chmod a+r /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" > /etc/apt/sources.list.d/docker.list
apt update
apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
systemctl enable --now docker
```

Check Docker:

```bash
docker compose version
```

## 6. Get the code onto the VPS

Using git:

```bash
git clone https://github.com/Cloud77077/Selling-bot.git
cd Selling-bot
```

If you do not want to use git, install FileZilla on your computer, connect with SFTP to `root@your_vps_ip`, upload the project folder, then SSH into the VPS and `cd` into that folder.

## 7. Configure `.env`

```bash
cp .env.example .env
nano .env
```

Variables:

- `BOT_TOKEN`: from @BotFather.
- `ADMIN_IDS`: your numeric Telegram IDs from @userinfobot.
- `DATABASE_URL`: defaults to the PostgreSQL container: `postgresql+psycopg://selling_bot:selling_bot@postgres:5432/selling_bot`. Beginners should not change it.
- `SECRET_KEY`: a long random web session secret. Generate one with `python3 -c 'import secrets; print(secrets.token_urlsafe(48))'`.
- `UPLOAD_DIR`: local disk upload folder for product images and Binance QR files.
- `UPI_ID`: your UPI address, such as `name@okhdfcbank`, `name@paytm`, or `phone@ybl`.
- `UPI_PAYEE_NAME`: the name buyers should see for UPI payments.
- `BINANCE_PAY_QR_PATH`: local path/URL for your Binance QR image after upload.
- `ORDER_EXPIRY_MINUTES`: how long unpaid orders stay pending before the bot expires them.
- `LOW_STOCK_THRESHOLD`: sends admins a Telegram warning when stock crosses down to this number.
- `PUBLIC_DOMAIN`: your domain, for example `shop.example.com`.
- `CERTBOT_EMAIL`: email used by Let's Encrypt for SSL notices.

## 8. UPI and Binance setup

A UPI ID is the payment address used by apps such as GPay, PhonePe, Paytm, BHIM, or your bank app. Open your UPI app profile or bank account details to find it.

For Binance Pay, open Binance, go to Pay/Receive, find your Pay ID or QR code, save the QR image, and upload it in the admin panel settings/uploads workflow. The app stores uploads on the VPS disk; it does not use S3 or any external storage bucket.

## 9. Point a domain at the VPS

At your domain registrar, create a DNS **A record**. An A record is like a phone book entry: it points a name to an IP address.

- Host/name: `@` for the root domain or `shop` for `shop.example.com`.
- Value/address: your VPS IP.
- TTL: default is fine.

Wait a few minutes to a few hours for DNS propagation.

## 10. Start the stack for the first time

```bash
docker compose up --build -d postgres
docker compose run --rm admin_panel alembic -c migrations/alembic.ini upgrade head
docker compose up --build -d
```

Create the first admin-panel user:

```bash
docker compose run --rm admin_panel python - <<'PY'
from passlib.context import CryptContext
from shared.database import SessionLocal
from shared.models import AdminUser
pwd=CryptContext(schemes=['bcrypt'], deprecated='auto')
with SessionLocal() as db:
    db.add(AdminUser(username='admin', password_hash=pwd.hash('change-me-now')))
    db.commit()
PY
```

## 11. Issue and renew SSL automatically

Make sure `PUBLIC_DOMAIN` and `CERTBOT_EMAIL` are set in `.env` and DNS points to this VPS. Then run:

```bash
./scripts/setup_ssl.sh
```

Renew manually any time:

```bash
./scripts/renew_ssl.sh
```

Add automatic renewal with cron:

```bash
(crontab -l 2>/dev/null; echo '17 3 * * * cd /root/Selling-bot && ./scripts/renew_ssl.sh >> /var/log/selling-bot-ssl.log 2>&1') | crontab -
```

## 12. Log into the admin panel

Open `https://your-domain/` after SSL, or `http://your_vps_ip/` before SSL. Log in with the admin user you created, then change the password by updating the admin row or creating a new admin user with a stronger password.

## 13. Add your first product in the admin panel

1. Go to **Products**.
2. Enter name, description, price, and optionally upload a logo/image.
3. Save the product.
4. Paste deliverable codes one per line in the restock box.
5. Open the bot in Telegram, press Browse products, and confirm it appears with stock.

## 14. Test purchase before going live

1. Use your own Telegram account to browse the bot.
2. Buy one product with UPI, press **I've Paid**, and confirm from your admin Telegram alert.
3. Repeat with Binance.
4. Confirm the buyer receives the delivery code in a Telegram code block for easy copy/paste.

## 15. Daily payment confirmation workflow

The buyer taps **I've Paid**. Admins receive a Telegram DM with order details and Confirm/Reject buttons. Check your real UPI or Binance app for the exact matching amount, then tap Confirm. The shared order logic lives in `shared/services/orders.py`, and the Telegram confirm/reject handlers live in `bot/main.py`; future automatic payment providers should call the same `confirm_payment` function.

## 16. New admin bot commands

- `/addproduct`: starts a conversation: name → description → price → category → codes → optional image → `/confirm`.
- `/restock <product_id>`: the bot asks you to paste extra codes, one per line.
- `/manualsale <telegram_id_or_username> <product_id>`: records an outside/manual sale, atomically consumes one code, and sends the buyer the normal delivery message. The buyer must have started the bot before.
- `/stats`: shows total orders, revenue, today's orders, top products, and low/out-of-stock products.

Example:

```text
/addproduct
Netflix 1 Month
Private account warranty included
499
Streaming
CODE-ONE
CODE-TWO
/skip
/confirm
```

## 17. Contact Admin / Buy Manually flow

If a buyer contacts you outside the bot, ask them to press `/start` once so their Telegram user is in the database. After payment, run `/manualsale @username 12` or `/manualsale 123456789 12`. This keeps the order, stock deduction, and delivery history consistent with normal bot sales.

## 18. Maintenance

Restock in the panel from Products, or in Telegram with `/restock <product_id>`. Check `/stats` regularly.

Logs:

```bash
docker compose logs -f bot
docker compose logs -f admin_panel nginx
docker compose ps
```

Back up now:

```bash
docker compose exec postgres pg_dump -U selling_bot selling_bot | gzip > backups/selling_bot-$(date +%F).sql.gz
```

Or use the included script from an environment with `pg_dump` available:

```bash
DATABASE_URL=postgresql+psycopg://selling_bot:selling_bot@localhost:5432/selling_bot scripts/backup_db.sh
```

Cron example:

```bash
mkdir -p backups
(crontab -l 2>/dev/null; echo '22 2 * * * cd /root/Selling-bot && docker compose exec -T postgres pg_dump -U selling_bot selling_bot | gzip > backups/selling_bot-$(date +\%F).sql.gz') | crontab -
```

## 19. Troubleshooting

- Bot not responding: check `BOT_TOKEN`, run `docker compose logs -f bot`, and make sure no other copy of the bot is polling.
- QR image not showing: verify the file is uploaded under `admin_panel/static/uploads` and nginx is running.
- Cannot log into admin panel: confirm `SECRET_KEY` stayed the same and create/reset an `AdminUser`.
- SSL errors: confirm DNS A record points to the VPS, ports 80/443 are open, then rerun `./scripts/setup_ssl.sh` and check `docker compose logs nginx`.
- VPS low on disk: run `docker system df`, remove old unused images with `docker system prune`, and keep backups off-server too.
- Containers not starting: run `docker compose ps` and `docker compose logs -f SERVICE_NAME`.

## 20. Future upgrades

Automatic UPI confirmation can be added through a PSP such as Cashfree or Razorpay, usually requiring business KYC. Binance Pay Merchant API webhooks can also confirm Binance payments. Add webhook endpoints in `admin_panel/`, verify signatures, find the pending order, and call `confirm_payment` in `shared/services/orders.py`; keep the Telegram manual confirm/reject path in `bot/main.py` as fallback.
