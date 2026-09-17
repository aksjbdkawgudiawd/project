from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LoginInput(StrictModel):
    username: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=1, max_length=256)


class SKUInput(StrictModel):
    name: str = Field(min_length=1, max_length=160)
    country: str = Field(min_length=1, max_length=80)
    country_code: str = Field(pattern="^[A-Z]{2}$")
    flag: str = Field(default="🌐", max_length=16)
    category: str = Field(default="Digital license", min_length=1, max_length=80)
    description: str = Field(default="", max_length=2000)
    retail_price_cents: int = Field(strict=True, gt=0, le=100_000_000)
    wholesale_price_cents: int = Field(strict=True, gt=0, le=100_000_000)
    active: bool = True


class InventoryInput(StrictModel):
    sku_id: str = Field(min_length=1, max_length=64)
    reference: str = Field(min_length=1, max_length=160)
    payload: str = Field(min_length=1, max_length=20_000)

    @field_validator("reference", "payload")
    @classmethod
    def not_blank(cls, value):
        if not value.strip():
            raise ValueError("Must not be blank")
        return value


class StatusInput(StrictModel):
    status: Literal["available", "quarantined", "invalid"]
    reason: str = Field(default="Operator status change", min_length=1, max_length=500)


class ReviewInput(StrictModel):
    decision: Literal["approve", "reject"]
    note: str = Field(min_length=3, max_length=1000)


class WholesaleInput(StrictModel):
    wholesale_access: bool


class CheckoutLine(StrictModel):
    sku_id: str = Field(min_length=1, max_length=64)
    quantity: int = Field(strict=True, ge=1, le=100)


class CheckoutInput(StrictModel):
    user_id: str = Field(min_length=1, max_length=64)
    items: list[CheckoutLine] = Field(min_length=1, max_length=20)
    idempotency_key: str = Field(min_length=8, max_length=160)
    wholesale: bool = False
    expected_total_cents: int | None = Field(default=None, strict=True, ge=1, le=2_000_000_000)


class ImportPreviewInput(StrictModel):
    format: Literal["csv", "json"]
    content: str = Field(min_length=1, max_length=1_000_000)
    sku_id: str | None = None


class ImportConfirmInput(StrictModel):
    batch_id: str = Field(min_length=1, max_length=64)


class SettingsInput(StrictModel):
    store_name: str = Field(default="Arshisney", min_length=1, max_length=100)
    currency: Literal["USD"] = "USD"
    display_currency: Literal["USD", "UAH"] = "UAH"
    usd_uah_rate: str = Field(default="41.50", pattern=r"^\d{1,4}(\.\d{1,4})?$")
    support_url: str = Field(default="", max_length=500)
    reviews_url: str = Field(default="", max_length=500)
    stock_channel_url: str = Field(default="", max_length=500)
    terms_url: str = Field(default="", max_length=500)
    default_language: Literal["en", "ru", "uk"] = "en"
    low_stock_threshold: int = Field(default=5, strict=True, ge=0, le=1000)
    maintenance_mode: bool = False
    subscription_required: bool = False
    welcome_message: str = Field(default="Welcome to {store_name}. Browse our available digital goods.", max_length=2000)

    @field_validator("support_url", "reviews_url", "stock_channel_url", "terms_url")
    @classmethod
    def safe_url(cls, value):
        from urllib.parse import urlparse
        if value and (urlparse(value).scheme != "https" or not urlparse(value).hostname):
            raise ValueError("Links must be absolute HTTPS URLs")
        return value

    @field_validator("usd_uah_rate")
    @classmethod
    def positive_rate(cls, value):
        from decimal import Decimal
        if Decimal(value) <= 0:
            raise ValueError("Exchange rate must be positive")
        return value
