# Selling Bot — beginner VPS guide

## 1. What this project does
Selling Bot is a self-hosted Telegram shop for digital products such as coupon codes, licence keys, gift cards, or account credentials. Buyers browse products in Telegram, choose UPI or Binance manual payment, tap **I've Paid**, and an admin confirms or rejects the payment. When confirmed, the bot sends the purchased code in a Telegram code block so it is easy to copy.

⚠️ Important: version 1 uses manual payment confirmation. The bot does not read your bank, UPI, or Binance account automatically.

## 2. What you need before starting
You need:
1. A VPS. Examples of cheap providers are Hetzner, DigitalOcean, Vultr, Linode, or Hostinger VPS.
2. Ubuntu 22.04 or 24.04 on that VPS.
3. A Telegram account.
4. A domain name if you want HTTPS for the admin panel.
5. Your UPI ID and/or Binance Pay details.

## 3. Create your Telegram bot with @BotFather
1. Open Telegram and search for `@BotFather`.
2. Send `/start`.
3. Send `/newbot`.
4. BotFather asks for a display name. Example: `My Digital Shop`.
5. BotFather asks for a username. It must end in `bot`, for example `my_digital_shop_bot`.
6. BotFather replies with a token that looks like `123456789:AAExampleTokenHere`.
7. Put that token into `.env` as `BOT_TOKEN=...`.

💡 Tip: keep the token private. Anyone with it can control your bot.

## 4. Get your Telegram numeric admin ID
1. Search Telegram for `@userinfobot`.
2. Send `/start`.
3. It replies with your numeric ID, for example `123456789`.
4. Put that into `.env` as `ADMIN_IDS=123456789`.
5. For multiple admins, use commas: `ADMIN_IDS=123456789,987654321`.

`ADMIN_IDS` controls who can use admin-only bot commands and who receives payment/low-stock alerts.

## 5. What SSH is and how to connect
SSH is the terminal connection from your computer to your VPS. Your provider shows an IP address such as `203.0.113.10`.

On macOS/Linux Terminal or Windows PowerShell, run:

```bash
ssh root@your_vps_ip
```

Example:

```bash
ssh root@203.0.113.10
```

The first time, you may see `Are you sure you want to continue connecting?`. Type `yes` and press Enter. Then enter the VPS password or use the SSH key provided by your VPS company.

## 6. Update Ubuntu and install Docker
Copy and paste these commands on the VPS:

```bash
apt update
apt upgrade -y
apt install -y ca-certificates curl gnupg git ufw
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
chmod a+r /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo $VERSION_CODENAME) stable" > /etc/apt/sources.list.d/docker.list
apt update
apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
systemctl enable --now docker
```

Optional firewall:

```bash
ufw allow OpenSSH
ufw allow 80
ufw allow 443
ufw --force enable
```

## 7. Get the code onto the VPS
### Option A: git clone
```bash
cd /opt
git clone https://github.com/Cloud77077/Selling-bot.git
cd Selling-bot
```

### Option B: upload files with SFTP/FileZilla
1. Install FileZilla on your computer.
2. Connect to your VPS using SFTP, host `sftp://your_vps_ip`, username `root`.
3. Upload the project folder to `/opt/Selling-bot`.
4. SSH into the VPS and run `cd /opt/Selling-bot`.

## 8. Configure `.env`
Create your `.env` file:

```bash
cp .env.example .env
nano .env
```

Variables explained:
- `BOT_TOKEN`: token from @BotFather.
- `ADMIN_IDS`: your Telegram numeric ID(s) from @userinfobot.
- `DATABASE_URL`: defaults to the in-VPS PostgreSQL container. Beginners should leave it unchanged.
- `SESSION_SECRET_KEY`: any long random text for admin panel login sessions. Generate one with `openssl rand -hex 32`.
- `UPLOAD_DIR`: local folder for uploaded images and QR files. The Docker stack mounts `./media` into the containers.
- `UPI_ID`: your UPI ID, such as `yourname@okaxis`.
- `UPI_PAYEE_NAME`: the name buyers should see when paying.
- `BINANCE_PAY_QR_PATH`: local path or text shown to buyers for Binance Pay, often `/media/uploads/binance-qr.png` after upload.
- `ORDER_EXPIRY_MINUTES`: unpaid pending orders older than this expire automatically.
- `LOW_STOCK_THRESHOLD`: admins are alerted when stock crosses down to this number.
- `DOMAIN_NAME`: your domain, for example `shop.example.com`, used for SSL.
- `CERTBOT_EMAIL`: email used by Let's Encrypt for certificate notices.

## 9. Find your UPI ID
Open GPay, PhonePe, Paytm, BHIM, or your bank app. Look for **Profile**, **UPI ID**, or **Manage UPI IDs**. Copy the ID exactly into `UPI_ID`.

## 10. Binance Pay ID and QR code
In the Binance app, open Pay. Find your Pay ID or receive-money QR code. Save the QR image, then upload it from the admin panel settings/product image upload area or place it under `media/uploads/` on the VPS. Set `BINANCE_PAY_QR_PATH=/media/uploads/your-qr-file.png`.

## 11. Point your domain at the VPS
A DNS **A record** tells the internet that your domain should open your VPS.

