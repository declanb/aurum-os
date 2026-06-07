# Changelog

All notable changes to Aurum OS will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-06-05

### 🎉 Initial Production Release

First production-ready release of Aurum OS — AI-native crypto trading copilot with autonomous agent orchestration and human-in-the-loop execution on Revolut X.

### Added

#### Agent Fleet
- **scout_agent**: Autonomous AI advisor polling recommendations every 15min
- **profit_hunter**: Per-position exit monitoring with auto-sell on profit target
- Agent registry coordination (`/tmp/aurum_agents.json`) for symbol claim/release
- Auto-approval pipeline with personal edge scoring (min confidence 80%, edge match 70%)
- Daily auto-approve cap (max 3/day) with guardian structural checks

#### Trade Execution
- Full Revolut X integration: market orders, limit orders, fills reconciliation
- Execution flow: TradeIdea → Approval → ExecutionTicket → Fill
- Paper-mode toggle (simulated trades without broker execution)
- Order status polling and fill backfilling
- Manual execution panel with qty/limit price controls

#### API & Endpoints
- `/api/agent/*`: Agent status, pause/resume, registry access
- `/api/cron/scout`: Scheduled AI recommendations (every 30min on Vercel)
- `/api/cron/hunt`: Position exit monitoring (every 2min on Vercel)
- `/api/approvals/*`: Approve/reject trade ideas, execution ticket creation
- `/api/revolut-x/*`: Live broker data (balances, orders, tickers, order book)
- `/api/openai-balance`: Real-time OpenAI API spend tracking

#### Frontend (Next.js)
- **Agents page**: Live fleet monitoring (scout, profit hunters, heartbeats)
- **Approvals page**: Auto-approved ideas with `[AUTO]` prefix, one-click execute
- **My Trade page**: Position entry with profit target + live execution
- **Exchange page**: Revolut X market data, order book, price chart
- Paper-mode pill (shows when trades are simulated)
- OpenAI balance pill (cost monitoring)

#### Infrastructure
- Vercel deployment configuration with cron jobs
- Database migrations: ExecutionTicket fill fields, approval nullability
- Agent log files: `/tmp/scout_agent.log`, `/tmp/profit_hunter_*.log`
- Reconciliation scripts: `backfill_tickets.py`, `reconcile.py`
- Start scripts: `start_scout.sh` for one-command agent launch

#### Configuration
- Auto-approve gates: confidence, edge match, R:R, daily cap, shorts blocked
- Playbook selection: wyckoff, ict_smc, trend_follower, macro, livermore
- Favourite symbols list (only auto-approve known instruments)
- Global pause flag (`AURUM_AGENTS_PAUSED`) for emergency stop

#### Documentation
- `AGENTS.md`: Agent architecture, coordination rules, API reference
- `DEPLOY_CHECKLIST.md`: Vercel deployment guide with cost protection
- `AI_RECOMMENDATIONS_GUIDE.md`: Playbook strategy definitions

### Changed
- Trade execution now requires explicit ExecutionTicket creation before broker order
- scout_agent checks symbol claims before auto-approving (prevents collision with profit_hunter)
- AI advisor uses personal edge history to score recommendations
- Guardian validates all approvals (R:R ≥1.8, thesis length, invalidation notes)

### Security
- Cron endpoints protected with optional `CRON_SECRET`
- OpenAI hard spending limit: $5/month (set in OpenAI dashboard)
- Vercel spending cap: $10/month (set in Vercel settings)
- No long-lived cloud credentials — OIDC federation where possible

### Cost Protection
- Default model: gpt-4o-mini (10x cheaper than gpt-4o)
- Rate limiting: min 25min scout, 110s hunt
- Global kill switch: `AURUM_AGENTS_ENABLED=false`
- Expected monthly spend: $1-4 (OpenAI + Vercel overage)

### Deployment
- Vercel production: `aurum-os.vercel.app` (not yet deployed)
- Local development: `npm run dev` (monorepo script)
- API: `uvicorn api.index:app --port 8000`
- Frontend: `cd web && npm run dev` (port 3000)

---

## How to Use

1. **Start local services**:
   ```bash
   # Terminal 1: API
   source .venv/bin/activate && uvicorn api.index:app --port 8000

   # Terminal 2: Scout agent
   ./scripts/start_scout.sh wyckoff

   # Terminal 3: Profit hunter (per position)
   python -m api.services.profit_hunter --symbol BTC-EUR --qty 0.00003443 --cost-eur 2.00 --min-profit-eur 0.01
   ```

2. **Monitor agents**: `curl http://localhost:8000/api/agent/status`

3. **Review auto-approvals**: http://localhost:3000/app/approvals

4. **Execute trades**: Click "Execute" → manually confirm qty/price → Submit

5. **Exit positions**: profit_hunter auto-sells when target hit

---

[1.0.0]: https://github.com/yourusername/aurum-os/releases/tag/v1.0.0
