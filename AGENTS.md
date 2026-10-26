# Helm agent fleet

**Helm** is the product: a discretionary, human-in-the-loop crypto trading copilot. This repository is `aurum-os`. Process names, `/tmp/aurum_agents.json`, env prefixes (`AURUM_*`), and package paths still use Aurum identifiers.

Helm is connected to a **live Revolut X spot account (real funds)**. Agents may recommend and stage trades for human review only. Never place, cancel, or modify a Revolut X order unless a human has recorded an `ApprovalEvent` and clicked execute. Path: `TradeIdea` → Approvals UI → human execute → broker. Auto-approve is not auto-execute. Spot only — no shorts, leverage, or perps. Keep the daily cap, pause flag, and kill switch.

The fleet coordinates through a shared registry. Each process handles one concern and registers itself so the others can see what is running.

The Helm recommendation path (signal → idea → human execute → exit), the `SignalBundle` / `TradeIdea` contracts, and the Revolut rules are in [docs/HELM_AGENT_FLEET.md](docs/HELM_AGENT_FLEET.md).

`trend_scout` is read-only and **off by default** (`AURUM_TREND_SCOUT=0`). It does not call the broker. Set `AURUM_TREND_SCOUT=1` to let `ai_advisor` attach untrusted SignalBundles as context. `AURUM_TREND_SCOUT_NETWORK=1` turns on allowlisted public feeds; otherwise the bundles are fixtures. Orders still need an `ApprovalEvent` and a human execute click.

A separate read, also off by default, is `AURUM_TREND_CONTEXT` (`api/services/trend_context.py`): public regime numbers for the same advisor prompt. The Copilot agent **Revolut X Trend Expert** (section 3) is advisory-only. Neither places an order.

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│  scout_agent        — AI advisor + auto-approve              │
│                       • Polls recommendations every 15min     │
│                       • Auto-approves high-confidence setups │
│                       • Never conflicts with profit_hunter   │
│                                                               │
│                              ▼                                │
│                    [Approved TradeIdea]                      │
│                              ▼ (manual click)                │
│                    [ExecutionTicket → Revolut X]             │
│                              ▼                                │
│  profit_hunter_*    — Exit strategy (N per position)         │
│                       • Sells when profit target hit         │
│                       • Claims symbol in registry            │
│                       • Auto-unregisters on exit             │
└──────────────────────────────────────────────────────────────┘

Shared coordination:  /tmp/aurum_agents.json
```

The manual click is the entry path onto Revolut X. `profit_hunter` (detailed below) is an exit watcher; do not add new unattended place, cancel, or modify behavior, and do not drop the `ApprovalEvent` gate on execute.

## Current Agents

### 1. scout_agent

**Purpose:** Autonomous AI trade advisor  
**Process:** Long-running loop  
**Log:** `/tmp/scout_agent.log`

**What it does:**
- Every 15 minutes:
  1. Fetches AI recommendations via `ai_advisor` (using your selected playbook). Optional read-only context: `AURUM_TREND_SCOUT` (SignalBundles, see the fleet doc) and `AURUM_TREND_CONTEXT` (public regime numbers, see below). Neither places an order.
  2. Computes your personal edge from approved-trade history
  3. Scores each recommendation against thresholds
  4. Auto-approves winners (if not already claimed by profit_hunter)

**Auto-approve gates** (all must pass):
- `confidence_score >= 80`
- `edge_match_score >= 70` (how well it matches your past winners)
- `risk_reward >= 1.8`
- Symbol is in your "favourite_symbols" list
- Guardian structural checks pass (R:R, thesis length, invalidation notes)
- Daily cap not exceeded (max 3/day)
- SHORTs blocked (Revolut X is spot-only)

**Start:**
```bash
./scripts/start_scout.sh [wyckoff|ict_smc|trend_follower|macro|livermore]
```

**Stop:**
```bash
pkill -f scout_agent
```

**Monitor:**
```bash
tail -f /tmp/scout_agent.log
curl http://localhost:8000/api/agent/status
```

### 2. profit_hunter_<symbol>

**Purpose:** Exit signal for one open long (hard stop, target, trail, or a euro floor)  
**Process:** One per position. Live mode signals only; it does not place the sell.  
**Log:** `/tmp/profit_hunter_<symbol>.log`  
**Bracket rule:** `docs/helm-exit-brackets.md`

**What it does:**
- Polls bid price every N seconds
- Applies the Helm bracket when entry, stop, and target are passed
- Live: logs the trigger and exits. The sell waits for an EXIT idea approval.
- Paper (`PAPER_TRADING=1`): simulates the sell
- Unregisters on exit (symbol freed for scout)

**Start:**
```bash
python -m api.services.profit_hunter \
  --symbol BTC-EUR \
  --qty 0.00003443 \
  --cost-eur 2.00 \
  --entry-price 60000 \
  --stop-price 58000 \
  --target-price 65000 \
  --poll-secs 10
