# Telegram Digital-Goods Marketplace Bot — Production SRS
## Reference implementation based on the audited `@arshisneybot` behavior
**Document version:** 1.0

**Target:** production-ready Telegram bot + backend + admin/inventory system

**Primary interface:** Telegram Bot

**Secondary interface:** private web admin panel

**Language:** Russian/Ukrainian-ready, all user-facing text must be configurable through i18n/message templates

**Currency model:** USD as base price/balance currency; optional UAH display equivalent
**Status:** implementation specification

---

# 0. Purpose

Build a production-ready Telegram marketplace that reproduces the audited product behavior while removing hard-coded business data and making inventory, prices, payment providers, links, support contacts, banners, exchange rates, texts, and external supplier integration configurable.

The client must be able to populate phone-number/account inventory in one of four ways:

1. manually through the admin panel;
2. bulk import from CSV/JSON;
3. push inventory through a protected REST API/webhook;
4. connect the client’s existing inventory/service through a provider adapter.

The bot must not depend on the developer manually inserting products after launch.

All delivery actions must operate only on inventory lawfully controlled by the client or supplied by an explicitly authorized upstream service. The system must not attempt to bypass Telegram authentication, 2FA, rate limits, ownership checks, or other platform protections.

---

# 1. Product scope

The system consists of:

- Telegram customer bot;
- backend API;
- PostgreSQL database;
- Redis for cache, FSM, locks, idempotency, and short-lived reservations;
- background worker/queue;
- private admin panel;
- inventory/provider integration layer;
- payment-provider integration layer;
- file/object storage for receipts and deliverable archives;
- notification publisher for stock channels;
- audit log;
- monitoring and alerting.

The bot must cover:

- subscription gate;
- main menu;
- catalog;
- retail and protected wholesale catalog;
- country discovery/search/sort;
- product-type discovery/search/sort;
- product cards;
- cart;
- balance;
- top-up;
- checkout;
- inventory reservation/pre-flight;
- purchase history;
- automatic or assisted digital delivery;
- help/legal links;
- stock notifications;
- admin inventory management;
- manual payment review;
- provider/webhook ingestion;
- operational dashboards.

---

# 2. Core business rules

## BR-001 — Internal balance
All catalog purchases are paid from the user's internal USD balance.

## BR-002 — Top-up != purchase
Payment providers only increase internal balance. Checkout never directly charges CryptoBot/xRocket/Heleket/card.

## BR-003 — Atomic checkout
A completed checkout must either:

- debit the exact total and create the order; or
- fail without partial debit.

## BR-004 — Inventory is finite
Each inventory unit is an individually trackable stock object.

## BR-005 — No overselling
One stock unit may belong to at most one successful order.

## BR-006 — Reservation
During checkout, inventory must be reserved atomically before balance debit is finalized.

## BR-007 — Pre-flight
Before delivery, the inventory adapter can verify that the unit is still deliverable.

## BR-008 — Failed pre-flight
If a reserved unit fails pre-flight:

- do not charge the customer for that unit;
- release/remove failed stock;
- attempt replacement from the same SKU if available;
- otherwise reduce/fail the order according to the configured all-or-nothing policy.

Default: **all-or-nothing** for a cart checkout.

## BR-009 — Base currency
Store all balances, prices, ledger movements, fees, and order totals as integer minor units or `NUMERIC`, never floating point.

## BR-010 — Display exchange rate
UAH is display-only unless the client explicitly enables UAH accounting.

## BR-011 — Provider fees
Provider fees are added to the user's top-up payment and do not reduce the requested amount credited to internal balance.

## BR-012 — Expired invoice
An expired top-up invoice cannot be credited automatically unless the provider confirms a valid late payment and the reconciliation process explicitly accepts it.

## BR-013 — Idempotency
Every payment webhook, inventory webhook, delivery action, balance operation, and order mutation must be idempotent.

## BR-014 — Auditability
Every balance change and every stock status change must have an immutable audit trail.

---

# 3. Roles and permissions

## 3.1 Customer
Can:

- start bot;
- pass subscription gate;
- browse retail catalog;
- search/sort;
- use cart;
- top up;
- purchase;
- view purchases;
- receive delivery data;
- open support/help/reviews/stock channels.

## 3.2 Wholesale customer
Customer + `wholesale_access=true`.

Access may be granted by:

- password;
- admin flag;
- invite code;
- allowlist;
- external CRM/provider rule.

Default audited behavior: password unlock.

## 3.3 Support operator
Can:

- search user/order/top-up;
- inspect status;
- resend permitted delivery;
- review payment evidence;
- create support note;
- approve/reject manual top-ups if authorized.

Cannot change global configuration unless separately granted.

## 3.4 Inventory operator
Can:

- create/edit SKUs;
- upload stock;
- quarantine stock;
- change prices if granted;
- reconcile provider stock.

## 3.5 Administrator
Full control over:

- users;
- catalog;
- providers;
- payments;
- prices;
- exchange rate;
- links;
- banners;
- message templates;
- stock;
- wholesale access;
- support;
- reports;
- system settings.

## 3.6 Super-admin
Can additionally manage:

- admin accounts;
- RBAC;
- secrets;
- API credentials;
- destructive operations;
- audit-log export.

---

# 4. Telegram UX rules

## UX-001
The bot uses inline keyboards as the primary navigation method.

## UX-002
Free text outside an expected FSM/input state is ignored by default.

Optional configuration:
`unknown_text_behavior = ignore | show_menu | help_message`.

Default: `ignore`.

## UX-003
Input states must always provide an **Отменить** action.

## UX-004
Section screens may be sent as:

- a new photo/banner message; or
- edited existing message/media.

Behavior must be consistent per flow.

## UX-005
Short feedback uses callback toast/alert when possible.

Examples:

- subscription confirmed;
- item added;
- cart cleared;
- top-up cancelled;
- payment not found;
- loading/checking status.

## UX-006
Every callback payload must be compact, versioned if necessary, and server-resolved. Do not encode sensitive data in callback data.

Example:
`cat:c:840:p:2`

## UX-007
All message texts must come from templates, not be scattered through handlers.

