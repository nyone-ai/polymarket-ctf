"""Pydantic settings for the Polymarket CTF Merge Bot."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import PrivateAttr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Global bot settings, loaded from env + optional YAML config file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Mode ---
    mode: str = "paper"  # paper | live
    threshold: float = 0.995
    min_profit_usd: float =  1.0
    min_profit_margin_bps: float =  10.0
    max_size_per_trade: float =  500.0
    max_daily_loss: float =  100.0
    cooldown_seconds: float =  5.0
    poll_interval: float =  30.0
    max_trades_per_minute: int =  10
    reserve_gas_usd: float =   2.0

    # --- Execution ---
    order_type: str = "FOK"  # FOK | IOC
    excess_mode: str = "cancel"  # cancel | sell
    merge_mode: str = "adapter"  # adapter | ctf_direct
    auto_wrap_usdce: bool = False
    tx_timeout_seconds: int =  120

    # --- Wallet ---
    private_key: Optional[str] = None
    wallet_address: Optional[str] = None

    # --- RPC / chain ---
    rpc_url: str = "https://polygon-rpc.com"
    chain_id: int =  137

    # --- CLOB ---
    clob_host: str = "https://clob.polymarket.com"
    clob_ws_url: str = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
    clob_api_key: Optional[str] = None
    clob_api_secret: Optional[str] = None
    clob_api_passphrase: Optional[str] = None
    clob_api_l2: bool = False
    ctf_exchange_address: Optional[str] = None
    neg_risk_adapter_address: Optional[str] = None
    wrapper_usdc_address: Optional[str] = None
    usdce_address: Optional[str] = None
    pusd_address: Optional[str] = None
    collateral_onramp_address: Optional[str] = None
    collateral_offramp_address: Optional[str] = None

    # --- Scanner / watchlist ---
    watchlist_mode: str = "explicit"  # explicit | auto | hybrid
    watchlist_path: str = "config/markets.watchlist.json"
    watchlist_condition_ids: list[str] = []  # manual condition_id list
    auto_discover: bool = True
    auto_discover_min_liquidity: float =   5000.0
    auto_discover_min_volume_24h: float =  1000.0
    auto_discover_active_only: bool = True

    # --- Fee / gas ---
    fee_rate_bps_override: Optional[float] = None
    matic_usd_price: Optional[float] = None

    # --- Telegram ---
    telegram_bot_token: Optional[str] = None
    telegram_chat_id: Optional[str] = None
    telegram_rate_limit_per_min: int =  20

    # --- Logging ---
    log_level: str = "INFO"
    log_dir: str = "logs"

    _config_file: Optional[Path] = PrivateAttr(default=None)

    @field_validator("mode", "order_type", "excess_mode", "merge_mode", "watchlist_mode")
    @classmethod
    def _normalize_enumish(cls, v: str) -> str:
        return v.strip().lower() if isinstance(v, str) else v

    @field_validator("private_key")
    @classmethod
    def _strip_secret(cls, v: Optional[str]) -> Optional[str]:
        return v.strip() if v else None

    @classmethod
    def from_yaml(cls, path: str | Path | None = None) -> "Settings":
        """Load settings, overlaying YAML values below env vars (env wins)."""

        settings = cls()
        if path is not None:
            p = Path(path)
            if p.exists():
                import yaml
                raw = p.read_text().replace("\ufe0f", "").replace("\ufe0e", "").strip()
                data = yaml.safe_load(raw) or {}
                if isinstance(data, dict):
                    adf = data.get("auto_discover_filters") or {}
                    for k, v in adf.items(): data[f"auto_discover_{k}"] = v
                    for sec_name in ("telegram", "logging"):
                        sec = data.get(sec_name) or {}
                        for sk, sv in sec.items():
                            data[f"{sec_name}_{sk}"] = sv

                    merged = settings.model_dump()
                    merged.update({k: v for k, v in data.items() if k in cls.model_fields})
                    settings = cls(**merged)
        return settings

    @property
    def is_live(self) -> bool:
        return self.mode == "live"

    @property
    def pusd_reserve_for_gas(self) -> float:
        return self.reserve_gas_usd

    @property
    def project_root(self) -> Path:
        return Path.cwd()


@lru_cache
def get_settings(path: str | Path | None = None) -> Settings:
    """Cached settings singleton."""

    return Settings.from_yaml(path)




