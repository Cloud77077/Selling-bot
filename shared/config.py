from functools import lru_cache
from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')
    database_url: str = Field('postgresql+psycopg://selling_bot:selling_bot@postgres:5432/selling_bot', alias='DATABASE_URL')
    bot_token: str = Field('', alias='BOT_TOKEN')
    admin_ids: str = Field('', alias='ADMIN_IDS')
    secret_key: str = Field('change-me', validation_alias=AliasChoices('SESSION_SECRET_KEY', 'SECRET_KEY'))
    upload_dir: str = Field('media/uploads', alias='UPLOAD_DIR')
    upi_id: str = Field('', alias='UPI_ID')
    upi_payee_name: str = Field('', alias='UPI_PAYEE_NAME')
    binance_pay_qr_path: str = Field('', alias='BINANCE_PAY_QR_PATH')
    order_expiry_minutes: int = Field(30, alias='ORDER_EXPIRY_MINUTES')
    low_stock_threshold: int = Field(3, alias='LOW_STOCK_THRESHOLD')
    domain_name: str = Field('example.com', alias='DOMAIN_NAME')
    certbot_email: str = Field('admin@example.com', alias='CERTBOT_EMAIL')

    @property
    def admin_id_set(self) -> set[int]:
        return {int(x.strip()) for x in self.admin_ids.split(',') if x.strip().isdigit()}

@lru_cache
def get_settings() -> Settings:
    return Settings()