## UX-008
All keyboards must be generated from data, not hard-coded country lists.

---

# 5. `/start` and subscription gate

## 5.1 Flow

1. User sends `/start`.
2. Create or update user.
3. Check configured required Telegram channel membership.
4. If not subscribed:
   - show access-limited screen;
   - button `Подписаться ↗`;
   - button `Проверить`.
5. On `Проверить`:
   - call Telegram `getChatMember`;
   - accepted states configurable, default:
     - member;
     - administrator;
     - creator.
6. If confirmed:
   - show success alert;
   - display main menu.
7. `/start` by already eligible customer displays main menu again.

## 5.2 Settings

```yaml
subscription_gate:
  enabled: true
  required_chat_id: ""
  public_url: ""
  accepted_statuses:
    - member
    - administrator
    - creator
  cache_seconds: 30
```

## 5.3 Failure handling

If Telegram cannot verify membership:

- do not falsely confirm;
- show retry action;
- log Telegram API error;
- retry with exponential backoff only for server-side calls;
- do not loop infinitely.

---

# 6. Main menu

Main menu must display:

- brand name;
- current internal balance;
- live stock count;
- configured banner.

Buttons:

```text
[🏛 Каталог]
[💲 Баланс] [💳 Мои покупки]
[🛒 Корзина]
[👥 Отзывы ↗] [💬 Помощь]
[ⓘ Уведомление о наличии товаров ↗]
```

## 6.1 Live stock count

Definition:

`available inventory units visible to customer under retail catalog`

Do not count:

- sold;
- reserved;
- quarantined;
- invalid;
- disabled SKU stock;
- expired provider stock.

Configuration may optionally count wholesale inventory separately.

---

# 7. Catalog hierarchy

```text
Catalog
 ├── Retail catalog
 │    └── Country
 │         └── SKU / department / product type
 │              └── individual stock units
 └── Wholesale catalog
      └── same hierarchy or separate catalog tree
```

---

# 8. Catalog root

Screen:

- catalog banner;
- `Выберите раздел`.

Buttons:

```text
[◤ ТГ]
[◤ ТГ (опт) - закрытый]
[🏠 В меню]
```

Catalog sections must be database records so additional sections can be added without code changes.

Schema concept:

```text
catalog_section
- id
- code
- title
- visibility
- requires_access_flag
- sort_order
- enabled
```

---

# 9. Wholesale access

## 9.1 Password mode

When customer opens protected section:

- enter FSM `WHOLESALE_PASSWORD`;
- prompt for password;
- provide `Отменить`.

Wrong password:

- remain in the state;
- show error;
- rate-limit retries.

Correct password:

- persist access flag;
- store who/when/how access was granted;
- open wholesale catalog.

## 9.2 Security

Do not store plaintext password.

Use:

- Argon2id or bcrypt hash;
- password rotation;
- attempt throttling;
- optional temporary lockout.

Recommended:
5 failed attempts / 15 min / Telegram user + IP where applicable.

---

# 10. Country list

## 10.1 Row format

Each country button:

- flag;
- localized country name;
- minimum available SKU price when stock > 0;
- number of available stock units.

Example logical format:

```text
🇺🇦 Украина от 3.80 $ (1)
🇦🇺 Австралия (0)
```

## 10.2 Pagination

Default:
7 countries/page.

Pagination keyboard:

```text
[<] [2/29] [>]
[🔍 Поиск] [Сортировка]
[↩ Назад]
```

Page count is computed dynamically.

## 10.3 Country universe

Country data must come from a canonical country table:

- ISO 3166-1 alpha-2;
- alpha-3;
- numeric code;
- localized name;
- English name;
- calling codes;
- flag emoji;
- search aliases.

Empty countries may still be shown if configured.

Setting:

```yaml
catalog:
  show_zero_stock_countries: true
  countries_per_page: 7
```

---

# 11. Country search

The search must accept:

- full country name;
- partial country name;
- aliases;
- ISO code;
- flag emoji;
- calling code;
- beginning/full phone number.

Normalization:

- trim;
- lowercase;
- Unicode normalize;
- remove spaces;
- ignore brackets;
- ignore hyphens;
- normalize leading `00` to `+` if desired;
- compare phone prefixes using canonical E.164 parsing.

Recommended library:
`phonenumbers`.

Search result screen displays:

- original query;
- result count;
- active sort.

Add `Сбросить поиск` once a filter is active.

---

# 12. Country sorting

Supported sorts:

- popularity descending;
- popularity ascending;
- minimum price ascending;
- minimum price descending;
- stock ascending;
- stock descending;
- alphabetic.

Popularity definition:

`completed order quantity for the country in the rolling last 30 days`.

Do not count:

- failed orders;
- refunded/reversed units;
- cancelled orders.

Selected sort persists for the user/session until reset.

---

# 13. Country page / departments

Header fields:

- selected country;
- available unit count;
- number of SKU/product types.

Rows represent SKUs.

Logical button/text:

```text
+1 USA | 14+ дней
1.20 $ ≈ <UAH>
1 шт
```

The exact UI may compress the row into one inline button.

## 13.1 SKU pagination
Separate pagination from country pagination.

## 13.2 Department search
Search only within the current country/catalog section.

Matches:

- exact SKU title;
- partial title;
- year token;
- age token;
- configured aliases.

## 13.3 Department sorting

- older first;
- newer first;
- less stock first;
- more stock first.

For age/year products, `age_rank` must be stored as structured data, not inferred from display string at runtime.

---

# 14. SKU/product model

Each product SKU describes a class of inventory.

Required fields:

```text
id
catalog_section_id
country_id
slug
title
delivery_mode
age_type
age_value
age_rank
attributes_json
description_template_key
price_usd
min_purchase_qty
max_purchase_qty_nullable
enabled
visible
sort_order
created_at
updated_at
```

Supported example product attributes:

- `14+ days`;
- `1+ month`;
- `2+ months`;
- `6+ months`;
- creation year;
- historical-use flag;
- `tdata/session+json only`;
- any client-defined metadata.

Do not parse business logic from the title. Store structured fields.

---

# 15. Product card

Display:

