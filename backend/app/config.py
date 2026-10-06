from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Configuração de infraestrutura (variáveis de ambiente com prefixo O51NT_)."""

    model_config = SettingsConfigDict(env_prefix="O51NT_", env_file=".env", extra="ignore")

    data_dir: Path = ROOT_DIR / "data"
    static_dir: Path = ROOT_DIR / "backend" / "static"
    host: str = "127.0.0.1"
    port: int = 8051
    user_agent: str = "O51NT-Workbench/1.0 (+local; contato: usuario local)"
    rate_limit_seconds: float = 3.0
    scraper_concurrency: int = 2
    scraper_timeout_seconds: float = 20.0
    scraper_retries: int = 1
    scheduler_enabled: bool = True
    max_upload_mb: int = 50
    searxng_url: str = "http://127.0.0.1:8080"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "o51nt.db"

    @property
    def evidence_dir(self) -> Path:
        return self.data_dir / "evidence"

    @property
    def alerts_dir(self) -> Path:
        return self.data_dir / "alerts"

    @property
    def logs_dir(self) -> Path:
        return self.data_dir / "logs"

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def settings_file(self) -> Path:
        return self.data_dir / "settings.json"

    def ensure_dirs(self) -> None:
        for d in (self.data_dir, self.evidence_dir, self.alerts_dir, self.logs_dir, self.uploads_dir):
            d.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    return Settings()
