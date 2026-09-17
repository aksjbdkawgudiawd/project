# MVP operations runbook

## Local startup

Run `bash scripts/setup.sh`, then `bash scripts/dev.sh`. The launcher sets demo mode only when `APP_ENV` is unset; it runs the API on loopback 8000 and Vite on 5175. Use the managed Preview launcher in Hoplite. `.env.example` is documentation, not an automatically loaded secret file.

Health: `GET /api/v1/health`. Admin collections: `/api/v1/admin/*`, protected by a session cookie. Bot API: `/api/bot/*`, protected by `BOT_INTERNAL_TOKEN`. See `backend/README.md` and `bot/API_CONTRACT.md` for exact contracts.

## Non-demo configuration

The API fails startup without an administrator username, a password of at least 16 characters, and an inventory encryption key. Generate a Fernet key securely with the installed cryptography package and place it in your secret manager. For PostgreSQL, use a `postgresql://` connection URL; SQLAlchemy selects psycopg 3.

Do not deploy Vite's development server as production ingress. Build the admin with `npm run build`, serve `dist/` on HTTPS, and reverse-proxy `/api` to the API using a trusted proxy that preserves the external host and protocol. Set exact `ADMIN_ALLOWED_ORIGINS` where required. Never use a wildcard origin or expose the bot's internal token to the browser.

**Non-demo startup is not a production certification.** Complete the release gaps in IMPLEMENTATION_STATUS.md first, including migrations and restore testing. Current startup uses SQLAlchemy schema creation; it is not a versioned migration framework.

## Routine operator actions

1. Create an active SKU and set retail/wholesale integer-cent prices through the form.
2. Enter authorized units or import CSV/JSON. The preview rejects malformed rows and confirmation revalidates duplicate references atomically.
3. Quarantine questionable available units with a reason; sold/reserved units cannot be restored through the stock form.
4. For manual transfers, independently verify settlement before approving. A customer claim or receipt alone is not settlement proof.
5. Inspect orders, balance journal and immutable audit history when investigating discrepancies. Do not directly edit ledger balances.

## Backups and incidents

- Back up the database **and encryption key**, separately access-controlled. Never rotate/delete the only key without a tested data re-encryption plan.
- Stop writes before copying a local SQLite database, or use SQLite's supported backup interface; do not copy only the main file while WAL writes continue.
- Before any real launch, configure encrypted PostgreSQL backups/PITR and perform a restore exercise. No scheduled backup system is bundled.
- Enable maintenance mode if prices/inventory are wrong. Existing carts and order records remain intact; investigate with the audit log.
- External payment failures cannot be monitored here because no live adapter is active. Never manually mark a provider connected to clear a warning.
- Do not use the demonstration workspace for production, even briefly.
