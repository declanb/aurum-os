from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    NEXT_PUBLIC_APP_URL: str = "http://localhost:3000"
    DATABASE_URL: str = "sqlite:///./aurum.db"
    OPENAI_API_KEY: str = ""

    # Revolut X — credentials live at ~/.config/revolut-x/ (managed by `revx configure`).
    # The `revx` CLI must be installed on PATH (`npm link -w cli` from revolut-x-api repo).
    REVOLUT_X_DEFAULT_PAIR: str = "BTC-EUR"

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

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()
