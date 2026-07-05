from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # server
    api_token: str = ""
    cors_origins: str = "http://localhost:5173"
    db_url: str = "sqlite:///./vix_screener.db"

    # interactive brokers
    ibkr_enabled: bool = True
    ibkr_host: str = "127.0.0.1"
    ibkr_port: int = 4002
    ibkr_client_id: int = 11
    ibkr_mode: str = "paper"
    ibkr_use_delayed: bool = True
    allow_order_staging: bool = False

    # alerts
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    alert_from: str = ""
    default_alert_email: str = ""
    ntfy_url: str = ""

    scheduler_enabled: bool = True

    # VIX hedge strategy defaults
    vix_macd_fast: int = 12
    vix_macd_slow: int = 26
    vix_macd_signal: int = 9
    vix_or_minutes: int = 30
    vix_spread_width: float = 1.0
    vix_net_debit_cap_usd: float = 100.0
    vix_dte_min: int = 15
    vix_dte_max: int = 34
    vix_low_lookback_days: int = 120
    vix_low_quantile: float = 0.4
    vix_abs_low: float = 20.0
    vix_armed_ttl_days: int = 4
    vix_strike_window_below: float = 8.0
    vix_strike_window_above: float = 5.0

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
