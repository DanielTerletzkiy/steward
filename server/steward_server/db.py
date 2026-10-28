"""Database engine and session handling."""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy import event, inspect, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class Database:
    def __init__(self, url: str) -> None:
        self.engine: AsyncEngine = create_async_engine(url)
        event.listen(self.engine.sync_engine, "connect", _sqlite_pragmas)
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)

    async def create_all(self) -> None:
        # Tables are created directly; columns added later are patched in by _add_missing_columns.
        # Alembic takes over once a change needs more than added columns.
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await conn.run_sync(_add_missing_columns)
            await conn.execute(
                text(
                    "CREATE VIRTUAL TABLE IF NOT EXISTS manual_page USING fts5("
                    "text, equipment_id UNINDEXED, file_id UNINDEXED, page UNINDEXED, tokenize='unicode61')"
                )
            )

    async def session(self) -> AsyncIterator[AsyncSession]:
        async with self.sessions() as session:
            yield session

    async def dispose(self) -> None:
        await self.engine.dispose()


def _sqlite_pragmas(dbapi_conn, _record) -> None:
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def _add_missing_columns(conn) -> None:
    """Add columns that exist in the models but not yet in an older database file."""
    inspector = inspect(conn)
    for table in Base.metadata.sorted_tables:
        existing = {c["name"] for c in inspector.get_columns(table.name)}
        for column in table.columns:
            if column.name in existing:
                continue
            ddl = column.type.compile(dialect=conn.dialect)
            default = column.default.arg if column.default is not None and column.default.is_scalar else None
            if column.server_default is not None:
                server = column.server_default.arg
                ddl += f" DEFAULT {getattr(server, 'text', None) or repr(str(server))}"
            elif default is not None:
                literal = int(default) if isinstance(default, bool) else default
                ddl += f" DEFAULT {literal!r}"
            conn.execute(text(f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {ddl}'))
