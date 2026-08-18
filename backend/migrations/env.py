from logging.config import fileConfig
import os

from alembic import context
from dotenv import load_dotenv
from sqlalchemy import engine_from_config, pool

from backend.database import Base
import backend.models  # noqa: F401 - 모든 ORM 모델을 metadata에 등록


config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

load_dotenv(".env")
database_url = os.getenv("DATABASE_URL")
if database_url:
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))

target_metadata = Base.metadata
LEGACY_TABLES = {"commercial_data", "score_data", "risk_index", "officials"}


def include_object(object_, name, type_, reflected, compare_to):
    # 레거시 테이블은 롤백용으로 동결한다. 신규 migration의 autogenerate/check 대상이 아니다.
    return not (type_ == "table" and name in LEGACY_TABLES)


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            include_object=include_object,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