- SKU title;
- country;
- unit price USD;
- optional converted UAH;
- minimum purchase;
- available stock;
- quantity already in cart;
- description derived from SKU type.

Buttons:

If stock > 0:

```text
[🛒 Добавить в корзину]
[↩ Назад]
```

If stock == 0:

```text
[↩ Назад]
```

---

# 16. Quantity selector

Display:

- SKU;
- country;
- available;
- already in cart;
- max additional quantity;
- minimum quantity;
- unit price;
- computed total.

Keyboard:

```text
[−] [1] [+]
[••• Ввести вручную]
[🛒 Добавить в корзину (1)]
[↩ Назад]
```

Rules:

- `−` never goes below minimum;
- `+` never exceeds available minus already-in-cart;
- manual quantity must be integer;
- invalid input does not leave FSM;
- cart addition must re-check stock.

---

# 17. Cart

## 17.1 Cart display

Show:

- total item quantity;
- total USD;
- current balance;
- every line item:
  - SKU;
  - country;
  - quantity;
  - line total.

Buttons:

```text
[📄 Изменить корзину]
[⊗ Очистить корзину]
[💳 Оплатить всё]
[🏠 В меню]
```

## 17.2 Empty cart

```text
🛒 Корзина
Пока пусто.
```

## 17.3 Edit cart

Flow:

1. show line items;
2. select line;
3. show quantity editor;
4. permit:
   - minus;
   - plus;
   - manual quantity;
   - remove;
   - back.

## 17.4 Cart freshness

Cart itself does not permanently reserve inventory.

Before checkout:

- re-query available stock;
- clamp/flag lines whose requested quantity is no longer available.

Optional:
soft reservation for 2–5 min after checkout begins.

---

# 18. Checkout

## 18.1 Insufficient balance

Flow:

1. user presses `Оплатить всё`;
2. callback toast `Проверяю корзину…`;
3. calculate current cart total;
4. compare with available wallet balance;
5. if insufficient:
   - do not reserve inventory;
   - do not prepare delivery;
   - show amount due and balance;
   - button `Пополнить баланс`;
   - button `В меню`.

## 18.2 Successful checkout algorithm

Use one database transaction where possible and distributed lock where external reservation is involved.

Pseudo-flow:

```text
1. acquire checkout lock(user_id)
2. reload cart
3. validate SKU visibility and price
4. calculate server-side total
5. verify wallet balance
6. reserve exact stock units
7. run provider/internal pre-flight
8. replace failed units if possible
9. create order
10. create order_items
11. create immutable wallet debit ledger record
12. mark stock SOLD / attach order
13. clear cart
14. commit
15. enqueue delivery
16. release lock
```

Never trust client-side/callback price.

## 18.3 Concurrency

Use:

- `SELECT ... FOR UPDATE SKIP LOCKED` for local stock; or
- provider reservation tokens for external stock.

Do not select `N` rows and update later without a lock.

---

# 19. Purchase history

Empty state:

```text
🛒 Мои покупки
Пока пусто.
```

When orders exist, show newest first.

Order list item:

- order number;
- date/time;
- total;
- item count;
- status.

Order detail:

- each SKU;
- quantity;
- delivered units;
- delivery status;
- guarantee deadline if used;
- action to retrieve/resend permitted delivery;
- support link.

Recommended pagination:
5–10 orders/page.

---

# 20. Inventory unit model

Every individual deliverable account/number is a separate unit.

Required fields:

```text
inventory_unit
- id UUID
- external_provider_id nullable
- external_item_id nullable
- sku_id
- phone_e164 nullable
- country_id
- status
- delivery_mode
- payload_type
- payload_encrypted nullable
- payload_object_key nullable
- upstream_reservation_token nullable
- upstream_expires_at nullable
- source
- cost_usd nullable
- acquired_at nullable
- account_created_at nullable
- metadata_json
- reserved_by_order_id nullable
- reserved_until nullable
- sold_order_id nullable
- last_preflight_at nullable
- last_preflight_status nullable
- created_at
- updated_at
```

Statuses:

```text
AVAILABLE
RESERVED
SOLD
QUARANTINED
INVALID
EXPIRED
DISABLED
RETURNED
```

---

# 21. Delivery modes

The system must support adapter-based delivery modes rather than one hard-coded method.

## 21.1 `PHONE_AND_AUTH_CODE`

Data initially available:

- phone number;
- external item ID or authorized session reference.

Delivery sequence:

1. reveal phone number to buyer;
2. buyer explicitly requests code;
3. backend asks the authorized upstream provider for the code;
4. poll only within provider limits and configured timeout;
5. deliver code if provider returns it;
6. log retrieval and response;
7. never bypass Telegram 2FA or security controls.

## 21.2 `TDATA_ARCHIVE`

Inventory holds:

- encrypted object-storage pointer to archive.

Delivery:

- generate single-use or short-lived signed download;
- optional direct Telegram document upload if configured;
- mark delivery event.

## 21.3 `SESSION_JSON`

Same as archive, but payload may contain one or more files.

## 21.4 `COMBINED_ARCHIVE`

Can package:

- tdata;
- session JSON;
- optional readme generated by the client.

## 21.5 `EXTERNAL_PROVIDER_DELIVERY`

The upstream service returns the final deliverable after purchase.

---

# 22. Client inventory/service integration

This is a mandatory part of the project.

The developer must implement a provider interface so the client can later provide their existing service without rewriting catalog/order code.

## 22.1 Provider interface

```python
class InventoryProvider:
    async def healthcheck(self) -> ProviderHealth: ...
    async def list_stock(self, cursor=None) -> StockPage: ...
    async def get_item(self, external_item_id: str) -> ProviderItem: ...
    async def reserve(self, external_item_id: str, ttl_seconds: int) -> Reservation: ...
    async def release(self, reservation_id: str) -> None: ...
    async def preflight(self, reservation_id: str) -> PreflightResult: ...
    async def commit_sale(self, reservation_id: str, order_id: str) -> CommitResult: ...
    async def get_delivery(self, external_item_id: str) -> DeliveryPayload: ...
    async def request_auth_code(self, external_item_id: str) -> AuthCodeResult: ...
```

