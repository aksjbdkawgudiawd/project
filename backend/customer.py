"""Trusted bot transport: customers never possess the internal bearer token."""
import hashlib
import hmac
import json
import os
import threading
import time
from collections import defaultdict

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import Field
from sqlalchemy import delete, func, select

from backend.models import CartItem, Inventory, Order, OrderItem, Setting, SKU, Topup, User
from backend.passwords import parse_password_hash, verify_password
from backend.schemas import CheckoutInput, SettingsInput, StrictModel
from backend.services import audit, checkout, fail, get


class QuantityInput(StrictModel):
    quantity: int = Field(strict=True, ge=0, le=100)


class ManualTopupInput(StrictModel):
    amount_cents: int = Field(strict=True, ge=100, le=1_000_000)


class UnlockInput(StrictModel):
    password: str = Field(min_length=1, max_length=256)


class PurchaseInput(StrictModel):
    quote_token: str = Field(pattern=r"^[a-f0-9]{64}$")


def cart_quote_token(items, wholesale_access):
    normalized = {"items": sorted((item["sku_id"], item["quantity"], item["price_cents"]) for item in items), "wholesale_access": wholesale_access}
    return hashlib.sha256(json.dumps(normalized, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def customer_router(db_for, *, demo=False):
    router = APIRouter(prefix="/api/bot", tags=["Trusted bot"])
    token = os.getenv("BOT_INTERNAL_TOKEN", "")
    wholesale_password_hash = os.getenv("WHOLESALE_PASSWORD_HASH", "")
    wholesale_password_enabled = demo and parse_password_hash(wholesale_password_hash) is not None
    manual_instructions = os.getenv("MANUAL_PAYMENT_INSTRUCTIONS", "")
    attempts = defaultdict(list)
    attempts_lock = threading.Lock()

    def customer(authorization: str = Header(default=""), x_telegram_id: str = Header(default=""), db=Depends(db_for)):
        if len(token) < 32:
            fail(503, "Bot transport is not configured")
        if not hmac.compare_digest(authorization.encode(), f"Bearer {token}".encode()):
            fail(401, "Invalid bot credentials")
        if not x_telegram_id.isascii() or not x_telegram_id.isdigit() or not 0 < int(x_telegram_id) < 2**63:
            fail(422, "Invalid Telegram user ID")
        identifier = "tg-" + str(int(x_telegram_id))
        with db.write() as session:
            # Serialize first-use account creation even across bot workers.
            if not db.sqlite:
                from sqlalchemy import text
                session.execute(text("SELECT pg_advisory_xact_lock(:id)"), {"id": int(x_telegram_id)})
            user = session.get(User, identifier)
            if user is None:
                session.add(User(id=identifier, name=f"Telegram user {x_telegram_id}", username=""))
                audit(session, "bot", "user.created", "user", identifier, "Zero-balance customer account")
        return identifier

    def store_settings(session):
        record = session.get(Setting, "store")
        return json.loads(record.value) if record else SettingsInput().model_dump()

    def stock_count(session, identifier):
        return session.scalar(select(func.count()).select_from(Inventory).where(Inventory.sku_id == identifier, Inventory.status == "available"))

    def cart_view(session, user, *, lock_prices=False):
        items = []
        for row in session.scalars(select(CartItem).where(CartItem.user_id == user.id).order_by(CartItem.sku_id)):
            sku = get(session, SKU, row.sku_id, lock=lock_prices)
            price = sku.wholesale_price_cents if user.wholesale_access else sku.retail_price_cents
            items.append({"sku_id": sku.id, "title": sku.name, "quantity": row.quantity, "price_cents": price, "line_total_cents": price * row.quantity})
        return {"items": items, "total_cents": sum(row["line_total_cents"] for row in items), "balance_cents": user.balance_cents, "quote_token": cart_quote_token(items, user.wholesale_access)}

    def order_view(session, order, include_delivery=False, db=None):
        result = {"id": order.id, "total_cents": order.total_cents, "status": order.status, "created_at": order.created_at}
        if include_delivery:
            items = list(session.scalars(select(OrderItem).where(OrderItem.order_id == order.id)))
            try:
                result["delivery"] = [{"title": item.sku_name, "payload": db.decrypt(session.get(Inventory, item.inventory_id).payload_encrypted)} for item in items]
            except Exception:
                # Corrupted or unavailable payloads must not leak internals or appear delivered.
                fail(503, "delivery_unavailable")
        return result

    @router.get("/config")
    def config(user=Depends(customer), db=Depends(db_for)):
        with db.read() as session:
            data = store_settings(session)
        return {"brand_name": data["store_name"], "manual_card_enabled": bool(manual_instructions), "manual_card_instructions": manual_instructions, "wholesale_password_enabled": wholesale_password_enabled, "subscription_gate": {"enabled": data["subscription_required"], "required_chat_id": os.getenv("BOT_REQUIRED_CHAT_ID", ""), "public_url": data["stock_channel_url"]}, "links": {"support": data["support_url"], "reviews": data["reviews_url"], "stock": data["stock_channel_url"], "terms": data["terms_url"]}}

    @router.get("/catalog")
    def catalog(identifier=Depends(customer), db=Depends(db_for)):
        with db.read() as session:
            user = get(session, User, identifier)
            products = list(session.scalars(select(SKU).where(SKU.active.is_(True)).order_by(SKU.name)))
            countries = {sku.country_code: {"id": sku.country_code, "code": sku.country_code, "name": sku.country, "flag": sku.flag} for sku in products}
            section = "wholesale" if user.wholesale_access else "retail"
            return {"sections": [{"id": section, "title": "Wholesale catalog" if user.wholesale_access else "Retail catalog", "title_ru": "Оптовый каталог" if user.wholesale_access else "Розничный каталог", "title_uk": "Оптовий каталог" if user.wholesale_access else "Роздрібний каталог"}], "countries": list(countries.values()), "skus": [{"id": sku.id, "title": sku.name, "description": sku.description, "section_id": section, "country_id": sku.country_code, "price_cents": sku.wholesale_price_cents if user.wholesale_access else sku.retail_price_cents, "stock": stock_count(session, sku.id), "min_quantity": 1, "max_quantity": 100, "wholesale": user.wholesale_access} for sku in products]}

    @router.get("/wallet")
    def wallet(identifier=Depends(customer), db=Depends(db_for)):
        with db.read() as session:
            user = get(session, User, identifier)
            return {"balance_cents": user.balance_cents, "currency": "USD", "wholesale_access": user.wholesale_access}

    @router.get("/cart")
    def cart(identifier=Depends(customer), db=Depends(db_for)):
        with db.read() as session:
            return cart_view(session, get(session, User, identifier))

    @router.put("/cart/items/{sku_id}")
    def quantity(sku_id: str, data: QuantityInput, identifier=Depends(customer), db=Depends(db_for)):
        with db.write() as session:
            user = get(session, User, identifier, lock=True)
            sku = get(session, SKU, sku_id)
            if data.quantity and (not sku.active or stock_count(session, sku_id) < data.quantity):
                fail(409, "insufficient_stock")
            record = session.get(CartItem, (identifier, sku_id))
            total = session.scalar(select(func.coalesce(func.sum(CartItem.quantity), 0)).where(CartItem.user_id == identifier))
            line_count = session.scalar(select(func.count()).select_from(CartItem).where(CartItem.user_id == identifier))
            if total - (record.quantity if record else 0) + data.quantity > 100 or (not record and data.quantity and line_count >= 20):
                fail(422, "Cart limit exceeded")
            if record and data.quantity:
                record.quantity = data.quantity
            elif record:
                session.delete(record)
            elif data.quantity:
                session.add(CartItem(user_id=identifier, sku_id=sku_id, quantity=data.quantity))
            session.flush()
            return cart_view(session, user)

    @router.delete("/cart")
    def clear_cart(identifier=Depends(customer), db=Depends(db_for)):
        with db.write() as session:
            user = get(session, User, identifier, lock=True)
            session.execute(delete(CartItem).where(CartItem.user_id == identifier))
            return cart_view(session, user)

    @router.post("/checkout")
    def purchase(data: PurchaseInput, idempotency_key: str = Header(min_length=8, max_length=160), identifier=Depends(customer), db=Depends(db_for)):
        key = "bot:" + hashlib.sha256(f"{identifier}:{idempotency_key}".encode()).hexdigest()
        with db.write() as session:
            user = get(session, User, identifier, lock=True)
            existing = session.scalar(select(Order).where(Order.idempotency_key == key))
            if existing:
                return {**order_view(session, existing), "replayed": True}
            # Hold deterministic SKU locks through debit, not only quote comparison.
            live_cart = cart_view(session, user, lock_prices=True)
            if not hmac.compare_digest(data.quote_token, live_cart["quote_token"]):
                fail(409, "cart_changed")
            if not live_cart["items"]:
                fail(409, "empty_cart")
            request = CheckoutInput(user_id=identifier, items=[{"sku_id": row["sku_id"], "quantity": row["quantity"]} for row in live_cart["items"]], wholesale=user.wholesale_access, idempotency_key=key, expected_total_cents=live_cart["total_cents"])
            try:
                order_id, _ = checkout(db, request, "bot:" + identifier, transaction=session)
            except HTTPException as exc:
                if exc.detail == "Insufficient wallet balance":
                    fail(409, "insufficient_balance")
                if str(exc.detail).startswith("Insufficient available stock"):
                    fail(409, "insufficient_stock")
                raise
            session.execute(delete(CartItem).where(CartItem.user_id == identifier))
            return {**order_view(session, session.get(Order, order_id)), "replayed": False}

    @router.get("/orders")
    def orders(identifier=Depends(customer), db=Depends(db_for)):
        with db.read() as session:
            return [order_view(session, order) for order in session.scalars(select(Order).where(Order.user_id == identifier).order_by(Order.created_at.desc()))]

    @router.get("/orders/{order_id}")
    def order_detail(order_id: str, identifier=Depends(customer), db=Depends(db_for)):
        with db.read() as session:
            order = session.scalar(select(Order).where(Order.id == order_id, Order.user_id == identifier))
            if order is None:
                fail(404, "Order not found")
            return order_view(session, order, include_delivery=True, db=db)

    @router.post("/topups/manual")
    def manual_topup(data: ManualTopupInput, idempotency_key: str = Header(min_length=8, max_length=160), identifier=Depends(customer), db=Depends(db_for)):
        if not manual_instructions:
            fail(503, "Manual payments are not configured")
        reference = "manual:" + hashlib.sha256(f"{identifier}:{idempotency_key}".encode()).hexdigest()
        with db.write() as session:
            get(session, User, identifier, lock=True)
            record = session.scalar(select(Topup).where(Topup.reference == reference))
            if record and record.amount_cents != data.amount_cents:
                fail(409, "Idempotency key conflicts with another amount")
            if not record:
                record = Topup(user_id=identifier, amount_cents=data.amount_cents, reference=reference, note="Customer requested top-up. Verify external settlement before approval.")
                session.add(record)
                session.flush()
                audit(session, "bot:" + identifier, "topup.requested", "topup", record.id)
            return {"id": record.id, "amount_cents": record.amount_cents, "status": record.status, "reference": record.reference, "instructions": manual_instructions}

    @router.post("/wholesale/unlock")
    def unlock(data: UnlockInput, identifier=Depends(customer), db=Depends(db_for)):
        if not wholesale_password_enabled:
            fail(503, "Wholesale password access is disabled")
        with attempts_lock:
            timestamp = time.monotonic()
            attempts[identifier] = [attempt for attempt in attempts[identifier] if timestamp - attempt < 300]
            if len(attempts[identifier]) >= 5:
                fail(429, "rate_limited")
            attempts[identifier].append(timestamp)
        if not verify_password(data.password, wholesale_password_hash):
            fail(403, "invalid_password")
        with db.write() as session:
            user = get(session, User, identifier, lock=True)
            if not user.wholesale_access:
                user.wholesale_access = True
                audit(session, "bot:" + identifier, "user.wholesale_unlocked", "user", identifier)
        return {"wholesale_access": True}

    return router
