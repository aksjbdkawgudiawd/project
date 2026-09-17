# Security boundaries

This MVP is not independently audited or approved for real customer funds.

## Implemented safeguards

- Admin sessions are random, hashed in the database, time-limited, HttpOnly and SameSite Strict; Secure cookies are used outside demo.
- Mutating browser requests are checked against their origin and cross-site fetch metadata. The development proxy preserves the browser host/protocol. Admin login is rate-limited in-process.
- Inventory payloads and import content are authenticated-encrypted at rest using Fernet. This is not the SRS's proposed KMS envelope/AES-GCM architecture; that remains deployment work.
- Listings do not return plaintext payloads. Only the owning authenticated Telegram customer can explicitly retrieve purchased local payloads. The bot sends protected documents and avoids raw secrets in handler errors.
- Integer-cent ledger changes and exact stock assignments share a transaction. Database constraints and immutable triggers guard ledger/audit integrity.
- Demo login, synthetic seed and checkout test bench require explicit demo mode. The bot service API rejects missing/weak internal credentials.
- No real upstream authentication-code capability or platform-protection bypass is implemented.

## Required hardening

Fine-grained RBAC, SSO/MFA, shared distributed rate limits, audit export/retention, immutable backup storage, secret-manager rotation, customer data deletion policy, receipts/object storage, webhook verification, deployment TLS and operational monitoring remain prerequisites. Restrict the API to trusted ingress; keep Redis and PostgreSQL private.

The database encryption key is a high-value secret. Do not include it in code, logs, reports, browser configuration or screenshots. The demo key and database are git-ignored. Separate staging and production tokens, keys, databases and buckets.
