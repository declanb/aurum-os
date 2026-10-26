from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    NEXT_PUBLIC_APP_URL: str = "http://localhost:3000"
    DATABASE_URL: str = "sqlite:///./aurum.db"
    OPENAI_API_KEY: str = ""
    GITHUB_TOKEN: str = ""  # GitHub PAT for Models API (free with Copilot Enterprise)

    # Revolut X — credentials live at ~/.config/revolut-x/ (managed by `revx configure`).
    # The `revx` CLI must be installed on PATH (`npm link -w cli` from revolut-x-api repo).
    REVOLUT_X_DEFAULT_PAIR: str = "BTC-EUR"

    # ── Paper trading ────────────────────────────────────────────────────────
    # When PAPER_TRADING=1, trade_executor simulates fills against live mid-prices
    # instead of placing real Revolut X orders. Use to stress-test playbooks 24/7
    # without risking capital. Fills are persisted as ExecutionTicket with
    # adapter_status="PaperFilled" so the rest of the system treats them normally.
    PAPER_TRADING: bool = False
    PAPER_STARTING_BALANCE_EUR: float = 1000.0

    # ── Auto-approve (optional). Preferred production value is off (0). ────────
    # Off: /api/cron/scout stages TradeIdeas as "Ready for Approval". Declan
    # signs them on the Approvals page (writes ApprovalEvent) and clicks Execute.
    # On: high-confidence ideas are also marked Approved. Broker orders are still
    # a separate Execute click — this flag never places an order.
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

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()
