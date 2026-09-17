"""Relational storage; monetary values are integer USD cents."""
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String, Text, event
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def now():
    return datetime.now(timezone.utc)


def uid():
    return uuid4().hex


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    __table_args__ = (CheckConstraint("balance_cents >= 0"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(String(120))
    username: Mapped[str] = mapped_column(String(120), default="")
    balance_cents: Mapped[int] = mapped_column(Integer, default=0)
    wholesale_access: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class SKU(Base):
    __tablename__ = "skus"
    __table_args__ = (CheckConstraint("retail_price_cents > 0"), CheckConstraint("wholesale_price_cents > 0"))
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(String(160))
    country: Mapped[str] = mapped_column(String(80))
    country_code: Mapped[str] = mapped_column(String(2))
    flag: Mapped[str] = mapped_column(String(16), default="🌐")
    category: Mapped[str] = mapped_column(String(80), default="Digital license")
    description: Mapped[str] = mapped_column(Text, default="")
    retail_price_cents: Mapped[int] = mapped_column(Integer)
    wholesale_price_cents: Mapped[int] = mapped_column(Integer)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    provider: Mapped[str] = mapped_column(String(80), default="Local inventory")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class CartItem(Base):
    __tablename__ = "cart_items"
    __table_args__ = (CheckConstraint("quantity > 0 AND quantity <= 100"),)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    sku_id: Mapped[str] = mapped_column(ForeignKey("skus.id"), primary_key=True)
    quantity: Mapped[int] = mapped_column(Integer)


class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (CheckConstraint("total_cents > 0"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    total_cents: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(32), default="completed")
    idempotency_key: Mapped[str] = mapped_column(String(160), unique=True)
    request_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Inventory(Base):
    __tablename__ = "inventory"
    __table_args__ = (CheckConstraint("status IN ('available','reserved','sold','quarantined','invalid')"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=uid)
    sku_id: Mapped[str] = mapped_column(ForeignKey("skus.id"), index=True)
    status: Mapped[str] = mapped_column(String(32), default="available", index=True)
    provider: Mapped[str] = mapped_column(String(80), default="Local inventory")
    reference: Mapped[str] = mapped_column(String(160), unique=True)
    payload_encrypted: Mapped[str] = mapped_column(Text)
    order_id: Mapped[str | None] = mapped_column(ForeignKey("orders.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class OrderItem(Base):
    __tablename__ = "order_items"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=uid)
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id"), index=True)
    sku_id: Mapped[str] = mapped_column(ForeignKey("skus.id"))
    inventory_id: Mapped[str] = mapped_column(ForeignKey("inventory.id"), unique=True)
    sku_name: Mapped[str] = mapped_column(String(160))
    unit_price_cents: Mapped[int] = mapped_column(Integer)


class Topup(Base):
    __tablename__ = "topups"
    __table_args__ = (CheckConstraint("amount_cents > 0"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    amount_cents: Mapped[int] = mapped_column(Integer)
    method: Mapped[str] = mapped_column(String(80), default="Manual transfer")
    status: Mapped[str] = mapped_column(String(32), default="pending")
    reference: Mapped[str] = mapped_column(String(160), unique=True)
    note: Mapped[str] = mapped_column(Text, default="")
    review_note: Mapped[str] = mapped_column(Text, default="")
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Ledger(Base):
    __tablename__ = "ledger"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    amount_cents: Mapped[int] = mapped_column(Integer)
    balance_after_cents: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(32))
    reference: Mapped[str] = mapped_column(String(160), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Audit(Base):
    __tablename__ = "audit"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=uid)
    actor: Mapped[str] = mapped_column(String(120))
    action: Mapped[str] = mapped_column(String(100))
    entity_type: Mapped[str] = mapped_column(String(60))
    entity_id: Mapped[str] = mapped_column(String(160))
    detail: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Setting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str] = mapped_column(Text)


class AdminSession(Base):
    __tablename__ = "admin_sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    actor: Mapped[str] = mapped_column(String(120))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ImportBatch(Base):
    __tablename__ = "import_batches"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=uid)
    encrypted_rows: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="preview")
    count: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


def immutable_record(mapper, connection, target):
    raise ValueError("Audit and ledger records are append-only")


for model in (Audit, Ledger):
    event.listen(model, "before_update", immutable_record)
    event.listen(model, "before_delete", immutable_record)
