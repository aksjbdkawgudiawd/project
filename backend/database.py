import os
from contextlib import contextmanager
from pathlib import Path

from cryptography.fernet import Fernet
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker

from backend.models import Base


class Database:
    def __init__(self, url=None, key=None, demo=False):
        url = url or os.getenv("DATABASE_URL", "sqlite:///.hoplite/marketplace.sqlite3")
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql+psycopg://", 1)
        elif url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+psycopg://", 1)
        if url.startswith("sqlite"):
            Path(".hoplite").mkdir(exist_ok=True)
        key = key or os.getenv("INVENTORY_ENCRYPTION_KEY")
        if not key:
            if not demo:
                raise RuntimeError("INVENTORY_ENCRYPTION_KEY is required outside explicit APP_ENV=demo")
            path = Path(".hoplite/demo-encryption.key")
            path.parent.mkdir(exist_ok=True)
            if not path.exists():
                with path.open("xb") as handle:
                    handle.write(Fernet.generate_key())
                path.chmod(0o600)
            key = path.read_bytes()
        self.cipher = Fernet(key)
        self.sqlite = url.startswith("sqlite")
        self.engine = create_engine(url, connect_args={"check_same_thread": False, "timeout": 30} if self.sqlite else {}, pool_pre_ping=True)
        if self.sqlite:
            @event.listens_for(self.engine, "connect")
            def pragmas(connection, _):
                connection.execute("PRAGMA foreign_keys=ON")
                connection.execute("PRAGMA journal_mode=WAL")
        self.sessions = sessionmaker(self.engine, expire_on_commit=False)

    def initialize(self):
        Base.metadata.create_all(self.engine)
        # Database guards also reject bulk SQL mutation, not only ORM updates.
        with self.engine.begin() as conn:
            for table in ("audit", "ledger"):
                if self.sqlite:
                    for operation in ("UPDATE", "DELETE"):
                        conn.execute(text(f"CREATE TRIGGER IF NOT EXISTS {table}_no_{operation.lower()} BEFORE {operation} ON {table} BEGIN SELECT RAISE(ABORT, 'append-only table'); END"))
                else:
                    conn.execute(text("CREATE OR REPLACE FUNCTION reject_immutable_mutation() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'append-only table'; END; $$"))
                    conn.execute(text(f"DROP TRIGGER IF EXISTS {table}_immutable ON {table}"))
                    conn.execute(text(f"CREATE TRIGGER {table}_immutable BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION reject_immutable_mutation()"))

    @contextmanager
    def read(self):
        with self.sessions() as session:
            yield session

    @contextmanager
    def write(self):
        with self.sessions() as session:
            try:
                if self.sqlite:
                    session.execute(text("BEGIN IMMEDIATE"))
                yield session
                session.commit()
            except Exception:
                session.rollback()
                raise

    def encrypt(self, payload):
        return self.cipher.encrypt(payload.encode()).decode()

    def decrypt(self, payload):
        return self.cipher.decrypt(payload.encode()).decode()
