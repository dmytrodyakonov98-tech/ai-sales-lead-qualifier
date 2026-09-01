from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    llm_provider: str = "openai"
    openai_api_key: str | None = None
    llm_model: str = "gpt-5.6-luna"
    database_url: str = "sqlite:///./data/leads.db"
    app_env: str = "development"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
