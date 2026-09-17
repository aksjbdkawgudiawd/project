# Backend MVP / API contract

Run `APP_ENV=demo .venv/bin/python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000`. Demo seeds synthetic local digital-license data only. No payment or inventory provider is connected. This implements the admin and transactional core, not the full production SRS.

All admin paths are prefixed `/api/v1/admin`. Collections return **plain JSON arrays**, dates ISO strings, amounts integer USD cents. Errors use `{ "detail": "message" }`. Session cookie is HttpOnly, SameSite Strict; HTTPS Secure outside demo. Mutation requests with Origin must be same-origin (or exact configured `ADMIN_ALLOWED_ORIGINS`).

- `GET /api/v1/health`: `{status, environment, providers_connected: false}`.
- `POST /auth/demo` (explicit demo only), `POST /auth/login {username,password}`, `GET /auth/me`, `POST /auth/logout`.
- `GET /dashboard`: `revenue_cents, revenue_change, orders_count, orders_change, stock_count, stock_change, users_count, users_change, pending_topups, wallet_liability_cents, reserved_stock, pending_manual_payments, failed_deliveries, low_stock_count, low_stock, revenue_chart:[{date,label,revenue_cents,orders}], recent_orders, activity, top_products`. Wallet liability is the current sum of all balances; reserved stock counts reserved units; pending manual payments counts pending `Manual transfer` requests. `low_stock` contains active SKU objects at or below the configured threshold, sorted by available stock then name. `failed_deliveries` is **null (not tracked)**, not zero: no delivery worker/outcome tracker is implemented.
- `GET /skus`: `id,name,country,country_code,flag,category,description,retail_price_cents,wholesale_price_cents,active,provider,stock_count,sold_count,created_at`. `POST /skus` and `PUT /skus/{id}` require name,country,country_code,retail_price_cents,wholesale_price_cents; accept flag,category,description,active. `DELETE /skus/{id}` disables (preserves order history).
- `GET /inventory`: `id,sku_id,sku_name,country,country_code,flag,category,status,provider,reference,order_id,created_at` (never encrypted or plaintext payload). `POST /inventory {sku_id,reference,payload}`. `POST /inventory/{id}/status {status:available|quarantined|invalid,reason}` (sold/reserved immutable). `POST /inventory/import/preview {format:csv|json,content,sku_id?}`: `{batch_id,valid_count,total_count,errors:[{row,message}],rows:[{sku_id,reference,status}]}`. CSV columns sku_id,reference,payload; sku_id optional with shared SKU. `POST /inventory/import/confirm {batch_id}` returns `{batch_id,imported_count,replayed}`. All-or-nothing confirmation, encrypted preview, one-hour expiry.
- `GET /orders`, `GET /orders/{id}`: `id,user_id,user_name,username,total_cents,status,quantity,created_at,items:[{id,sku_id,sku_name,inventory_id,unit_price_cents}]`. Never reveals payloads through admin listing.
- `GET /topups`: `id,user_id,user_name,username,amount_cents,method,status,reference,note,review_note,reviewed_at,created_at`. `POST /topups/{id}/review {decision:approve|reject,note}`. Repeated identical decision cannot double credit.
- `GET /users`: `id,name,username,balance_cents,wholesale_access,orders_count,total_spent_cents,created_at`. `POST /users/{id}/wholesale {wholesale_access:boolean}`.
- `GET /providers`: disabled, unconfigured integration definitions; there is deliberately no enable/connect endpoint.
- `GET /audit`: `id,actor,action,entity_type,entity_id,detail,created_at` newest first. `GET /ledger`: append-only balance journal.
- `GET /settings`, `PUT /settings`: `store_name,currency:USD,display_currency:USD|UAH,usd_uah_rate:string,support_url,reviews_url,stock_channel_url,terms_url,default_language:en|ru|uk,low_stock_threshold,maintenance_mode,subscription_required,welcome_message`. HTTPS links only.
- `POST /demo/checkout` (demo only): `{user_id,items:[{sku_id,quantity}],idempotency_key,wholesale?:false,expected_total_cents?:integer}` returns order plus `replayed`. If supplied, the expected total must match locked current prices or checkout returns `409 cart_changed` before preflight/debit. Include the displayed total in the demo test bench. Genuine wallet debit/reservation/order transaction; does not mint credits.

