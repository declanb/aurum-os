# Helm paper copy book

Revolut X has no native copy-trading API. This book does not follow another Revolut account. It paper-mirrors two signal layers Helm already has, on a virtual EUR balance, so an overnight run can show would-be P&L.

It never places, cancels, or modifies a live order. It does not write an `ApprovalEvent`, does not create an `ExecutionTicket`, and does not change Guardian or the Approvals execute click. Live trades stay on `TradeIdea` → Approvals → human execute.

`PAPER_TRADING` is a different switch. That flag makes the existing order service simulate a fill. The copy book does not call that service.

## What it copies

* **Scout ideas.** `TradeIdea` rows with direction `LONG`, status `Ready for Approval` or `Approved`, and an EUR spot symbol (`UNI-EUR`). The thesis is stored as the signal reason. Stop and target are kept when they sit on the correct side of the fill.
* **24h EUR gainers.** The ticker read (`api/services/market_data.py`). A pair ranks only when that ticker row has a percent-change field, or an open and a last on the same row. A missing change is skipped. It is not treated as zero. USD pairs and shorts are ignored.

Ticker payloads may say `UNI/EUR`. The book stores `UNI-EUR`, the same form as the rest of Helm.

## Sizing and exits

Default bankroll is **€200** (`HELM_COPY_BANKROLL_EUR`, alias `AURUM_COPY_BANKROLL_EUR`).

Each new name spends `position_pct` of virtual equity (default 10%), capped by `HELM_COPY_MAX_NOTIONAL_EUR` (default €40) and by 25% of the starting bankroll, and never more cash than the book has. A fill below €1 is skipped. One open name at a time, and a symbol already copied in the session is not re-opened.

The paper buy prints at mid, or at the bid/ask average, or at last. The mark for P&L and exits is the bid. P&L uses the same sell-side 0.09% taker fee as My Trade, so a flat price is slightly red.

Exits, in order:

1. Stop, target, and the trailing ratchet when both stop and target were stored. Same bid checks as `evaluate_long_bracket`. Paper only: no EXIT idea and no live bracket row.
2. Any-green, when the session has it on (the default): close once sell-side P&L is above zero.
3. A manual paper close, or flattening when the session stops.

A fill is not eligible to exit on the same tick that opened it. The next poll marks it.

## Start a session

Environment (optional; defaults are enough):

```bash
HELM_COPY_BANKROLL_EUR=200
# AURUM_COPY_BANKROLL_EUR=200
HELM_COPY_POSITION_PCT=0.10
HELM_COPY_MAX_NOTIONAL_EUR=40
```

HTTP (same app, behind the existing Vercel Authentication — do not add a public bypass):

```bash
curl -s -X POST http://localhost:8000/api/copy/session \
  -H 'content-type: application/json' \
  -d '{"bankroll_eur":200,"sources":["trade_ideas","gainers"],"any_green":true}'

curl -s -X POST http://localhost:8000/api/copy/tick
curl -s http://localhost:8000/api/copy/status
curl -s http://localhost:8000/api/copy/positions?status=open
curl -s -X POST http://localhost:8000/api/copy/stop
```

An empty `POST /api/copy/session` uses the env bankroll. `POST /api/copy/tick` reads tickers when the body has no `quotes`. Passing `quotes` only supplies paper marks. It does not submit an order.

Only one session runs at a time. A second start returns 409 with the running id. `dry_run: false` is rejected.

CLI, against the configured database:

```bash
python -m api.services.copy_book start --bankroll 200
python -m api.services.copy_book tick
python -m api.services.copy_book status
python -m api.services.copy_book stop
```

In-memory smoke (no network, no database file, no broker):

```bash
python -m api.services.copy_book smoke
python scripts/copy_book_smoke.py
```

Apply the Alembic revision `c3b71e0a5f42` before the first real session so `copysession` and `copyposition` exist.

The Helm page is `/app/copy`. Recommendations links to it. Tick from the page or from the watcher. The page polls status. It does not tick on its own.
