"""Tests for V2 live-path fixes (#1-#3) and SQLite persistence (#4-#5."""
import asyncio
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.config import Settings
from src.models import (
    Market,
    MergeResult,
    Opportunity,
    OrderFill,
    Side,
    TradeRecord,
)
from src.persistence import TradeStore
from src.wallet import EoWallet
from src.ctf import CtfAdapter
from src.utils.constants import CTF_COLLATERAL_ADAPTER


@pytest.fixture
def paper_settings():
    return Settings(mode="paper")


@pytest.fixture
def market():
    return Market(
        condition_id="0x" + "a" * 64,
        slug="test-market",
        question="Test",
        yes_token_id="1234-yes",
        no_token_id="1234-no",
        neg_risk=False,
    )


@pytest.fixture
def opportunity(market):
    return Opportunity(
        market=market,
        yes_ask=0.45,
        no_ask=0.50,
        combined_cost=0.95,
        profit_per_pair=0.05,
        profit_margin_bps=526,
        max_size=100.0,
        quote_ts=datetime.now(timezone.utc),
    )


def test_live_credential_validation_rejects_short_key():
    with pytest.raises(ValueError, match="PRIVATE_KEY"):
        Settings(
            mode="live",
            private_key="abc",
            wallet_address="0x" + "2" * 40,
            rpc_url="https://rpc",
            clob_api_key="k",
        )


def test_live_credential_validation_rejects_mismatched_wallet():
    with pytest.raises(ValueError, match="does not match"):
        Settings(
            mode="live",
            private_key="0x" + "1" * 64,
            wallet_address="0x" + "2" * 40,
            rpc_url="https://rpc",
            clob_api_key="k",
        )


def test_live_credential_validation_accepts_raw_key():
    import eth_account

    acct = eth_account.Account.create()
    settings = Settings(
        mode="live",
        private_key=acct.key.hex(),
        wallet_address=acct.address,
        rpc_url="https://rpc",
        clob_api_key="k",
    )
    assert settings.wallet_address == acct.address


def test_wallet_normalizes_key_prefix():
    wallet = EoWallet(Settings(private_key="0x" + "11" * 32, wallet_address="0x" + "22" * 40))
    assert wallet._normalize_key("0x" + "aa" * 32) == "aa" * 32
    assert wallet._normalize_key("bb" * 32) == "bb" * 32


def test_wallet_parse_fills_extracts_tx_hash():
    wallet = EoWallet(Settings())
    fills = wallet.parse_fills(
        [
            {
                "token_id": "tok1",
                "price": 0.5,
                "size": 10.0,
                "transactionsHashes": ["0xtx1"],
                "orderID": "order-1",
                "status": "matched",
                "tradeIDs": ["t1"],
            }
        ]
    )
    assert fills[0]["tx_hash"] == "0xtx1"
    assert fills[0]["order_id"] == "order-1"
    assert fills[0]["trade_ids"] == ["t1"]


def test_ctf_constants_point_to_v2_adapter():
    assert CTF_COLLATERAL_ADAPTER.startswith("0x")
    assert len(CTF_COLLATERAL_ADAPTER) == 42


async def test_trade_store_record_and_pnl_roundtrip(tmp_path, opportunity):
    store = TradeStore(tmp_path / "bot.db")
    await store.init()
    fill = OrderFill(token_id="t", side=Side.YES, price=0.45, size=10.0, fee_usd=0.1,
    )
    merge = MergeResult(
        market=opportunity.market,
        yes_fill=fill,
        no_fill=fill,
        merged_amount=10.0,
    )
    record = TradeRecord(
        opportunity=opportunity,
        fills=[fill, fill],
        merge=merge,
        status="settled",
        mode="paper",
    )
    await store.record_trade(record)
    recent = await store.load_recent(limit=5)
    pnl = await store.compute_daily_pnl(days=3)
    await store.close()

    assert len(recent) == 1
    assert recent[0]["status"] == "settled"
    assert recent[0]["market_slug"] == "test-market"
    assert len(pnl) == 1
    assert pnl[0]["trades_count"] == 1
    assert pnl[0]["pnl_est"] == pytest.approx(0.3)  # size 10*(1-0.95)=0.5 - fees 0.2
def test_wallet_parse_fills_v2_order_response_shape():
    wallet = EoWallet(Settings())
    fills = wallet.parse_fills(
        [
            {
                "orderID": "order-7",
                "status": "matched",
                "transactionsHashes": ["0xtxabc"],
                "tokenID": "tok-v2",
                "assetID": "tok-v2",
                "price": "0.5123",
                "originalSize": "100",
                "sizeMatched": "50",
                "makingAmount": "25615000",
                "takingAmount": "50000000",
                "fee": "0.123456",
                "tradeIDs": ["t9"],
            }
        ]
    )
    assert len(fills) ==  1
    fill = fills[0]
    assert fill["token_id"] == "tok-v2"
    assert fill["size"] == pytest.approx(50.0)
    assert fill["price"] == pytest.approx(0.5123)
    assert fill["tx_hash"] == "0xtxabc"
    assert fill["order_id"] == "order-7"
    assert fill["trade_ids"] == ["t9"]


def test_wallet_parse_fills_buy_uses_taker_amount_as_size_when_no_direct_size():
    wallet = EoWallet(Settings())
    fills = wallet.parse_fills(
        [
            {
                "status": "matched",
                "tokenID": "tok-v2",
                "price": "0.5",
                "makingAmount": "5000000",
                "takingAmount": "10000000",
                "transactionsHashes": ["0xtx"],
            }
        ]
    )
    assert len(fills) ==  1
    assert fills[0]["size"] == pytest.approx(10.0)
    assert fills[0]["price"] == pytest.approx(0.5)


def test_wallet_parse_fills_derives_price_from_amounts():
    wallet = EoWallet(Settings())
    fills = wallet.parse_fills(
        [
            {
                "status": "matched",
                "tokenID": "tok-v2",
                "makingAmount": "5000000",
                "takingAmount": "10000000",
            }
        ]
    )
    assert len(fills) ==  1
    assert fills[0]["price"] == pytest.approx(0.5)


def test_wallet_zero_fill_canceled_response_produces_no_fill():
    wallet = EoWallet(Settings())
    fills = wallet.parse_fills(
        [{"status": "canceled", "tokenID": "tok-v2", "originalSize": "100", "sizeMatched": "0"}]
    )
    assert fills == []


def test_wallet_canceled_fok_without_size_matched_produces_no_fill():
    wallet = EoWallet(Settings())
    fills = wallet.parse_fills(
        [{"status": "canceled", "tokenID": "tok-v2", "originalSize": "100"}]
    )
    assert fills == []
