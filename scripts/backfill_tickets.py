#!/usr/bin/env python3
"""Backfill ExecutionTicket rows from Revolut X order history.

For each held asset (broker balance > 0) that's missing from the DB,
fetch the most recent successful BUY order and insert a synthetic
ExecutionTicket so the UI / hunter / reconcile have something to read.

Usage:
    python scripts/backfill_tickets.py [--dry-run] [--symbols BTC-EUR,SOL-EUR]

Notes:
  * Uses filled_amount as cost_eur (most reliable on Revolut X — fees are
    baked into the spread on market orders, not exposed separately).
  * Synthetic tickets have approval_event_id=NULL to mark them as legacy.
    (Requires the FK to be nullable — if not, the script will tell you.)
  * Idempotent: skips assets already in DB.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import desc, text  # noqa: E402
from sqlmodel import Session, select  # noqa: E402

from api.core.db import engine  # noqa: E402
from api.models.trade import ExecutionTicket  # noqa: E402
from api.services import revolut_x_client as rx  # noqa: E402


def _f(v) -> float:
    try:
        return float(v) if v is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


def _normalise_symbol(s: str) -> str:
    """Revolut X returns 'BTC/EUR', we store 'BTC-EUR'."""
    return (s or "").replace("/", "-").upper()


async def _held_assets() -> dict[str, float]:
    balances = await rx.get_balances(include_zero=False)
    out: dict[str, float] = {}
    for b in balances or []:
        ccy = (b.get("currency") or "").upper()
        qty = _f(b.get("total") or b.get("balance"))
        if ccy and ccy != "EUR" and qty > 0:
            out[ccy] = qty
    return out


async def _latest_buy_fill(symbol: str) -> dict | None:
    """Return the most recent filled BUY order dict for symbol, or None."""
    try:
        history = await rx.list_order_history(symbol=symbol)
    except Exception as exc:  # noqa: BLE001
        print(f"  ⚠ could not fetch history for {symbol}: {exc}")
        return None
    if not isinstance(history, list):
        return None

    # Filter to filled buys, sort by created_date desc
    buys = [
        o for o in history
        if (o.get("side") or "").lower() == "buy"
        and (o.get("status") or "").lower() in {"filled", "partially_filled"}
        and _f(o.get("filled_quantity")) > 0
    ]
    if not buys:
        return None
    buys.sort(key=lambda o: int(o.get("created_date") or 0), reverse=True)
    return buys[0]


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Show what would be inserted, don't write")
    parser.add_argument("--symbols", default="", help="Comma-separated asset list (BTC,SOL,...) to limit scope")
    args = parser.parse_args()

    limit_assets: set[str] = set()
    if args.symbols:
        for s in args.symbols.split(","):
            s = s.strip().upper()
            if "-" in s:
                s = s.split("-")[0]
            if s:
                limit_assets.add(s)

    held = await _held_assets()
    if limit_assets:
        held = {k: v for k, v in held.items() if k in limit_assets}
    if not held:
        print("No held assets to backfill.")
        return 0

    print(f"Held on broker: {', '.join(f'{k}={v:g}' for k, v in held.items())}")
    print()

    # Existing assets in DB (so we skip them)
    db_assets: set[str] = set()
    with Session(engine) as session:
        existing = session.exec(
            select(ExecutionTicket)
            .where(ExecutionTicket.side == "buy")
            .where(ExecutionTicket.fill_qty != None)  # noqa: E711
        ).all()
        for t in existing:
            if t.symbol:
                db_assets.add(t.symbol.split("-")[0].upper())

    # Check whether approval_event_id is nullable (use a fresh session)
    approval_fk_nullable = True  # optimistic — model says it is
    try:
        with Session(engine) as check_session:
            row = check_session.exec(text(
                "SELECT is_nullable FROM information_schema.columns "
                "WHERE table_name='executionticket' AND column_name='approval_event_id'"
            )).first()
            if row is not None:
                # SQLAlchemy returns a Row; index 0 is the value
                val = row[0] if not isinstance(row, str) else row
                approval_fk_nullable = (str(val) or "").lower() == "yes"
    except Exception as exc:
        print(f"  (could not verify FK nullability, assuming nullable: {exc})")

    if not approval_fk_nullable:
        print("⚠ approval_event_id is NOT NULL — backfilled tickets need a placeholder approval row.")
        print("  Run: python3 -m alembic upgrade head")
        print("  Then re-run this script.")
        return 2

    inserted = 0
    skipped = 0
    not_found = 0

    for asset, broker_qty in sorted(held.items()):
        if asset in db_assets:
            print(f"  ✅ {asset}: already in DB, skipping")
            skipped += 1
            continue
        symbol = f"{asset}-EUR"
        print(f"  🔎 {asset}: searching {symbol} history...")
        order = await _latest_buy_fill(symbol)
        if not order:
            print(f"     ❌ no filled BUY found in history")
            not_found += 1
            continue

        oid = order.get("id") or order.get("venue_order_id")
        fill_qty = _f(order.get("filled_quantity"))
        avg_price = _f(order.get("average_fill_price"))
        cost_eur = _f(order.get("filled_amount") or order.get("amount"))
        ts = int(order.get("updated_date") or order.get("created_date") or 0) / 1000.0
        filled_at = datetime.fromtimestamp(ts, tz=timezone.utc) if ts else datetime.now(timezone.utc)
        # Fees aren't exposed on Revolut X market buys (baked into spread).
        # Estimate: filled_amount - (qty * avg_fill_price). Usually ~0 or tiny.
        notional = fill_qty * avg_price
        est_fees = max(0.0, cost_eur - notional)

        print(f"     ↪ order_id={oid}")
        print(f"     ↪ qty={fill_qty} @ €{avg_price:,.4f} = €{notional:,.4f}")
        print(f"     ↪ cost (filled_amount)=€{cost_eur:,.4f}  est_fees=€{est_fees:,.4f}")
        print(f"     ↪ filled_at={filled_at.isoformat()}")

        # Drift check: did we sell some since? broker_qty may be < fill_qty
        if broker_qty < fill_qty * 0.99:
            print(f"     ⚠ broker holds {broker_qty:g} but history shows {fill_qty:g} filled — partial exit likely")

        if args.dry_run:
            print(f"     (dry-run) would insert ExecutionTicket")
            continue

        with Session(engine) as session:
            ticket = ExecutionTicket(
                approval_event_id=None,  # nullable — legacy backfill
                adapter_status="Filled",
                provider_response=f"BACKFILL from revx order history (order {oid})",
                broker_order_id=oid,
                symbol=symbol,
                side="buy",
                fill_qty=fill_qty,
                fill_price=avg_price,
                fees_eur=est_fees,
                filled_at=filled_at,
            )
            session.add(ticket)
            session.commit()
            session.refresh(ticket)
            print(f"     ✅ inserted ticket id={ticket.id}")
            inserted += 1

    print()
    print(f"Done. inserted={inserted} skipped={skipped} not_found={not_found}")
    if args.dry_run and inserted == 0:
        print("Re-run without --dry-run to write rows.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
