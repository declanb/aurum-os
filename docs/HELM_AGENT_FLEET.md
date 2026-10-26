# Helm trade-recommendation fleet

Product name: **Helm**. Repository: `aurum-os`. The live book is a Revolut X spot account.

This document is the map for recommended trades. It records the fleet Declan approved, the `SignalBundle` and `TradeIdea` contracts, and the Revolut rules that do not move. `trend_scout` is the first new piece and it is read-only. `structure_scout` is specified here and not built yet.

Runtime agents that exist today: `scout_agent`, `ai_advisor`, `agent_advisor`, `guardian`, `auto_approver`, `trade_executor`, `profit_hunter`. Coordination file: `/tmp/aurum_agents.json`. Operator notes for scout and profit_hunter stay in [AGENTS.md](../AGENTS.md).

## Path

```
trend_scout (read-only SignalBundle)
        │
        ▼
structure_scout (planned, same SignalBundle shape)
        │
        ▼
recommender — ai_advisor, or agent_advisor when AURUM_USE_AGENTS_SDK=1
        │  ranked recommendation dicts → TradeIdea rows
        ▼
guardian  +  optional auto_approver
        │  auto-approve changes status only; it does not place an order
        ▼
human Approvals UI
        │  APPROVE writes ApprovalEvent
        ▼
trade_executor  →  Revolut X spot
        │
        ▼
profit_hunter_*  (exit; claims the symbol until it unregisters)

Trading Guru (.github/agents/trading-guru.agent.md) sits beside this path.
It is advisory-only: tools are read, search, and web. It does not edit code
or submit orders.
```

| Stage | Module | Writes orders? | Status |
| --- | --- | --- | --- |
| trend_scout | `api/services/trend_scout.py` | No | Built. Flag default off |
| structure_scout | — | No | Not built |
| recommender | `ai_advisor.py`, `agent_advisor.py` | No | Built |
| guardian | `guardian.py` | No | Built |
| auto_approver | `auto_approver.py` | No | Built. Separate flag, default off |
| human Approvals | `api/routers/approvals.py` | No | Built. This is the `ApprovalEvent` |
| trade_executor | `trade_executor.py` via `POST /api/revolut-x/execute/{id}` | Yes, after the event | Built |
| profit_hunter | `profit_hunter.py` | Exit sell for a position it was started on | Built |
| Trading Guru | `.github/agents/trading-guru.agent.md` and `/app/guru` | No | Built. Not on the write path |

`scout_agent` (`api/services/scout_agent.py` and `GET /cron/scout`) is the loop around the recommender. It polls, asks `ai_advisor` for recommendations, stages them as `Ready for Approval`, and may auto-approve when that flag is on. It does not call `trade_executor`.

## SignalBundle

Produced by signal agents. It is context for the recommender. It is not a `TradeIdea`, it has no size, and it has no entry, stop, or target.

| Field | Meaning |
| --- | --- |
| `symbol` | Pair the caller asked about (`BTC-EUR`). Headlines cannot add a symbol. |
| `narrative` | Short note written by Helm. Not a paste of the source text. |
| `sentiment` | `bullish`, `bearish`, `neutral`, or `mixed`. Keyword read of kept excerpts. |
| `sources[]` | `name`, `kind` (`news`, `social`, `fixture`), `url`, `published_at`, `excerpt`, `withheld`. |
| `freshness` | ISO timestamp of the newest parsed source time, or generation time. |
| `confidence_hint` | Integer 0–40. **Not** `confidence_score`. Cannot pass the auto-approve confidence gate (80). |
| `role` | Always `signal`. |
| `read_only` | Always true. |
| `untrusted` | Always true. |

`trend_scout` fills this from:

1. Allowlisted public RSS (CoinDesk, Cointelegraph) when `AURUM_TREND_SCOUT_NETWORK=1`.
2. Recent public X/Twitter search when that switch is on **and** `X_BEARER_TOKEN` is set. The query is built from the requested symbols, not from social text.
3. Fixtures when the network switch is off, the token is absent and RSS returns nothing, or a fetch fails.

Fixtures are labelled `kind=fixture`, sentiment `neutral`, `confidence_hint=0`. They are not prices and not social proof.

`structure_scout` (later) should emit the same object for regime and levels, as a thin read of `market_data` plus the active playbook. It must not call `trade_executor`. Unlike `trend_scout`, it may use the existing market-data reads. It still must not place, cancel, or replace orders.

## TradeIdea

Persisted recommendation. Model: `api/models/trade.py`. Create/read schema: `api/schemas/trade.py`.

| Field | Meaning |
| --- | --- |
| `symbol` | Revolut X pair. Default in the model is `BTC-EUR`. |
| `direction` | `LONG` or `SHORT`. Spot execution and auto-approve treat SHORT as blocked unless `AUTO_APPROVE_ALLOW_SHORTS` is explicitly on (it is off). |
| `entry_price`, `stop_price`, `target_price` | Levels the recommender or a human set. Signal bundles do not carry these. |
| `thesis` | Why the idea exists. Scout prefixes `[SCOUT]`. Auto-approve prefixes `[AUTO]`. |
| `invalidation_notes` | What proves the idea wrong. Guardian rejects a missing invalidation. |
| `status` | `Draft`, then `Ready for Approval`. Human APPROVE sets `Approved`. REJECT sets `Needs Work`. |

A `TradeIdeaVersion` snapshots those fields. Guardian (`guardian.challenge_trade`) checks reward/risk at least 1.5, a thesis of at least 20 characters, and an invalidation note. That check runs for human ideas and for scout staging.