Methods may map to different upstream APIs. Unsupported operations must return a typed capability error, not crash the flow.

## 22.2 Provider capabilities

Each provider record exposes:

```json
{
  "can_list_stock": true,
  "can_push_stock": true,
  "can_reserve": true,
  "can_release": true,
  "can_preflight": true,
  "can_commit": true,
  "can_get_delivery": true,
  "can_request_auth_code": false
}
```

The order engine adapts to capabilities.

## 22.3 Pull synchronization

If the client service has a stock API:

- scheduled worker polls changed inventory;
- use cursor/incremental sync if available;
- upsert by `(provider_id, external_item_id)`;
- never duplicate stock;
- mark missing provider items according to configured policy:
  - unavailable;
  - quarantine;
  - leave unchanged.

Recommended interval:
30–120 seconds, configurable.

## 22.4 Push synchronization

If client service can send webhooks:

Endpoint:

`POST /api/v1/providers/{provider_id}/inventory-events`

Events:

```text
inventory.created
inventory.updated
inventory.deleted
inventory.sold_upstream
inventory.restored
inventory.code_ready
```

Requirements:

- HMAC or asymmetric signature verification;
- timestamp tolerance;
- event ID idempotency;
- replay protection;
- structured error response;
- audit log.

## 22.5 Manual API for the client

Protected endpoint for client-side stock insertion:

`POST /api/v1/inventory/bulk`

Example schema:

```json
{
  "items": [
    {
      "external_item_id": "client-123",
      "sku_code": "ua_1m",
      "phone_e164": "+380XXXXXXXXX",
      "delivery_mode": "PHONE_AND_AUTH_CODE",
      "account_created_at": "2026-07-01T00:00:00Z",
      "metadata": {}
    }
  ]
}
```

Authentication options:

- API key + HMAC;
- OAuth2 client credentials;
- mTLS for enterprise deployment.

Default recommendation:
API key ID + HMAC secret + IP allowlist where practical.

## 22.6 CSV import

Admin supports `.csv` and `.json`.

CSV columns:

```text
external_item_id
sku_code
phone_e164
country_iso2
delivery_mode
account_created_at
payload_file
price_override_usd
metadata_json
```

Import process:

1. upload;
2. parse;
3. validate;
4. show preview;
5. show errors per row;
6. confirm;
7. transactional/batched import;
8. final report.

No silent row drops.

## 22.7 Manual admin entry

Admin can create one stock unit by form.

Required:

- SKU;
- delivery mode;
- phone or payload depending on mode;
- optional external ID;
- metadata.

---

# 23. Provider reconciliation

Background reconciliation must detect:

- local AVAILABLE but upstream sold;
- local RESERVED but reservation expired;
- local SOLD but upstream commit missing;
- duplicate external IDs;
- SKU mapping failures;
- country mismatch;
- invalid phone format;
- missing payload;
- unknown provider state.

Admin dashboard must display these as actionable reconciliation issues.

---

# 24. SKU mapping from upstream service

The upstream service may use its own categories.

Implement mapping table:

```text
provider_sku_mapping
- provider_id
- external_sku_id
- local_sku_id
- enabled
- transform_json
```

No code deployment should be required to remap provider SKU IDs.

---

# 25. Stock notifications

When stock is added and transitions into sellable availability, publish a message to configured Telegram stock channel/group.

Message data:

- catalog;
- country;
- SKU;
- unit price;
- optional UAH equivalent;
- number added;
- current available stock.

Rules:

- aggregate bursts within a configurable window, e.g. 10–30 sec;
- do not announce quarantined/invalid stock;
- do not post duplicate notifications for replayed webhooks;
- support disabling notifications per SKU/provider.

---

# 26. Balance

Balance screen:

```text
💲 Баланс: X.XX $
[💳 Пополнить баланс]
[🏠 В меню]
```

Wallet is ledger-backed.

Do not use a mutable `users.balance` value as the only source of truth.

Recommended:

```text
wallet_account
wallet_ledger_entry
wallet_balance_snapshot
```

Ledger entry types:

```text
TOPUP
PURCHASE
REFUND
ADJUSTMENT
CHARGEBACK
REVERSAL
BONUS
```

---

# 27. Top-up menu

Payment methods are configurable and ordered.

Default target methods:

```text
[💳 Украинской картой]
[💠 Crypto Bot (+3%)]
[🚀 xRocket (+1.5%)]
[💎 Heleket (+2%)]
[↩ Назад]
```

All percentages and labels must be config/database values.

---

# 28. Top-up amount validation

Amount is entered in USD.

Config:

```yaml
payments:
  min_topup_usd: 1.00
  max_topup_usd: 10000.00
```

Validation:

- numeric only;
- max 2 decimals unless provider requires otherwise;
- positive;
- within provider limits;
- server calculates fee.

Formula:

```text
requested_credit = 10.00
fee_rate = 0.03
provider_fee = provider-specific rounding
amount_to_pay = requested_credit + provider_fee
wallet_credit_on_success = requested_credit
```

---

# 29. Exchange rate

Use one central service.

Sources, in priority order:

1. admin-fixed rate;
2. configured FX API;
3. cached last-good rate.

Store:

- rate;
- source;
- timestamp;
- who changed it if manual.

Do not silently use a stale rate beyond configured maximum age.

Example config:

```yaml
fx:
  base: USD
  display: UAH
  mode: admin_or_api
  max_staleness_minutes: 180
```

---

# 30. Manual Ukrainian-card flow

The production system must **not hard-code** payment card, IBAN, legal entity, tax ID, or recipient name from the reference bot.

Store client data in encrypted configuration/admin settings.

Flow:

1. customer enters desired USD credit;
2. create top-up request;
3. calculate UAH using active rate;
4. show configured payment methods/recipient details;
5. set TTL, default 15 min;
6. customer uploads receipt/document/image;
7. store evidence in private object storage;
8. create operator-review task;
9. operator approves/rejects;
10. approval creates exactly one ledger credit;
11. customer receives result notification.

States:

```text
CREATED
WAITING_RECEIPT
UNDER_REVIEW
APPROVED
REJECTED
EXPIRED
CANCELLED
```

