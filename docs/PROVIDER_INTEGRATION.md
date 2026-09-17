# Provider integration handoff

No live payment or external stock adapter is implemented. The integrations page deliberately has no “connect” switch that pretends credentials alone enable functionality. Existing services in `backend/services.py` implement **local encrypted payload inventory only**.

Before extending them, obtain the client's authorized API contract and implement typed provider capabilities at a service boundary, not inside Telegram handlers. Follow SRS sections 21–24 and 34–35.

## Inventory adapter acceptance

- Authenticated health, stable external IDs, SKU/country mapping, incremental listing and signed push ingestion.
- Explicit reserve/release/expiry semantics, idempotent commit, pre-flight and replacement behavior.
- Failure mapping and bounded retries; no phantom successful purchase on upstream failure.
- Owner-bound delivery and secret-redacted logs. Auth-code retrieval only through an explicitly authorized provider capability; never bypass authentication or 2FA.
- Reconciliation for upstream sold/expired stock, duplicate IDs and missing commits.
- Contract, race, restart and outage tests before activation.

## Payment adapter acceptance

- Create/status/cancel invoice interface; internal top-ups distinct from purchases.
- Provider-specific raw-body signature verification, replay checks and strict amount/currency/invoice validation.
- Transactional exactly-once wallet credit, bounded invoice lifetime, explicit late-payment handling.
- Pending invoice reconciliation independent of webhook arrival.
- Sandbox fixtures from authoritative provider documentation matching the chosen API version.

Do not reuse the manual top-up approval route as a public provider webhook. It is a private, authenticated administrator operation.
