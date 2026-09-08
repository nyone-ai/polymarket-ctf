"""Pydantic settings for the Polymarket CTF Merge Bot."""
from __future__ import annotations

from functools import lru_cache
import os
from pathlib import Path
from typing import Optional

from dotenv import dotenv_values
from pydantic import Field, PrivateAttr, field_validator, model_validator
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
    order_type: str = "FOK"  # FOK fill-or-kill; FAK fill-and-kill (partial fills dibatalkan)
    excess_mode: str = "cancel"  # cancel | sell
    merge_mode: str = "adapter"  # adapter | ctf_direct
    auto_wrap_usdce: bool = False
    tx_timeout_seconds: int =  120
    order_timeout_seconds: int =  20   # max seconds to await a place_orders response/fill

    # --- Wallet ---
    private_key: Optional[str] = None
    wallet_address: Optional[str] = None
    polymarket_proxy_address: Optional[str] = None

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
    clob_signature_type: int = 0  # 0=EOA,, 1=POLY_PROXY
    ctf_exchange_address: Optional[str] = None
    neg_risk_exchange_address: Optional[str] = None
    neg_risk_adapter_address: Optional[str] = None
    ctf_collateral_adapter_address: Optional[str] = None
    ctf_condition_tokens_address: Optional[str] = None
    wrapper_usdc_address: Optional[str] = None
    usdce_address: Optional[str] = None
    pusd_address: Optional[str] = None
    collateral_onramp_address: Optional[str] = None
    collateral_offramp_address: Optional[str] = None

    # --- Scanner / watchlist ---
    watchlist_mode: str = "explicit"  # explicit | auto | hybrid
    watchlist_path: str = "config/markets.watchlist.json"
    watchlist_condition_ids: list[str] = Field(default_factory=list)  # manual condition_id list
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

    @field_validator("mode", "excess_mode", "merge_mode", "watchlist_mode")
    @classmethod
    def _normalize_enumish(cls, v: str) -> str:
        return v.strip().lower() if isinstance(v, str) else v

    @field_validator("clob_signature_type")
    @classmethod
    def _validate_clob_signature_type(cls, v: int) -> int:
        if v not in {0, 1}:
            raise ValueError("clob_signature_type must be 0 (EOA) or 1 (POLY_PROXY)")
        return v

    @field_validator("order_type")
    @classmethod
    def _normalize_order_type(cls, v: str) -> str:
        return v.strip().upper() if isinstance(v, str) else v

    @model_validator(mode="after")
    def _validate_values(self) -> "Settings":
        if self.mode not in {"paper", "live"}:
            raise ValueError("mode must be 'paper' or 'live'")
        if self.order_type not in {"FOK", "FAK"}:
            raise ValueError("order_type must be FOK or FAK")
        if not 0 < self.threshold <= 1:
            raise ValueError("threshold must be greater than 0 and at most 1")
        if self.max_size_per_trade <= 0 or self.poll_interval <= 0:
            raise ValueError("max_size_per_trade and poll_interval must be positive")
        if self.max_trades_per_minute <= 0:
            raise ValueError("max_trades_per_minute must be positive")

        if self.mode == "live":
            self._validate_live_credentials()
        return self

    def _validate_live_credentials(self) -> None:
        if not self.private_key or not self.wallet_address:
            raise ValueError("mode=live requires PRIVATE_KEY and WALLET_ADDRESS")
        if not self.rpc_url or not self.clob_api_key:
            raise ValueError("mode=live requires RPC_URL and CLOB_API_KEY")
        pk_raw = self.private_key.strip()
        if pk_raw.lower().startswith("0x"):
            pk_raw = pk_raw[2:]
        if len(pk_raw) != 64:
            raise ValueError("PRIVATE_KEY must be 32 bytes (0x + 64 hex chars)")
        try:
            int(pk_raw, 16)
        except ValueError:
            raise ValueError("PRIVATE_KEY must contain only hex characters")
        self._validate_address("WALLET_ADDRESS", self.wallet_address, expect_bytes=20)
        try:
            from eth_account import Account
            derived = Account.from_key(pk_raw).address
            if derived.lower() != self.wallet_address.lower():
                raise ValueError(
                    "WALLET_ADDRESS does not match derived address from PRIVATE_KEY "
                    f"(derived={derived})"
                )
        except ValueError as exc:
            raise ValueError(f"invalid PRIVATE_KEY/WALLET_ADDRESS pair: {exc}") from exc

    @staticmethod
    def _validate_address(label: str, value: Optional[str], expect_bytes: int) -> None:
        if not value:
            raise ValueError(f"{label} is required")
        v = value.strip()
        if not v.lower().startswith("0x"):
            raise ValueError(f"{label} must be a hex string starting with 0x")
        body = v[2:]
        expected_len = expect_bytes * 2
        if len(body) != expected_len:
            raise ValueError(
                f"{label} must be a {expect_bytes}-byte address (0x + {expected_len} hex chars, got {len(body)}"
            )
        try:
            int(body, 16)
        except ValueError:
            raise ValueError(f"{label} must contain only hex characters") from None

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
                    dotenv = dotenv_values(".env")
                    field_names = {name.lower() for name in cls.model_fields}
                    configured_env_keys = {
                        key.lower()
                        for key, value in {**dotenv, **dict(os.environ)}.items()
                        if value is not None and key.lower() in field_names
                    }
                    merged.update({
                        k: v for k, v in data.items()
                        if k in cls.model_fields and k.lower() not in configured_env_keys
                    })
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

