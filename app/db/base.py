from datetime import datetime

from sqlalchemy import DateTime, MetaData
from sqlalchemy.orm import DeclarativeBase

# Explicit naming convention so every constraint has a predictable name in
# migrations (autogenerate diffs stay stable, and trigger/constraint errors
# are readable).
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)

    # Every `Mapped[datetime]` column defaults to a timezone-aware Postgres
    # column (matching migration 0001's explicit `DateTime(timezone=True)`).
    # Without this, SQLAlchemy infers a naive TIMESTAMP for the Python side,
    # and asyncpg rejects the tz-aware datetimes this codebase actually
    # produces (e.g. `reviewed_at = datetime.now(timezone.utc)`).
    type_annotation_map = {
        datetime: DateTime(timezone=True),
    }
