# Telegram customer bot foundation

Python 3.12+, aiogram 3, HTTP backend. This is a working customer subset, **not a
claim that the production SRS is complete**. All commerce decisions remain in the
backend; the bot never modifies a database or creates wallet credits.

## Run

From the repository root, install `bot/requirements.txt` into your virtual
environment, start the backend, and run:

```sh
export BOT_API_URL=http://127.0.0.1:8000/api/bot
export BOT_INTERNAL_TOKEN='<same private service token as the backend>'
export BOT_TOKEN='<BotFather token>'
export BOT_DEFAULT_LOCALE=ru
python -m bot
```

Do not paste real tokens into source files, screenshots, tickets or shared shell
history. Load them through your deployment's secret manager. Without `BOT_TOKEN`,
the process exits successfully without creating a bot client or polling Telegram.
There is no demo-token fallback, impersonation endpoint or authentication bypass.

Production requires `APP_ENV=production` and `REDIS_URL`; startup pings Redis and
fails if it is unavailable. FSM and per-user event isolation both use Redis.
Redis keys include the bot ID so different bots sharing Redis cannot share FSM
state or user locks. State expires after 24 hours, making older confirmation
buttons safely stale.
`development`, `demo` and `test` may use local MemoryStorage when `REDIS_URL` is
absent; it loses all FSM/navigation state on restart and is not production-safe.
Run one long-polling instance per bot token. Webhook deployment is not implemented.

Use TLS for a remote backend and restrict the bot API to trusted service traffic.
The internal bearer token must have at least 32 characters, grants authority to act for Telegram customers and
must never be exposed to a browser. The Telegram user ID is obtained only from
the Telegram update sender, never from callback data or customer-entered text.

## Supported customer flow

- Private chat `/start`, backend user context, current wallet and live stock.
- Subscription gate: `getChatMember` before each routed interaction; errors,
  missing channel configuration, and non-membership all deny access. Disabling
  the gate requires an explicit backend `enabled: false`. The bot must be an
  administrator in the required channel for reliable membership checks.
- Dynamic sections → countries → SKU cards. Seven-row pagination; localized
  name/ISO/alias substring search; alphabetical, price-ascending and
  stock-descending country sorting. Nothing is populated from hard-coded country
  or product lists.
- Quantity FSM with plus/minus, direct integer entry, cancel and removal. This
  foundation edits the **absolute final quantity** rather than an additive
  quantity. Buttons carry a per-screen nonce so a stale selector cannot mutate a
  different selection. Backend revalidates stock and limits on every mutation.
- Server-calculated cart, pagination, clear, wallet, explicit checkout
  confirmation and backend idempotency key. A failed/ambiguous network request is
  not automatically retried; pressing the same confirmation retries the same
  key and original server quote. The quote is captured with the displayed total,
  never refreshed silently at payment. If prices, cart contents or wholesale
  entitlement change, the old confirmation is invalidated and the customer must
  review the cart and explicitly reconfirm. Check purchases before beginning a
  new checkout after a network failure.
- Purchase history, order detail, and explicit retrieval of owner-authorized
  delivery as a protected Telegram JSON document. Payloads are not placed in
  callback data, UI logs or public links. Telegram content protection is not DRM;
  customers can still retain their purchases.
- Manual-card requests only when backend configuration explicitly enables them;
  they create pending operator review and **never credit the wallet directly**.
  Transfer instructions and support contacts come from configuration/backend.
- Optional wholesale-password input is posted directly to the backend for
  verification/throttling; it is never saved in FSM. The bot attempts to delete
  the password message, but Telegram deletion can fail. Admin-granted access does
  not require enabling password entry. The current backend restricts password
  entry to demo mode with a valid versioned scrypt `WHOLESALE_PASSWORD_HASH`;
  production password entry remains disabled until durable throttling is added.
- Configured HTTPS support, reviews, stock, terms and privacy links; absent or
  invalid links are omitted. Unsolicited text outside FSM states is ignored.

## Localization

All bot-authored screen copy and feedback is in `bot/locales/ru.json` and
`uk.json`. Telegram's language selects ru/uk; other languages fall back to
`BOT_DEFAULT_LOCALE`. Product titles/descriptions are data, not hard-coded copy.

To customize wording without editing handlers, set `BOT_TEMPLATES_DIRECTORY` to
a private directory containing partial `ru.json` / `uk.json` overrides. Keys and
format placeholders are validated at startup. Templates may contain trusted
Telegram HTML; substituted catalog/user data is HTML escaped. Button labels are
plain text. Template changes require restarting the bot.

## Verification

```sh
python -m unittest discover -s bot/tests -v
env -u BOT_TOKEN python -m bot
```

Tests exercise ru/uk parity, template overrides, integer money, HTML escaping,
safe links, dynamic pagination, production configuration, authenticated HTTP
requests, gate failures, group isolation, actual aiogram dispatcher navigation,
quantity FSM, stale callbacks, checkout-key replay and backend-only wholesale
verification. Dispatcher tests simulate Telegram and HTTP with aiogram's session
interface and httpx transports. With repository `requirements.txt` installed,
three additional contract tests run the actual FastAPI/SQLAlchemy backend in a
fresh temporary SQLite database: catalog rendering, insufficient-funds rollback,
atomic checkout, idempotent replay, wallet debit, cart clearing, owner-only
decrypted delivery, stale-quote rejection after price/entitlement changes,
authenticated service access and pending-only manual top-ups.
Otherwise those three integration tests are explicitly skipped. No real Telegram
token or channel is needed. Live
Telegram membership permissions, actual customer delivery and production Redis
must still be verified in staging with authorized test data.

## Remaining SRS scope

No claim of provider integration: CryptoBot, xRocket, Heleket, external inventory
adapters and auth-code retrieval are not exposed. No Telegram authentication,
2FA, rate-limit or ownership bypass exists. Deliver only lawfully controlled
inventory through the backend's permitted adapter.

Not implemented here: banner/media administration, E.164/calling-code country
search, popularity and structured age sorting, configurable zero-stock country
universe, manual receipt upload/status polling/cancellation, external-provider
invoices, archive packaging/signed downloads, automated outbox delivery/retries,
stock-channel publishing, browser-based message editing, webhook scaling or
production monitoring. The backend must implement authentication, ownership,
wholesale authorization and throttling, atomic checkout, immutable ledger,
inventory reservation/preflight, encrypted storage and operator review. See
`bot/API_CONTRACT.md` for the service boundary and actual endpoint schemas.
