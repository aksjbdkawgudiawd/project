import asyncio
import json
import logging
import re
from typing import Any
from uuid import uuid4

from aiogram import BaseMiddleware, Bot, F, Router
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.filters import CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BufferedInputFile, CallbackQuery, Message

from .api import APIError, Backend
from .i18n import Messages, parse_amount, usd
from .ui import Screen, Views


logger = logging.getLogger(__name__)


class Input(StatesGroup):
    quantity = State()
    search = State()
    wholesale = State()
    topup = State()


class StaleScreen(Exception):
    pass


def message_of(event: Message | CallbackQuery) -> Message | None:
    message = event.message if isinstance(event, CallbackQuery) else event
    return message if isinstance(message, Message) else None


async def send(event: Message | CallbackQuery, screen: Screen) -> None:
    message = message_of(event)
    if message:
        await message.answer(screen.text, reply_markup=screen.keyboard)


async def subscribed(bot: Bot, user_id: int, config: dict) -> bool:
    gate = config.get("subscription_gate", {})
    if gate.get("enabled") is False:
        return True
    chat_id = gate.get("required_chat_id")
    if not chat_id:
        return False
    accepted = set(gate.get("accepted_statuses", ["member", "administrator", "creator"]))
    accepted &= {"member", "administrator", "creator"}
    try:
        member = await bot.get_chat_member(chat_id=chat_id, user_id=user_id)
    except (TelegramAPIError, asyncio.TimeoutError):
        logger.warning("Subscription verification unavailable")
        return False
    return member.status in accepted


class CustomerMiddleware(BaseMiddleware):
    def __init__(self, backend: Backend, messages: Messages) -> None:
        self.backend = backend
        self.messages = messages

    async def __call__(self, handler, event: Message | CallbackQuery, data: dict[str, Any]) -> Any:
        user = event.from_user
        message = message_of(event)
        if not user or not message:
            return None
        view = Views(self.messages, self.messages.locale(user.language_code))
        if isinstance(event, CallbackQuery):
            try:
                await event.answer()
            except TelegramBadRequest:
                return None
        if message.chat.type != "private":
            return None
        try:
            config = await self.backend.config(user.id)
            if not await subscribed(data["bot"], user.id, config):
                await send(event, view.gate(config))
                return None
            data.update(backend=self.backend, view=view, config=config)
            return await handler(event, data)
        except APIError as exc:
            codes = {
                "insufficient_balance": "insufficient_balance", "insufficient_stock": "insufficient_stock",
                "out_of_stock": "insufficient_stock", "wholesale_denied": "wholesale_denied",
                "invalid_password": "wholesale_denied", "rate_limited": "rate_limited",
                "amount_rejected": "amount_rejected", "empty_cart": "cart_empty",
            }
            key = "rate_limited" if exc.status == 429 else codes.get(exc.code, "error")
            # Request contents may include passwords or purchased inventory.
            logger.warning("Backend request failed (HTTP %s)", exc.status)
            await send(event, Screen(view.t(key), [view.cancel()]))
        except (StaleScreen, StopIteration):
            await send(event, Screen(view.t("stale"), [view.home()]))


def find(records: list[dict], record_id: str) -> dict:
    result = next((record for record in records if str(record["id"]) == record_id), None)
    if result is None:
        raise StaleScreen()
    return result


def item_quantity(cart: dict, sku_id: str) -> int:
    return next((item["quantity"] for item in cart["items"] if str(item["sku_id"]) == sku_id), 0)


async def menu(event, state: FSMContext, backend: Backend, view: Views, config: dict) -> None:
    await state.clear()
    wallet, catalog = await asyncio.gather(backend.wallet(event.from_user.id), backend.catalog(event.from_user.id))
    await send(event, view.menu(config, wallet, catalog))


async def show_countries(event, state: FSMContext, backend: Backend, view: Views, page: int = 0) -> None:
    data = await state.get_data()
    section_id = data.get("section_id")
    if not section_id:
        raise StaleScreen()
    catalog = await backend.catalog(event.from_user.id)
    find(catalog["sections"], section_id)
    await send(event, view.countries(catalog, section_id, page, data.get("search", ""), data.get("sort", "name")))


async def show_quantity(event, state: FSMContext, backend: Backend, view: Views, sku_id: str, quantity: int | None = None) -> None:
    catalog, cart = await asyncio.gather(backend.catalog(event.from_user.id), backend.cart(event.from_user.id))
    sku = find(catalog["skus"], sku_id)
    minimum = sku.get("min_quantity", 1)
    maximum = min(sku["stock"], sku.get("max_quantity") or sku["stock"])
    if maximum < minimum:
        await state.set_state(None)
        await send(event, Screen(view.t("insufficient_stock"), [[view.button("remove_button", f"remove:{sku_id}")], view.home()]))
        return
    quantity = max(minimum, min(maximum, quantity if quantity is not None else item_quantity(cart, sku_id) or minimum))
    key = uuid4().hex[:12]
    await state.set_state(Input.quantity)
    await state.update_data(sku_id=sku_id, quantity=quantity, minimum=minimum, maximum=maximum,
                            section_id=str(sku["section_id"]), country_id=str(sku["country_id"]), quantity_key=key)
    await send(event, view.quantity(sku, quantity, key))


