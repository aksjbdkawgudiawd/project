import json
from concurrent.futures import ThreadPoolExecutor

import pytest
from cryptography.fernet import Fernet
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.exc import DatabaseError

from backend.database import Database
from backend.main import COOKIE, create_app
from backend.models import Audit, Inventory, Ledger, Order, OrderItem, SKU, Topup, User
from backend.passwords import hash_password, verify_password
from backend.schemas import CheckoutInput, InventoryInput, ReviewInput
from backend.services import add_inventory, checkout, move_balance, review_topup


@pytest.fixture
def db(tmp_path):
    database = Database(f"sqlite:///{tmp_path}/test.sqlite3", key=Fernet.generate_key(), demo=True)
    database.initialize()
    with database.write() as session:
        session.add_all([User(id="u1", name="One"), User(id="u2", name="Two")])
        session.add(SKU(id="sku", name="Synthetic license", country="United States", country_code="US", retail_price_cents=500, wholesale_price_cents=350))
        session.add(SKU(id="empty", name="Empty", country="Ukraine", country_code="UA", retail_price_cents=900, wholesale_price_cents=700))
        session.flush()
        for user in session.scalars(select(User)):
            move_balance(session, user, 5000, "demo_seed", "opening:" + user.id, "test")
        for index in range(3):
            add_inventory(database, session, InventoryInput(sku_id="sku", reference=f"ref-{index}", payload=f"PRIVATE-PAYLOAD-{index}"), "test")
        session.add(Topup(id="topup", user_id="u1", amount_cents=1200, reference="payment-reference"))
    yield database
    database.engine.dispose()


@pytest.fixture(scope="module")
def wholesale_hash():
    return hash_password("synthetic-wholesale-password")


@pytest.fixture
def bot_headers(monkeypatch):
    token = "synthetic-bot-token-" + "x" * 32
    monkeypatch.setenv("BOT_INTERNAL_TOKEN", token)
    return {"Authorization": f"Bearer {token}", "X-Telegram-Id": "12345"}


def test_wholesale_hash_is_salted_and_verifies(wholesale_hash):
    assert wholesale_hash != hash_password("synthetic-wholesale-password")
    assert "synthetic-wholesale-password" not in wholesale_hash
    assert verify_password("synthetic-wholesale-password", wholesale_hash)
    assert not verify_password("incorrect-password", wholesale_hash)
    assert not verify_password("synthetic-wholesale-password", "invalid-hash")


def test_demo_wholesale_correct_wrong_password_and_replay(db, monkeypatch, bot_headers, wholesale_hash):
    monkeypatch.setenv("WHOLESALE_PASSWORD_HASH", wholesale_hash)
    with TestClient(create_app(db, demo=True, seed=False), headers=bot_headers) as bot:
        assert bot.get("/api/bot/config").json()["wholesale_password_enabled"] is True
        wrong = bot.post("/api/bot/wholesale/unlock", json={"password": "wrong-password"})
        assert wrong.status_code == 403
        assert wrong.json()["detail"] == "invalid_password"
        assert bot.get("/api/bot/wallet").json()["wholesale_access"] is False
        for _ in range(2):
            result = bot.post("/api/bot/wholesale/unlock", json={"password": "synthetic-wholesale-password"})
            assert result.status_code == 200
            assert result.json() == {"wholesale_access": True}
        assert bot.get("/api/bot/wallet").json()["wholesale_access"] is True
    with db.read() as session:
        assert session.scalar(select(func.count()).select_from(Audit).where(Audit.action == "user.wholesale_unlocked")) == 1


def test_demo_wholesale_password_attempts_are_limited(db, monkeypatch, bot_headers, wholesale_hash):
    monkeypatch.setenv("WHOLESALE_PASSWORD_HASH", wholesale_hash)
    with TestClient(create_app(db, demo=True, seed=False), headers=bot_headers) as bot:
        for _ in range(5):
            assert bot.post("/api/bot/wholesale/unlock", json={"password": "incorrect-password"}).status_code == 403
        assert bot.post("/api/bot/wholesale/unlock", json={"password": "synthetic-wholesale-password"}).status_code == 429
        assert bot.get("/api/bot/wallet").json()["wholesale_access"] is False


