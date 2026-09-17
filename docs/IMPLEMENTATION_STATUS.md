# Implementation status

## Release boundary

This repository implements a **functional MVP**, not the production definition of done in [SRS.md](SRS.md). No third-party provider is represented as connected. Seed stock consists of synthetic local digital goods, not working Telegram accounts. This avoids inventing delivery behavior for the client's unknown authorized upstream service.

### Implemented and tested locally

| Area | Available behavior |
| --- | --- |
| Admin | Cookie authentication, demo isolation, responsive dashboard, inventory/catalog/orders/top-ups/customers/settings/audit pages |
| Inventory | Per-unit records, encrypted payloads, unique references, manual entry, CSV/JSON validation preview, atomic confirmation, status management |
| Wallet/checkout | Integer USD cents, immutable ledger, nonnegative balance constraints, transactionally linked order/stock/debit, idempotent checkout, last-unit contention protection, pre-flight of local encrypted payloads |
| Payments | Manual operator decision, mandatory note, exactly-once credit; no direct provider charging at checkout |
| Bot | Private-chat-only handlers, fail-closed subscription verification, dynamic sections/countries/SKUs, search and basic sorts, pagination, quantity/cart FSM, balance, checkout confirmation, history, explicit owner-only local payload delivery |
| Wholesale | Separate server-side pricing entitlement; audited admin grants |
| Configuration | Store name, display FX, support/review/stock/terms URLs, maintenance, stock threshold; bot ru/uk template overrides loaded at startup |
| Verification | Backend unit/integration/race tests, simulated aiogram dispatcher tests, real bot-to-FastAPI contract tests, browser-tested admin mutations |

### Not complete: must not be advertised as production-ready

- CryptoBot, xRocket, Heleket invoice creation, signed webhooks, amount/currency validation, late-payment reconciliation, refunds/chargebacks, fees/TTLs.
- Client inventory provider adapters, protected external bulk API/webhook, provider SKU mapping, upstream reservation/release/commit/reconciliation, authorized authentication-code retrieval.
- Durable delivery outbox/worker, retries/dead letters, archive packaging, private object storage, receipts, expiring links, delivery acknowledgements, stock-channel publishing.
- Fine-grained operator RBAC, SSO/MFA, shared/distributed abuse limits, durable payment receipt review, temporary wholesale password lockouts across instances.
- Versioned migrations, PostgreSQL race validation, Redis integration validation, staging deployment, TLS/reverse proxy, monitoring/alerts, backup automation and restore exercises.
- Full country universe and E.164 search, audited popularity/structured age sorts, arbitrary catalog sections, quantity policies per SKU, complete banner/content/legal version management.
- Admin UI localization, runtime bot-template editing, template-backed welcome screen integration, customer block/adjustment/refund/support workflows.
- Full SRS end-to-end acceptance matrix and external provider contract tests.

The dashboard reports unavailable delivery monitoring as unknown, not a verified zero. `completed` in this MVP means local payment/allocation completed; it is not proof that Telegram delivered a document. Local delivery is retrieved explicitly by the order owner.

## Local verification evidence

The admin was exercised in the managed preview: manual stock creation and search, two-row CSV preview/confirmation, product creation and price editing, manual payment approval, settings save, and balance-funded demo checkout. The checkout returned an order and updated the ledger/stock rather than only changing client state. Desktop rendering and narrow-screen navigation were inspected separately.

Automated tests run with `npm test`; frontend typechecking/production bundling with `npm run build`. They do not establish real Telegram membership permissions, real payments, external delivery, or PostgreSQL behavior.

## Client inputs for the next implementation phase

1. Authorized inventory service documentation, sample sanitized payloads, reservation semantics and limits.
2. Payment provider choice, merchant sandbox access, settlement policy, manual-review operators.
3. Staging Telegram bot/channel, configured support/legal/review links, branding and translations.
4. Hosting/domain, PostgreSQL, Redis, private object storage, secret manager, backup and monitoring destinations.

Supply credentials through secret configuration—not source files, chat, import fixtures, or screenshots.
