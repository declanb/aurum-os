# Vercel Deployment Checklist

## ✅ What Was Refactored

1. **`GET /api/cron/scout`** — AI recommendations every 15 minutes, staged for Approvals
2. **`GET /api/cron/hunt`** — exists in the API and is **not** on the Vercel schedule (it places market sells)
3. **Cost protection**:
   - gpt-4o-mini by default (10x cheaper)
   - Rate limiting (min 14min scout, 110s hunt)
   - Global kill switch (`AURUM_AGENTS_ENABLED`)
   - Cron secret auth
4. **`vercel.json` `crons`** calls `/api/cron/scout` on `*/15 * * * *`
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
AURUM_AUTO_APPROVE=0
SCOUT_SYMBOLS=BTC-EUR,SOL-EUR,SHIB-EUR,AVAX-EUR,ENA-EUR,DOGE-EUR,SUI-EUR,XRP-EUR
SCOUT_PLAYBOOK=trend_follower
OPENAI_MODEL=gpt-4o-mini
```

`AURUM_AUTO_APPROVE=0` is the setting that prompts Declan. Each scout tick calls `stage_recommendation` and saves a TradeIdea as **Ready for Approval**. On `/app/approvals` he clicks **Sign & Approve** (writes an `ApprovalEvent`) and then **Send to Execution Matrix**. Execute is the only production path that sends a Revolut X order. Spot shorts stay blocked (`AUTO_APPROVE_ALLOW_SHORTS` defaults to false).

Leave `AURUM_AUTO_APPROVE` off. Turning it on also marks high-confidence ideas Approved inside the cron, and those rows have no `ApprovalEvent`, so Execute refuses them. The staged **Ready for Approval** row is the one that can be signed and sent.

### Cron auth
```
CRON_SECRET=<generate-in-vercel-dashboard>
```

Set this in Vercel only. When the variable is present, Vercel calls cron paths with `Authorization: Bearer <CRON_SECRET>`, and `/api/cron/scout` rejects any other caller. Do not commit the value.

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
| OpenAI (gpt-4o-mini @ 15min scout) | $2-4 |
| Supabase | $0 (free tier) |
| **Total NEW spend** | **$2-6/month** |

## 🚨 Kill Switch

If costs spike or agents misbehave:

1. **Instant stop**: Vercel Dashboard → Env Vars → Set `AURUM_AGENTS_ENABLED=false` → Redeploy
2. **Nuclear option**: Vercel Dashboard → delete the `crons` section from vercel.json → Redeploy

## ✅ Verification After Deploy

1. Check crons registered: Vercel Dashboard → Deployments → (your project) → Cron Jobs tab
2. Test scout manually (secret stays in your shell, not in the repo):

   ```bash
   curl -H "Authorization: Bearer $CRON_SECRET" https://your-domain.vercel.app/api/cron/scout
   ```

   A successful body includes `"staged"` and `"auto_approve": false`. New rows show up on `/app/approvals` as **Ready for Approval**.
3. Wait 15 min → Check logs for the first scheduled scout run
4. Check OpenAI usage after 24h

## 📝 Cron Schedule

- **Scout** (`/api/cron/scout`): every 15 minutes (`*/15 * * * *`) = 96 runs/day. In-process floor is 14 minutes.
- **Hunter** (`/api/cron/hunt`): no Vercel cron. The handler sells at market when a target is hit, with no `ApprovalEvent`. Exits stay on Approvals → Execute.

**Plan:** a 15-minute expression requires Vercel Pro. Hobby accounts only allow a cron that runs once per day, and a faster expression fails the deployment (the same check that removed the old `*/30` and `*/2` entries). Confirm the project is on Pro before merging.
