from types import SimpleNamespace

import pytest

from src.models import Market, Side
from src.config import Settings
from src.executor import Executor
from src.wallet import EoWallet
from src.notifier import Notifier
from src.risk import find_opportunity
from src.risk import RiskManager
from src.scanner.clob import ClobClient


def test_clob_client_combines_yes_and_no_books(monkeypatch):
    market = Market("condition", "question", yes_token_id="yes", no_token_id="no")
    client = ClobClient()

    async def get_orderbook(token_id, depth=20):
        return client._parse_book(token_id, {"asks": [{"price": "0.40", "size": "12"}]})

    monkeypatch.setattr(client, "get_orderbook", get_orderbook)

    async def check():
        book = await client.get_market_orderbook(market)
        assert book.asks_yes[0].token_id == "yes"
        assert book.asks_no[0].token_id == "no"
        assert book.asks_yes[0].side is Side.YES

    import asyncio
    asyncio.run(check())


def test_minimum_profit_is_evaluated_for_trade_size():
    market = Market("condition", "question", yes_token_id="yes", no_token_id="no")
    client = ClobClient()
    book = client._parse_book("yes", {"asks": [{"price": "0.49", "size": "200"}]})
    book.market = market
    no_book = client._parse_book("no", {"asks": [{"price": "0.49", "size": "200"}]})
    book.asks_no = no_book.asks_yes
    settings = SimpleNamespace(
        threshold=0.995,
        min_profit_usd=5.0,
        min_profit_margin_bps=10.0,
        max_size_per_trade=500.0,
    )

    opportunity = find_opportunity(market, book, settings)

    assert opportunity is not None
    assert opportunity.max_size * opportunity.profit_per_pair == pytest.approx(4.0)


@pytest.mark.asyncio
async def test_notifier_uses_instance_settings():
    settings = SimpleNamespace(telegram_bot_token="token", telegram_chat_id="chat")
    notifier = Notifier(settings)
    calls = []

    class Client:
        async def post(self, url, json):
            calls.append((url, json))
            return SimpleNamespace(raise_for_status=lambda: None)

    notifier._client = Client()
    await notifier.send("alert")

    assert calls == [("https://api.telegram.org/bottoken/sendMessage", {"chat_id": "chat", "text": "alert"})]


def test_environment_values_override_yaml(tmp_path, monkeypatch):
    path = tmp_path / "settings.yaml"
    path.write_text("mode: paper\norder_type: FOK\n", encoding="utf-8")
    monkeypatch.setenv("MODE", "live")
    monkeypatch.setenv("ORDER_TYPE", "ioc")
    monkeypatch.setenv("PRIVATE_KEY", "5b3c49b8fd3b9bf1d771ae61f6b14cfc1adcf309c01cba03488abf1ae89f1591")
    monkeypatch.setenv("WALLET_ADDRESS", "0x4113a96bca721d9FEd8448360D72878A9cCcd5bC")
    monkeypatch.setenv("RPC_URL", "https://rpc.example")
    monkeypatch.setenv("CLOB_API_KEY", "test-key")

    settings = Settings.from_yaml(path)

    assert settings.mode == "live"
    assert settings.order_type == "IOC"


@pytest.mark.asyncio
async def test_paper_mode_never_calls_live_executor(monkeypatch):
    settings = Settings(mode="paper")
    executor = Executor(settings)
    opportunity = find_opportunity(
        Market("condition", "question", yes_token_id="yes", no_token_id="no"),
        _book_with_asks(),
        settings,
    )
    assert opportunity is not None

    async def fail_live(*args):
        raise AssertionError("paper execution must not enter the live path")

    monkeypatch.setattr(executor, "_execute_live", fail_live)
    result = await executor.execute(opportunity, 1)

    assert result.status == "settled"


def _book_with_asks():
    client = ClobClient()
    book = client._parse_book("yes", {"asks": [{"price": "0.49", "size": "200"}]})
    book.asks_no = client._parse_book("no", {"asks": [{"price": "0.49", "size": "200"}]}).asks_yes
    return book


@pytest.mark.asyncio
async def test_placeholder_clob_rest_path_fails_closed():
    wallet = EoWallet(Settings(private_key="0x" + "1" * 64, wallet_address="0x" + "2" * 40))

    with pytest.raises(NotImplementedError, match="refusing to fabricate"):
        await wallet.submit_and_wait({"token_id": "token"})


def test_daily_loss_limit_halts_subsequent_trades():
    risk = RiskManager(Settings(max_daily_loss=10))

    assert risk.check_daily_loss(-10) is False
    assert risk.can_trade() is False