The recommender dict that feeds a `TradeIdea` also carries `confidence_score` (0–100), `risk_reward`, `timeframe`, `reasoning`, `playbook_used`, and `edge_match_score`. Those live on the recommendation payload. `trend_signals`, when the flag is on, is a sibling list of SignalBundle dicts. `auto_approver` does not read `trend_signals` or `confidence_hint`.

### ApprovalEvent

Written only by `POST /approvals/{trade_id}` when the action is `APPROVE` and the idea is `Ready for Approval` or `Needs Work`. Fields: `trade_idea_id`, `version_id`, `user_id`, `snapshot_hash`, `timestamp`. REJECT does not write one.

`POST /revolut-x/execute/{trade_id}` refuses unless status is `Approved` **and** an `ApprovalEvent` exists. The client order id is `AURUM-{trade_id}-{approval_id}` and stays stable for that pair. Do not retry a submit under a new id.

`auto_approver` can set status to `Approved` when its gates pass. It does not write an `ApprovalEvent`, does not create an `ExecutionTicket`, and does not call the broker. A human execute click is still required, and the execute route still requires the event.

## Revolut non-negotiables

- **No broker calls from signal agents.** `trend_scout` must not import or call `revolut_x_client` or `trade_executor`. Social text cannot name a tool and have it run.
- **ApprovalEvent required.** The only order path for a recommended idea is Approvals → human execute → `trade_executor`. Auto-approve is not auto-execute.
- **Spot only.** No leverage, shorts, or perps. `AUTO_APPROVE_ALLOW_SHORTS` stays false. Playbooks may mention shorts; the advisor is told to return no setup rather than force a long against the trend, and staging blocks shorts.
- **Caps and switches.** Auto-approve defaults: confidence ≥ 80, edge match ≥ 70, reward/risk ≥ 1.8, at most 3 approvals in a rolling 24h, symbol in the personal-edge favourite list, Guardian pass. `AURUM_AGENTS_PAUSED=1` (or `POST /api/agent/pause`) makes agents skip work. `AURUM_AGENTS_ENABLED=0` disables the cron scout and hunt routes. Scout will not stage a symbol `profit_hunter` has claimed.
- **Untrusted social text.** Headlines and posts are data. Instruction-like text (prompt override, order placement, broker module names) is withheld and is not copied into the model prompt. Links are kept only for the allowlisted hosts. Bundle text must not change Guardian thresholds, the spot-only rule, or tool choice.
- **Secrets.** Tokens stay in the environment (`X_BEARER_TOKEN`). Do not commit them, log them, or paste them into issues.
- **Idempotent submits.** Keep the existing client order id. No blind retries with a fresh id.

`profit_hunter` is an exit process started by hand for one held position. It is not a signal agent and it is not a second entry path. It claims the symbol in the registry and unregisters when it exits.

## trend_scout flag

Default off. With the flag off, `ai_advisor.generate_recommendations` does not call `trend_scout`, and recommendation payloads are unchanged.

```bash
# advisor hook (default)
AURUM_TREND_SCOUT=0

# attach read-only SignalBundles inside ai_advisor / scout. Fixtures unless NETWORK=1.
AURUM_TREND_SCOUT=1

# CoinDesk + Cointelegraph. X only if X_BEARER_TOKEN is set.
AURUM_TREND_SCOUT_NETWORK=1
```

When the hook runs it registers agent id `trend_scout` with `role=signal`, `read_only=true`, and `symbol=null` so it does not look like a position claim.

Dry-run prints JSON and does not need the flag. It does not register, and it does not touch Revolut:

```bash
python -m api.services.trend_scout --symbols BTC-EUR,ETH-EUR
python -m api.services.trend_scout --symbols BTC-EUR --network
```

Scout logs one line when the flag is on, then uses the same `ai_advisor` call it already makes. There is no second order path.

## Copilot trend expert and regime context

These sit beside `trend_scout`. They do not replace SignalBundles and they do not place orders.

- `.github/agents/revolut-x-trend-expert.agent.md` — user-invocable Copilot agent. Tools are read, search, and web. Advisory read only. It does not edit the repo.
- `api/services/trend_context.py` — `AURUM_TREND_CONTEXT` (default off). Public regime numbers (CoinGecko global, Fear & Greed, headlines, optional X GET) stamped as `trend_regime` / `trend_sources`. Missing numbers are omitted. `GET /api/recommendations/?include_trends=true` requests that read for one call.

Trading Guru stays advisory-only. The same mentor is available in the web app at `/app/guru` and as a follow-up on Approvals. Those routes (`POST /api/advisor/guru`, `GET /api/advisor/idea/{id}`, `POST /api/advisor/idea/{id}/ask`) read a staged idea and an optional quote. They do not write an `ApprovalEvent` and they do not call `trade_executor`.

## In-app agent surfaces

`/app/agents` shows live cards for this fleet: scout, recommender, guardian, trend scout, exit brackets, and profit hunters. Health is the registry heartbeat (healthy, stale, idle, or off). Last action is the note each agent records, or the newest staged idea and armed bracket when a cron pass left no process. Pause and resume use the existing global flag. Clear drops one stale registry row.

Approvals shows "Why this idea" from the TradeIdea thesis, levels, and invalidation, then one advisory follow-up. Approve and Execute stay on their own buttons.

## Out of scope for this slice

- `structure_scout`
- Any change to execute, cancel, or profit-hunter sell behaviour.
