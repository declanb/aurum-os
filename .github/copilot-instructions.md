# Helm coding guardrails

Product brand is **Helm**. The git repository and Python/TS identifiers stay **aurum-os** / Aurum. Do not rename the repo.

## Stack

- Next.js App Router in `/web` (Clerk for auth, shadcn/ui, dark mode)
- FastAPI in `/api`
- Neon/Postgres, schema changes via Alembic
- Deployed on Vercel (`vercel.json` routes `/web` and `/api`)
- Revolut X spot via the `revx` CLI. Credentials stay in `~/.config/revolut-x/` (`revx configure`), never in git

## Human in the loop (real funds)

Helm can reach a **live Revolut X account**. Orders spend real money. Spot only: no leverage, no shorts, no perps, no off-venue products. Leave `AUTO_APPROVE_ALLOW_SHORTS=false`.

Scout, the Revolut X Trend Expert, the OpenAI Agents advisor, and any Copilot agent **recommend only**. They may produce recommendation dicts and stage `TradeIdea` rows (`Ready for Approval`, or `Approved` when auto-approve gates pass). They stop there.

A broker place, cancel, or modify runs only after both of these exist:

1. An `ApprovalEvent` for that `TradeIdea`
2. An explicit human execute action in the UI (`POST /api/revolut-x/execute/{trade_id}`)

That path is the only place an `ExecutionTicket` is created for an entry. Auto-approve does not send an order. `AURUM_TREND_CONTEXT` and `include_trends` end at the advisor prompt and the Approvals queue.

Caps stay in force. Do not raise them to make an agent look more useful:

- `AUTO_APPROVE_MAX_PER_DAY` (default 3, rolling 24h)
- `AUTO_APPROVE_MAX_RISK_EUR` (default €2, informational guard on auto-approve)
- Guardian still checks R:R, thesis length, and invalidation on every idea

Kill switches:

- Local fleet: `POST /api/agent/pause`, or `AURUM_AGENTS_PAUSED=1`. Resume with `POST /api/agent/resume`.
- Vercel cron (scout and profit-hunter ticks): `AURUM_AGENTS_ENABLED=false`.
- Cron scout also honors `is_paused()` / `AURUM_AGENTS_PAUSED` before it generates ideas.

`profit_hunter` sells a held spot position only under the safety model already in `api/services/profit_hunter.py`: net P&L versus the configured target, hard slippage cap, quantity limited to what is held, single position. Do not loosen auto-sell, widen size, or add a retry loop. If you touch that path, keep it at least as strict (human-gated is acceptable; a quieter or larger sell is not).

No silent retries of broker place, cancel, or modify. An ambiguous or failed order is surfaced to the human. Retrying can double-fill. Pass a stable `client_order_id` when the existing execute path already does; do not invent a second submit.

Never log credentials, API keys, bearer tokens, `Authorization` headers, or `revx` config. Never print `X_BEARER_TOKEN`, `OPENAI_API_KEY`, `CRON_SECRET`, or Clerk secrets. Do not commit `.env`.

Do not invent metrics, fills, balances, backtests, or sentiment. If a feed is missing, omit the field and say it was unavailable.

## Agents

- `.github/agents/trading-guru.agent.md` — Trading Guru. Advisory mentor only. Do not give it code-editing or order-placing tools, and do not turn its replies into orders.
- `.github/agents/revolut-x-trend-expert.agent.md` — Revolut X Trend Expert. Public-trend scout (X/Twitter read-only, headlines, BTC dominance / risk-on cues). Structured advisory output for the human and for `ai_advisor`. It does not write code or place orders.
- Runtime recommendations go through `api/services/ai_advisor.py` (and `agent_advisor.py` when `AURUM_USE_AGENTS_SDK=1`). Extend that path. Do not add a second stack that can reach `trade_executor` or `revolut_x_client.place_order`.

## Code

- Prefer extending scout / `ai_advisor` / the OpenAI Agents advisor over a parallel recommendation service.
- Public trend reads live in `api/services/trend_context.py`. GET requests only. X search runs only when `X_BEARER_TOKEN` is set, with redirects disabled so the bearer is not forwarded.
- Alembic for every schema change.
- Keep changes scoped to the task. Do not rename Helm/aurum-os identifiers in drive-by edits.
