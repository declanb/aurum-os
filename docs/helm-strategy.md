# Helm strategy: symmetric brackets, conviction cap, paper week

Helm no longer sells on any green. Every new scout long gets a symmetric bracket, net of the 0.09% sell fee:

| Setting | Default | Meaning |
|---|---|---|
| `HELM_TP_PCT` | `3` | Take profit: +3% net of the sell fee |
| `HELM_SL_PCT` | `3` | Stop loss: −3% net of the sell fee |
| `HELM_SYMMETRIC_BRACKETS` | `true` | Scout longs are staged with those levels |
| `HELM_MAX_IDEAS_PER_DAY` | `2` | New scout ideas staged per UTC day, best score first |
| `HELM_STALE_IDEA_HOURS` | `48` | Age at which an unapproved idea counts as stale |
| `HELM_PAPER_POSITION_EUR` | `50` | Paper week size per position |
| `HELM_COPY_PUBLIC_QUOTES` | `false` | Paper ticks mark from Revolut X public tickers (no API key) |

Levels: `target = entry × (1 + tp) / (1 − fee)` and `stop = entry × (1 − sl) / (1 − fee)`. A €50 position therefore makes +€1.50 or −€1.50 after fees.

Human-in-the-loop does not change. A buy still needs **Approve** and then **Execute**. A bracket trigger still becomes an `EXIT` idea that needs approval.

## Where it applies

* **Staging** (`auto_approver.stage_recommendation`): scout longs get symmetric levels. Guardian checks them with an R:R floor of 1.0, because 1:1 is the design. Manual ideas keep the 1.5 floor.
* **Ranking**: scout and the cron sort recommendations by the scout score (confidence × R:R) before staging. After two in a UTC day, the rest are refused with "daily cap".
* **Exit brackets** (`exit_bracket.default_levels`): when a scout idea fills, the bracket is rebased on the actual fill price.
* **Paper copy book**: `strategy=symmetric` is the default. See `docs/helm-copy-book.md`.

## Stale ideas

Preview only (the default):

```bash
python -m api.services.helm_strategy expire-stale --hours 48
curl -X POST $HOST/api/strategy/expire-stale -d '{"hours":48}' -H 'content-type: application/json'
```

Add `--apply` (CLI) or `"dry_run": false` (HTTP) to set them to `Cancelled`. `EXIT` ideas are never touched. This has **not** been run against production.

`GET /api/strategy/rules` and `python -m api.services.helm_strategy rules` print the live settings. `levels --entry 100` prints one bracket.

## Paper week

€200 virtual bank, €50 per position, the top 2 ideas per day, marks from Revolut X public prices.

```bash
python -m api.services.copy_book start                 # symmetric, €200, €50, 2/day
python -m api.services.copy_book tick --public-quotes --quiet   # run from a scheduler
python -m api.services.copy_book status --summary
```

`GET /api/copy/status` returns `summary` with realised and open P&L, equity, win rate, average win and loss, fees, and exit reasons.

Without production database access, use a local SQLite book:

```bash
export DATABASE_URL=sqlite:////workspace/helm-paper.db
python -m api.services.copy_book init-db
python -m api.services.copy_book start --sources trade_ideas,gainers
python -m api.services.copy_book tick --public-quotes --quiet
python -m api.services.copy_book status --summary
```

Against Supabase, run `alembic upgrade head` first (migration `a9e3c5d7f214` adds the strategy columns).
