import asyncio
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from app.db.base import Base
from app.db.models import (  # noqa: F401  (import registers tables on Base.metadata)
    AuditLog,
    Department,
    Organization,
    Skill,
    SkillVersion,
    ToolGrant,
    User,
)

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# Migrations always run as the admin/owner role — never the RLS-restricted
# app_role — because they need to CREATE ROLE, enable RLS, and define
# triggers. See app/db/session.py for the contrasting runtime engine.
ADMIN_DATABASE_URL = os.environ.get(
    "ADMIN_DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/skill_registry",
)


def run_migrations_offline() -> None:
    context.configure(
        url=ADMIN_DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    connectable = create_async_engine(ADMIN_DATABASE_URL, poolclass=pool.NullPool)

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
