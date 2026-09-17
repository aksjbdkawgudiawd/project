import csv
import hashlib
import io
import json
from collections import Counter
from contextlib import nullcontext
from datetime import timedelta

from cryptography.fernet import InvalidToken
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select

from backend.models import Audit, ImportBatch, Inventory, Ledger, Order, OrderItem, SKU, Setting, Topup, User, now, uid
from backend.schemas import InventoryInput


def fail(status, message):
    raise HTTPException(status_code=status, detail=message)


def get(session, model, identifier, lock=False):
    query = select(model).where(model.id == identifier)
    if lock:
        query = query.with_for_update()
    record = session.scalar(query)
    if record is None:
        fail(404, f"{model.__name__} not found")
    return record


def audit(session, actor, action, entity_type, entity_id, detail=""):
    session.add(Audit(actor=actor, action=action, entity_type=entity_type, entity_id=entity_id, detail=detail))


def move_balance(session, user, amount, kind, reference, actor):
    if user.balance_cents + amount < 0:
        fail(409, "Insufficient wallet balance")
    if user.balance_cents + amount > 2_000_000_000:
        fail(409, "Wallet limit exceeded")
    user.balance_cents += amount
    session.add(Ledger(user_id=user.id, amount_cents=amount, balance_after_cents=user.balance_cents, kind=kind, reference=reference))
    audit(session, actor, f"wallet.{kind}", "user", user.id, f"{amount:+d} USD cents; reference {reference}")


def checkout(db, data, actor, transaction=None):
    quantities = Counter()
    for item in data.items:
        quantities[item.sku_id] += item.quantity
    if sum(quantities.values()) > 100:
        fail(422, "A checkout may contain at most 100 units")
    request_identity = {"user": data.user_id, "items": sorted(quantities.items()), "wholesale": data.wholesale}
    if data.expected_total_cents is not None:
        request_identity["expected_total_cents"] = data.expected_total_cents
    fingerprint = hashlib.sha256(json.dumps(request_identity, sort_keys=True).encode()).hexdigest()
    with (db.write() if transaction is None else nullcontext(transaction)) as session:
        user = get(session, User, data.user_id, lock=True)
        existing = session.scalar(select(Order).where(Order.idempotency_key == data.idempotency_key))
        if existing:
            if existing.request_hash != fingerprint:
                fail(409, "Idempotency key was already used for a different checkout")
            return existing.id, True
        setting = session.get(Setting, "store")
        if setting and json.loads(setting.value).get("maintenance_mode"):
            fail(409, "Store is in maintenance mode")
        if data.wholesale and not user.wholesale_access:
            fail(403, "Wholesale access is required")
        priced_lines = []
        total = 0
        for sku_id, quantity in sorted(quantities.items()):
            sku = get(session, SKU, sku_id, lock=True)
            if not sku.active:
                fail(409, f"{sku.name} is disabled")
            price = sku.wholesale_price_cents if data.wholesale else sku.retail_price_cents
            priced_lines.append((sku, quantity, price))
            total += price * quantity
        if total > 2_000_000_000:
            fail(422, "Checkout total exceeds supported limit")
        if data.expected_total_cents is not None and data.expected_total_cents != total:
            fail(409, "cart_changed")
        if user.balance_cents < total:
            fail(409, "Insufficient wallet balance")
        chosen = []
        for sku, quantity, price in priced_lines:
            stock = session.scalars(select(Inventory).where(Inventory.sku_id == sku.id, Inventory.status == "available").order_by(Inventory.created_at, Inventory.id).with_for_update(skip_locked=True)).all()
            valid = []
            for unit in stock:
                try:
                    if not db.decrypt(unit.payload_encrypted).strip():
                        raise ValueError("Empty payload")
                except (InvalidToken, ValueError):
                    unit.status = "invalid"
                    audit(session, actor, "inventory.preflight_failed", "inventory", unit.id, "Local encrypted payload validation failed")
                    continue
                valid.append(unit)
                if len(valid) == quantity:
                    break
            if len(valid) != quantity:
                fail(409, f"Insufficient available stock for {sku.name}")
            for unit in valid:
                unit.status = "reserved"
                audit(session, actor, "inventory.reserved", "inventory", unit.id)
                chosen.append((sku, unit, price))
        order = Order(id=uid(), user_id=user.id, total_cents=total, idempotency_key=data.idempotency_key, request_hash=fingerprint)
        session.add(order)
        session.flush()
        move_balance(session, user, -total, "purchase", f"order:{order.id}", actor)
        for sku, unit, price in chosen:
            unit.status = "sold"
            unit.order_id = order.id
            session.add(OrderItem(order_id=order.id, sku_id=sku.id, inventory_id=unit.id, sku_name=sku.name, unit_price_cents=price))
            audit(session, actor, "inventory.sold", "inventory", unit.id, f"Order {order.id}")
        audit(session, actor, "order.completed", "order", order.id, f"{len(chosen)} units; {total} USD cents")
        return order.id, False