@pytest.mark.parametrize("encoded", ["", "malformed", "scrypt-v1$00$00"])
def test_plaintext_and_malformed_wholesale_configuration_fail_closed(db, monkeypatch, bot_headers, encoded):
    monkeypatch.setenv("WHOLESALE_PASSWORD", "legacy-plaintext-password")
    monkeypatch.setenv("WHOLESALE_PASSWORD_HASH", encoded)
    with TestClient(create_app(db, demo=True, seed=False), headers=bot_headers) as bot:
        assert bot.get("/api/bot/config").json()["wholesale_password_enabled"] is False
        assert bot.post("/api/bot/wholesale/unlock", json={"password": "legacy-plaintext-password"}).status_code == 503


def test_production_wholesale_password_disabled_but_admin_grants_work(db, monkeypatch, bot_headers, wholesale_hash):
    monkeypatch.setenv("ADMIN_USERNAME", "admin")
    monkeypatch.setenv("ADMIN_PASSWORD", "a-long-test-password-123")
    monkeypatch.setenv("WHOLESALE_PASSWORD_HASH", wholesale_hash)
    monkeypatch.setenv("APP_ENV", "demo")
    with TestClient(create_app(db, demo=False, seed=False), base_url="https://testserver", headers=bot_headers) as bot:
        assert bot.get("/api/bot/config").json()["wholesale_password_enabled"] is False
        assert bot.post("/api/bot/wholesale/unlock", json={"password": "synthetic-wholesale-password"}).status_code == 503
        assert bot.get("/api/bot/wallet").json()["wholesale_access"] is False
        bot.post("/api/v1/admin/auth/login", json={"username": "admin", "password": "a-long-test-password-123"}).raise_for_status()
        bot.post("/api/v1/admin/users/tg-12345/wholesale", json={"wholesale_access": True}).raise_for_status()
        assert bot.get("/api/bot/wallet").json()["wholesale_access"] is True
        assert all(sku["wholesale"] for sku in bot.get("/api/bot/catalog").json()["skus"])


@pytest.fixture
def client(db):
    with TestClient(create_app(db, demo=True, seed=False)) as client:
        assert client.post("/api/v1/admin/auth/demo").status_code == 200
        yield client


def cart(key="checkout-key", user="u1", quantity=1, **kwargs):
    return CheckoutInput(user_id=user, items=[{"sku_id": "sku", "quantity": quantity}], idempotency_key=key, **kwargs)


def balance(db, user="u1"):
    with db.read() as session:
        return session.get(User, user).balance_cents


def count(db, model):
    with db.read() as session:
        return session.scalar(select(func.count()).select_from(model))


def test_atomic_checkout_and_replay(db):
    identifier, replayed = checkout(db, cart(quantity=2), "test")
    assert not replayed
    assert balance(db) == 4000
    assert checkout(db, cart(quantity=2), "test") == (identifier, True)
    assert balance(db) == 4000
    assert count(db, Order) == 1
    assert count(db, OrderItem) == 2
    with db.read() as session:
        assert session.scalar(select(func.count()).select_from(Inventory).where(Inventory.status == "sold")) == 2
        assert session.scalar(select(func.count()).select_from(Ledger).where(Ledger.kind == "purchase")) == 1
        assert len(session.scalars(select(Audit).where(Audit.action == "inventory.reserved")).all()) == 2


def test_changed_replay_rejected(db):
    checkout(db, cart(), "test")
    with pytest.raises(HTTPException) as exc:
        checkout(db, cart(quantity=2), "test")
    assert exc.value.status_code == 409
    assert balance(db) == 4500


def test_other_user_cannot_replay_order(db):
    checkout(db, cart(), "test")
    with pytest.raises(HTTPException) as exc:
        checkout(db, cart(user="u2"), "test")
    assert exc.value.status_code == 409
    assert balance(db, "u2") == 5000


def test_insufficient_stock_rolls_back_entire_cart(db):
    request = CheckoutInput(user_id="u1", items=[{"sku_id": "sku", "quantity": 1}, {"sku_id": "empty", "quantity": 1}], idempotency_key="atomic-cart")
    before = count(db, Audit)
    with pytest.raises(HTTPException):
        checkout(db, request, "test")
    assert balance(db) == 5000
    assert count(db, Order) == 0
    assert count(db, Audit) == before
    with db.read() as session:
        assert all(unit.status == "available" for unit in session.scalars(select(Inventory)))


def test_insufficient_balance_rolls_back_stock(db):
    with db.write() as session:
        move_balance(session, session.get(User, "u1"), -4900, "adjustment", "reduce", "test")
    with pytest.raises(HTTPException):
        checkout(db, cart(), "test")
    assert balance(db) == 100
    assert count(db, Order) == 0
    with db.read() as session:
        assert all(unit.status == "available" for unit in session.scalars(select(Inventory)))


