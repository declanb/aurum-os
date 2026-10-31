# Helm commodities venue (MetaApi)

Helm can stage and paper-trade gold, silver and oil through [MetaApi](https://metaapi.cloud), which bridges to an MT4/MT5 broker account. It sits beside the Revolut X venue and does not change it.

> **Leveraged CFDs, not spot.** MT4/MT5 brokers sell CFDs. You don't own the commodity, losses can exceed margin, and overnight swap is charged. This breaks Helm's spot-only rule, so every idea needs its own `leveraged_ok` acknowledgement before a live order, and Guardian always shows this warning.

## Modes

| `HELM_METAAPI_MODE` | What Execute does |
|---|---|
| `paper` (default) | Opens a row in the paper ledger (`metaapipaperposition`) at the live ask (LONG) or bid (SHORT). No broker call. |
| `live` | Sends one MetaApi market order with mandatory stop-loss and take-profit. |

Live execution requires, in order: the TradeIdea is **Approved** with an `ApprovalEvent` whose snapshot still matches, the idea is a MetaApi idea, `leveraged_ok` is true, symbol in `HELM_METAAPI_ALLOWED_SYMBOLS`, `0 < lots <= HELM_METAAPI_MAX_LOTS`, SL/TP on the correct sides, and account margin level ≥ **300%** (when any margin is in use). Any failure refuses the order.

The Revolut X execute route refuses MetaApi ideas, so a commodities idea can't be sent to Revolut X by mistake.

## Setup

1. **MetaApi token.** In metaapi.cloud → *API access*, create an API token. Give it the narrowest scope that allows account info, market data and (only if you will go live) trading for one account.
2. **Account id.** In metaapi.cloud → *Accounts*, add your MT4/MT5 broker account (start with a **demo** account) and copy its account id. Note the region (e.g. `new-york`, `london`).
3. **Vercel env vars** (Project → Settings → Environment Variables, Production + Preview). Don't paste these into chat.

   ```
   METAAPI_TOKEN=<token>                 # secret
   METAAPI_ACCOUNT_ID=<account id>       # secret
   METAAPI_REGION=new-york               # optional, MetaApi region of the account
   HELM_METAAPI_MODE=paper               # paper (default) | live
   HELM_METAAPI_MAX_LOTS=0.01
   HELM_METAAPI_ALLOWED_SYMBOLS=XAUUSD,XAGUSD,XBRUSD,XTIUSD
   # optional
   HELM_METAAPI_SWAP_PCT_PER_NIGHT=0.0002          # swap estimate, fraction of notional per night
   HELM_METAAPI_CONTRACT_SIZES=XAUUSD=100,XAGUSD=5000,XBRUSD=1000,XTIUSD=1000
   ```

   Broker symbol names vary (`XAUUSD.m`, `UKOIL`, `USOIL`…). Set `HELM_METAAPI_ALLOWED_SYMBOLS` and `HELM_METAAPI_CONTRACT_SIZES` to your broker's names and sizes.
4. **Migration.** Run `alembic upgrade head` against Supabase (adds `metaapiidea` and `metaapipaperposition`, revision `f2a9d4c61b80`).
5. Redeploy, open `/app/commodities`, and check the badge says *MetaApi connected* and *Paper*.

Deployment Protection is unchanged; these routes sit behind the same Vercel Authentication as the rest of Helm.

## Flow

1. `POST /api/metaapi/scout` (or the *Run commodities scout* button) reads 1h candles and stages `TradeIdea`s with `venue=metaapi`: SMA20 trend with slope, stop 1.5×ATR14, target 3×ATR14, lots = max lots. One pending idea per symbol.
2. Approve it in **Approvals** as usual.
3. Tick *I understand this is a leveraged CFD* (`POST /api/metaapi/ideas/{id}/ack`).
4. **Execute** (`POST /api/metaapi/execute/{id}`): paper ledger row, or a live order in live mode.
5. `POST /api/metaapi/paper/mark` marks open paper rows at the exit side, deducts the swap estimate, and closes on SL/TP touch. Entry pays the spread (`spread_cost` is recorded). P&L is in USD.

## Routes

Read-only: `GET /api/metaapi/status | account | positions | price/{symbol} | candles/{symbol} | ideas | paper`.
Writes: `POST /api/metaapi/ideas`, `/ideas/{id}/ack`, `/scout`, `/execute/{id}`, `/paper/mark`, `/paper/{id}/close`.

`METAAPI_TOKEN` and `METAAPI_ACCOUNT_ID` are only sent as MetaApi request credentials. They're never returned or logged, and broker errors are redacted.

## Tests

`pytest tests/test_metaapi_venue.py` — all MetaApi calls are mocked.
