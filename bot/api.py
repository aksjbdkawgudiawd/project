from typing import Any
import re

import httpx


class APIError(Exception):
    def __init__(self, code: str, status: int = 0) -> None:
        super().__init__(code)
        self.code = code
        self.status = status


class Backend:
    def __init__(self, api_url: str, token: str, transport=None) -> None:
        self.client = httpx.AsyncClient(
            base_url=api_url.rstrip("/") + "/",
            headers={"Authorization": f"Bearer {token}"},
            timeout=httpx.Timeout(20, connect=5),
            follow_redirects=False,
            transport=transport,
        )

    async def close(self) -> None:
        await self.client.aclose()

    async def request(self, user_id: int, method: str, path: str, *, payload: Any = None, key: str | None = None) -> Any:
        if user_id <= 0:
            raise ValueError("Telegram user ID must be positive")
        headers = {"X-Telegram-Id": str(user_id)}
        if key:
            headers["Idempotency-Key"] = key
        try:
            response = await self.client.request(method, path.lstrip("/"), headers=headers, json=payload)
        except httpx.HTTPError as exc:
            # Never log request headers, response payloads or delivery data.
            raise APIError("unavailable") from exc
        if not response.is_success:
            try:
                body = response.json()
                detail = body.get("detail", {})
                code = detail.get("code", "unknown") if isinstance(detail, dict) else detail
            except (ValueError, AttributeError):
                code = "unknown"
            if isinstance(code, str) and code.startswith("Insufficient wallet balance"):
                code = "insufficient_balance"
            elif isinstance(code, str) and code.startswith("Insufficient available stock"):
                code = "insufficient_stock"
            raise APIError(str(code), response.status_code)
        if response.status_code == 204:
            return None
        try:
            return response.json()
        except ValueError as exc:
            raise APIError("unavailable") from exc

    async def config(self, user_id: int) -> dict:
        return await self.request(user_id, "GET", "config")

    async def catalog(self, user_id: int) -> dict:
        return await self.request(user_id, "GET", "catalog")

    async def cart(self, user_id: int) -> dict:
        return await self.request(user_id, "GET", "cart")

    async def wallet(self, user_id: int) -> dict:
        return await self.request(user_id, "GET", "wallet")

    async def set_quantity(self, user_id: int, sku_id: str, quantity: int) -> dict:
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,40}", sku_id):
            raise APIError("invalid_sku", 400)
        return await self.request(user_id, "PUT", f"cart/items/{sku_id}", payload={"quantity": quantity})
