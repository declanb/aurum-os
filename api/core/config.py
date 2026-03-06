from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    NEXT_PUBLIC_APP_URL: str = "http://localhost:3000"
    DATABASE_URL: str = "sqlite:///./aurum.db"
    OPENAI_API_KEY: str = ""
    META_API_TOKEN: str = ""
    META_API_ACCOUNT_ID: str = ""
    
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()