@pytest.mark.parametrize("wholesale,expected_total", [(False, 1400), (True, 1050)])
def test_full_cart_balance_checked_before_any_preflight(db, monkeypatch, wholesale, expected_total):
    from unittest.mock import Mock

    with db.write() as session:
        user = session.get(User, "u1")
        user.wholesale_access = wholesale
        move_balance(session, user, expected_total - 1 - user.balance_cents, "test_adjustment", "adjustment:u1", "test")
    decrypt = Mock(side_effect=AssertionError("Unaffordable checkout must not decrypt inventory"))
    monkeypatch.setattr(db, "decrypt", decrypt)
    request = CheckoutInput(user_id="u1", items=[{"sku_id": "sku", "quantity": 1}, {"sku_id": "empty", "quantity": 1}], wholesale=wholesale, idempotency_key="early-balance-check")
    before_audit = count(db, Audit)
    before_ledger = count(db, Ledger)
    with pytest.raises(HTTPException) as exc:
        checkout(db, request, "test")
    assert exc.value.detail == "Insufficient wallet balance"
    decrypt.assert_not_called()
    assert count(db, Audit) == before_audit
    assert count(db, Ledger) == before_ledger
    assert count(db, Order) == 0
    assert balance(db) == expected_total - 1
    with db.read() as session:
        assert all(unit.status == "available" for unit in session.scalars(select(Inventory)))


def test_exact_balance_checkout_replays_after_wallet_empty(db):
    with db.write() as session:
        move_balance(session, session.get(User, "u1"), -4500, "test_adjustment", "adjustment:u1", "test")
    identifier, replayed = checkout(db, cart(), "test")
    assert not replayed
    assert balance(db) == 0
    assert checkout(db, cart(), "test") == (identifier, True)


def test_preflight_skips_corrupt_payload(db):
    with db.write() as session:
        unit = session.scalar(select(Inventory).order_by(Inventory.created_at).limit(1))
        identifier = unit.id
        unit.payload_encrypted = "corrupted"
    checkout(db, cart(quantity=2), "test")
    with db.read() as session:
        assert session.get(Inventory, identifier).status == "invalid"
    assert balance(db) == 4000


def test_simultaneous_buyers_cannot_oversell(db):
    def buy(index):
        try:
            return checkout(db, cart(key=f"concurrent-{index}", user="u1" if index % 2 else "u2"), "race")
        except HTTPException as exc:
            assert exc.status_code == 409
            return None
    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(buy, range(10)))
    assert sum(result is not None for result in results) == 3
    assert count(db, Order) == 3
    assert count(db, OrderItem) == 3
    assert balance(db) + balance(db, "u2") == 8500


def test_concurrent_replay_charges_once(db):
    with ThreadPoolExecutor(max_workers=6) as executor:
        results = list(executor.map(lambda _: checkout(db, cart(), "race"), range(6)))
    assert len({result[0] for result in results}) == 1
    assert sum(not result[1] for result in results) == 1
    assert balance(db) == 4500


def test_wholesale_is_enforced_and_priced(db):
    with pytest.raises(HTTPException) as exc:
        checkout(db, cart(wholesale=True), "test")
    assert exc.value.status_code == 403
    with db.write() as session:
        session.get(User, "u1").wholesale_access = True
    checkout(db, cart(wholesale=True), "test")
    assert balance(db) == 4650


def test_manual_payment_approval_replay_and_conflict(db):
    data = ReviewInput(decision="approve", note="Verified external settlement")
    with ThreadPoolExecutor(max_workers=5) as executor:
        results = list(executor.map(lambda _: review_topup(db, "topup", data, "operator"), range(5)))
    assert sum(not result[1] for result in results) == 1
    assert balance(db) == 6200
    with pytest.raises(HTTPException):
        review_topup(db, "topup", ReviewInput(decision="reject", note="Changed decision"), "operator")
    with db.read() as session:
        assert session.scalar(select(func.count()).select_from(Ledger).where(Ledger.kind == "topup")) == 1


def test_manual_payment_rejection_never_credits(db):
    review_topup(db, "topup", ReviewInput(decision="reject", note="No settlement found"), "operator")
    assert balance(db) == 5000


