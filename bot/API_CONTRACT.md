# Bot ↔ backend customer contract

Implemented by `backend/customer.py`; verified against the real backend by
`bot/tests/test_backend_integration.py`. Prefix: `/api/bot`.

Every request requires `Authorization: Bearer $BOT_INTERNAL_TOKEN` (32+ characters)
and `X-Telegram-Id: <positive Telegram sender ID>`. Missing backend service-token
configuration disables these routes. The backend creates zero-balance `tg-ID`
customers and enforces ownership, wholesale access and monetary rules. Never
expose this token or these headers to a browser customer.

## Read responses

- `GET /config`: `brand_name`, `manual_card_enabled`,
  `manual_card_instructions`, `wholesale_password_enabled`,
  `subscription_gate: {enabled, required_chat_id, public_url}` and
  `links: {support, reviews, stock, terms}`. The bot also understands optional
  `subscription_gate.accepted_statuses` and `links.privacy`.
- `GET /catalog`: `{sections: [{id,title,title_ru,title_uk}],
  countries: [{id,code,name,flag}],
  skus: [{id,title,description,section_id,country_id,price_cents,stock,
  min_quantity,max_quantity,wholesale}]}`. Optional localized name/description
  fields and country aliases are supported. IDs must fit compact Telegram
  callbacks; the current backend uses 32-character SKU/order IDs and ISO country
  codes. The current backend exposes one retail or wholesale section according
  to server-granted access; arbitrary database-backed sections remain future
  backend work, although the bot renders a dynamic section array.
- `GET /wallet`: `{balance_cents,currency,wholesale_access}`.
- `GET /cart`: `{items:[{sku_id,title,quantity,price_cents,line_total_cents}],
  total_cents,balance_cents,quote_token}`. The SHA-256 quote binds cart contents,
  current prices and wholesale entitlement. The bot never computes authoritative
  prices or quote tokens.
- `GET /orders`: plain array of `{id,total_cents,status,created_at}`.
- `GET /orders/{id}`: same order fields plus
  `delivery:[{title,payload}]`. Only the owning Telegram customer may retrieve
  it. The bot sends this data as a protected document only on explicit request.

## Mutations

- `PUT /cart/items/{sku_id}`: `{quantity:N}` sets **absolute** final quantity;
  zero removes. Server checks stock and limits, without reserving or charging.
- `DELETE /cart`: clear the cart.
- `POST /checkout`: `Idempotency-Key` header and required JSON
  `{quote_token: "<64-character SHA-256 hex>"}`. The bot captures the token from
  the same cart response whose total appears on the confirmation screen, stores
  it alongside the idempotency key in FSM, and submits it unchanged on payment
  and retries. It never silently fetches a newer quote at payment time.
  Returns order plus `replayed`. The backend binds the key to the customer,
  handles replay after cart clearing, validates current inventory/prices, debits,
  records delivery ownership and clears the cart atomically. A `cart_changed`
  conflict performs no payment; the bot clears the old confirmation and asks the
  customer to reopen the cart and explicitly confirm the newly displayed total.
  Successful checkout replay remains valid with the original quote after cart
  clearing.
- `POST /topups/manual`: `Idempotency-Key` and `{amount_cents}`; returns
  `{id,amount_cents,status,reference,instructions}`. Enabled only when backend
  `MANUAL_PAYMENT_INSTRUCTIONS` is configured. Requests remain pending until an
  authorized operator verifies external settlement. No bank/provider integration
  or receipt-upload endpoint is claimed. The current server accepts $1–$10,000;
  server validation remains authoritative.
- `POST /wholesale/unlock`: `{password}`. The backend alone verifies, throttles
  and persists access. The current backend enables password entry only in demo
  mode with a valid `WHOLESALE_PASSWORD_HASH` (versioned scrypt). Password entry
  is disabled outside demo because attempt throttling is process-local;
  production uses admin-granted wholesale access until durable throttling is
  implemented. No plaintext password configuration is supported.

Errors use `{"detail":"code or message"}` or `{"detail":{"code":"..."}}`.
Known business codes are localized. Unknown failures never display raw backend
responses. Mutations are not automatically retried; checkout/manual-request
screens retain an idempotency key across an ambiguous retry.
