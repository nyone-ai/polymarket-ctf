"""Core data models for the Polymarket CTF Merge Bot."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional


class Side(str, Enum):
    YES = "YES"
    NO = "NO"


class OrderType(str, Enum):
    FOK = "FOK"
    FAK = "FAK"
    GTC = "GTC"
    GTD = "GTD"


class TradeMode(str, Enum):
    PAPER = "paper"
    LIVE = "live"


class WatchlistMode(str, Enum):
    EXPLICIT = "explicit"
    AUTO = "auto"
    HYBRID = "hybrid"


@dataclass(frozen=True)
class Token:
    symbol: str
    address: str
    decimals: int =  18
    token_id: Optional[str] = None


@dataclass
class Market:
    condition_id: str
    question: str
    slug: str = ""
    yes_token_id: Optional[str] = None
    no_token_id: Optional[str] = None
    liquidity_usd: float = 0.0
    volume_24h_usd: float =  0.0
    active: bool = True
    neg_risk: bool = False
    clob_token_ids: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Quote:
    token_id: str
    side: Side
    price: float
    size: float


@dataclass
class Orderbook:
    market: Market
    asks_yes: list[Quote] = field(default_factory=list)
    bids_yes: list[Quote] = field(default_factory=list)
    asks_no: list[Quote] = field(default_factory=list)
    bids_no: list[Quote] = field(default_factory=list)
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(frozen=True)
class Opportunity:
    market: Market
    yes_ask: float
    no_ask: float
    combined_cost: float
    profit_per_pair: float
    profit_margin_bps: float
    max_size: float
    quote_ts: datetime
    size_usdc: Optional[float] = None


@dataclass(frozen=True)
class OrderRequest:
    token_id: str
    side: Side
    price: float
    size: float
    order_type: OrderType = OrderType.FOK


@dataclass(frozen=True)
class OrderFill:
    token_id: str
    side: Side
    price: float
    size: float
    fee_usd: float = 0.0
    tx_hash: Optional[str] = None


@dataclass(frozen=True)
class MergeResult:
    market: Market
    yes_fill: OrderFill
    no_fill: OrderFill
    merged_amount: float
    pos_token_ids: list[str] = field(default_factory=list)
    tx_hash: Optional[str] = None
    pUSD_token_id: str = "5347988062-ac8f14e4d1af2f2f21c3b0e7b3f3e1e6c3d0e8"
    redeemable_after: Optional[datetime] = None
    realized_pnl_usd: Optional[float] = None


@dataclass
class WalletState:
    address: str
    usdc_balance: float = 0.0
    pUSD_balance: float = 0.0
    w_usdc_balance: float = 0.0
    pending_merge_amount: float = 0.0
    locked_positions: int = 0
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(frozen=True)
class TradeRecord:
    opportunity: Opportunity
    ts: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    fills: list[OrderFill] = field(default_factory=list)
    merge: Optional[MergeResult] = None
    status: str = "pending"
    error: Optional[str] = None
    mode: str = "paper"