from functools import lru_cache
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')
    database_url: str = Field('sqlite:///./selling_bot.db', alias='DATABASE_URL')
    bot_token: str = Field('', alias='BOT_TOKEN')
    admin_ids: str = Field('', alias='ADMIN_IDS')
    secret_key: str = Field('change-me', alias='SECRET_KEY')
    upload_dir: str = Field('admin_panel/static/uploads', alias='UPLOAD_DIR')

    @property
    def admin_id_set(self) -> set[int]:
        return {int(x.strip()) for x in self.admin_ids.split(',') if x.strip().isdigit()}

@lru_cache
def get_settings() -> Settings:
    return Settings()
