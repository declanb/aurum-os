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
```
DATABASE_URL=postgresql://<user>:<password>@<host>:5432/postgres?sslmode=require
OPENAI_API_KEY=sk-proj-...            # your real key (set in Vercel env, never commit)
REVOLUT_X_API_KEY=<your-revolut-x-api-key>   # set in Vercel env, never commit
```

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
