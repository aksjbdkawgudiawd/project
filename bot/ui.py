from dataclasses import dataclass, field
from html import unescape
from math import ceil
from typing import Any
import unicodedata
from urllib.parse import urlparse

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from .i18n import Messages, usd


@dataclass
class Screen:
    text: str
    rows: list[list[InlineKeyboardButton]] = field(default_factory=list)

    @property
    def keyboard(self) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(inline_keyboard=self.rows)


def callback(label: str, action: str) -> InlineKeyboardButton:
    data = f"v1:{action}"
    if len(data.encode()) > 64:
        raise ValueError("Callback exceeds Telegram's 64-byte limit")
    return InlineKeyboardButton(text=unescape(label)[:100], callback_data=data)


def safe_url(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = urlparse(value)
    except ValueError:
        return None
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        return None
    return value


def localized(record: dict, field: str, locale: str) -> str:
    return str(record.get(f"{field}_{locale}") or record.get(field) or "")


def normalize_search(value: str) -> str:
    return "".join(char for char in unicodedata.normalize("NFKC", value).casefold() if char.isalnum())


def paginate(items: list, page: int, size: int = 7) -> tuple[list, int, int]:
    pages = max(1, ceil(len(items) / size))
    page = min(max(0, page), pages - 1)
    return items[page * size:(page + 1) * size], page, pages


class Views:
    def __init__(self, messages: Messages, locale: str) -> None:
        self.messages = messages
        self.locale = locale

    def t(self, key: str, **values: Any) -> str:
        return self.messages.text(self.locale, key, **values)

    def button(self, key: str, action: str, **values: Any) -> InlineKeyboardButton:
        return callback(self.t(key, **values), action)

    def home(self) -> list[InlineKeyboardButton]:
        return [self.button("home_button", "menu")]

    def cancel(self) -> list[InlineKeyboardButton]:
        return [self.button("cancel_button", "cancel")]

    def links(self, config: dict, names: tuple[str, ...]) -> list[list[InlineKeyboardButton]]:
        rows = []
        for name in names:
            url = safe_url(config.get("links", {}).get(name))
            if url:
                rows.append([InlineKeyboardButton(text=unescape(self.t(f"{name}_button")), url=url)])
        return rows

    def gate(self, config: dict) -> Screen:
        rows = []
        url = safe_url(config.get("subscription_gate", {}).get("public_url"))
        if url:
            rows.append([InlineKeyboardButton(text=self.t("subscribe_button"), url=url)])
        rows.append([self.button("check_button", "check")])
        return Screen(self.t("gate"), rows)

    def menu(self, config: dict, wallet: dict, catalog: dict) -> Screen:
        return Screen(self.t("menu", brand=config.get("brand_name", ""), balance=usd(wallet["balance_cents"]),
                             stock=sum({str(sku["id"]): sku["stock"] for sku in catalog["skus"]}.values())), [
            [self.button("catalog_button", "catalog")],
            [self.button("wallet_button", "wallet"), self.button("orders_button", "orders:0")],
            [self.button("cart_button", "cart"), self.button("help_button", "help")],
            *self.links(config, ("reviews", "stock")),
        ])

    def catalog(self, catalog: dict, config: dict) -> Screen:
        rows = [[callback(localized(section, "title", self.locale), f"section:{section['id']}")]
                for section in catalog["sections"]]
        if config.get("wholesale_password_enabled"):
            rows.append([self.button("wholesale_button", "wholesale")])
        return Screen(self.t("catalog") if rows else self.t("empty_catalog"), rows + [self.home()])

    def page_buttons(self, action: str, page: int, pages: int) -> list[InlineKeyboardButton]:
        rows = []
        if page > 0:
            rows.append(self.button("previous_button", f"{action}:{page - 1}"))
        rows.append(self.button("page_button", "noop", page=page + 1, pages=pages))
        if page + 1 < pages:
            rows.append(self.button("next_button", f"{action}:{page + 1}"))
        return rows

    def countries(self, catalog: dict, section_id: str, page: int = 0, search: str = "", sort: str = "name") -> Screen:
        section = next(section for section in catalog["sections"] if str(section["id"]) == section_id)
        skus = [sku for sku in catalog["skus"] if str(sku["section_id"]) == section_id]
        countries = []
        for country in catalog["countries"]:
            matching = [sku for sku in skus if str(sku["country_id"]) == str(country["id"])]
            if not matching:
                continue
            terms = [country.get("code", ""), country.get("name", ""), country.get("name_ru", ""),
                     country.get("name_uk", ""), *country.get("aliases", [])]
            if search and not any(normalize_search(search) in normalize_search(str(term)) for term in terms):
                continue
            available = [sku for sku in matching if sku["stock"] > 0]
            countries.append({**country, "stock": sum(sku["stock"] for sku in matching),
                              "price_cents": min(sku["price_cents"] for sku in available or matching)})
        if sort == "price":
            countries.sort(key=lambda country: country["price_cents"])
        elif sort == "stock":
            countries.sort(key=lambda country: -country["stock"])
        else:
            countries.sort(key=lambda country: localized(country, "name", self.locale).casefold())
        visible, page, pages = paginate(countries, page)
        rows = [[self.button("country_row", f"country:{country['id']}", country=localized(country, "name", self.locale),
                             stock=country["stock"], price=usd(country["price_cents"]))] for country in visible]
        rows += [self.page_buttons("countries", page, pages),
                 [self.button("search_button", "search"), self.button("sort_button", "sort", sort=unescape(self.t(f"sort_{sort}")))]]
        if search:
            rows.append([self.button("reset_search_button", "reset-search")])
        rows.append([self.button("back_button", "catalog")])
        text = self.t("countries", section=localized(section, "title", self.locale))
        if not countries:
            text += "\n" + self.t("no_results")
        return Screen(text, rows)

    def products(self, catalog: dict, section_id: str, country_id: str, page: int = 0) -> Screen:
        country = next(country for country in catalog["countries"] if str(country["id"]) == country_id)
        skus = [sku for sku in catalog["skus"] if str(sku["section_id"]) == section_id and str(sku["country_id"]) == country_id]
        visible, page, pages = paginate(skus, page)
        rows = [[self.button("sku_row", f"sku:{sku['id']}", title=localized(sku, "title", self.locale),
                             price=usd(sku["price_cents"]), stock=sku["stock"])] for sku in visible]
        rows += [self.page_buttons("products", page, pages), [self.button("back_button", "countries:0")]]
        return Screen(self.t("products", country=localized(country, "name", self.locale)), rows)

    def product(self, sku: dict, country: dict, quantity: int) -> Screen:
        rows = []
        if sku["stock"] >= sku.get("min_quantity", 1):
            rows.append([self.button("quantity_button", f"quantity:{sku['id']}")])
        if quantity:
            rows.append([self.button("remove_button", f"remove:{sku['id']}")])
        rows += [[self.button("back_button", "products:0")], self.home()]
        return Screen(self.t("product", title=localized(sku, "title", self.locale), country=localized(country, "name", self.locale),
                             price=usd(sku["price_cents"]), stock=sku["stock"], minimum=sku.get("min_quantity", 1),
                             quantity=quantity, description=localized(sku, "description", self.locale)), rows)

    def quantity(self, sku: dict, quantity: int, key: str) -> Screen:
        maximum = min(sku["stock"], sku.get("max_quantity") or sku["stock"])
        minimum = sku.get("min_quantity", 1)
        return Screen(self.t("quantity", title=localized(sku, "title", self.locale), minimum=minimum, maximum=maximum,
                             quantity=quantity, total=usd(quantity * sku["price_cents"])), [
            [callback("−", f"adjust:{key}:-1"), callback(str(quantity), "noop"), callback("+", f"adjust:{key}:1")],
            [self.button("save_quantity_button", f"save-quantity:{key}", quantity=quantity)],
            [self.button("remove_button", f"remove:{sku['id']}")], self.cancel(),
        ])

    def cart(self, cart: dict, wallet: dict, page: int = 0) -> Screen:
        if not cart["items"]:
            return Screen(self.t("cart_empty"), [self.home()])
        items, page, pages = paginate(cart["items"], page)
        text = self.t("cart", quantity=sum(item["quantity"] for item in cart["items"]),
                      total=usd(cart["total_cents"]), balance=usd(wallet["balance_cents"]))
        rows = []
        for item in items:
            text += "\n" + self.t("cart_line", title=item["title"], quantity=item["quantity"], total=usd(item["line_total_cents"]))
            rows.append([callback(item["title"], f"quantity:{item['sku_id']}")])
        rows += [self.page_buttons("cart", page, pages),
                 [self.button("clear_button", "clear"), self.button("checkout_button", "checkout")], self.home()]
        return Screen(text, rows)

    def wallet(self, wallet: dict, config: dict) -> Screen:
        text = self.t("wallet", balance=usd(wallet["balance_cents"]))
        rows = []
        if config.get("manual_card_enabled"):
            rows.append([self.button("topup_button", "topup")])
        else:
            text += "\n\n" + self.t("topup_unavailable")
        return Screen(text, rows + self.links(config, ("support",)) + [self.home()])

    def status(self, status: str) -> str:
        key = f"status_{status.lower()}"
        return unescape(self.t(key if key in self.messages.locales[self.locale] else "status_unknown"))

    def orders(self, orders: list[dict], page: int = 0) -> Screen:
        visible, page, pages = paginate(orders, page)
        rows = [[self.button("order_row", f"order:{order['id']}", id=order["id"], total=usd(order["total_cents"]),
                             status=self.status(order["status"]))] for order in visible]
        return Screen(self.t("orders" if orders else "orders_empty"), rows + [self.page_buttons("orders", page, pages), self.home()])

    def order(self, order: dict) -> Screen:
        return Screen(self.t("order", id=order["id"], date=order.get("created_at", ""), total=usd(order["total_cents"]),
                             status=self.status(order["status"])), [
            [self.button("delivery_button", f"delivery:{order['id']}")],
            [self.button("back_button", "orders:0")], self.home(),
        ])
