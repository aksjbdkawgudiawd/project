from html import escape
import json
from pathlib import Path
from string import Formatter
from typing import Any


class Messages:
    def __init__(self, override_directory: str = "", default: str = "ru") -> None:
        self.default = default
        self.locales = {}
        for locale in ("ru", "uk"):
            content = json.loads((Path(__file__).parent / "locales" / f"{locale}.json").read_text())
            if override_directory:
                override = Path(override_directory) / f"{locale}.json"
                if override.exists():
                    overrides = json.loads(override.read_text())
                    for key, value in overrides.items():
                        if key not in content or not isinstance(value, str):
                            raise ValueError(f"Invalid template override: {locale}.{key}")
                        fields = lambda template: {name for _, name, _, _ in Formatter().parse(template) if name is not None}
                        if fields(value) != fields(content[key]):
                            raise ValueError(f"Template placeholders differ: {locale}.{key}")
                    content.update(overrides)
            self.locales[locale] = content
        if self.locales["ru"].keys() != self.locales["uk"].keys():
            raise ValueError("ru and uk template keys must match")

    def locale(self, language_code: str | None) -> str:
        language = (language_code or "").split("-")[0].lower()
        return language if language in self.locales else self.default

    def text(self, locale: str, key: str, **values: Any) -> str:
        template = self.locales.get(locale, self.locales[self.default])[key]
        return template.format(**{key: escape(str(value)) for key, value in values.items()})


def usd(cents: int) -> str:
    if not isinstance(cents, int) or isinstance(cents, bool):
        raise ValueError("Money must use integer minor units")
    sign = "−" if cents < 0 else ""
    amount = abs(cents)
    return f"{sign}{amount // 100}.{amount % 100:02d} $"


def parse_amount(text: str) -> int:
    import re

    normalized = text.strip().replace(",", ".")
    if not re.fullmatch(r"[0-9]{1,7}(?:\.[0-9]{1,2})?", normalized):
        raise ValueError("Enter a positive decimal amount with at most two decimal places")
    whole, _, fraction = normalized.partition(".")
    cents = int(whole) * 100 + int(fraction.ljust(2, "0"))
    if cents <= 0:
        raise ValueError("Amount must be positive")
    return cents
