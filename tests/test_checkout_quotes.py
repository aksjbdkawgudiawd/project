import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from backend.customer import cart_quote_token
from backend.database import Database
from backend.main import create_app
from backend.models import Inventory, Ledger, Order, SKU, User
from backend.schemas import InventoryInput
from backend.services import add_inventory, move_balance


@pytest.fixture
def shop(tmp_path, monkeypatch):
    token = "synthetic-quote-test-token-" + "x" * 32
    monkeypatch.setenv("BOT_INTERNAL_TOKEN", token)
    db = Database(f"sqlite:///{tmp_path}/quotes.db", key=Fernet.generate_key(), demo=True)
    db.initialize()
    with db.write() as session:
        user = User(id="tg-77", name="Synthetic buyer", balance_cents=0)
        session.add(user)
        for identifier in ("first", "second"):
            session.add(SKU(id=identifier, name=identifier, country="United States", country_code="US", retail_price_cents=500, wholesale_price_cents=500))
        session.flush()
        move_balance(session, user, 20000, "test_opening", "test-opening", "fixture")
        for identifier in ("first", "second"):
            for index in range(3):
                add_inventory(db, session, InventoryInput(sku_id=identifier, reference=f"{identifier}-{index}", payload="SYNTHETIC-TEST-ONLY"), "fixture")
    with TestClient(create_app(db, demo=True, seed=False), headers={"Authorization": f"Bearer {token}", "X-Telegram-Id": "77"}) as client:
        client.put("/api/bot/cart/items/first", json={"quantity": 1}).raise_for_status()
        yield client, db
    db.engine.dispose()


def assert_no_purchase(db):
    with db.read() as session:
        assert session.get(User, "tg-77").balance_cents == 20000
        assert session.scalar(select(func.count()).select_from(Order)) == 0
        assert session.scalar(select(func.count()).select_from(Ledger).where(Ledger.kind == "purchase")) == 0
        assert session.scalar(select(func.count()).select_from(Inventory).where(Inventory.status == "available")) == 6


@pytest.mark.parametrize("mutation", ["price_increase", "quantity", "replace_equal_price", "grant_access", "revoke_access", "clear_cart"])
def test_stale_quote_rejects_without_preflight_or_debit(shop, monkeypatch, mutation):
    client, db = shop
    if mutation == "revoke_access":
        with db.write() as session:
            session.get(User, "tg-77").wholesale_access = True
    quote = client.get("/api/bot/cart").json()["quote_token"]
    if mutation == "price_increase":
        with db.write() as session:
            session.get(SKU, "first").retail_price_cents = 9000
    elif mutation == "quantity":
        client.put("/api/bot/cart/items/first", json={"quantity": 2}).raise_for_status()
    elif mutation == "replace_equal_price":
        client.put("/api/bot/cart/items/first", json={"quantity": 0}).raise_for_status()
        client.put("/api/bot/cart/items/second", json={"quantity": 1}).raise_for_status()
    elif mutation == "clear_cart":
        client.delete("/api/bot/cart").raise_for_status()
    else:
        with db.write() as session:
            session.get(User, "tg-77").wholesale_access = mutation == "grant_access"

    def forbidden_preflight(_):
        pytest.fail("A stale quote must fail before inventory preflight")

    monkeypatch.setattr(db, "decrypt", forbidden_preflight)
    response = client.post("/api/bot/checkout", json={"quote_token": quote}, headers={"Idempotency-Key": "stale-quote-key"})
    assert response.status_code == 409
    assert response.json()["detail"] == "cart_changed"
    assert_no_purchase(db)


def test_refreshed_quote_works_and_replay_precedes_live_quote(shop):
    client, db = shop
    with db.write() as session:
        session.get(SKU, "first").retail_price_cents = 9000
    cart = client.get("/api/bot/cart").json()
    response = client.post("/api/bot/checkout", json={"quote_token": cart["quote_token"]}, headers={"Idempotency-Key": "accepted-quote-key"})
    assert response.status_code == 200
    assert response.json()["total_cents"] == cart["total_cents"] == 9000
    with db.write() as session:
        user = session.get(User, "tg-77")
        move_balance(session, user, -user.balance_cents, "test_adjustment", "test-adjustment", "fixture")
        session.get(SKU, "first").retail_price_cents = 15000
    replay = client.post("/api/bot/checkout", json={"quote_token": "0" * 64}, headers={"Idempotency-Key": "accepted-quote-key"})
    assert replay.status_code == 200
    assert replay.json()["replayed"] is True
    assert replay.json()["id"] == response.json()["id"]
    with db.read() as session:
        assert session.get(User, "tg-77").balance_cents == 0
        assert session.scalar(select(func.count()).select_from(Ledger).where(Ledger.kind == "purchase")) == 1


def test_quote_excludes_balance_and_normalizes_item_order(shop):
    client, db = shop
    original = client.get("/api/bot/cart").json()
    with db.write() as session:
        move_balance(session, session.get(User, "tg-77"), 100, "test_credit", "test-credit", "fixture")
    refreshed = client.get("/api/bot/cart").json()
    assert original["quote_token"] == refreshed["quote_token"]
    assert original["balance_cents"] != refreshed["balance_cents"]
    lines = [{"sku_id": "b", "quantity": 1, "price_cents": 200}, {"sku_id": "a", "quantity": 2, "price_cents": 100}]
    assert cart_quote_token(lines, False) == cart_quote_token(list(reversed(lines)), False)
    assert cart_quote_token(lines, False) != cart_quote_token(lines, True)


@pytest.mark.parametrize("body", [{}, {"quote_token": "bad"}, {"quote_token": None}])
def test_quote_is_required(shop, body):
    client, db = shop
    response = client.post("/api/bot/checkout", json=body, headers={"Idempotency-Key": "required-quote-key"})
    assert response.status_code == 422
    assert_no_purchase(db)


def test_demo_expected_total_rejects_stale_price_and_preserves_replay(shop):
    client, db = shop
    client.post("/api/v1/admin/auth/demo").raise_for_status()
    request = {"user_id": "tg-77", "items": [{"sku_id": "first", "quantity": 1}], "idempotency_key": "demo-quoted-checkout", "expected_total_cents": 100}
    rejected = client.post("/api/v1/admin/demo/checkout", json=request)
    assert rejected.status_code == 409
    assert rejected.json()["detail"] == "cart_changed"
    assert_no_purchase(db)
    request["expected_total_cents"] = 500
    accepted = client.post("/api/v1/admin/demo/checkout", json=request)
    assert accepted.status_code == 200
    with db.write() as session:
        session.get(SKU, "first").retail_price_cents = 9000
    replay = client.post("/api/v1/admin/demo/checkout", json=request)
    assert replay.status_code == 200
    assert replay.json()["replayed"] is True
    assert replay.json()["id"] == accepted.json()["id"]
    request["expected_total_cents"] = 9000
    assert client.post("/api/v1/admin/demo/checkout", json=request).status_code == 409


@pytest.mark.parametrize("value", [500.0, True, "500", -1, 0])
def test_demo_expected_total_requires_positive_integer_cents(shop, value):
    client, db = shop
    client.post("/api/v1/admin/auth/demo").raise_for_status()
    response = client.post("/api/v1/admin/demo/checkout", json={"user_id": "tg-77", "items": [{"sku_id": "first", "quantity": 1}], "idempotency_key": "invalid-expected-total", "expected_total_cents": value})
    assert response.status_code == 422
    assert_no_purchase(db)
