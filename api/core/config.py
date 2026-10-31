from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    NEXT_PUBLIC_APP_URL: str = "http://localhost:3000"
    DATABASE_URL: str = "sqlite:///./aurum.db"
    OPENAI_API_KEY: str = ""
    GITHUB_TOKEN: str = ""  # GitHub PAT for Models API (free with Copilot Enterprise)

    # Revolut X. Local CLI: `revx` on PATH plus ~/.config/revolut-x/ (`revx configure`).
    # Vercel has no CLI. Set REVX_API_KEY and REVX_PRIVATE_KEY (PEM or base64) to
    # sign REST calls. REVX_TRANSPORT=auto uses HTTP when both are set, else the CLI.
    # REVOLUT_X_API_KEY is accepted as an alias of REVX_API_KEY. Never log these.
    REVOLUT_X_DEFAULT_PAIR: str = "BTC-EUR"
    REVX_API_KEY: str = ""
    REVOLUT_X_API_KEY: str = ""
    REVX_PRIVATE_KEY: str = ""
    REVX_PRIVATE_KEY_B64: str = ""
    REVX_API_BASE_URL: str = "https://revx.revolut.com"
    REVX_TRANSPORT: str = "auto"

    # ── Paper trading ────────────────────────────────────────────────────────
    # When PAPER_TRADING=1, trade_executor simulates fills against live mid-prices
    # instead of placing real Revolut X orders. Use to stress-test playbooks 24/7
    # without risking capital. Fills are persisted as ExecutionTicket with
    # adapter_status="PaperFilled" so the rest of the system treats them normally.
    PAPER_TRADING: bool = False
    PAPER_STARTING_BALANCE_EUR: float = 1000.0

    # ── Paper copy book (dry-run only; never a broker order) ──────────────
    # Revolut X has no native copy API. This virtual book mirrors scout
    # TradeIdeas and EUR ticker gainers. HELM_COPY_BANKROLL_EUR is the
    # starting cash. AURUM_COPY_BANKROLL_EUR is accepted as an alias.
    # See docs/helm-copy-book.md. This flag does not enable PAPER_TRADING
    # and does not reach the order path.
    HELM_COPY_BANKROLL_EUR: float = Field(
        default=200.0,
        validation_alias=AliasChoices("HELM_COPY_BANKROLL_EUR", "AURUM_COPY_BANKROLL_EUR"),
    )
    HELM_COPY_POSITION_PCT: float = 0.10       # fraction of virtual equity per new name
    HELM_COPY_MAX_NOTIONAL_EUR: float = 40.0   # hard cap per name, also clamped to 25% of bankroll
    HELM_COPY_MAX_POSITIONS: int = 5
    HELM_COPY_GAINER_LIMIT: int = 3

    # ── Helm strategy (approved Oct 2026 after the overnight paper test) ──
    # Symmetric exit brackets replace "sell on any green". Percents are net of
    # the Revolut X sell taker fee: +3% / -3% of the entry notional after fees.
    HELM_TP_PCT: float = 3.0
    HELM_SL_PCT: float = 3.0
    HELM_SYMMETRIC_BRACKETS: bool = True     # apply TP/SL to new scout LONG ideas
    HELM_MAX_IDEAS_PER_DAY: int = 2          # scout conviction cap per UTC day
    HELM_STALE_IDEA_HOURS: float = 48.0      # expire-stale cutoff (never auto-run)
    # Strategy paper week: EUR 200 virtual bank, EUR 50 per position.
    HELM_PAPER_POSITION_EUR: float = 50.0
    HELM_COPY_PUBLIC_QUOTES: bool = False    # mark via REVX public tickers (no keys)

    # ── Auto-approve (Trade Advisor → Approved TradeIdea, NO order placement) ────
    # Off by default. Flip AURUM_AUTO_APPROVE=1 in .env to enable.
    # When enabled, high-confidence recommendations are auto-created as TradeIdeas
    # AND auto-approved (status="Approved"), but no broker order is sent.
    # You still execute manually from the Approvals page.
    AURUM_AUTO_APPROVE: bool = False
    AUTO_APPROVE_MIN_CONFIDENCE: int = 80    # rec.confidence_score must be ≥ this
    AUTO_APPROVE_MIN_EDGE_MATCH: int = 70    # rec.edge_match_score must be ≥ this
    AUTO_APPROVE_MIN_RR: float = 1.8         # rec.risk_reward must be ≥ this
    AUTO_APPROVE_MAX_RISK_EUR: float = 2.0   # implied risk per trade (informational guard)
    AUTO_APPROVE_MAX_PER_DAY: int = 3        # circuit breaker — N approvals / rolling 24h
    AUTO_APPROVE_ALLOW_SHORTS: bool = False  # Revolut X is spot-only; SHORTs never auto-approved

    # ── Vercel Cron Agents ────────────────────────────────────────────────────
    AURUM_AGENTS_ENABLED: bool = True        # Global kill switch for cron agents
    CRON_SECRET: str = ""                    # Bearer token for Vercel cron auth (optional)
    SCOUT_SYMBOLS: str = "BTC-EUR,SOL-EUR,SHIB-EUR,AVAX-EUR,ENA-EUR,DOGE-EUR,SUI-EUR,XRP-EUR"
    SCOUT_PLAYBOOK: str = "trend_follower"   # wyckoff, ict_smc, trend_follower, macro, livermore
    OPENAI_MODEL: str = "gpt-4o-mini"        # Cost protection: mini is ~10x cheaper than gpt-4o

    # ── OpenAI Agents SDK ─────────────────────────────────────────────────────
    # When set, recommendations are generated via the OpenAI Agents SDK (the model
    # calls tools to fetch price/candles/indicators itself) instead of the single-shot
    # Chat Completions path. Requires a real OPENAI_API_KEY — the Agents SDK targets
    # OpenAI's Responses API and does NOT use the GitHub Models fallback.
    AURUM_USE_AGENTS_SDK: bool = False

    # ── trend_scout (read-only SignalBundles; never places orders) ───────────
    # Off by default. When on, ai_advisor may attach untrusted public-trend context.
    # AURUM_TREND_SCOUT_NETWORK=1 fetches the allowlisted RSS feeds. X/Twitter is
    # queried only when X_BEARER_TOKEN is also set. See docs/HELM_AGENT_FLEET.md.
    AURUM_TREND_SCOUT: bool = False
    AURUM_TREND_SCOUT_NETWORK: bool = False
    X_BEARER_TOKEN: str = ""

    # ── Public regime context (read-only; advisory prompt input) ─────────────
    # Separate from trend_scout. When set, ai_advisor loads CoinGecko / Fear &
    # Greed / headlines (and X recent search if X_BEARER_TOKEN is set) and
    # attaches them to the prompt. This flag does not place orders.
    # Recommendations still end at a TradeIdea.
    # trend_context.py reads the bearer from the environment and must not log it.
    AURUM_TREND_CONTEXT: bool = False
    X_TREND_QUERY: str = "(bitcoin OR ethereum OR solana) lang:en -is:retweet"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()
