# Arshisney marketplace

A working first release of a Telegram digital-goods marketplace: React admin workspace, FastAPI service layer, encrypted local inventory, ledger-backed checkout, and a Russian/Ukrainian aiogram bot.

**This is an MVP, not the completed production SRS.** Live payments, external inventory providers, and production infrastructure are not connected. The preview uses explicitly synthetic products, customers, payments, and payloads. Never put real credentials, receipts, accounts, or customer data into a public demo workspace.

## Run the demo

Requirements: Python 3.12+, Node 22+, npm, Linux/macOS shell.

```sh
bash scripts/setup.sh
bash scripts/dev.sh
```

Open `http://localhost:5175`. The managed preview uses the same repository-owned scripts. The API listens on loopback port 8000; Vite proxies `/api` while preserving origin information. Demo login is automatic **only** when the API explicitly reports `APP_ENV=demo`. Do not expose that mode to real data.

The demo database and generated encryption key persist under `.hoplite/` and are git-ignored. Restarting does not reset your changes. Protect the database and key together; losing the key loses access to encrypted delivery data.

## What works

- Dashboard with database-derived revenue, stock, wallet liability, and payment-review counts.
- Product creation/editing, retail and wholesale pricing, product visibility.
- Individual inventory entry, CSV/JSON validation and atomic import confirmation, quarantine/restore/invalidate, filtering and pagination.
- Exact stock allocation, local payload pre-flight, integer-cent wallet ledger, atomic checkout, duplicate-order protection, concurrent last-unit protection.
- Operator-reviewed manual top-ups with exactly-once credit, customer wholesale grants, immutable database audit/ledger guards.
- Bot subscription checks, dynamic catalog, country/SKU search, quantity FSM, cart, balance, checkout, purchase history, ownership-checked local delivery, and ru/uk templates.
- A demo-only storefront test bench that exercises the real checkout service without real funds.

## Test and build

```sh
npm test
npm run build
env -u BOT_TOKEN .venv/bin/python -m bot
```

Tests use isolated SQLite databases and simulated Telegram transports. They do not call real payment providers or Telegram. PostgreSQL is supported by the database layer, but PostgreSQL concurrency must be verified in staging before launch.

## Telegram setup

Read [bot/README.md](bot/README.md). Inject `BOT_TOKEN`, a long random `BOT_INTERNAL_TOKEN` shared with the API, and `BOT_API_URL` into the process environment. Start the API, then run `.venv/bin/python -m bot` separately. Without a bot token, no polling starts. Production mode requires Redis for FSM storage. Do not run two polling instances with the same token.

## Repository

```text
frontend/src/     React admin, API client, styles, test bench
backend/          FastAPI routes, reusable services, models, demo seed
bot/              aiogram handlers, HTTP client, ru/uk templates, tests
tests/            Transaction, race, security and import tests
scripts/          Reproducible setup and managed development launcher
docs/             Original SRS, implementation boundaries, operations
```

## Before a real launch

Use [IMPLEMENTATION_STATUS.md](docs/IMPLEMENTATION_STATUS.md) as the acceptance-gap checklist, [RUNBOOK.md](docs/RUNBOOK.md) for operations, and [SECURITY.md](docs/SECURITY.md) for deployment boundaries. Complete the missing provider adapters and release infrastructure, configure your own Telegram channel and legal/payment details, then run full staging acceptance tests. Credentials alone do not complete these missing features.
