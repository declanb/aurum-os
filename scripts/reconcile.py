#!/usr/bin/env python3
"""Reconcile Revolut X broker balances against DB ExecutionTicket fills.

Usage:
    python -m scripts.reconcile
    python scripts/reconcile.py

Prints a drift table — any non-zero drift means the DB is wrong about what
we actually hold on the exchange. Read this first, build UI second.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Allow running as `python scripts/reconcile.py` from repo root
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import desc  # noqa: E402
from sqlmodel import Session, select  # noqa: E402

from api.core.db import engine  # noqa: E402
from api.models.trade import ExecutionTicket  # noqa: E402
from api.services import revolut_x_client as rx  # noqa: E402


def _f(v) -> float:
    try:
        return float(v) if v is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


async def main() -> int:
    # 1. Live broker balances
    try:
        balances = await rx.get_balances(include_zero=False)
    except Exception as e:  # noqa: BLE001
        print(f"❌ Could not fetch broker balances: {e}")
        return 2

    broker: dict[str, float] = {}
    for b in balances or []:
        ccy = (b.get("currency") or "").upper()
        qty = _f(b.get("total") or b.get("balance"))
        if ccy and ccy != "EUR" and qty > 0:
            broker[ccy] = qty

    # 2. DB: latest BUY ticket per symbol with positive fill
    db_qty: dict[str, float] = {}
    db_meta: dict[str, dict] = {}
    with Session(engine) as session:
        tickets = session.exec(
            select(ExecutionTicket)
            .where(ExecutionTicket.side == "buy")
            .where(ExecutionTicket.fill_qty != None)  # noqa: E711
            .order_by(desc(ExecutionTicket.filled_at), desc(ExecutionTicket.id))
        ).all()
        for t in tickets:
            if not t.symbol:
                continue
            asset = t.symbol.split("-")[0].upper()
            if asset in db_qty:
                # Already have a newer ticket for this asset (sorted desc)
                continue
            db_qty[asset] = _f(t.fill_qty)
            db_meta[asset] = {
                "symbol": t.symbol,
                "broker_order_id": t.broker_order_id,
                "fill_price": t.fill_price,
                "fees_eur": t.fees_eur,
                "filled_at": t.filled_at.isoformat() if t.filled_at else None,
            }

    # 3. Diff
    all_assets = sorted(set(broker) | set(db_qty))
    if not all_assets:
        print("No non-EUR balances on broker and no buy tickets in DB. Nothing to reconcile.")
        return 0

    print(f"{'ASSET':<8} {'BROKER':>16} {'DB':>16} {'DRIFT':>16}  STATUS  ORDER_ID")
    print("─" * 90)
    drift_count = 0
    for asset in all_assets:
        b = broker.get(asset, 0.0)
        d = db_qty.get(asset, 0.0)
        drift = b - d
        if asset not in db_qty:
            status = "❌ MISSING IN DB"
            drift_count += 1
        elif asset not in broker:
            status = "⚠️  SOLD ON BROKER (stale DB)"
            drift_count += 1
        elif abs(drift) > max(b, d) * 0.001:  # >0.1% drift
            status = "⚠️  DRIFT"
            drift_count += 1
        else:
            status = "✅ OK"
        oid = (db_meta.get(asset) or {}).get("broker_order_id") or "-"
        print(f"{asset:<8} {b:>16.8f} {d:>16.8f} {drift:>16.8f}  {status:<24} {oid}")

    print("─" * 90)
    print(f"{len(all_assets)} asset(s) checked · {drift_count} with drift")
    return 0 if drift_count == 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