Requirements:

- duplicate receipt detection where feasible;
- operator note;
- reason required for rejection;
- approval requires permission;
- double approval cannot double-credit.

---

# 31. CryptoBot integration

Configurable provider fee default:
3%.

Flow:

1. create internal top-up;
2. call provider invoice API;
3. store provider invoice ID;
4. show:
   - invoice number;
   - requested credit;
   - fee;
   - total;
   - TTL;
   - status;
5. URL button opens provider invoice;
6. `Проверить оплату` performs provider status check;
7. webhook is authoritative where available;
8. paid event credits wallet idempotently.

Default TTL:
30 min.

Never trust Telegram deep-link return alone as payment proof.

---

# 32. xRocket integration

Configurable provider fee default:
1.5%.

Flow mirrors CryptoBot except manual `Проверить оплату` button is optional/disabled by provider capability.

Default:
automatic credit via webhook/API reconciliation.

Default TTL:
30 min.

---

# 33. Heleket integration

Configurable provider fee default:
2%.

Flow:

1. request USD credit;
2. create hosted invoice;
3. show base USD;
4. explain provider/network fee may be finalized by hosted page;
5. open hosted payment page;
6. webhook confirms payment;
7. credit internal balance;
8. reconcile status in background.

Default TTL:
60 min.

---

# 34. Payment provider abstraction

```python
class PaymentProvider:
    async def create_invoice(self, request: CreateInvoice) -> Invoice: ...
    async def get_status(self, external_invoice_id: str) -> PaymentStatus: ...
    async def cancel(self, external_invoice_id: str) -> None: ...
    async def verify_webhook(self, headers, body) -> VerifiedWebhook: ...
```

Providers:

- `manual_card`;
- `cryptobot`;
- `xrocket`;
- `heleket`;
- future providers.

Do not mix provider-specific logic into Telegram handlers.

---

# 35. Payment webhooks

Requirements:

- verify signature;
- parse raw body before mutation;
- validate amount/currency/invoice ID;
- enforce event idempotency;
- transactionally create ledger credit;
- log rejected webhooks;
- return HTTP 2xx only after safe handling;
- do not expose secret errors to public caller.

Reconciliation worker must periodically verify pending invoices because webhooks can fail.

---

# 36. FSM/input states

Minimum states:

```text
WHOLESALE_PASSWORD
COUNTRY_SEARCH
DEPARTMENT_SEARCH
CART_QUANTITY_MANUAL
CART_EDIT_QUANTITY_MANUAL
TOPUP_AMOUNT_MANUAL_CARD
TOPUP_AMOUNT_CRYPTOBOT
TOPUP_AMOUNT_XROCKET
TOPUP_AMOUNT_HELEKET
MANUAL_CARD_RECEIPT_WAIT
```

Each state must define:

- allowed input types;
- validation;
- timeout;
- cancel behavior;
- restore behavior after restart.

Use Redis-backed FSM so process restarts do not lose active input states.

---

# 37. Help section

Help screen includes configurable buttons:

- User Agreement;
- Purchase/fulfillment terms;
- Guarantee/replacement rules;
- Recommendations;
- Instructions;
- FAQ;
- Contact support;
- Back to menu.

Do not hard-code third-party reference URLs.

All URLs live in admin-configurable settings.

---

# 38. Legal/content documents

Admin must be able to set:

- external Telegraph/website URL; or
- internally hosted Markdown/HTML page.

Documents:

```text
terms_of_service
purchase_terms
guarantee_policy
recommendations
instructions
faq
privacy_policy
```

Version fields:

- version;
- effective date;
- published;
- URL/content hash.

Optional:
store accepted Terms version per user.

---

# 39. Guarantee/replacement support data

Even if replacement is performed manually, order data must support:

```text
guarantee_started_at
guarantee_expires_at
replacement_count
replacement_limit
replacement_status
support_case_id
```

Default business values may mimic the audited store only if the client explicitly configures them.

Do not hard-code 24 h or one replacement as immutable product behavior.

---

# 40. Data model

## 40.1 `users`

```text
id
telegram_user_id UNIQUE
username
first_name
last_name
language_code
is_blocked
is_admin
wholesale_access
wholesale_access_granted_at
wholesale_access_source
created_at
updated_at
last_seen_at
```

## 40.2 `wallet_accounts`

```text
id
user_id UNIQUE
currency = USD
created_at
```

## 40.3 `wallet_ledger_entries`

```text
id UUID
wallet_account_id
type
amount
currency
reference_type
reference_id
idempotency_key UNIQUE
description
created_by_type
created_by_id
created_at
```

Use signed amount:
credit positive, debit negative.

## 40.4 `catalog_sections`

See section 8.

## 40.5 `countries`

```text
id
iso2
iso3
name_en
name_ru
name_uk
flag
calling_codes_json
aliases_json
enabled
```

## 40.6 `skus`

See section 14.

## 40.7 `inventory_units`

See section 20.

## 40.8 `carts`

```text
id
user_id UNIQUE
updated_at
```

## 40.9 `cart_items`

```text
id
cart_id
sku_id
quantity
created_at
updated_at
UNIQUE(cart_id, sku_id)
```

## 40.10 `orders`

```text
id UUID
public_order_number UNIQUE
user_id
status
subtotal_usd
total_usd
currency
created_at
paid_at
delivery_started_at
completed_at
failed_at
failure_code
metadata_json
```

Statuses:

```text
PENDING
RESERVING
PAID
DELIVERING
COMPLETED
PARTIAL
FAILED
CANCELLED
REFUNDED
```

## 40.11 `order_items`

```text
id UUID
order_id
sku_id
unit_price_usd
quantity
line_total_usd
created_at
```

## 40.12 `order_inventory_units`

```text
order_item_id
inventory_unit_id
delivery_status
delivered_at
replacement_for_inventory_unit_id nullable
```

## 40.13 `topups`

```text
id UUID
user_id
provider
status
requested_credit_usd
provider_fee
amount_to_pay
pay_currency
fx_rate nullable
external_invoice_id nullable
expires_at
paid_at nullable
credited_at nullable
cancelled_at nullable
metadata_json
created_at
```