def make_router() -> Router:
    router = Router(name="customer")

    @router.message(CommandStart())
    async def start(message: Message, state: FSMContext, backend: Backend, view: Views, config: dict):
        await menu(message, state, backend, view, config)

    @router.callback_query(F.data.startswith("v1:"))
    async def navigate(query: CallbackQuery, state: FSMContext, backend: Backend, view: Views, config: dict):
        parts = (query.data or "").split(":", 2)
        action = parts[1]
        value = parts[2] if len(parts) == 3 else ""
        user_id = query.from_user.id
        data = await state.get_data()
        if action == "noop":
            return
        if action in {"menu", "check", "cancel"}:
            await menu(query, state, backend, view, config)
            return
        input_actions = {"adjust", "save-quantity"}
        if action not in input_actions:
            await state.set_state(None)
        if action == "catalog":
            await send(query, view.catalog(await backend.catalog(user_id), config))
        elif action == "section":
            catalog = await backend.catalog(user_id)
            find(catalog["sections"], value)
            await state.update_data(section_id=value, search="", sort="name")
            await show_countries(query, state, backend, view)
        elif action in {"countries", "reset-search", "sort"}:
            if action == "reset-search":
                await state.update_data(search="")
            if action == "sort":
                sorts = ["name", "price", "stock"]
                await state.update_data(sort=sorts[(sorts.index(data.get("sort", "name")) + 1) % len(sorts)])
            await show_countries(query, state, backend, view, parse_page(value) if action == "countries" else 0)
        elif action == "search":
            if not data.get("section_id"):
                raise StaleScreen()
            await state.set_state(Input.search)
            await send(query, Screen(view.t("search_prompt"), [view.cancel()]))
        elif action in {"country", "products"}:
            country_id = value if action == "country" else data.get("country_id")
            section_id = data.get("section_id")
            if not country_id or not section_id:
                raise StaleScreen()
            catalog = await backend.catalog(user_id)
            find(catalog["countries"], country_id)
            find(catalog["sections"], section_id)
            await state.update_data(country_id=country_id)
            await send(query, view.products(catalog, section_id, country_id, parse_page(value) if action == "products" else 0))
        elif action == "sku":
            catalog, cart = await asyncio.gather(backend.catalog(user_id), backend.cart(user_id))
            sku = find(catalog["skus"], value)
            country = find(catalog["countries"], str(sku["country_id"]))
            await state.update_data(section_id=str(sku["section_id"]), country_id=str(sku["country_id"]))
            await send(query, view.product(sku, country, item_quantity(cart, value)))
        elif action == "quantity":
            await show_quantity(query, state, backend, view, value)
        elif action in input_actions:
            if await state.get_state() != Input.quantity.state or not data.get("sku_id"):
                raise StaleScreen()
            key, _, delta = value.partition(":")
            if not key or key != data.get("quantity_key"):
                raise StaleScreen()
            if action == "adjust":
                if delta not in {"-1", "1"}:
                    raise StaleScreen()
                await show_quantity(query, state, backend, view, data["sku_id"], data["quantity"] + int(delta))
            else:
                await backend.set_quantity(user_id, data["sku_id"], data["quantity"])
                await state.set_state(None)
                await state.update_data(checkout_key=None, checkout_quote=None)
                await send(query, view.cart(await backend.cart(user_id), await backend.wallet(user_id)))
        elif action in {"cart", "clear", "remove"}:
            if action == "clear":
                await backend.request(user_id, "DELETE", "cart")
            elif action == "remove":
                await backend.set_quantity(user_id, value, 0)
            await state.update_data(checkout_key=None, checkout_quote=None)
            await send(query, view.cart(await backend.cart(user_id), await backend.wallet(user_id), parse_page(value) if action == "cart" else 0))
        elif action == "checkout":
            cart = await backend.cart(user_id)
            if not cart["items"]:
                await send(query, view.cart(cart, await backend.wallet(user_id)))
                return
            key = uuid4().hex
            quote = cart.get("quote_token", "")
            if not isinstance(quote, str) or not re.fullmatch(r"[a-f0-9]{64}", quote):
                raise StaleScreen()
            await state.update_data(checkout_key=key, checkout_quote=quote)
            await send(query, Screen(view.t("checkout_confirm", total=usd(cart["total_cents"])), [
                [view.button("confirm_button", f"pay:{key}")], view.cancel(),
            ]))
        elif action == "pay":
            if not value or value != data.get("checkout_key") or not data.get("checkout_quote"):
                raise StaleScreen()
            try:
                order = await backend.request(user_id, "POST", "checkout", payload={"quote_token": data["checkout_quote"]}, key=value)
            except APIError as exc:
                if exc.code != "cart_changed":
                    raise
                await state.update_data(checkout_key=None, checkout_quote=None)
                await send(query, Screen(view.t("cart_changed"), [[view.button("cart_button", "cart")], view.home()]))
                return
            await send(query, view.order(order))
        elif action == "wallet":
            await send(query, view.wallet(await backend.wallet(user_id), config))
        elif action == "topup":
            if not config.get("manual_card_enabled"):
                raise StaleScreen()
            await state.set_state(Input.topup)
            await state.update_data(topup_key=uuid4().hex, topup_amount=None)
            await send(query, Screen(view.t("topup_amount"), [view.cancel()]))
        elif action == "wholesale":
            if not config.get("wholesale_password_enabled"):
                raise StaleScreen()
            await state.set_state(Input.wholesale)
            await send(query, Screen(view.t("wholesale_prompt"), [view.cancel()]))
        elif action == "orders":
            orders = await backend.request(user_id, "GET", "orders")
            await send(query, view.orders(orders, parse_page(value)))
        elif action in {"order", "delivery"}:
            if not re.fullmatch(r"[A-Za-z0-9_-]{1,40}", value):
                raise StaleScreen()
            order = await backend.request(user_id, "GET", f"orders/{value}")
            if action == "order":
                await send(query, view.order(order))
            else:
                payload = order.get("delivery")
                if not payload:
                    await send(query, Screen(view.t("delivery_pending"), [view.home()]))
                else:
                    document = BufferedInputFile(json.dumps(payload, ensure_ascii=False, indent=2).encode(), filename=f"order-{value}.json")
                    await query.message.answer_document(document, protect_content=True)
        elif action == "help":
            await send(query, Screen(view.t("help"), view.links(config, ("support", "terms", "privacy")) + [view.home()]))
        else:
            raise StaleScreen()

    @router.message(StateFilter(Input.quantity), F.text)
    async def quantity_input(message: Message, state: FSMContext, backend: Backend, view: Views):
        data = await state.get_data()
        text = (message.text or "").strip()
        if not re.fullmatch(r"[0-9]{1,9}", text) or not data["minimum"] <= int(text) <= data["maximum"]:
            await send(message, Screen(view.t("invalid_quantity", minimum=data["minimum"], maximum=data["maximum"]), [view.cancel()]))
            return
        await show_quantity(message, state, backend, view, data["sku_id"], int(text))

    @router.message(StateFilter(Input.search), F.text)
    async def search_input(message: Message, state: FSMContext, backend: Backend, view: Views):
        await state.update_data(search=(message.text or "")[:128])
        await state.set_state(None)
        await show_countries(message, state, backend, view)

    @router.message(StateFilter(Input.wholesale), F.text)
    async def wholesale_input(message: Message, state: FSMContext, backend: Backend, view: Views, config: dict):
        if not config.get("wholesale_password_enabled"):
            raise StaleScreen()
        try:
            await message.delete()
        except TelegramAPIError:
            pass
        await backend.request(message.from_user.id, "POST", "wholesale/unlock", payload={"password": message.text})
        await state.set_state(None)
        await send(message, view.catalog(await backend.catalog(message.from_user.id), config))

    @router.message(StateFilter(Input.topup), F.text)
    async def topup_input(message: Message, state: FSMContext, backend: Backend, view: Views, config: dict):
        if not config.get("manual_card_enabled"):
            raise StaleScreen()
        try:
            amount = parse_amount(message.text or "")
        except ValueError:
            await send(message, Screen(view.t("invalid_amount"), [view.cancel()]))
            return
        data = await state.get_data()
        if data.get("topup_amount") is not None and data["topup_amount"] != amount:
            raise APIError("request_conflict", 409)
        await state.update_data(topup_amount=amount)
        try:
            topup = await backend.request(message.from_user.id, "POST", "topups/manual", payload={"amount_cents": amount}, key=data["topup_key"])
        except APIError as exc:
            if exc.status == 422:
                await state.update_data(topup_amount=None)
                raise APIError("amount_rejected", 422) from exc
            raise
        await state.set_state(None)
        await send(message, Screen(view.t("topup_pending", id=topup["id"], amount=usd(amount),
                                          instructions=topup.get("instructions", "")), view.links(config, ("support",)) + [view.home()]))

    return router


def parse_page(value: str) -> int:
    if not value:
        return 0
    if not re.fullmatch(r"[0-9]{1,6}", value):
        raise StaleScreen()
    return int(value)
