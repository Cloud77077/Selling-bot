from logging.config import fileConfig
from alembic import context
from shared.config import get_settings
from shared.database import Base
from shared import models
config = context.config
fileConfig(config.config_file_name)
target_metadata = Base.metadata

def run_migrations_offline():
    context.configure(url=get_settings().database_url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction(): context.run_migrations()

def run_migrations_online():
    from sqlalchemy import create_engine
    connectable = create_engine(get_settings().database_url, future=True)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction(): context.run_migrations()
(context.is_offline_mode() and run_migrations_offline()) or (not context.is_offline_mode() and run_migrations_online())