## 40.14 `payment_events`

```text
id UUID
provider
external_event_id
topup_id nullable
event_type
payload_hash
verified
processed
processing_error
created_at
UNIQUE(provider, external_event_id)
```

## 40.15 `providers`

```text
id
code
name
enabled
adapter_type
encrypted_credentials
capabilities_json
settings_json
health_status
last_healthcheck_at
```

## 40.16 `provider_sku_mapping`

See section 24.

## 40.17 `admin_users`

Prefer SSO/OIDC where practical.

## 40.18 `audit_log`

```text
id UUID
actor_type
actor_id
action
object_type
object_id
before_json nullable
after_json nullable
request_id
ip_hash_or_address_by_policy
created_at
```

Audit log is append-only.

---

# 41. Admin panel

Required sections:

## 41.1 Dashboard

Cards:

- active users;
- 24 h revenue;
- 7 d revenue;
- outstanding wallet liability;
- available stock;
- reserved stock;
- failed preflights;
- pending manual payments;
- pending provider reconciliation;
- failed webhooks;
- provider health.

## 41.2 Users

Search by:

- Telegram ID;
- username;
- order number.

Actions:

- view wallet;
- view orders;
- grant/revoke wholesale;
- block/unblock;
- ledger adjustment with mandatory reason and RBAC.

## 41.3 Catalog

CRUD:

- sections;
- countries visibility;
- SKUs;
- prices;
- min quantity;
- descriptions;
- sorting;
- enabled state.

## 41.4 Inventory

Filters:

- provider;
- status;
- country;
- SKU;
- delivery mode;
- age;
- external ID.

Actions:

- create;
- CSV/JSON import;
- export;
- quarantine;
- restore;
- invalidate;
- inspect provider sync;
- reconcile.

Never display secret payload by default. Require privileged reveal action.

## 41.5 Orders

- list;
- detail;
- stock units;
- delivery log;
- wallet debit;
- replacement history;
- support notes.

## 41.6 Top-ups

- provider;
- invoice ID;
- status;
- amount;
- fee;
- timestamps;
- webhook events;
- manual evidence;
- approve/reject.

## 41.7 Provider integrations

- credentials;
- endpoint;
- capabilities;
- mapping;
- sync status;
- health check;
- last errors;
- force sync.

## 41.8 Bot content

- banners;
- texts;
- links;
- support usernames;
- review channel;
- stock notification channel;
- subscription gate channel.

## 41.9 Settings

- FX;
- fees;
- invoice TTLs;
- pagination;
- wholesale rules;
- rate limits;
- maintenance mode.

## 41.10 Audit

Searchable immutable change history.

---

# 42. Backend API

Recommended private/internal API namespaces:

```text
/api/v1/admin/*
/api/v1/providers/*
/api/v1/payments/webhooks/*
/api/v1/inventory/*
/api/v1/health/*
```

Telegram bot may call service-layer functions directly if deployed as one monorepo, but business logic must remain transport-independent.

---

# 43. API idempotency

For write endpoints that can be retried:

Request header:
`Idempotency-Key`.

Store:

- key;
- request hash;
- result;
- expiry.

If same key + different payload:
return conflict.

---

# 44. Security

## 44.1 Secrets

Never commit:

- bot token;
- provider API keys;
- payment secrets;
- encryption keys;
- admin credentials.

Use:

- environment-injected secret manager;
- Docker/Kubernetes secrets;
- Vault/Cloud secret manager.

## 44.2 Encryption

Sensitive inventory payloads must be encrypted at rest.

Recommended:

- envelope encryption;
- AES-256-GCM data encryption key;
- KMS-managed master key.

## 44.3 Object storage

Private bucket only.

Use signed URLs with:

- short TTL;
- single-purpose key;
- optional one-time application token.

## 44.4 Logs

Never log:

- full auth codes;
- full session JSON;
- raw tdata contents;
- full payment credentials;
- API secrets.

Mask phone numbers in ordinary logs.

## 44.5 Admin security

- HTTPS only;
- secure cookies;
- CSRF protection;
- MFA strongly recommended;
- RBAC;
- login rate limit;
- session timeout;
- audit every privileged action.

## 44.6 Webhook security

- signature verification;
- replay prevention;
- rate limiting;
- strict content type;
- body-size limit.

---

# 45. Anti-abuse and rate limits

Minimum rate limits:

- `/start`;
- subscription checks;
- search inputs;
- wholesale password;
- invoice creation;
- payment check;
- auth-code request;
- checkout;
- file uploads.

Example:

```text
auth-code request: provider-specific, never more aggressive than upstream allowance
payment status button: 1 / 5 sec
checkout: 1 concurrent request/user
search: 5 / sec burst, lower sustained
```

Use Redis token bucket/sliding window.

---

# 46. Reliability

## 46.1 Queue jobs

Use background workers for:

- provider sync;
- payment reconciliation;
- stock notifications;
- delivery;
- stale reservation release;
- invoice expiry;
- receipt processing;
- scheduled reports.

## 46.2 Retry policy

Retry only transient errors.

Example:

```text
attempts: 5
backoff: exponential + jitter
dead-letter after final failure
```

Do not retry semantic failures such as invalid credentials indefinitely.

## 46.3 Distributed locks

Use locks for:

- checkout per user;
- provider reservation item;
- wallet mutation if needed;
- manual top-up approval.

---

# 47. Observability

Expose metrics:

```text
telegram_updates_total
telegram_handler_errors_total
orders_created_total
orders_completed_total
orders_failed_total
checkout_latency_seconds
wallet_credits_total
wallet_debits_total
topups_by_provider_total
payment_webhook_failures_total
inventory_available
inventory_reserved
inventory_preflight_failures_total
provider_sync_errors_total
provider_health
delivery_failures_total
queue_depth
```

Use:

- structured JSON logs;
- request/correlation IDs;
- Sentry/OpenTelemetry;
- Prometheus/Grafana or managed equivalent.

Alerts:

- provider down;
- payment webhook error spike;
- order failures spike;
- queue backlog;
- DB connection exhaustion;
- low disk/storage;
- manual top-up backlog.