@pytest.mark.parametrize("table", ["audit", "ledger"])
@pytest.mark.parametrize("operation", ["DELETE FROM {table}", "UPDATE {table} SET id = 'tampered'"])
def test_database_enforces_append_only(db, table, operation):
    with pytest.raises(DatabaseError):
        with db.engine.begin() as connection:
            connection.execute(text(operation.format(table=table)))


def test_admin_auth_is_required(db):
    with TestClient(create_app(db, demo=True, seed=False)) as anonymous:
        for path in ["dashboard", "skus", "inventory", "orders", "topups", "users", "providers", "audit", "settings", "ledger"]:
            assert anonymous.get("/api/v1/admin/" + path).status_code == 401
        assert anonymous.post("/api/v1/admin/topups/topup/review", json={"decision": "approve", "note": "malicious"}).status_code == 401


def test_session_logout_and_cookie_flags(client):
    response = client.post("/api/v1/admin/auth/demo")
    cookie = response.headers["set-cookie"]
    assert "HttpOnly" in cookie and "SameSite=strict" in cookie
    assert client.get("/api/v1/admin/auth/me").status_code == 200
    token = client.cookies.get(COOKIE)
    assert client.post("/api/v1/admin/auth/logout").status_code == 200
    client.cookies.set(COOKIE, token)
    assert client.get("/api/v1/admin/users").status_code == 401