def review_topup(db, identifier, data, actor):
    target = "approved" if data.decision == "approve" else "rejected"
    with db.write() as session:
        topup = get(session, Topup, identifier, lock=True)
        if topup.status == target:
            return topup.id, True
        if topup.status != "pending":
            fail(409, "This top-up has already been reviewed")
        user = get(session, User, topup.user_id, lock=True)
        if target == "approved":
            move_balance(session, user, topup.amount_cents, "topup", f"topup:{topup.id}", actor)
        topup.status = target
        topup.review_note = data.note
        topup.reviewed_at = now()
        audit(session, actor, f"topup.{target}", "topup", topup.id, data.note)
        return topup.id, False


def add_inventory(db, session, data, actor):
    get(session, SKU, data.sku_id)
    if session.scalar(select(Inventory.id).where(Inventory.reference == data.reference)):
        fail(409, "Inventory reference already exists")
    unit = Inventory(id=uid(), sku_id=data.sku_id, reference=data.reference, payload_encrypted=db.encrypt(data.payload))
    session.add(unit)
    session.flush()
    audit(session, actor, "inventory.created", "inventory", unit.id, f"SKU {data.sku_id}; status available")
    return unit


def preview_import(db, data, actor):
    try:
        if data.format == "json":
            rows = json.loads(data.content)
            if not isinstance(rows, list):
                fail(422, "JSON must be an array of inventory objects")
        else:
            rows = list(csv.DictReader(io.StringIO(data.content)))
    except (ValueError, csv.Error):
        fail(422, "Could not parse import file")
    if not rows or len(rows) > 500:
        fail(422, "Import must contain 1–500 rows")
    valid = []
    errors = []
    seen = set()
    with db.write() as session:
        for index, row in enumerate(rows, 1):
            try:
                if not isinstance(row, dict):
                    raise ValueError("Each row must be an object")
                if data.sku_id and not row.get("sku_id"):
                    row["sku_id"] = data.sku_id
                item = InventoryInput.model_validate(row)
                if not session.get(SKU, item.sku_id):
                    raise ValueError("Unknown SKU")
                if item.reference in seen or session.scalar(select(Inventory.id).where(Inventory.reference == item.reference)):
                    raise ValueError("Duplicate inventory reference")
                seen.add(item.reference)
                valid.append(item.model_dump())
            except ValidationError:
                errors.append({"row": index, "message": "Expected sku_id, unique reference and a non-empty payload; no extra columns"})
            except ValueError as exc:
                errors.append({"row": index, "message": str(exc)})
        batch_id = None
        if not errors:
            batch = ImportBatch(id=uid(), encrypted_rows=db.encrypt(json.dumps(valid)), count=len(valid))
            session.add(batch)
            batch_id = batch.id
            audit(session, actor, "inventory.import_preview", "import", batch.id, f"{len(valid)} validated rows")
        return {"batch_id": batch_id, "valid_count": len(valid), "total_count": len(rows), "errors": errors, "rows": [{"sku_id": row["sku_id"], "reference": row["reference"], "status": "ready"} for row in valid]}


def confirm_import(db, identifier, actor):
    with db.write() as session:
        batch = get(session, ImportBatch, identifier, lock=True)
        if batch.status == "confirmed":
            return {"batch_id": batch.id, "imported_count": batch.count, "replayed": True}
        created = batch.created_at.replace(tzinfo=now().tzinfo) if batch.created_at.tzinfo is None else batch.created_at
        if now() - created > timedelta(hours=1):
            fail(409, "Import preview expired; validate the file again")
        for row in json.loads(db.decrypt(batch.encrypted_rows)):
            add_inventory(db, session, InventoryInput.model_validate(row), actor)
        batch.status = "confirmed"
        batch.encrypted_rows = db.encrypt("[]")
        audit(session, actor, "inventory.import_confirmed", "import", batch.id, f"{batch.count} units imported")
        return {"batch_id": batch.id, "imported_count": batch.count, "replayed": False}
