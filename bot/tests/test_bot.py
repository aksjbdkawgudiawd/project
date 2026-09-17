from copy import deepcopy
from datetime import datetime, timezone
import json
import unittest

from aiogram import Bot, Dispatcher
from aiogram.client.session.base import BaseSession
from aiogram.exceptions import TelegramNetworkError
from aiogram.fsm.storage.memory import MemoryStorage, SimpleEventIsolation
from aiogram.methods import GetChatMember, SendDocument, SendMessage
from aiogram.types import Chat, ChatMemberLeft, ChatMemberMember, Message, Update, User
import httpx

from bot.api import APIError, Backend
from bot.handlers import CustomerMiddleware, make_router
from bot.i18n import Messages
from bot.tests.test_rendering import CATALOG


class TelegramSession(BaseSession):
    def __init__(self):
        super().__init__()
        self.calls = []
        self.membership_error = False
        self.member_present = True

    async def close(self):
        pass

    async def make_request(self, bot, method, timeout=None):
        self.calls.append(method)
        if isinstance(method, GetChatMember):
            if self.membership_error:
                raise TelegramNetworkError(method=method, message="synthetic outage")
            member_type = ChatMemberMember if self.member_present else ChatMemberLeft
            return member_type(user=User(id=77, is_bot=False, first_name="Demo"))
        if isinstance(method, SendMessage):
            return Message(message_id=len(self.calls), date=datetime.now(timezone.utc), chat=Chat(id=77, type="private"), text=method.text)
        return True

    async def stream_content(self, url, headers=None, timeout=30, chunk_size=65536, raise_for_status=True):
        if False:
            yield b""


class CustomerFlowTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.session = TelegramSession()
        self.bot = Bot("123456789:" + "A" * 35, session=self.session)
        self.calls = []
        self.config = {"brand_name": "Demo", "subscription_gate": {"enabled": False}, "links": {}}
        self.catalog = deepcopy(CATALOG)
        self.cart = {"items": [], "total_cents": 0, "quote_token": "a" * 64}
        self.completed_checkout_keys = set()
        self.order = {"id": "order-1", "total_cents": 246, "status": "completed", "delivery": [{"text": "DEMO ONLY"}]}
        self.backend = Backend("https://backend.example/api/bot", "test-internal", transport=httpx.MockTransport(self.respond))
        self.dispatcher = Dispatcher(storage=MemoryStorage(), events_isolation=SimpleEventIsolation())
        middleware = CustomerMiddleware(self.backend, Messages())
        self.dispatcher.message.outer_middleware(middleware)
        self.dispatcher.callback_query.outer_middleware(middleware)
        self.dispatcher.include_router(make_router())
        self.update_id = 0

    async def asyncTearDown(self):
        await self.backend.close()
        await self.dispatcher.storage.close()
        await self.dispatcher.fsm.events_isolation.close()

    def respond(self, request):
        self.calls.append(request)
        self.assertEqual(request.headers["authorization"], "Bearer test-internal")
        self.assertEqual(request.headers["x-telegram-id"], "77")
        path = request.url.path.removeprefix("/api/bot/")
        if path == "config":
            return httpx.Response(200, json=self.config)
        if path == "catalog":
            return httpx.Response(200, json=self.catalog)
        if path == "wallet":
            return httpx.Response(200, json={"balance_cents": 1000})
        if path == "cart":
            return httpx.Response(200, json=self.cart)
        if path == "cart/items/sku-1" and request.method == "PUT":
            quantity = json.loads(request.content)["quantity"]
            self.cart = {"items": [{"sku_id": "sku-1", "title": "Demo", "quantity": quantity, "line_total_cents": quantity * 123}], "total_cents": quantity * 123, "quote_token": "a" * 64}
            return httpx.Response(200, json=self.cart)
        if path == "checkout":
            key = request.headers["idempotency-key"]
            if key not in self.completed_checkout_keys and json.loads(request.content).get("quote_token") != self.cart["quote_token"]:
                return httpx.Response(409, json={"detail": "cart_changed"})
            self.completed_checkout_keys.add(key)
            return httpx.Response(200, json=self.order)
        if path == "orders/order-1":
            return httpx.Response(200, json=self.order)
        if path == "orders":
            return httpx.Response(200, json=[self.order])
        if path == "wholesale/unlock":
            return httpx.Response(403, json={"detail": {"code": "invalid_password"}})
        if path == "topups/manual":
            amount = json.loads(request.content)["amount_cents"]
            if amount < 100:
                return httpx.Response(422, json={"detail": [{"type": "greater_than_equal"}]})
            return httpx.Response(200, json={"id": "topup-1", "amount_cents": amount, "status": "pending", "instructions": "DEMO ONLY"})
        return httpx.Response(404, json={"detail": "not_found"})

    async def update(self, text=None, callback=None, chat_type="private"):
        self.update_id += 1
        user = {"id": 77, "is_bot": False, "first_name": "Demo", "language_code": "ru"}
        message = {"message_id": self.update_id, "date": 1700000000, "chat": {"id": 77, "type": chat_type}, "from": user, "text": text or "screen"}
        payload = {"update_id": self.update_id}
        if callback:
            payload["callback_query"] = {"id": str(self.update_id), "from": user, "message": message, "chat_instance": "test", "data": callback}
        else:
            payload["message"] = message
        await self.dispatcher.feed_update(self.bot, Update.model_validate(payload))

    def last_screen(self):
        return next(call for call in reversed(self.session.calls) if isinstance(call, SendMessage))

    def last_callback(self, prefix):
        return next(button.callback_data for row in self.last_screen().reply_markup.inline_keyboard for button in row if (button.callback_data or "").startswith(prefix))

    async def test_browse_quantity_checkout_and_replay_key(self):
        await self.update(text="/start")
        self.assertIn("Demo", self.last_screen().text)
        for callback in ("v1:catalog", "v1:section:retail", "v1:country:UA", "v1:sku:sku-1", "v1:quantity:sku-1"):
            await self.update(callback=callback)
        await self.update(text="2")
        save = self.last_callback("v1:save-quantity:")
        await self.update(callback=save)
        self.assertEqual(self.cart["items"][0]["quantity"], 2)
        await self.update(callback="v1:checkout")
        pay = self.last_callback("v1:pay:")
        await self.update(callback=pay)
        self.cart["quote_token"] = "b" * 64
        await self.update(callback=pay)
        requests = [request for request in self.calls if request.url.path.endswith("/checkout")]
        self.assertEqual(len(requests), 2)
        self.assertEqual(requests[0].headers["idempotency-key"], requests[1].headers["idempotency-key"])
        self.assertEqual([json.loads(request.content) for request in requests], [{"quote_token": "a" * 64}] * 2)

    async def test_changed_quote_requires_explicit_reconfirmation_without_silent_refresh(self):
        await self.backend.set_quantity(77, "sku-1", 2)
        await self.update(callback="v1:checkout")
        self.assertIn("2.46", self.last_screen().text)
        old_pay = self.last_callback("v1:pay:")
        self.cart.update(quote_token="b" * 64, total_cents=492)
        cart_reads = sum(request.url.path.endswith("/cart") for request in self.calls)
        await self.update(callback=old_pay)
        self.assertIn("Оплата не выполнена", self.last_screen().text)
        self.assertEqual(sum(request.url.path.endswith("/cart") for request in self.calls), cart_reads)
        requests = [request for request in self.calls if request.url.path.endswith("/checkout")]
        self.assertEqual(json.loads(requests[0].content), {"quote_token": "a" * 64})
        self.assertEqual(self.completed_checkout_keys, set())
        context = self.dispatcher.fsm.get_context(bot=self.bot, chat_id=77, user_id=77)
        self.assertIsNone((await context.get_data())["checkout_key"])
        self.assertIsNone((await context.get_data())["checkout_quote"])
        await self.update(callback=old_pay)
        self.assertEqual(sum(request.url.path.endswith("/checkout") for request in self.calls), 1)
        await self.update(callback="v1:cart")
        await self.update(callback="v1:checkout")
        self.assertIn("4.92", self.last_screen().text)
        new_pay = self.last_callback("v1:pay:")
        self.assertNotEqual(old_pay, new_pay)
        await self.update(callback=new_pay)
        request = next(request for request in reversed(self.calls) if request.url.path.endswith("/checkout"))
        self.assertEqual(json.loads(request.content), {"quote_token": "b" * 64})

    async def test_checkout_without_quote_cannot_create_confirmation(self):
        await self.backend.set_quantity(77, "sku-1", 1)
        self.cart.pop("quote_token")
        await self.update(callback="v1:checkout")
        self.assertIn("устарел", self.last_screen().text)
        self.assertFalse(any((button.callback_data or "").startswith("v1:pay:")
                             for row in self.last_screen().reply_markup.inline_keyboard for button in row))

    async def test_quantity_old_keyboard_cannot_mutate_current_selection(self):
        await self.update(callback="v1:quantity:sku-1")
        old = self.last_callback("v1:save-quantity:")
        await self.update(text="3")
        await self.update(callback=old)
        self.assertFalse(any(request.method == "PUT" for request in self.calls))
        self.assertIn("устарел", self.last_screen().text)

    async def test_invalid_quantity_stays_in_state_with_cancel(self):
        await self.update(callback="v1:quantity:sku-1")
        await self.update(text="1.5")
        self.assertIn("целое", self.last_screen().text)
        self.assertEqual(self.last_callback("v1:cancel"), "v1:cancel")
        await self.update(text="2")
        self.assertTrue(self.last_callback("v1:save-quantity:"))

    async def test_gate_failure_does_not_reach_customer_routes(self):
        self.config["subscription_gate"] = {"enabled": True, "required_chat_id": "@demo"}
        self.session.membership_error = True
        await self.update(text="/start")
        self.assertIn("подпишитесь", self.last_screen().text)
        self.assertTrue(all(request.url.path.endswith("/config") for request in self.calls))
        await self.update(callback="v1:pay:forged")
        self.assertTrue(all(request.url.path.endswith("/config") for request in self.calls))

    async def test_missing_gate_configuration_fails_closed(self):
        self.config.pop("subscription_gate")
        await self.update(text="/start")
        self.assertIn("подпишитесь", self.last_screen().text)

    async def test_membership_is_rechecked_after_revocation(self):
        self.config["subscription_gate"] = {"enabled": True, "required_chat_id": "@demo"}
        await self.update(text="/start")
        self.assertIn("Баланс", self.last_screen().text)
        self.session.member_present = False
        self.calls.clear()
        await self.update(callback="v1:delivery:order-1")
        self.assertIn("подпишитесь", self.last_screen().text)
        self.assertTrue(all(request.url.path.endswith("/config") for request in self.calls))
        self.assertFalse(any(isinstance(call, SendDocument) for call in self.session.calls))

    async def test_delivery_requires_explicit_action_and_uses_protected_document(self):
        await self.update(callback="v1:order:order-1")
        self.assertFalse(any(isinstance(call, SendDocument) for call in self.session.calls))
        await self.update(callback="v1:delivery:order-1")
        document = next(call for call in self.session.calls if isinstance(call, SendDocument))
        self.assertTrue(document.protect_content)
        self.assertIn(b"DEMO ONLY", document.document.data)
        self.assertFalse(any("DEMO ONLY" in call.text for call in self.session.calls if isinstance(call, SendMessage)))

    async def test_no_customer_action_in_groups_and_unknown_text_ignored(self):
        await self.update(text="/start", chat_type="group")
        self.assertEqual(self.calls, [])
        await self.update(text="arbitrary input")
        self.assertFalse(any(isinstance(call, SendMessage) for call in self.session.calls))

    async def test_unconfigured_topup_callback_is_rejected(self):
        await self.update(callback="v1:topup")
        self.assertIn("устарел", self.last_screen().text)
        self.assertFalse(any("topups" in request.url.path for request in self.calls))

    async def test_rejected_topup_amount_can_be_corrected(self):
        self.config["manual_card_enabled"] = True
        await self.update(callback="v1:topup")
        await self.update(text="0.01")
        self.assertIn("лимитов", self.last_screen().text)
        await self.update(text="5")
        self.assertIn("ожидает проверки оператором", self.last_screen().text)
        requests = [request for request in self.calls if request.url.path.endswith("/topups/manual")]
        self.assertEqual(len(requests), 2)
        self.assertEqual(requests[0].headers["idempotency-key"], requests[1].headers["idempotency-key"])

    async def test_wholesale_password_is_only_verified_by_backend(self):
        self.config["wholesale_password_enabled"] = True
        await self.update(callback="v1:wholesale")
        await self.update(text="synthetic-password")
        request = next(request for request in self.calls if request.url.path.endswith("/wholesale/unlock"))
        self.assertEqual(json.loads(request.content), {"password": "synthetic-password"})
        self.assertIn("Доступ не подтверждён", self.last_screen().text)
        context = self.dispatcher.fsm.get_context(bot=self.bot, chat_id=77, user_id=77)
        self.assertNotIn("synthetic-password", str(await context.get_data()))

    async def test_api_rejects_path_traversal_and_redirects(self):
        with self.assertRaises(APIError):
            await self.backend.set_quantity(77, "../../admin", 1)
        backend = Backend("https://backend.example", "secret", transport=httpx.MockTransport(lambda request: httpx.Response(302, headers={"location": "https://elsewhere.example"})))
        try:
            with self.assertRaises(APIError):
                await backend.config(77)
        finally:
            await backend.close()


if __name__ == "__main__":
    unittest.main()
