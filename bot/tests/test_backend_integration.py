"""Real backend contract checks using a fresh synthetic database, never live data."""
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import httpx

from bot.api import APIError, Backend
from bot.i18n import Messages
from bot.ui import Views


HAS_BACKEND = all(importlib.util.find_spec(name) for name in ("fastapi", "sqlalchemy", "cryptography"))


@unittest.skipUnless(HAS_BACKEND, "Install repository requirements.txt for real-backend integration tests")
class BackendIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from cryptography.fernet import Fernet
        from backend.database import Database
        from backend.main import create_app
        from backend.models import Inventory, SKU

        self.directory = tempfile.TemporaryDirectory()
        self.environment = patch.dict(os.environ, {"BOT_INTERNAL_TOKEN": "synthetic-test-token-" + "x" * 32,
                                                   "WHOLESALE_PASSWORD_HASH": "", "MANUAL_PAYMENT_INSTRUCTIONS": "Synthetic instructions — do not transfer funds."})
        self.environment.start()
        self.db = Database(url=f"sqlite:///{Path(self.directory.name) / 'test.sqlite3'}", key=Fernet.generate_key())
        self.app = create_app(database=self.db, demo=True, seed=False)
        self.lifespan = self.app.router.lifespan_context(self.app)
        await self.lifespan.__aenter__()
        with self.db.write() as session:
            session.add(SKU(id="fixture-sku", name="Synthetic license", country="Україна", country_code="UA", flag="🇺🇦",
                            retail_price_cents=125, wholesale_price_cents=100, category="Demo", description="Synthetic payload only"))
            session.flush()
            for index in range(3):
                session.add(Inventory(sku_id="fixture-sku", reference=f"synthetic-{index}", payload_encrypted=self.db.encrypt(f"DEMO-NOT-A-REAL-LICENSE-{index}")))
        self.backend = Backend("http://testserver/api/bot", os.environ["BOT_INTERNAL_TOKEN"], transport=httpx.ASGITransport(app=self.app))
        self.view = Views(Messages(), "uk")

    async def asyncTearDown(self):
        await self.backend.close()
        await self.lifespan.__aexit__(None, None, None)
        self.db.engine.dispose()
        self.environment.stop()
        self.directory.cleanup()

    async def test_actual_catalog_cart_atomic_checkout_delivery_and_ownership(self):
        from sqlalchemy import func, select
        from backend.models import Ledger, Order, User
        from backend.services import move_balance

        config = await self.backend.config(77)
        catalog = await self.backend.catalog(77)
        self.assertEqual(catalog["skus"][0]["stock"], 3)
        self.assertEqual((await self.backend.wallet(77))["balance_cents"], 0)
        self.view.menu(config, await self.backend.wallet(77), catalog)
        self.view.catalog(catalog, config)
        self.view.countries(catalog, "retail")
        self.view.products(catalog, "retail", "UA")
        self.view.product(catalog["skus"][0], catalog["countries"][0], 0)
        self.view.quantity(catalog["skus"][0], 2, "synthetic-nonce")

        await self.backend.set_quantity(77, "fixture-sku", 2)
        cart = await self.backend.cart(77)
        self.assertEqual(cart["total_cents"], 250)
        quote = {"quote_token": cart["quote_token"]}
        self.view.cart(cart, await self.backend.wallet(77))
        with self.assertRaises(APIError) as error:
            await self.backend.request(77, "POST", "checkout", payload=quote, key="synthetic-checkout")
        self.assertEqual(error.exception.code, "insufficient_balance")
        self.assertEqual((await self.backend.catalog(77))["skus"][0]["stock"], 3)

        # Fixture-only ledger credit; no bot endpoint can mint a wallet balance.
        with self.db.write() as session:
            move_balance(session, session.get(User, "tg-77"), 1000, "test_opening", "synthetic-opening", "test-fixture")
        order = await self.backend.request(77, "POST", "checkout", payload=quote, key="synthetic-checkout")
        replay = await self.backend.request(77, "POST", "checkout", payload=quote, key="synthetic-checkout")
        self.assertEqual(order["id"], replay["id"])
        self.assertEqual((await self.backend.wallet(77))["balance_cents"], 750)
        self.assertEqual((await self.backend.cart(77))["items"], [])
        self.assertEqual((await self.backend.catalog(77))["skus"][0]["stock"], 1)
        history = await self.backend.request(77, "GET", "orders")
        self.view.orders(history)
        detail = await self.backend.request(77, "GET", f"orders/{order['id']}")
        self.view.order(detail)
        self.assertEqual(len(detail["delivery"]), 2)
        self.assertTrue(all(item["payload"].startswith("DEMO-NOT-A-REAL-LICENSE") for item in detail["delivery"]))
        with self.assertRaises(APIError) as error:
            await self.backend.request(88, "GET", f"orders/{order['id']}")
        self.assertEqual(error.exception.status, 404)
        with self.db.read() as session:
            self.assertEqual(session.scalar(select(func.count()).select_from(Order)), 1)
            self.assertEqual(session.scalar(select(func.count()).select_from(Ledger).where(Ledger.kind == "purchase")), 1)

    async def test_stale_quote_rejects_price_and_entitlement_changes_without_debit(self):
        from sqlalchemy import func, select
        from backend.models import Ledger, Order, SKU, User
        from backend.services import move_balance

        for user_id, change in ((77, "price"), (78, "entitlement")):
            with self.subTest(change=change):
                await self.backend.config(user_id)
                with self.db.write() as session:
                    move_balance(session, session.get(User, f"tg-{user_id}"), 1000, "test_opening", f"opening-{user_id}", "test-fixture")
                    if change == "entitlement":
                        session.get(User, f"tg-{user_id}").wholesale_access = True
                await self.backend.set_quantity(user_id, "fixture-sku", 1)
                original = await self.backend.cart(user_id)
                with self.db.write() as session:
                    if change == "price":
                        session.get(SKU, "fixture-sku").retail_price_cents = 250
                    else:
                        session.get(User, f"tg-{user_id}").wholesale_access = False
                with self.assertRaises(APIError) as error:
                    await self.backend.request(user_id, "POST", "checkout", payload={"quote_token": original["quote_token"]}, key=f"stale-{change}")
                self.assertEqual(error.exception.code, "cart_changed")
                self.assertEqual((await self.backend.wallet(user_id))["balance_cents"], 1000)
                self.assertEqual((await self.backend.catalog(user_id))["skus"][0]["stock"], 3)
                self.assertNotEqual((await self.backend.cart(user_id))["quote_token"], original["quote_token"])
        with self.db.read() as session:
            self.assertEqual(session.scalar(select(func.count()).select_from(Order)), 0)
            self.assertEqual(session.scalar(select(func.count()).select_from(Ledger).where(Ledger.kind == "purchase")), 0)
        with self.assertRaises(APIError) as error:
            await self.backend.request(77, "POST", "checkout", payload={}, key="missing-quote")
        self.assertEqual(error.exception.status, 422)

    async def test_actual_manual_request_stays_pending_and_service_auth_is_required(self):
        config = await self.backend.config(77)
        self.assertTrue(config["manual_card_enabled"])
        self.view.wallet(await self.backend.wallet(77), config)
        first = await self.backend.request(77, "POST", "topups/manual", payload={"amount_cents": 500}, key="synthetic-topup")
        replay = await self.backend.request(77, "POST", "topups/manual", payload={"amount_cents": 500}, key="synthetic-topup")
        self.assertEqual(first["id"], replay["id"])
        self.assertEqual(first["status"], "pending")
        self.assertEqual((await self.backend.wallet(77))["balance_cents"], 0)
        self.assertIn("Synthetic instructions", first["instructions"])
        unauthorized = Backend("http://testserver/api/bot", "wrong", transport=httpx.ASGITransport(app=self.app))
        try:
            with self.assertRaises(APIError) as error:
                await unauthorized.config(77)
            self.assertEqual(error.exception.status, 401)
        finally:
            await unauthorized.close()


if __name__ == "__main__":
    unittest.main()
