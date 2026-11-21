from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", "../.env"), extra="ignore")

    database_url: str = "sqlite:///./app.db"
    jwt_secret: str = "change-me-in-production-please-32-bytes-min"
    jwt_expire_minutes: int = 12 * 60

    # local    = model uruchomiony w urzędzie (Ollama / vLLM), dane nie opuszczają serwera
    # external = zewnętrzne API (tylko dev / demo), dane są pseudonimizowane
    # fake     = bez modelu; deterministyczne heurystyki (testy, CI, demo offline)
    llm_mode: Literal["local", "external", "fake"] = "local"
    llm_model: str = "ollama_chat/SpeakLeash/bielik-11b-v2.3-instruct:Q4_K_M"
    llm_api_key: str | None = None
    llm_timeout: int = 180
    # gdy model nie odpowiada / zwraca niepoprawny JSON -> heurystyka zamiast błędu
    llm_heuristic_fallback: bool = True

    embedding_model: str = "ollama/bge-m3"
    ollama_base_url: str = "http://localhost:11434"

    pseudonymize: bool = True
    seed_demo_data: bool = True

    k_anonymity: int = 5
    recency_window_days: int = 60
    recency_threshold: float = 0.5

    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    # powiadomienia e-mail (opcjonalne; bez SMTP powiadomienia są tylko w systemie)
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "asystent-ocen@urzad.gov.pl"
    smtp_starttls: bool = True
    app_url: str = "http://localhost:3000"

    @property
    def cors_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