---

# 48. Deployment

Recommended stack:

```text
Python 3.12+
aiogram 3.x
FastAPI
PostgreSQL 16+
Redis 7+
SQLAlchemy 2 + Alembic
Pydantic 2
ARQ/Celery/Dramatiq
S3-compatible object storage
Next.js/React admin panel
Docker
Nginx/Caddy or managed ingress
```

Recommended services:

```text
bot
api
worker
scheduler
admin-web
postgres
redis
object-storage/external
reverse-proxy
monitoring
```

Telegram bot mode:
webhook preferred in production.

Long polling may be supported for development.

---

# 49. Environment separation

Required:

- local/dev;
- staging;
- production.

Never share:

- database;
- bot token;
- payment credentials;
- provider credentials;
- object-storage namespace.

Use separate Telegram bot for staging.

---

# 50. Database migrations

All schema changes through migrations.

Requirements:

- forward migration;
- tested rollback where feasible;
- backup before destructive production migration;
- no manual production schema edits.

---

# 51. Backups

Minimum:

- PostgreSQL daily backup;
- point-in-time recovery if hosting supports it;
- object-storage versioning where practical;
- backup retention policy;
- quarterly restore test.

For wallet/order systems, restore testing is mandatory.

---

# 52. Telegram media/banners

Admin-configurable banner slots:

```text
main_menu
catalog
balance
cart
purchases
help
```

Store Telegram `file_id` after first upload to avoid repeated media uploads.

Fallback to object storage URL/file if file_id is unavailable.

---

# 53. Message/template management

Templates must support variables.

Example:

```text
main_menu:
  "🏪 {brand_name}\n\n💲 Баланс: {balance_usd}\n🗃 Товаров в наличии: {stock_count}"
```

Validation must reject templates with unknown mandatory placeholders.

---

# 54. Error UX

User-facing errors must be categorized.

## 54.1 Recoverable
Examples:

- invalid quantity;
- invoice not yet paid;
- stock changed;
- invalid search.

Show concise retry/cancel actions.

## 54.2 Operational
Examples:

- payment provider unavailable;
- provider inventory API unavailable.

Show:

- temporary-unavailable text;
- safe back/menu action;
- support link where relevant.

## 54.3 Internal
Never show stack trace, SQL error, provider secret, raw API response.

Give error/reference ID.

---

# 55. Maintenance mode

Admin can enable:

- full maintenance;
- checkout-only disabled;
- top-up disabled;
- provider-specific disabled.

Browsing may remain available.

---

# 56. Data retention

Configurable policy.

Recommended:

- payment/audit/order records according to legal/accounting needs;
- auth-code retrieval logs without retaining code value;
- uploaded receipts retained only as required;
- expired sensitive delivery links revoked immediately;
- secrets/payloads deleted or archived under client policy.

Provide admin tools for lawful deletion/anonymization where applicable.

---

# 57. Testing

## 57.1 Unit tests

Required coverage:

- wallet math;
- fee calculation;
- FX conversion;
- cart totals;
- stock allocation;
- sorting;
- search normalization;
- provider mapping;
- payment idempotency;
- webhook verification;
- FSM validators.

## 57.2 Integration tests

- Telegram handler -> service -> DB;
- checkout transaction;
- concurrent checkout;
- provider reserve/release;
- provider sync;
- payment webhook -> wallet credit;
- invoice reconciliation;
- delivery worker.

## 57.3 Contract tests

Each external provider gets mocked contract fixtures.

## 57.4 End-to-end

At minimum:

```text
/start -> gate -> menu
menu -> catalog -> country -> SKU -> cart
cart -> insufficient balance
topup sandbox -> wallet credit
checkout -> stock reservation -> delivery
purchase history
manual card review
wholesale password
country search
country sort
department search
department sort
inventory import
provider webhook ingestion
stock notification
```

## 57.5 Race tests

Test:

- two users buying last unit;
- repeated payment webhook;
- repeated checkout callback;
- double operator approval;
- provider reservation expiry;
- bot retry after timeout.

---

# 58. Acceptance criteria

The project is not accepted until all applicable items below pass.

## AC-001
A new user who is not subscribed receives only the subscription gate.

## AC-002
After confirmed subscription, main menu appears and stock/balance are correct.

## AC-003
Catalog supports database-driven countries and SKUs.

## AC-004
7-country pagination works with any country count.

## AC-005
Country search matches name, partial name, aliases, ISO, flag, calling code, phone prefix.

## AC-006
Country sorts work exactly and persist until reset.

## AC-007
Country page stock count equals sellable unit count.

## AC-008
SKU search is scoped to current country.

## AC-009
SKU sort works using structured age/stock data.

## AC-010
Product card shows correct stock and price.

## AC-011
Cart cannot exceed current stock.

## AC-012
Manual quantity entry validates boundaries.

## AC-013
Cart edit/remove/clear is correct and idempotent.

## AC-014
Insufficient-balance checkout does not reserve or mutate stock.

## AC-015
Successful checkout cannot oversell under concurrent load.

## AC-016
Wallet debit is immutable and exactly once.

## AC-017
Order references exact inventory units.

## AC-018
Failed pre-flight does not result in a customer paying for an undeliverable unit.

## AC-019
Purchase history persists after bot/server restart.

## AC-020
Retail and wholesale access are isolated.

## AC-021
Wrong wholesale password does not unlock access.

## AC-022
Manual card receipt can be approved only once.

## AC-023
CryptoBot webhook credits exactly once.

## AC-024
xRocket webhook/reconciliation credits exactly once.

## AC-025
Heleket webhook/reconciliation credits exactly once.

## AC-026
Cancelled/expired invoice does not auto-credit without valid confirmed payment.

## AC-027
Provider webhook replay creates no duplicate stock.

## AC-028
Bulk import identifies row-level validation errors.

## AC-029
Client API can add inventory without bot restart.

## AC-030
External provider adapter can sync inventory without catalog code changes.

## AC-031
Stock notifications fire only for newly sellable stock.

## AC-032
Sensitive inventory payloads are encrypted at rest.

