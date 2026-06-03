# Aurum Agent Fleet

Aurum runs multiple autonomous agents that coordinate via a shared registry. Each agent handles one concern and registers itself so others can see what's running.

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

## Current Agents

### 1. scout_agent

**Purpose:** Autonomous AI trade advisor  
**Process:** Long-running loop  
**Log:** `/tmp/scout_agent.log`

**What it does:**
- Every 15 minutes:
  1. Fetches AI recommendations via `ai_advisor` (using your selected playbook)
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

**Purpose:** Exit strategy — sells position when profit target hit  
**Process:** One per position, exits after fill  
**Log:** `/tmp/profit_hunter_<symbol>.log`

**What it does:**
- Polls bid price every N seconds
- Computes net P&L (after fees)
- When P&L >= target, fires market sell
- Unregisters on exit (symbol freed for scout)

**Start:**
```bash
python -m api.services.profit_hunter \
  --symbol BTC-EUR \
  --qty 0.00003443 \
  --cost-eur 2.00 \
  --min-profit-eur 0.01 \
  --poll-secs 10
```

**Stop:**
```bash
pkill -f "profit_hunter.*BTC"
```

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
      "poll_minutes": 15
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

### Pause all agents

Set env var:
```bash
export AURUM_AGENTS_PAUSED=1
```

Or via API:
```bash
curl -X POST http://localhost:8000/api/agent/pause
```

## Safety

1. **No auto-execution** — scout only auto-approves TradeIdeas. You still manually click "Execute" to place the broker order.
2. **Symbol collision prevention** — scout won't auto-approve a symbol that profit_hunter has already claimed.
3. **Daily cap** — max 3 auto-approvals per 24h (rolling window).
4. **Personal-edge filter** — only auto-approves symbols you've historically traded.
5. **Guardian checks** — all structural rules (R:R, thesis, invalidation) still enforced.
6. **Global pause** — one flag stops all agents instantly.

## Typical Workflow

1. **Start scout agent** (weekends or before bed):
   ```bash
   ./scripts/start_scout.sh wyckoff
   ```

2. **Scout discovers + auto-approves a trade** → appears in Approvals page with `[AUTO]` prefix.

3. **You review + execute** → `ExecutionTicket` created, order placed on Revolut X.

4. **Start profit_hunter for that position**:
   ```bash
   python -m api.services.profit_hunter --symbol BTC-EUR --qty 0.00003443 --cost-eur 2.00 --min-profit-eur 0.01
   ```

5. **profit_hunter claims the symbol** → scout won't auto-approve BTC again until hunter exits.

6. **profit_hunter hits target, sells, unregisters** → symbol freed, cycle repeats.

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