## Security and operations

Outside demo require `ADMIN_USERNAME`, `ADMIN_PASSWORD` (at least 16 characters), and `INVENTORY_ENCRYPTION_KEY` (Fernet key). Production never seeds users or exposes demo login/checkout. Set `DATABASE_URL=postgresql://...` for PostgreSQL (psycopg 3); local demo uses `.hoplite/marketplace.sqlite3` and a private generated `.hoplite/demo-encryption.key`. Preserve that key with protected backups; losing it loses delivery payload access. Never commit database/key files.

SQLite writes use BEGIN IMMEDIATE; PostgreSQL uses row locks in deterministic SKU order. Ledger, order, inventory sale, and wallet changes commit atomically; database constraints prohibit negative balances and multiple order items per stock unit. Database triggers reject audit/ledger updates and deletion. Schema creation is for MVP startup; production migrations, fine-grained RBAC, provider integrations/webhooks, outbox delivery workers, monitoring, backups and deployment hardening remain rollout prerequisites.

Checkout locks the customer and all requested SKUs in deterministic order, computes the complete server-priced retail/wholesale total, and rejects insufficient balance before inventory preflight or reservation. The final ledger-backed debit remains in the same transaction; valid replay returns the original order even if the remaining balance is now zero.

Run `.venv/bin/python -m pytest tests/test_backend.py`.

## Browser and bot integration

Admin authentication routes and field names above are stable. Browser mutations, including login, reject cross-site Fetch Metadata and mismatched Origin scheme/host/port unless the exact origin is explicitly allowlisted. Keep production proxy scheme forwarding configured correctly; never broadly allow origins. Requests without browser Origin remain supported for server clients. All API responses, including middleware denials, carry `Cache-Control: no-store`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`, and `X-Frame-Options: DENY`.

The customer router is mounted at `/api/bot` (separate from the admin API). See `bot/API_CONTRACT.md` for its exact contract and `bot/tests/test_backend_integration.py` for real-backend integration checks. It requires `Authorization: Bearer $BOT_INTERNAL_TOKEN` (32+ characters) plus `X-Telegram-Id`, and is disabled when unconfigured. Customer wallets start at zero; cart, checkout, owned-order delivery, and manual top-up requests use the same transactional services. Never expose the bot service token in browser code. Telegram subscription verification and message handling belong to the bot; the backend trusts this authenticated transport, not arbitrary browser identity headers.

### Checkout quote confirmation

`GET /api/bot/cart` and cart mutations return `quote_token`, a SHA-256 digest of SKU IDs, quantities, current unit prices, and wholesale entitlement. Lines are sorted by SKU ID; wallet balance and display labels are excluded. Treat the token as opaque and retain it with the displayed confirmation, not a newly fetched cart at submission time.

`POST /api/bot/checkout` now **requires** JSON `{quote_token}` (64 lowercase hexadecimal characters) plus `Idempotency-Key`. Existing successful replay is checked first. Otherwise the backend locks the user and SKUs in deterministic order, recomputes the quote, and rejects changed price, quantity, items, or wholesale entitlement with `409 {"detail":"cart_changed"}` before any inventory preflight or debit. Refresh and show a new confirmation on this error. Locks remain held through checkout; a price update cannot slip between quote validation and debit. The digest detects stale confirmation; it is not a replacement for trusted bot authentication or stock/balance validation.

### Wholesale password mode

`WHOLESALE_PASSWORD` is no longer read. Demo password unlock requires `WHOLESALE_PASSWORD_HASH`, generated with `.venv/bin/python -m backend.passwords` (hidden password prompt; 12–256 characters). Store the output as a quoted environment value so its `$` separators remain literal; never commit it. The versioned format is `scrypt-v1$<16-byte salt hex>$<32-byte digest hex>`, using scrypt N=32768, r=8, p=3 and constant-time digest comparison. Parameters are fixed to prevent unbounded work from malformed configuration.

Outside explicit demo mode, password unlock always returns 503 and `/api/bot/config` reports `wholesale_password_enabled: false`, even with a valid hash. The in-process five-attempt/five-minute limiter is demo-only; password mode must stay disabled until a shared Redis limiter is implemented and verified. Administrator grants remain supported in every environment. Missing or malformed hashes disable demo unlock as well. Request/response shapes for `/wholesale/unlock` remain unchanged.