def test_cross_origin_mutation_is_blocked(client):
    response = client.post("/api/v1/admin/topups/topup/review", json={"decision": "approve", "note": "forged review"}, headers={"Origin": "https://evil.example"})
    assert response.status_code == 403
    assert client.post("/api/v1/admin/auth/demo", headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403


def test_login_requires_matching_origin_scheme_and_has_security_headers(client):
    assert client.post("/api/v1/admin/auth/demo", headers={"Origin": "http://testserver"}).status_code == 200
    denied = client.post("/api/v1/admin/auth/demo", headers={"Origin": "https://testserver"})
    assert denied.status_code == 403
    for response in (denied, client.get("/api/v1/admin/dashboard")):
        assert response.headers["Cache-Control"] == "no-store"
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert response.headers["Referrer-Policy"] == "no-referrer"
        assert response.headers["X-Frame-Options"] == "DENY"


def test_dashboard_operational_metrics_follow_real_records(client, db):
    with db.write() as session:
        session.scalar(select(Inventory).where(Inventory.reference == "ref-0")).status = "reserved"
        session.add(Topup(id="other-method", user_id="u1", amount_cents=200, reference="other-method", method="Disabled provider"))
    response = client.get("/api/v1/admin/dashboard")
    assert response.status_code == 200
    data = response.json()
    assert data["wallet_liability_cents"] == 10000
    assert data["reserved_stock"] == 1
    assert data["pending_manual_payments"] == 1
    assert data["pending_topups"] == 2
    assert data["failed_deliveries"] is None
    assert [(sku["id"], sku["stock_count"]) for sku in data["low_stock"]] == [("empty", 0), ("sku", 2)]
    assert data["low_stock_count"] == len(data["low_stock"])
    client.post("/api/v1/admin/topups/topup/review", json={"decision": "approve", "note": "Verified payment"}).raise_for_status()
    checkout(db, cart(), "test")
    data = client.get("/api/v1/admin/dashboard").json()
    assert data["wallet_liability_cents"] == 10700
    assert data["pending_manual_payments"] == 0


def test_payloads_encrypted_and_never_in_admin_responses(db, client):
    for path in ["inventory", "audit", "orders", "dashboard"]:
        response = client.get("/api/v1/admin/" + path)
        assert response.status_code == 200
        assert "PRIVATE-PAYLOAD" not in response.text
        assert "payload_encrypted" not in response.text
    with db.read() as session:
        unit = session.scalar(select(Inventory))
        assert "PRIVATE-PAYLOAD" not in unit.payload_encrypted
        assert db.decrypt(unit.payload_encrypted).startswith("PRIVATE-PAYLOAD")


def test_import_preview_confirm_is_atomic_and_idempotent(client, db):
    request = {"format": "csv", "sku_id": "sku", "content": "reference,payload\nnew-1,SECRET-ONE\nnew-2,SECRET-TWO\n"}
    response = client.post("/api/v1/admin/inventory/import/preview", json=request)
    assert response.status_code == 200
    preview = response.json()
    assert preview["valid_count"] == 2 and not preview["errors"]
    assert "SECRET" not in response.text
    assert count(db, Inventory) == 3
    confirm = client.post("/api/v1/admin/inventory/import/confirm", json={"batch_id": preview["batch_id"]})
    assert confirm.status_code == 200
    assert confirm.json()["imported_count"] == 2
    assert client.post("/api/v1/admin/inventory/import/confirm", json={"batch_id": preview["batch_id"]}).json()["replayed"]
    assert count(db, Inventory) == 5


def test_import_errors_prevent_partial_import(client, db):
    request = {"format": "json", "content": json.dumps([{"sku_id": "sku", "reference": "new-ref", "payload": "secret"}, {"sku_id": "sku", "reference": "ref-0", "payload": "secret"}])}
    preview = client.post("/api/v1/admin/inventory/import/preview", json=request).json()
    assert preview["batch_id"] is None
    assert preview["errors"][0]["row"] == 2
    assert count(db, Inventory) == 3


def test_confirm_rechecks_conflicting_inventory(client, db):
    row = {"sku_id": "sku", "reference": "race-ref", "payload": "secret"}
    preview = client.post("/api/v1/admin/inventory/import/preview", json={"format": "json", "content": json.dumps([row])}).json()
    assert client.post("/api/v1/admin/inventory", json=row).status_code == 201
    assert client.post("/api/v1/admin/inventory/import/confirm", json={"batch_id": preview["batch_id"]}).status_code == 409
    assert count(db, Inventory) == 4


def test_sold_stock_cannot_be_reactivated(client, db):
    identifier, _ = checkout(db, cart(), "test")
    order = client.get(f"/api/v1/admin/orders/{identifier}").json()
    unit = order["items"][0]["inventory_id"]
    assert client.post(f"/api/v1/admin/inventory/{unit}/status", json={"status": "available"}).status_code == 409


def test_production_fails_closed(db, monkeypatch):
    monkeypatch.delenv("ADMIN_USERNAME", raising=False)
    monkeypatch.delenv("ADMIN_PASSWORD", raising=False)
    with pytest.raises(RuntimeError, match="ADMIN_USERNAME"):
        with TestClient(create_app(db, demo=False, seed=False)):
            pass
    monkeypatch.delenv("INVENTORY_ENCRYPTION_KEY", raising=False)
    with pytest.raises(RuntimeError, match="INVENTORY_ENCRYPTION_KEY"):
        Database(demo=False)


def test_production_has_no_demo_and_secure_cookie(db, monkeypatch):
    monkeypatch.setenv("ADMIN_USERNAME", "admin")
    monkeypatch.setenv("ADMIN_PASSWORD", "a-long-test-password-123")
    with TestClient(create_app(db, demo=False, seed=False), base_url="https://testserver") as production:
        assert production.post("/api/v1/admin/auth/demo").status_code == 404
        response = production.post("/api/v1/admin/auth/login", json={"username": "admin", "password": "a-long-test-password-123"})
        assert response.status_code == 200
        assert "Secure" in response.headers["set-cookie"]
        assert production.post("/api/v1/admin/demo/checkout", json=cart().model_dump()).status_code == 404
        assert production.get("/api/docs").status_code == 404


def test_reject_noninteger_money_and_unsafe_links(client):
    sku = {"name": "Test", "country": "US", "country_code": "US", "retail_price_cents": 10.1, "wholesale_price_cents": 5}
    assert client.post("/api/v1/admin/skus", json=sku).status_code == 422
    assert client.put("/api/v1/admin/settings", json={"support_url": "javascript:alert(1)"}).status_code == 422


def test_settings_and_maintenance(client, db):
    response = client.put("/api/v1/admin/settings", json={"store_name": "Test store", "maintenance_mode": True})
    assert response.status_code == 200
    assert client.get("/api/v1/admin/settings").json()["store_name"] == "Test store"
    with pytest.raises(HTTPException):
        checkout(db, cart(), "test")
    assert balance(db) == 5000


def test_seed_smoke_and_provider_truth(tmp_path):
    database = Database(f"sqlite:///{tmp_path}/seed.db", key=Fernet.generate_key(), demo=True)
    with TestClient(create_app(database, demo=True)) as client:
        client.post("/api/v1/admin/auth/demo")
        for path in ["dashboard", "skus", "inventory", "orders", "topups", "users", "providers", "audit", "settings"]:
            assert client.get("/api/v1/admin/" + path).status_code == 200
        assert all(not provider["connected"] and not provider["enabled"] for provider in client.get("/api/v1/admin/providers").json())
        assert client.get("/api/v1/admin/dashboard").json()["orders_count"] == 18
    database.engine.dispose()
