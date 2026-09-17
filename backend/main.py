import hashlib
import hmac
import json
import os
import secrets
import threading
import time
from collections import defaultdict
from contextlib import asynccontextmanager
from datetime import timedelta
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from backend.database import Database
from backend.models import AdminSession, Audit, Inventory, Ledger, Order, OrderItem, SKU, Setting, Topup, User, now
from backend.schemas import CheckoutInput, ImportConfirmInput, ImportPreviewInput, InventoryInput, LoginInput, ReviewInput, SettingsInput, SKUInput, StatusInput, WholesaleInput
from backend.services import add_inventory, audit, checkout, confirm_import, fail, get, preview_import, review_topup

COOKIE = "arshisney_admin"


def fields(record, *names):
    return {name: getattr(record, name) for name in names}


def sku_view(session, sku):
    result = fields(sku, "id", "name", "country", "country_code", "flag", "category", "description", "retail_price_cents", "wholesale_price_cents", "active", "provider", "created_at")
    result["stock_count"] = session.scalar(select(func.count()).select_from(Inventory).where(Inventory.sku_id == sku.id, Inventory.status == "available"))
    result["sold_count"] = session.scalar(select(func.count()).select_from(Inventory).where(Inventory.sku_id == sku.id, Inventory.status == "sold"))
    return result


def inventory_view(session, unit):
    result = fields(unit, "id", "sku_id", "status", "provider", "reference", "order_id", "created_at")
    sku = session.get(SKU, unit.sku_id)
    result.update(sku_name=sku.name, country=sku.country, country_code=sku.country_code, flag=sku.flag, category=sku.category)
    return result


def order_view(session, order):
    result = fields(order, "id", "user_id", "total_cents", "status", "created_at")
    user = session.get(User, order.user_id)
    result.update(user_name=user.name, username=user.username)
    result["items"] = [fields(item, "id", "sku_id", "sku_name", "inventory_id", "unit_price_cents") for item in session.scalars(select(OrderItem).where(OrderItem.order_id == order.id))]
    result["quantity"] = len(result["items"])
    return result


def topup_view(session, topup):
    result = fields(topup, "id", "user_id", "amount_cents", "method", "status", "reference", "note", "review_note", "reviewed_at", "created_at")
    user = session.get(User, topup.user_id)
    result.update(user_name=user.name, username=user.username)
    return result


def user_view(session, user):
    result = fields(user, "id", "name", "username", "balance_cents", "wholesale_access", "created_at")
    result["orders_count"] = session.scalar(select(func.count()).select_from(Order).where(Order.user_id == user.id))
    result["total_spent_cents"] = session.scalar(select(func.coalesce(func.sum(Order.total_cents), 0)).where(Order.user_id == user.id))
    return result


def audit_view(record):
    return fields(record, "id", "actor", "action", "entity_type", "entity_id", "detail", "created_at")


