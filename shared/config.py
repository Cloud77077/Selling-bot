from functools import lru_cache
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')
    database_url: str = Field('postgresql+psycopg://selling_bot:selling_bot@postgres:5432/selling_bot', alias='DATABASE_URL')
    bot_token: str = Field('', alias='BOT_TOKEN')
    admin_ids: str = Field('', alias='ADMIN_IDS')
    secret_key: str = Field('change-me', alias='SECRET_KEY')
    order_expiry_minutes: int = Field(30, alias='ORDER_EXPIRY_MINUTES')
    low_stock_threshold: int = Field(5, alias='LOW_STOCK_THRESHOLD')
    public_domain: str = Field('', alias='PUBLIC_DOMAIN')
    certbot_email: str = Field('', alias='CERTBOT_EMAIL')
    upload_dir: str = Field('admin_panel/static/uploads', alias='UPLOAD_DIR')

    @property
    def admin_id_set(self) -> set[int]:
        return {int(x.strip()) for x in self.admin_ids.split(',') if x.strip().isdigit()}

@lru_cache
def get_settings() -> Settings:
    return Settings()