```

**Stop:**
```bash
pkill -f "profit_hunter.*BTC"
```

Its safety model is unchanged: net P&L versus the target, a hard slippage cap, quantity limited to the coins actually held, and a single position. Do not loosen the sell or add a retry. Pause still skips the next action (`AURUM_AGENTS_PAUSED=1` or `POST /api/agent/pause`).

### 3. Copilot — Revolut X Trend Expert (advisory)

Not a long-running process. This is a user-invocable GitHub Copilot custom agent.

**File:** `.github/agents/revolut-x-trend-expert.agent.md`  
**Coding guardrails (every Copilot that edits this repo):** `.github/copilot-instructions.md`  
**Mentor persona (also advisory, no code):** `.github/agents/trading-guru.agent.md`

**Invoke:** In Copilot Chat on github.com or in VS Code, open the agent picker and choose **Revolut X Trend Expert**. Ask for a regime read or a public-trend check. It searches public X/Twitter posts, headlines, and BTC dominance / risk-on cues, then returns regime, Revolut X spot symbols, thesis, invalidation, pitfall watch, and confidence.

It does not write code and does not place, cancel, or modify orders. Hand the read to a human or let scout stage a `TradeIdea`. Trading Guru stays the voice for discipline and "should I take this?" questions.

This is not `trend_scout`. SignalBundles stay on `AURUM_TREND_SCOUT` and are specified in `docs/HELM_AGENT_FLEET.md`. The expert and `trend_context` add a regime read beside that.

**Signal flow** (`AURUM_TREND_CONTEXT=1`, off by default):

1. `api/services/trend_context.py` reads public sources only: CoinGecko `/global`, alternative.me Fear & Greed, CoinDesk RSS, and X API v2 recent search when `X_BEARER_TOKEN` is set. GET only. No posting. Missing fields are omitted.
2. `ai_advisor.generate_recommendations` puts that block in the Chat Completions prompt and, when `AURUM_USE_AGENTS_SDK=1`, in the OpenAI Agents advisor instructions, next to any SignalBundle block.
3. Scout (`scout_agent` and `GET /api/cron/scout`) and `GET /api/recommendations/?include_trends=true` use the same function.
4. Output is a recommendation. Scout may stage a `TradeIdea` on the Approvals queue (thesis gains a `Regime risk_on|risk_off|unclear` suffix). Auto-approve may mark it Approved. An `ExecutionTicket` is created only after an `ApprovalEvent` and a human Execute click.

```bash
AURUM_TREND_CONTEXT=1
X_BEARER_TOKEN=          # optional read-only bearer; empty skips X
X_TREND_QUERY=(bitcoin OR ethereum OR solana) lang:en -is:retweet
```

Do not commit a real `X_BEARER_TOKEN`. The loader never logs it.

## Agent Registry (`/tmp/aurum_agents.json`)

Shared JSON file where agents register on startup + heartbeat every ~60s.

**Example:**
```json
{
  "scout": {
    "agent_id": "scout",
    "symbol": null,
    "status": "running",
    "last_heartbeat": "2026-06-03T14:23:45.123456+00:00",
    "pid": 12345,
    "metadata": {
      "playbook": "wyckoff",
      "symbols": ["BTC-USD", "ETH-USD", "SOL-USD"],
      "poll_minutes": 15,
      "trend_context": false
    }
  },
  "profit_hunter_btc": {
    "agent_id": "profit_hunter_btc",
    "symbol": "BTC-EUR",
    "status": "running",
    "last_heartbeat": "2026-06-03T14:23:50.234567+00:00",
    "pid": 12346,
    "metadata": {
      "qty": 0.00003443,
      "cost_eur": 2.0,
      "min_profit_eur": 0.01,
      "poll_secs": 10
    }
  }
}
```

**Coordination rules:**
- `scout_agent` checks `is_symbol_claimed(symbol)` before auto-approving
- `profit_hunter` registers symbol on startup, unregisters on exit
- All agents check `is_paused()` before acting
- Entries with no heartbeat for >5min are marked as "stale"

## API Endpoints

### `GET /api/agent/status`
Quick summary: agent count, running, stale, paused.

```bash
curl http://localhost:8000/api/agent/status
```
```json
{
  "total_agents": 2,
  "running": 2,
  "stale": 0,
  "paused": false
}
```

### `GET /api/agent/`
Full registry — all agents + metadata.

```bash
curl http://localhost:8000/api/agent/
```

### `POST /api/agent/pause`
Set global pause flag — all agents skip their next actions.

```bash
curl -X POST http://localhost:8000/api/agent/pause
```

### `POST /api/agent/resume`
Clear pause flag.

```bash
curl -X POST http://localhost:8000/api/agent/resume
```

### `POST /api/agent/clean`
Remove stale entries (no heartbeat for >5min).

```bash
curl -X POST http://localhost:8000/api/agent/clean
```

## Configuration

### Enable auto-approve

Add to `.env`:
```bash
AURUM_AUTO_APPROVE=1
AUTO_APPROVE_MIN_CONFIDENCE=80
AUTO_APPROVE_MIN_EDGE_MATCH=70
AUTO_APPROVE_MIN_RR=1.8
AUTO_APPROVE_MAX_RISK_EUR=2.0
AUTO_APPROVE_MAX_PER_DAY=3
AUTO_APPROVE_ALLOW_SHORTS=false
```

### Public trend context

```bash
AURUM_TREND_CONTEXT=1
X_BEARER_TOKEN=
X_TREND_QUERY=(bitcoin OR ethereum OR solana) lang:en -is:retweet
```

Feeds the advisor prompt only. See "Revolut X Trend Expert" above. Real funds: this still ends at Approvals.

### Pause all agents

Set env var:
```bash
export AURUM_AGENTS_PAUSED=1
```

Or via API:
```bash
curl -X POST http://localhost:8000/api/agent/pause
```

Vercel cron (scout and profit-hunter ticks) stops when `AURUM_AGENTS_ENABLED=false`. Cron scout also honors the pause flag above before it generates ideas. The pause file lives on local disk (`/tmp/aurum_agents.json`); on serverless, set `AURUM_AGENTS_PAUSED=1` or `AURUM_AGENTS_ENABLED=false` in the project env so the switch survives a new instance.

## Safety

1. **No auto-execution** — scout only auto-approves TradeIdeas. Exit brackets propose a sell; you still approve and click Execute before a live broker order. Paper mode is the only path that simulates the exit fill.
2. **Symbol collision prevention** — scout won't auto-approve a symbol that profit_hunter has already claimed.
3. **Daily cap** — max 3 auto-approvals per 24h (rolling window).
4. **Personal-edge filter** — only auto-approves symbols you've historically traded.
5. **Guardian checks** — all structural rules (R:R, thesis, invalidation) still enforced.
6. **Global pause** — `POST /api/agent/pause` or `AURUM_AGENTS_PAUSED=1` makes local agents skip their next action. `AURUM_AGENTS_ENABLED=false` is the cron kill switch.
7. **Real funds** — broker writes need an `ApprovalEvent` and a human Execute click. Trend context and Copilot agents stop at a `TradeIdea`. No silent retry of place/cancel/modify (a retry can double-fill). Never log credentials or `X_BEARER_TOKEN`.
8. **profit_hunter stays strict** — slippage cap, held quantity only, single position. Do not loosen auto-sell.

## Typical Workflow

1. **Start scout agent** (weekends or before bed):
   ```bash
   ./scripts/start_scout.sh wyckoff
   ```

2. **Scout discovers + auto-approves a trade** → appears in Approvals page with `[AUTO]` prefix.

3. **You review + execute** → `ExecutionTicket` created, order placed on Revolut X.

4. **Helm bracket arms on the fill** (stop, target, trail). `/api/cron/hunt` watches it while agents are enabled. See `docs/helm-exit-brackets.md`.

5. **A breach creates an EXIT idea** → approve it, then execute. That market-sells the bracket quantity. Paper mode does this step itself.

6. **The symbol is free again** after the exit fill. Scout can consider it on the next pass.

## Monitoring

**Live agent status:**
```bash
watch -n 5 'curl -s http://localhost:8000/api/agent/status'
```

**All agents with metadata:**
```bash
curl -s http://localhost:8000/api/agent/ | jq
```

**Scout logs:**
```bash
tail -f /tmp/scout_agent.log
```

**Profit hunter logs:**
```bash
tail -f /tmp/profit_hunter_*.log
```

## Troubleshooting

**Scout not auto-approving:**
- Check `AURUM_AUTO_APPROVE=1` in `.env`
- Verify you have ≥3 approved trades (builds personal edge)
- Check thresholds: conf ≥80, edge ≥70, R:R ≥1.8
- Check daily cap: max 3/day

**profit_hunter not exiting:**
- Verify position still held: `revx account balances`
- Check target is reachable: `revx market ticker <symbol>`
- Review logs: `/tmp/profit_hunter_<symbol>.log`

**Agents marked as stale:**
- No heartbeat for >5min
- Process may have crashed — check logs
- Clean with: `curl -X POST http://localhost:8000/api/agent/clean`

**Global pause active:**
- Check `curl http://localhost:8000/api/agent/status`
- Resume with: `curl -X POST http://localhost:8000/api/agent/resume`
