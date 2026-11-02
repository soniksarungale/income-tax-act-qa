from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql://taxqa:taxqa@127.0.0.1:5433/taxqa"
    act_pdf_path: Path = Path("data/Income-tax-Act-1961_2026.pdf")
    model_cache_dir: Path = Path("data/cache/models")
    embed_threads: int = 2

    llm_provider: str = "claude-cli"
    llm_model: str = ""
    llm_api_key: str = ""
    claude_bin: str = "claude"


settings = Settings()
