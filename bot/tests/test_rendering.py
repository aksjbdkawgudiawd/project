import json
from pathlib import Path
from string import Formatter
import tempfile
import unittest

from bot.config import Settings
from bot.i18n import Messages, parse_amount, usd
from bot.ui import Views, callback, paginate, safe_url


CATALOG = {
    "sections": [{"id": "retail", "title": "Retail"}],
    "countries": [{"id": "UA", "code": "UA", "name_ru": "Украина", "name_uk": "Україна"}],
    "skus": [{"id": "sku-1", "section_id": "retail", "country_id": "UA", "title": "Demo <script>",
              "price_cents": 123, "stock": 5, "min_quantity": 1, "max_quantity": 4, "description": "A & B"}],
}


class RenderingTests(unittest.TestCase):
    def setUp(self):
        self.messages = Messages()
        self.view = Views(self.messages, "ru")

    def test_locale_key_and_placeholder_parity(self):
        for key, ru in self.messages.locales["ru"].items():
            fields = lambda text: {name for _, name, _, _ in Formatter().parse(text) if name is not None}
            self.assertEqual(fields(ru), fields(self.messages.locales["uk"][key]), key)
        self.assertEqual(self.messages.locale("uk-UA"), "uk")
        self.assertEqual(self.messages.locale("en"), "ru")

    def test_override_validated_and_applied(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ru.json"
            path.write_text(json.dumps({"menu": "{brand}: {balance}, {stock}"}))
            self.assertEqual(Messages(directory).text("ru", "menu", brand="Shop", balance=0, stock=1), "Shop: 0, 1")
            path.write_text(json.dumps({"menu": "{secret}"}))
            with self.assertRaises(ValueError):
                Messages(directory)

    def test_money_never_uses_float(self):
        self.assertEqual(usd(123), "1.23 $")
        self.assertEqual(usd(-1), "−0.01 $")
        self.assertEqual(parse_amount(" 10,01 "), 1001)
        self.assertEqual(parse_amount("1.1"), 110)
        for value in ("0", "-1", "1.234", "NaN", "1e3", "1 000", "١٢"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_amount(value)
        for value in (1.2, True):
            with self.assertRaises(ValueError):
                usd(value)

    def test_external_content_is_html_escaped(self):
        screen = self.view.product(CATALOG["skus"][0], CATALOG["countries"][0], 0)
        self.assertIn("&lt;script&gt;", screen.text)
        self.assertIn("A &amp; B", screen.text)
        self.assertNotIn("<script>", screen.text)

    def test_country_catalog_is_data_driven_and_searchable(self):
        screen = self.view.countries(CATALOG, "retail", search="uA")
        self.assertEqual(screen.rows[0][0].callback_data, "v1:country:UA")
        self.assertIn("1.23", screen.rows[0][0].text)
        uk = Views(self.messages, "uk").countries(CATALOG, "retail")
        self.assertIn("Україна", uk.rows[0][0].text)
        missing = self.view.countries(CATALOG, "retail", search="absent")
        self.assertIn(self.view.t("no_results"), missing.text)

    def test_pagination_clamps_untrusted_pages(self):
        self.assertEqual(paginate(list(range(15)), 99), ([14], 2, 3))
        self.assertEqual(paginate([], -99), ([], 0, 1))

    def test_unconfigured_payment_and_external_links_hidden(self):
        screen = self.view.wallet({"balance_cents": 0}, {})
        self.assertFalse(any(button.callback_data == "v1:topup" for row in screen.rows for button in row))
        self.assertTrue(safe_url("https://t.me/example"))
        for url in (None, "javascript:alert(1)", "http://example.com", "https://user:pass@example.com", "https://["):
            self.assertIsNone(safe_url(url))

    def test_callback_limits_and_quantity_nonce(self):
        screen = self.view.quantity(CATALOG["skus"][0], 2, "nonce")
        self.assertEqual(screen.rows[1][0].callback_data, "v1:save-quantity:nonce")
        self.assertIn("4", screen.text)
        with self.assertRaises(ValueError):
            callback("label", "x" * 64)

    def test_production_requires_shared_fsm_and_internal_auth(self):
        with self.assertRaises(ValueError):
            Settings(token="present").validate()
        with self.assertRaises(ValueError):
            Settings(token="present", internal_token="x" * 32, environment="production").validate()
        Settings(token="present", internal_token="x" * 32, redis_url="redis://localhost", environment="production").validate()


if __name__ == "__main__":
    unittest.main()
