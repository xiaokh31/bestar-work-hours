from contextlib import contextmanager

from sqlalchemy import (
    MetaData, Table, Column, String, Integer, Boolean, LargeBinary, JSON,
    ForeignKey, UniqueConstraint, create_engine, select, insert, text, event,
)
from sqlalchemy.pool import NullPool, StaticPool

metadata = MetaData()
versions = Table("schema_versions", metadata, Column("version", Integer, primary_key=True))
imports = Table(
    "attendance_imports", metadata,
    Column("id", String(36), primary_key=True),
    Column("sha256", String(64), nullable=False, unique=True),
    Column("filename", String(240), nullable=False),
    Column("original", LargeBinary, nullable=False),
    Column("summary", JSON, nullable=False),
    Column("parsed", JSON, nullable=True),
    Column("revision", Integer, nullable=False, default=0),
    Column("deleted", Boolean, nullable=False, default=False),
    Column("created_at", String(40), nullable=False),
    Column("updated_at", String(40), nullable=False),
)
rows = Table(
    "attendance_rows", metadata,
    Column("id", String(36), primary_key=True),
    Column("import_id", String(36), ForeignKey("attendance_imports.id"), nullable=False, index=True),
    Column("row_key", String(64), nullable=False),
    Column("data", JSON, nullable=False),
    Column("deleted", Boolean, nullable=False, default=False),
    Column("corrected", Boolean, nullable=False, default=False),
    UniqueConstraint("import_id", "row_key"),
)
files = Table(
    "generated_files", metadata,
    Column("id", String(36), primary_key=True),
    Column("import_id", String(36), ForeignKey("attendance_imports.id"), nullable=False, index=True),
    Column("revision", Integer, nullable=False),
    Column("status", String(20), nullable=False),
    Column("filename", String(240), nullable=True),
    Column("sha256", String(64), nullable=True),
    Column("content", LargeBinary, nullable=True),
    Column("report", JSON, nullable=False),
    Column("created_at", String(40), nullable=False),
)
audit = Table(
    "attendance_audit", metadata,
    Column("id", String(36), primary_key=True),
    Column("import_id", String(36), ForeignKey("attendance_imports.id"), nullable=False, index=True),
    Column("row_id", String(36), nullable=True),
    Column("action", String(32), nullable=False),
    Column("actor", String(120), nullable=False),
    Column("reason", String(1000), nullable=False),
    Column("snapshot", JSON, nullable=False),
    Column("occurred_at", String(40), nullable=False),
)
class Database:
    def __init__(self, url: str):
        if url.startswith("postgres://"):
            url = "postgresql+psycopg://" + url[len("postgres://"):]
        elif url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+psycopg://", 1)
        options = {"poolclass": NullPool}
        if url.startswith("sqlite"):
            options["connect_args"] = {"check_same_thread": False, "timeout": 10}
            if url.endswith(":memory:"):
                options["poolclass"] = StaticPool
        self.engine = create_engine(url, **options)
        if self.engine.dialect.name == "sqlite":
            @event.listens_for(self.engine, "connect")
            def configure_sqlite(connection, _):
                connection.execute("PRAGMA foreign_keys=ON")

    @contextmanager
    def transaction(self):
        with self.engine.begin() as connection:
            yield connection

    def migrate(self):
        # Explicit deployment step, never an import/startup side effect.
        with self.engine.begin() as connection:
            if connection.dialect.name == "postgresql":
                connection.execute(text("SELECT pg_advisory_xact_lock(78200101)"))
            metadata.create_all(connection)
            current = connection.execute(select(versions.c.version)).scalars().all()
            if current not in ([], [1], [2]):
                raise RuntimeError("Unsupported database schema version")
            if current == [1]:
                # v2 removes only obsolete login state; attendance and audit stay intact.
                connection.execute(text("DROP TABLE IF EXISTS manager_sessions"))
                connection.execute(text("DROP TABLE IF EXISTS login_throttle"))
                connection.execute(versions.update().values(version=2))
            elif not current:
                connection.execute(insert(versions).values(version=2))

    def healthy(self):
        with self.engine.connect() as connection:
            return connection.execute(select(versions.c.version)).scalars().all() == [2]
