"""Synthetic demonstration data; never loaded outside explicit demo mode."""
import json
from datetime import timedelta

from sqlalchemy import select

from backend.models import Inventory, SKU, Setting, Topup, User, now, uid
from backend.schemas import CheckoutInput, SettingsInput
from backend.services import audit, checkout, move_balance


def seed_demo(db):
    with db.write() as session:
        if session.scalar(select(User.id).limit(1)):
            return
        session.add(Setting(key="store", value=json.dumps(SettingsInput().model_dump())))
        users = [
            User(id="demo-alex", name="Alex Morgan", username="alex_m", wholesale_access=True),
            User(id="demo-sofia", name="Sofia Kovalenko", username="sofia_k"),
            User(id="demo-daniel", name="Daniel Weber", username="daniel_w", wholesale_access=True),
            User(id="demo-olena", name="Olena Marchenko", username="olena_m"),
            User(id="demo-james", name="James Wilson", username="james_w"),
            User(id="demo-emma", name="Emma Laurent", username="emma_l"),
        ]
        session.add_all(users)
        session.flush()
        for index, user in enumerate(users):
            move_balance(session, user, 25000 + index * 5000, "demo_seed", f"demo-opening:{user.id}", "demo-seed")
        specs = [
            ("us-license", "Creative Suite · US", "United States", "US", "🇺🇸", "Software license", 1290, 990, 32),
            ("uk-license", "Studio Pro · UK", "United Kingdom", "GB", "🇬🇧", "Software license", 1490, 1190, 18),
            ("de-assets", "Design Assets · Germany", "Germany", "DE", "🇩🇪", "Digital assets", 850, 650, 24),
            ("ua-course", "Learning Pass · Ukraine", "Ukraine", "UA", "🇺🇦", "Education", 590, 450, 4),
            ("fr-assets", "Creator Pack · France", "France", "FR", "🇫🇷", "Digital assets", 1090, 850, 12),
            ("ca-license", "Workspace Plus · Canada", "Canada", "CA", "🇨🇦", "Software license", 1690, 1390, 3),
            ("pl-course", "Language Pass · Poland", "Poland", "PL", "🇵🇱", "Education", 690, 490, 16),
            ("nl-assets", "Icon Library · Netherlands", "Netherlands", "NL", "🇳🇱", "Digital assets", 750, 550, 0),
        ]
        for identifier, name, country, code, flag, category, retail, wholesale, stock in specs:
            session.add(SKU(id=identifier, name=name, country=country, country_code=code, flag=flag, category=category, retail_price_cents=retail, wholesale_price_cents=wholesale, description="Synthetic demonstration product. Not a real license or account."))
            session.flush()
            for index in range(stock):
                unit = Inventory(id=uid(), sku_id=identifier, reference=f"DEMO-{code}-{index + 1:04}", payload_encrypted=db.encrypt(f"SYNTHETIC-ONLY:{identifier}:{index + 1}"), created_at=now() - timedelta(days=14))
                session.add(unit)
                audit(session, "demo-seed", "inventory.created", "inventory", unit.id, "Synthetic local demo stock")
        for index, user in enumerate(users[:4]):
            session.add(Topup(id=f"demo-topup-{index + 1}", user_id=user.id, amount_cents=[5000, 10000, 2500, 7500][index], reference=f"DEMO-TRANSFER-{index + 1:04}", note="Synthetic review request — no real payment or receipt.", created_at=now() - timedelta(hours=index * 3 + 1)))
    for index in range(18):
        sku_id = ["us-license", "uk-license", "de-assets", "fr-assets", "pl-course"][index % 5]
        identifier, _ = checkout(db, CheckoutInput(user_id=users[index % len(users)].id, items=[{"sku_id": sku_id, "quantity": 1 + index % 2}], idempotency_key=f"demo-seed-order-{index:03}"), "demo-seed")
        # Historical timestamps make the synthetic chart useful without fabricated aggregates.
        from backend.models import Order
        with db.write() as session:
            session.get(Order, identifier).created_at = now() - timedelta(days=17 - index, hours=index % 12)