## AC-033
Logs contain no raw secrets/session payload/auth codes.

## AC-034
Every balance mutation is visible in the ledger and audit trail.

## AC-035
Every admin privileged action has actor, time, object, and result.

## AC-036
A process restart does not corrupt FSM/cart/order/top-up state.

## AC-037
Provider outage degrades gracefully and does not create phantom purchases.

## AC-038
All user-facing links/contacts/banners/payment details can be changed without code deployment.

## AC-039
The bot supports maintenance mode.

## AC-040
Staging uses isolated credentials and database.

---

# 59. Exact configurable business values

The following values from the audited reference must be implemented as settings, not constants:

```text
subscription channel
review link
stock notification link
support link
instruction link
legal-document links
brand name
banners
country page size
payment provider fee percentages
payment invoice TTLs
USD/UAH rate
manual payment recipient details
manual payment instructions
wholesale password/access logic
minimum purchase quantity
SKU prices
guarantee duration
replacement limit
stock notification target
```

---

# 60. Unverified behavior from the audit

The reference audit could not directly verify:

1. successful paid checkout;
2. exact final delivery payload;
3. protected wholesale catalog contents;
4. exact internal pre-flight implementation.

Therefore the implementation must use the explicit behavior defined in this SRS rather than inventing invisible reference-bot behavior.

Production defaults:

- checkout is atomic;
- pre-flight is adapter-based;
- delivery is adapter-based;
- wholesale inventory is fully data-driven;
- provider/service integration is mandatory;
- all final deliverables are tied to exact sold inventory units.

---

# 61. Required client handoff items before production launch

The client must provide/configure:

## Telegram
- production bot token;
- subscription channel ID/link;
- stock notification channel/group and bot permissions;
- review link;
- support username/link;
- instruction/help URLs.

## Branding
- brand name;
- banners;
- legal text/links;
- user-facing wording.

## Payments
For every enabled provider:

- production API credentials;
- webhook secret;
- merchant/account identifiers;
- fee policy;
- min/max;
- allowed currencies/networks where applicable.

For manual card flow:

- recipient details;
- payment purpose text;
- operator list;
- processing rules.

## Inventory
One or more:

- manual stock files;
- client API docs;
- endpoint/base URL;
- auth method;
- webhook spec;
- SKU mapping;
- sample payloads;
- reservation semantics;
- code-retrieval semantics if legally/technically supported;
- pre-flight semantics;
- error codes;
- rate limits.

## Infrastructure
- domain;
- VPS/cloud;
- Postgres;
- Redis;
- object storage;
- TLS;
- backup destination;
- monitoring destination.

---

# 62. Provider onboarding checklist

Before enabling an external inventory provider in production:

```text
[ ] Auth works
[ ] Healthcheck works
[ ] Rate limits documented
[ ] List/push inventory works
[ ] External item IDs are stable
[ ] Duplicate protection verified
[ ] SKU mapping verified
[ ] Country mapping verified
[ ] Reservation semantics verified
[ ] Reservation expiration verified
[ ] Release verified
[ ] Pre-flight verified
[ ] Commit-sale verified
[ ] Delivery payload verified
[ ] Auth-code capability verified if used
[ ] Error mapping implemented
[ ] Retry policy agreed
[ ] Reconciliation tested
[ ] Webhook signature verified
[ ] Sandbox E2E passed
```

---

# 63. Recommended repository structure

```text
repo/
├─ apps/
│  ├─ bot/
│  ├─ api/
│  ├─ worker/
│  └─ admin/
├─ packages/
│  ├─ core/
│  │  ├─ catalog/
│  │  ├─ cart/
│  │  ├─ checkout/
│  │  ├─ wallet/
│  │  ├─ payments/
│  │  ├─ inventory/
│  │  ├─ delivery/
│  │  └─ users/
│  ├─ providers/
│  │  ├─ inventory_base/
│  │  ├─ client_service/
│  │  ├─ cryptobot/
│  │  ├─ xrocket/
│  │  └─ heleket/
│  ├─ database/
│  ├─ config/
│  └─ observability/
├─ migrations/
├─ tests/
│  ├─ unit/
│  ├─ integration/
│  ├─ contract/
│  └─ e2e/
├─ infra/
│  ├─ docker/
│  ├─ nginx/
│  └─ monitoring/
├─ docs/
│  ├─ SRS.md
│  ├─ API.md
│  ├─ PROVIDER_INTEGRATION.md
│  ├─ RUNBOOK.md
│  └─ SECURITY.md
└─ docker-compose.yml
```

---

# 64. Production definition of done

The task is complete only when:

1. the bot reproduces every customer-visible audited flow covered by this SRS;
2. no core catalog/payment/inventory value is hard-coded;
3. the client can add inventory without developer intervention;
4. an external client stock service can be connected through the provider adapter;
5. the system prevents overselling;
6. all wallet operations are ledger-backed and idempotent;
7. top-ups are verified by provider/API/operator rather than user claims;
8. purchased inventory is traceable to an exact order;
9. delivery survives worker/bot restarts;
10. failed delivery jobs are recoverable;
11. admin panel covers catalog, stock, orders, top-ups, providers, users, settings, and audit;
12. all secrets are outside source control;
13. sensitive payloads are encrypted;
14. payment and provider webhooks are signed/idempotent;
15. monitoring, backups, migrations, and staging exist;
16. unit/integration/contract/E2E/race tests pass;
17. no unresolved critical/high security issue remains;
18. staging end-to-end test passes using provider/payment sandbox or mocks;
19. production runbook and `.env.example` are present;
20. the client can operate the marketplace day-to-day without editing source code.

---

# 65. Final implementation principle

Telegram handlers are only UI/controllers.

The actual business logic must live in reusable services:

```text
CatalogService
SearchService
CartService
CheckoutService
WalletService
TopupService
PaymentService
InventoryService
ProviderService
DeliveryService
NotificationService
AdminService
AuditService
```

This separation is mandatory because the client’s actual phone-number/account service is expected to be connected later. The inventory provider must be replaceable without rewriting Telegram screens, checkout, payments, wallet, orders, or admin workflows.