def create_app(database=None, *, demo=None, seed=True):
    is_demo = os.getenv("APP_ENV") == "demo" if demo is None else demo
    username = os.getenv("ADMIN_USERNAME", "")
    password = os.getenv("ADMIN_PASSWORD", "")
    allowed_origins = {origin.rstrip("/") for origin in os.getenv("ADMIN_ALLOWED_ORIGINS", "").split(",") if origin}

    @asynccontextmanager
    async def lifespan(application):
        if not is_demo and (not username or len(password) < 16):
            raise RuntimeError("ADMIN_USERNAME and ADMIN_PASSWORD (16+ characters) are required outside demo")
        db = database or Database(demo=is_demo)
        db.initialize()
        application.state.db = db
        if is_demo and seed:
            from backend.seed import seed_demo
            seed_demo(db)
        yield
        if database is None:
            db.engine.dispose()

    app = FastAPI(title="Arshisney Marketplace API", version="0.1.0", lifespan=lifespan, docs_url="/api/docs" if is_demo else None, redoc_url=None, openapi_url="/api/openapi.json" if is_demo else None)
    attempts = defaultdict(list)
    attempts_lock = threading.Lock()

    def secure_response(response):
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        return response

    @app.middleware("http")
    async def protect_requests(request, call_next):
        origin = request.headers.get("origin")
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            if request.headers.get("sec-fetch-site") == "cross-site":
                return secure_response(JSONResponse({"detail": "Cross-site mutations are forbidden"}, status_code=403))
            if origin:
                parsed = urlparse(origin)
                same_host = parsed.netloc == request.headers.get("host") and parsed.scheme == request.url.scheme
                if not same_host and origin.rstrip("/") not in allowed_origins:
                    return secure_response(JSONResponse({"detail": "Origin is not allowed"}, status_code=403))
            length = request.headers.get("content-length", "0")
            if not length.isdigit() or int(length) > 1_100_000:
                return secure_response(JSONResponse({"detail": "Request too large"}, status_code=413))
        response = await call_next(request)
        return secure_response(response)

    @app.exception_handler(IntegrityError)
    async def conflict_handler(request, exc):
        return JSONResponse({"detail": "Conflicting record or operation; refresh and retry"}, status_code=409)

    def db_for(request: Request):
        return request.app.state.db

    def admin(request: Request, db=Depends(db_for)):
        token = request.cookies.get(COOKIE)
        if not token:
            fail(401, "Admin authentication required")
        with db.read() as session:
            record = session.get(AdminSession, hashlib.sha256(token.encode()).hexdigest())
            expires = record.expires_at if record else None
            if expires and expires.tzinfo is None:
                expires = expires.replace(tzinfo=now().tzinfo)
            if not record or expires <= now():
                fail(401, "Admin session expired")
            return record.actor

    def new_session(db, response, actor):
        token = secrets.token_urlsafe(48)
        with db.write() as session:
            session.add(AdminSession(token_hash=hashlib.sha256(token.encode()).hexdigest(), actor=actor, expires_at=now() + timedelta(hours=8)))
            audit(session, actor, "admin.login", "admin", actor)
        response.set_cookie(COOKIE, token, httponly=True, secure=not is_demo, samesite="strict", max_age=28800, path="/")
        return {"username": actor, "name": "Demo Administrator" if is_demo else actor, "role": "administrator", "demo": is_demo}

    @app.get("/api/v1/health")
    def health(db=Depends(db_for)):
        with db.read() as session:
            session.execute(select(1))
        return {"status": "ok", "environment": "demo" if is_demo else "production", "providers_connected": False}

    @app.post("/api/v1/admin/auth/demo")
    def demo_login(response: Response, db=Depends(db_for)):
        if not is_demo:
            fail(404, "Not found")
        return new_session(db, response, "demo-admin")

    @app.post("/api/v1/admin/auth/login")
    def login(data: LoginInput, request: Request, response: Response, db=Depends(db_for)):
        address = request.client.host if request.client else "unknown"
        with attempts_lock:
            timestamp = time.monotonic()
            attempts[address] = [t for t in attempts[address] if timestamp - t < 300]
            if len(attempts[address]) >= 10:
                fail(429, "Too many login attempts; try again in five minutes")
            attempts[address].append(timestamp)
        if not username or not password or not (hmac.compare_digest(data.username.encode(), username.encode()) & hmac.compare_digest(data.password.encode(), password.encode())):
            fail(401, "Invalid credentials")
        return new_session(db, response, username)

    router = APIRouter(prefix="/api/v1/admin", dependencies=[Depends(admin)])

    @router.get("/auth/me")
    def me(actor=Depends(admin)):
        return {"username": actor, "name": "Demo Administrator" if is_demo else actor, "role": "administrator", "demo": is_demo}

    @router.post("/auth/logout")
    def logout(request: Request, response: Response, db=Depends(db_for), actor=Depends(admin)):
        with db.write() as session:
            record = session.get(AdminSession, hashlib.sha256(request.cookies[COOKIE].encode()).hexdigest())
            session.delete(record)
            audit(session, actor, "admin.logout", "admin", actor)
        response.delete_cookie(COOKIE, path="/")
        return {"ok": True}

    @router.get("/skus")
    def skus(db=Depends(db_for)):
        with db.read() as session:
            return [sku_view(session, sku) for sku in session.scalars(select(SKU).order_by(SKU.created_at))]

    @router.post("/skus", status_code=201)
    def create_sku(data: SKUInput, db=Depends(db_for), actor=Depends(admin)):
        with db.write() as session:
            sku = SKU(**data.model_dump())
            session.add(sku)
            session.flush()
            audit(session, actor, "sku.created", "sku", sku.id, sku.name)
            return sku_view(session, sku)

    @router.put("/skus/{identifier}")
    def update_sku(identifier: str, data: SKUInput, db=Depends(db_for), actor=Depends(admin)):
        with db.write() as session:
            sku = get(session, SKU, identifier, lock=True)
            for key, value in data.model_dump().items():
                setattr(sku, key, value)
            audit(session, actor, "sku.updated", "sku", sku.id, sku.name)
            return sku_view(session, sku)

    @router.delete("/skus/{identifier}")
    def disable_sku(identifier: str, db=Depends(db_for), actor=Depends(admin)):
        with db.write() as session:
            sku = get(session, SKU, identifier, lock=True)
            if sku.active:
                sku.active = False
                audit(session, actor, "sku.disabled", "sku", sku.id)
            return sku_view(session, sku)

    @router.get("/inventory")
    def inventory(db=Depends(db_for)):
        with db.read() as session:
            return [inventory_view(session, unit) for unit in session.scalars(select(Inventory).order_by(Inventory.created_at.desc()))]

    @router.post("/inventory", status_code=201)
    def create_inventory(data: InventoryInput, db=Depends(db_for), actor=Depends(admin)):
        with db.write() as session:
            return inventory_view(session, add_inventory(db, session, data, actor))

    @router.post("/inventory/import/preview")
    def import_preview(data: ImportPreviewInput, db=Depends(db_for), actor=Depends(admin)):
        return preview_import(db, data, actor)

    @router.post("/inventory/import/confirm")
    def import_confirm(data: ImportConfirmInput, db=Depends(db_for), actor=Depends(admin)):
        return confirm_import(db, data.batch_id, actor)

    @router.post("/inventory/{identifier}/status")
    def inventory_status(identifier: str, data: StatusInput, db=Depends(db_for), actor=Depends(admin)):
        with db.write() as session:
            unit = get(session, Inventory, identifier, lock=True)
            if unit.status in ("sold", "reserved"):
                fail(409, "Sold or reserved inventory cannot be changed")
            if data.status == "available":
                from cryptography.fernet import InvalidToken
                try:
                    if not db.decrypt(unit.payload_encrypted).strip():
                        fail(409, "Payload is not deliverable")
                except InvalidToken:
                    fail(409, "Payload is not deliverable")
            if unit.status != data.status:
                previous = unit.status
                unit.status = data.status
                audit(session, actor, "inventory.status_changed", "inventory", unit.id, f"{previous} → {data.status}: {data.reason}")
            return inventory_view(session, unit)

    @router.get("/orders")
    def orders(db=Depends(db_for)):
        with db.read() as session:
            return [order_view(session, order) for order in session.scalars(select(Order).order_by(Order.created_at.desc()))]

    @router.get("/orders/{identifier}")
    def order_detail(identifier: str, db=Depends(db_for)):
        with db.read() as session:
            return order_view(session, get(session, Order, identifier))

    @router.get("/topups")
    def topups(db=Depends(db_for)):
        with db.read() as session:
            return [topup_view(session, topup) for topup in session.scalars(select(Topup).order_by(Topup.created_at.desc()))]

    @router.post("/topups/{identifier}/review")
    def topup_review(identifier: str, data: ReviewInput, db=Depends(db_for), actor=Depends(admin)):
        identifier, replayed = review_topup(db, identifier, data, actor)
        with db.read() as session:
            return {**topup_view(session, get(session, Topup, identifier)), "replayed": replayed}

    @router.get("/users")
    def users(db=Depends(db_for)):
        with db.read() as session:
            return [user_view(session, user) for user in session.scalars(select(User).order_by(User.created_at))]

    @router.post("/users/{identifier}/wholesale")
    def wholesale(identifier: str, data: WholesaleInput, db=Depends(db_for), actor=Depends(admin)):
        with db.write() as session:
            user = get(session, User, identifier, lock=True)
            if user.wholesale_access != data.wholesale_access:
                user.wholesale_access = data.wholesale_access
                audit(session, actor, "user.wholesale_changed", "user", user.id, str(data.wholesale_access))
            return user_view(session, user)

    @router.get("/providers")
    def providers():
        return [{"id": identifier, "name": name, "type": kind, "status": "unconfigured", "enabled": False, "connected": False, "description": description, "last_sync_at": None} for identifier, name, kind, description in [
            ("cryptobot", "CryptoBot", "payment", "Crypto top-ups. Credentials and webhook verification not configured."),
            ("xrocket", "xRocket", "payment", "Crypto top-ups. No live connection."),
            ("heleket", "Heleket", "payment", "Crypto payment gateway. No live connection."),
            ("manual", "Manual transfer", "payment", "Operator review workflow only. No bank integration or payment instructions configured."),
            ("inventory-api", "External inventory", "inventory", "Authorized supplier adapter not implemented. Local encrypted stock is available."),
        ]]

    @router.get("/audit")
    def audit_log(db=Depends(db_for)):
        with db.read() as session:
            return [audit_view(row) for row in session.scalars(select(Audit).order_by(Audit.created_at.desc()).limit(1000))]

    @router.get("/ledger")
    def ledger(db=Depends(db_for)):
        with db.read() as session:
            return [fields(row, "id", "user_id", "amount_cents", "balance_after_cents", "kind", "reference", "created_at") for row in session.scalars(select(Ledger).order_by(Ledger.created_at.desc()).limit(1000))]

    @router.get("/settings")
    def settings(db=Depends(db_for)):
        with db.read() as session:
            setting = session.get(Setting, "store")
            return json.loads(setting.value) if setting else SettingsInput().model_dump()

    @router.put("/settings")
    def update_settings(data: SettingsInput, db=Depends(db_for), actor=Depends(admin)):
        with db.write() as session:
            record = session.get(Setting, "store", with_for_update=True)
            if record:
                record.value = data.model_dump_json()
            else:
                session.add(Setting(key="store", value=data.model_dump_json()))
            audit(session, actor, "settings.updated", "settings", "store")
        return data.model_dump()

    @router.post("/demo/checkout")
    def demo_checkout(data: CheckoutInput, db=Depends(db_for), actor=Depends(admin)):
        if not is_demo:
            fail(404, "Not found")
        identifier, replayed = checkout(db, data, actor)
        with db.read() as session:
            return {**order_view(session, get(session, Order, identifier)), "replayed": replayed}

    @router.get("/dashboard")
    def dashboard(db=Depends(db_for)):
        with db.read() as session:
            all_orders = list(session.scalars(select(Order).order_by(Order.created_at.desc())))
            all_skus = [sku_view(session, sku) for sku in session.scalars(select(SKU))]
            today = now().date()
            chart = []
            for offset in range(13, -1, -1):
                day = today - timedelta(days=offset)
                matching = [order for order in all_orders if order.created_at.date() == day]
                chart.append({"date": str(day), "label": day.strftime("%b %d"), "revenue_cents": sum(order.total_cents for order in matching), "orders": len(matching)})
            recent = [order_view(session, order) for order in all_orders[:5]]
            revenue = sum(order.total_cents for order in all_orders)
            stock = sum(sku["stock_count"] for sku in all_skus)
            user_count = session.scalar(select(func.count()).select_from(User))
            pending = session.scalar(select(func.count()).select_from(Topup).where(Topup.status == "pending"))
            wallet_liability = session.scalar(select(func.coalesce(func.sum(User.balance_cents), 0)))
            reserved_stock = session.scalar(select(func.count()).select_from(Inventory).where(Inventory.status == "reserved"))
            pending_manual = session.scalar(select(func.count()).select_from(Topup).where(Topup.status == "pending", Topup.method == "Manual transfer"))
            setting = session.get(Setting, "store")
            threshold = json.loads(setting.value).get("low_stock_threshold", 5) if setting else 5
            low_stock = sorted((sku for sku in all_skus if sku["active"] and sku["stock_count"] <= threshold), key=lambda sku: (sku["stock_count"], sku["name"]))
            top_products = sorted(all_skus, key=lambda sku: sku["sold_count"], reverse=True)[:5]
            for product in top_products:
                product["revenue_cents"] = session.scalar(select(func.coalesce(func.sum(OrderItem.unit_price_cents), 0)).where(OrderItem.sku_id == product["id"]))
            return {"revenue_cents": revenue, "revenue_change": None, "orders_count": len(all_orders), "orders_change": None, "stock_count": stock, "stock_change": None, "users_count": user_count, "users_change": None, "pending_topups": pending, "wallet_liability_cents": wallet_liability, "reserved_stock": reserved_stock, "pending_manual_payments": pending_manual, "failed_deliveries": None, "low_stock": low_stock, "low_stock_count": len(low_stock), "revenue_chart": chart, "recent_orders": recent, "activity": [audit_view(row) for row in session.scalars(select(Audit).order_by(Audit.created_at.desc()).limit(8))], "top_products": top_products, "demo": is_demo}

    app.include_router(router)
    from backend.customer import customer_router
    app.include_router(customer_router(db_for, demo=is_demo))
    return app


app = create_app()
