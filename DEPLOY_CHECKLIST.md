# Vercel Deployment Checklist

## ✅ What Was Refactored

1. **Created `/api/cron/scout`** — AI recommendations every 30 minutes
2. **Created `/api/cron/hunt`** — Position exit monitoring every 2 minutes
3. **Cost protection**:
   - gpt-4o-mini by default (10x cheaper)
   - Rate limiting (min 25min scout, 110s hunt)
   - Global kill switch (`AURUM_AGENTS_ENABLED`)
   - Cron secret auth
4. **Updated `vercel.json`** with cron schedule
5. **Added revx CLI** to package.json

## 📝 Environment Variables to Set in Vercel

After deploy, go to **Vercel Dashboard → Settings → Environment Variables** and add:

### Required

`postgresql://` and `postgresql+psycopg://` both use the psycopg v3 driver (`psycopg[binary]` in the root `requirements.txt`, which `@vercel/python` installs for `api/index.py`). SQLAlchemy 2.1 selects that dialect for a bare `postgresql://` URL. `postgresql+psycopg2://` selects the legacy `psycopg2` driver.

```
DATABASE_URL=postgresql://<user>:<password>@<host>:5432/postgres?sslmode=require
OPENAI_API_KEY=sk-proj-...            # your real key (set in Vercel env, never commit)
```

### Revolut X on Vercel (signed HTTP)

The Python function cannot shell out to `revx`. Broker reads (`/api/revolut-x/*`) use the REST API when these secrets are set. Do not bundle the CLI. Do not paste real keys into git.

Set on **Vercel → Settings → Environment Variables** (Production):

```
REVX_API_KEY=<64-char key from Revolut X → Profile → API keys>
REVX_PRIVATE_KEY=<Ed25519 PKCS#8 PEM; one line with literal \n between lines>
```

`REVOLUT_X_API_KEY` is accepted as an alias of `REVX_API_KEY` and is not enough on its own. Alternatively set `REVX_PRIVATE_KEY_B64` to the base64 of that PEM, of the PKCS#8 DER, or of the raw 32-byte seed, and leave `REVX_PRIVATE_KEY` empty.

`REVX_TRANSPORT=auto` (default) uses HTTP when both values are present, and falls back to `revx` on a machine where the binary is on PATH and the env keys are unset. Optional: `REVX_API_BASE_URL=https://revx.revolut.com`.

Order placement still requires an Approved `TradeIdea` and an `ApprovalEvent` before `POST /api/revolut-x/execute/{trade_id}`. This checklist does not turn on `AURUM_AGENTS_ENABLED`.

### Agent Control
```
AURUM_AGENTS_ENABLED=true
AURUM_AUTO_APPROVE=true
SCOUT_SYMBOLS=BTC-EUR,SOL-EUR,SHIB-EUR,AVAX-EUR,ENA-EUR,DOGE-EUR,SUI-EUR,XRP-EUR
SCOUT_PLAYBOOK=trend_follower
OPENAI_MODEL=gpt-4o-mini
```

### Optional (Security)
```
CRON_SECRET=<random-string>  # Protects cron endpoints from external calls
```

## 🔒 Cost Protection Setup (Do AFTER deploy)

### 1. OpenAI Spending Limit
1. Go to https://platform.openai.com/account/limits
2. Set **Hard limit**: **$5/month**
3. Set **Soft limit**: $3/month (email alert)

### 2. Vercel Spending Cap
1. Vercel Dashboard → Account Settings → Billing
2. Under "Spend Management" → Set **Monthly spend limit**: **$10**
3. Choose **Pause deployments** when limit reached

### 3. Monitor First Week
- Check Vercel logs daily for first 3 days
- OpenAI usage: https://platform.openai.com/usage
- Vercel usage: Dashboard → Analytics

## 📊 Expected Monthly Costs

| Item | Cost |
|---|---|
| Vercel Pro | $20 (you're paying anyway) |
| Vercel overage | $0-2 |
| OpenAI (gpt-4o-mini @ 30min scout) | $1-2 |
| Supabase | $0 (free tier) |
| **Total NEW spend** | **$1-4/month** |

## 🚨 Kill Switch

If costs spike or agents misbehave:

1. **Instant stop**: Vercel Dashboard → Env Vars → Set `AURUM_AGENTS_ENABLED=false` → Redeploy
2. **Nuclear option**: Vercel Dashboard → delete the `crons` section from vercel.json → Redeploy

## ✅ Verification After Deploy

1. Check crons registered: Vercel Dashboard → Deployments → (your project) → Cron Jobs tab
2. Test scout manually: `curl https://your-domain.vercel.app/api/cron/scout`
3. Test hunter manually: `curl https://your-domain.vercel.app/api/cron/hunt`
4. Wait 30 min → Check logs for first real scout run
5. Check OpenAI usage after 24h

## 📝 Cron Schedule

- **Scout** (`/api/cron/scout`): Every 30 minutes = 48 runs/day
- **Hunter** (`/api/cron/hunt`): Every 2 minutes = 720 runs/day

Both have rate limiting in code as backup.
