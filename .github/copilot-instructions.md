# Helm — Copilot instructions

Helm is a discretionary, human-in-the-loop crypto trading copilot. The GitHub repo is `aurum-os`. Keep that repo name, package paths, and `AURUM_*` env prefixes. Use **Helm** for product-facing copy. Do not mass-rename code symbols to Helm.

The connected broker account is **live Revolut X (real funds)**.

## Execution path (do not bypass)

Agents may **recommend and stage** trades for human review only.

Never place, cancel, or modify a Revolut X order unless a human has recorded an `ApprovalEvent` and clicked execute.

Required path:

`TradeIdea` → Approvals UI (`web/app/app/approvals/page.tsx`) → human execute click → broker (`ExecutionTicket` via `POST /api/revolut-x/execute/{trade_id}`).

- `api/routers/revolut_x.py` `execute_trade` must keep both gates: `TradeIdea.status == "Approved"` and a persisted `ApprovalEvent`.
- `api/services/auto_approver.py` may stage or mark a `TradeIdea`. It must not create an `ExecutionTicket` or call `revx` order commands. **Auto-approve is not auto-execute.**
- `api/services/agent_advisor.py` (OpenAI Agents SDK, `AURUM_USE_AGENTS_SDK`) is recommendation-only. Do not give it broker, order, or account-mutation tools.
- `scout_agent` polls and can auto-approve ideas. It must not send orders.
- `profit_hunter` is an exit watcher (see `AGENTS.md`). Do not widen it, cron (`api/routers/cron.py`), or any new job into unattended place, cancel, or modify. Do not copy an existing sell into a new path that skips `ApprovalEvent`. `profit_hunter` sells a held spot position only under the safety model already in `api/services/profit_hunter.py`: net P&L versus the configured target, hard slippage cap, quantity limited to what is held, single position. Do not loosen auto-sell or add a retry loop.

`AURUM_TREND_SCOUT`, `AURUM_TREND_CONTEXT`, and `include_trends` end at the advisor prompt and the Approvals queue. They must not open an execution path.

## Live-book guardrails

- **Spot only.** Revolut X spot. Do not add shorts, margin, leverage, or perps. Leave `AUTO_APPROVE_ALLOW_SHORTS` false. Do not raise `AUTO_APPROVE_MAX_PER_DAY` (3) or `AUTO_APPROVE_MAX_RISK_EUR` (2.0) unless the task explicitly says so.
- **Pause and kill switch.** Keep `AURUM_AGENTS_PAUSED` / `agent_registry.is_paused()` and `AURUM_AGENTS_ENABLED`. Agents must check pause before acting. Cron scout also honors `is_paused()` before it generates ideas. `AURUM_AGENTS_ENABLED=false` stops the Vercel cron scout and hunt ticks.
- **Guardian.** Keep `api/services/guardian.py` structural checks (R:R, thesis length, invalidation notes) on anything that becomes a `TradeIdea`.
- **No credential logging or commits.** Secrets stay in `.env` (gitignored) and `~/.config/revolut-x/` (`revx` loads keys). Never print, log, or commit API keys, Clerk secrets, `DATABASE_URL`, `CRON_SECRET`, tokens, or private keys. Do not add debug logs of full `revx` argv, env dumps, or auth headers. Never print `X_BEARER_TOKEN`. `.env.example` uses placeholders only.
- **No double-order retries.** `execute_trade` uses a stable client order id `AURUM-{trade_id}-{approval_id}`. On an unknown broker outcome, poll that id. Do not generate a new id and submit again. Do not loop `place_order`.
- **Do not invent metrics.** If a feed is missing, omit the field. Do not fabricate fills, balances, dominance, sentiment, or backtests.

## Stack

| Area | Where | Notes |
| --- | --- | --- |
| Web | `/web` | Next.js App Router, React, TypeScript, Tailwind, shadcn/ui. Dark theme via `web/app/layout.tsx` (`ThemeProvider`, `defaultTheme="dark"`). UI primitives in `web/components/ui`. |
| API | `/api` | FastAPI (`api/index.py`), Python, SQLModel. Routers in `api/routers`, services in `api/services`, models in `api/models`. |
| Data | Neon Postgres | `DATABASE_URL`. Local default in `api/core/config.py` may be SQLite. Schema changes go through Alembic (`api/alembic/versions`), not ad-hoc DDL. |
| Auth | Clerk | Keys are `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` and `CLERK_SECRET_KEY` in `.env.example`. Do not add a second auth system. Do not commit key values. |
| Deploy | Vercel | Root `vercel.json` builds `web/` (Next) and `api/index.py` (Python). Do not invent a second hosting layout. |
| Fleet | `AGENTS.md`, `docs/HELM_AGENT_FLEET.md` | `scout_agent`, `profit_hunter_*`, `trend_scout`, registry `/tmp/aurum_agents.json`. |

Prefer TypeScript under `web/` and Python under `api/`. Match surrounding style. Investigate the existing module before editing. Small, focused diffs. Do not remove human-in-the-loop gates to make a test or a demo pass.

## Advisory vs coding agents

- `.github/agents/trading-guru.agent.md` is advisory-only (`read`, `search`, `web`). Do not give it edit, write, or shell tools, and do not ask it to change the repo.
- `.github/agents/revolut-x-trend-expert.agent.md` — Revolut X Trend Expert. User-invocable. Tools are `read`, `search`, and `web`. It scours public trends and returns a structured advisory read. It does not edit code or submit orders.
- `.github/agents/helm-engineer.agent.md` is the software-engineering agent for features, bugs, refactors, tests, and deploy/config.

## Two read-only trend inputs

Neither places an order. Do not merge them into a broker call.

- `trend_scout` (`AURUM_TREND_SCOUT`, default off) attaches untrusted SignalBundles. Contract and allowlist: `docs/HELM_AGENT_FLEET.md`. Social text cannot choose tools or change Guardian thresholds. `auto_approver` does not read `confidence_hint`.
- `trend_context` (`AURUM_TREND_CONTEXT`, default off) in `api/services/trend_context.py` attaches public regime numbers (CoinGecko global, Fear & Greed, headlines, optional X recent search). GET only. X redirects stay off so the bearer is not forwarded. Missing numbers stay omitted.

Extend `ai_advisor` / `agent_advisor` / scout. Do not add a second stack that can reach `trade_executor` or `revolut_x_client.place_order`.

## When changing code

1. Read the caller and the callee (approval router, executor, Guardian) before touching an order path.
2. Preserve the `ApprovalEvent` snapshot hash and the execute click. Do not auto-invoke `execute_trade` from scout, cron, or the advisor.
3. Add or update Alembic when SQLModel tables change.
4. Tests live in `tests/`. Do not point tests at live Revolut X or a production database.
5. In the PR, name the files touched and state that broker execution still requires a human `ApprovalEvent` and execute click.