At your domain registrar:
1. Open DNS settings.
2. Add an A record.
3. Host/name: `@` for root domain or `shop` for `shop.example.com`.
4. Value/target: your VPS IP address.
5. Wait 5 minutes to a few hours.

## 12. First launch
```bash
cd /opt/Selling-bot
docker compose up --build -d postgres
docker compose run --rm admin_panel alembic -c migrations/alembic.ini upgrade head
docker compose up --build -d
```

Check containers:

```bash
docker compose ps
```

## 13. SSL certificate issue and renewal
This repo includes a dockerized Certbot setup. After your DNS A record points to the VPS and ports 80/443 are open, run:

```bash
./scripts/init_ssl.sh
```

Renew manually any time:

```bash
docker compose run --rm certbot renew --webroot -w /var/www/certbot && docker compose exec nginx nginx -s reload
```

Add automatic renewal with cron:

```bash
(crontab -l 2>/dev/null; echo "0 3 * * * cd /opt/Selling-bot && docker compose run --rm certbot renew --webroot -w /var/www/certbot && docker compose exec nginx nginx -s reload") | crontab -
```

## 14. First admin panel login
Create an admin user:

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

Open `https://your-domain/`, log in with `admin` and `change-me-now`, then change the password by updating the admin user in the database or adding your own password-management route later.

⚠️ Important: do not keep the example password.

## 15. Add your first product in the admin panel
1. Open `https://your-domain/products`.
2. Enter product name.
3. Enter description.
4. Enter price.
5. Include category in the description if needed.
6. Upload a logo/image.
7. Save the product.
8. Paste deliverable codes one per line in the stock box and submit.
9. Open your Telegram bot and tap **Browse products** to confirm it appears.

## 16. Test purchase before going live
1. In Telegram, send `/start` to your bot.
2. Browse products and choose one.
3. Test UPI path: choose UPI, note the unique amount, tap **I've Paid**.
4. As admin, receive the Telegram confirm/reject buttons.
5. Check that the buyer receives the delivery code in a code block after Confirm.
6. Repeat with Binance path.

## 17. How manual payment confirmation works
The buyer taps **I've Paid**. Admins receive a Telegram DM with Confirm/Reject buttons. The admin checks their real UPI or Binance app for the exact amount/order, then taps Confirm. The code path is in `bot/main.py`, while shared payment/stock logic is in `shared/services/orders.py`.

This manual design avoids KYC, PSP fees, and webhook complexity in v1. A future automatic payment integration should plug into `confirm_payment()` in `shared/services/orders.py`.

## 18. Admin bot commands
### `/addproduct`
Conversational flow:
```text
/addproduct
Product name?
Description?
Price?
Category?
Paste codes one per line
Upload image or /skip
CONFIRM
```

### `/restock <product_id>`
```text
/restock 1
CODE-ONE
CODE-TWO
CODE-THREE
```

### `/manualsale <telegram_id_or_username> <product_id>`
```text
/manualsale 123456789 1
/manualsale @buyerusername 1
```
The buyer must have sent `/start` once before. This creates a normal order, atomically assigns stock, sends the same delivery message, and keeps database history consistent.

### `/stats`
Shows total orders, revenue, orders today, top products, and low/out-of-stock products.

## 19. Contact Admin / Buy Manually flow
Some buyers may contact you outside the bot. After they pay manually, run `/manualsale`. This avoids losing records: the order, product, buyer, delivered code, and revenue are stored like normal bot-driven sales.

## 20. Maintenance
Restock from panel: open Products and paste new codes.

Restock from bot:
```text
/restock 1
NEWCODE1
NEWCODE2
```

Check stats:
```text
/stats
```

Read logs:
```bash
docker compose logs -f bot
docker compose logs -f admin_panel
docker compose logs -f nginx
```

Backup now:
```bash
DATABASE_URL="$(grep DATABASE_URL .env | cut -d= -f2-)" ./scripts/backup_db.sh
```

Daily backup cron:
```bash
(crontab -l 2>/dev/null; echo "30 2 * * * cd /opt/Selling-bot && DATABASE_URL=\$(grep DATABASE_URL .env | cut -d= -f2-) ./scripts/backup_db.sh") | crontab -
```

## 21. Troubleshooting
- Bot not responding: run `docker compose logs -f bot`, verify `BOT_TOKEN`, and make sure only this VPS is running the bot.
- QR image not showing: verify the file is under `media/uploads/` and the URL starts with `/media/`.
- Can't log into admin panel: verify the admin user exists and `SESSION_SECRET_KEY` is set.
- SSL errors: confirm DNS points to the VPS, ports 80/443 are open, then rerun `./scripts/init_ssl.sh`.
- VPS low on disk: run `df -h`, delete old backups/logs, and consider resizing the VPS.
- Containers not starting: run `docker compose ps` and `docker compose logs -f SERVICE_NAME`.

## 22. Future upgrades
Automatic UPI detection can be added through a PSP such as Cashfree or Razorpay, but usually requires business KYC. Binance Pay Merchant API webhooks can also confirm payments automatically. Future developers should add webhook endpoints in `admin_panel/main.py` and call `confirm_payment()` in `shared/services/orders.py` after verifying provider signatures.
