# Polymarket CTF Merge Arbitrage Bot

Bot arbitrage **Polymarket CTF Merge** berbasis Python 3.11+ (asyncio).

## Strategi

Saat harga gabungan `YES_ask + NO_ask` di bawah ambang (default `0.995`),
bot membeli **YES dan NO secara bersamaan** di CLOB, lalu **merge** pasangan
token menjadi **pUSD** lewat Conditional Tokens Framework (CTF).

Profit per pasang:

```
profit = 1.00 - total_cost
total_cost = YES_ask + NO_ask + fee + gas
```

## Fitur

- **Paper trading dan live trading**
  - Paper = simulasi penuh, tanpa private key.
  - Live = eksekusi nyata di Polymarket CLOB + CTF merge.
  - Guard preflight otomatis menolak jika `private_key`, `wallet_address`, atau `clob_api_key`
    belum diisi saat mode `live`.
- **Watchlist mode** `explicit` | `auto` | `hybrid`
  - `explicit`: pakai daftar manual JSON atau `watchlist_condition_ids`.
  - `auto`: filter hasil discovery CLOB berdasarkan likuiditas, volume,
    status aktif, dan binary-only.
  - `hybrid`: gabungan daftar explicit plus tambahan auto.
- **Risk management**: `min_profit_usd`, `max_size_per_trade`, `max_daily_loss`,
  cooldown antar trade, rate-limit per menit, reserve gas pUSD.
- **Notifikasi Telegram** opsional, rate-limited.
- **State persist**: async SQLite untuk riwayat trade dan daily PnL.
- **Logging**: terstruktur ke file di `logs/`.

## Arsitektur

```
main.py                   entrypoint loop
                          resolve watchlist, orderbook, opportunity, execute
src/config.py             Settings pydantic-settings dari env + YAML
src/models.py             Market, Orderbook, Quote, Side, OrderType, TradeMode
src/scanner/clob.py      client publik CLOB: markets, orderbooks
src/scanner/watchlist.py load explicit, filter auto, merge hybrid
src/risk/                pencari opportunity dan RiskManager
src/executor/            eksekusi paper/live: preflight, CLOB order, CTF merge
src/collateral/          wrap/unwrap USDC.e <-> pUSD via CollateralOnramp/Offramp
src/ctf/                 adaptor CTF merge (mergePositions)
src/wallet/              EOA wallet with EIP-712 signing for CLOB orders
src/notifier.py          pengirim Telegram
src/utils/               constants, number, retry
```

## Requirements

- Python 3.11+.
- Akses jaringan ke Polymarket CLOB, dan RPC Polygon untuk live.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
pip install -r requirements.txt   # alternatif
```

## Instalasi

```bash
cp .env.example .env
cp config/settings.example.yaml config/settings.yaml
```

## Konfigurasi

Dua lapis: environment lewat `.env`, dan YAML lewat `config/settings.yaml`.
Nilai environment menang atas YAML.

Untuk live mode, isi di `.env`:

```dotenv
MODE=live
PRIVATE_KEY=0x...
WALLET_ADDRESS=0x...
CLOB_API_KEY=...
CLOB_API_SECRET=...
CLOB_API_PASSPHRASE=...
RPC_URL=https://polygon-rpc.com
```

Credential CLOB didapat dari flow `derive_api_key` di Polymarket.
Wallet EOA harus sudah **deposit-funding dan proxy/deposit-authorized**
sebelum live trading.

## Parameter utama

| Parameter | Default | Arti |
|---|---|---|
| `mode` | `paper` | paper atau live |
| `threshold` | `0.995` | ambang YES_ask + NO_ask |
| `min_profit_usd` | `1.0` | profit minimum per pasang, USD |
| `max_size_per_trade` | `500` | ukuran maks per trade, jumlah pasang |
| `max_daily_loss` | `100` | batas rugi harian, USD |
| `cooldown_seconds` | `5` | jeda antar trade |
| `max_trades_per_minute` | `10` | rate limit |
| `order_type` | `FOK` | FOK atau FAK |
| `watchlist_mode` | `explicit` | explicit, auto, hybrid |

Field lain yang bisa di-set: `min_profit_margin_bps`, `reserve_gas_usd`,
`poll_interval`, `excess_mode`, `merge_mode`, `auto_wrap_usdce`,
`tx_timeout_seconds`, `chain_id`, `clob_host`, `clob_ws_url`,
`ctf_exchange_address`, `ctf_collateral_adapter_address`, `ctf_condition_tokens`,
`neg_risk_exchange_address`, `neg_risk_adapter_address`, `wrapper_usdc_address`,
`usdce_address`, `pusd_address`, `collateral_onramp_address`, `collateral_offramp_address`,
`fee_rate_bps_override`, `matic_usd_price`, `log_level`.

## Kontrak Polygon Mainnet (Official)

| Kontrak | Alamat |
|---|---|
| CTF Exchange V2 | `0xE111180000d2663C0091e4f400237545B87B996B` |
| CtfCollateralAdapter (merge/split V2) | `0xAdA100Db00Ca00073811820692005400218FcE1f` |
| NegRiskCtfCollateralAdapter | `0xadA2005600Dec949baf300f4C6120000bDB6eAab` |
| NegRisk CTF Exchange V2 | `0xe2222d279d744050d28e00520010520000310F59` |
| Conditional Tokens (CTF, legacy) | `0x4D97DCd97eC945f40cF65F87097ACe5EA0476045` |
| pUSD (CollateralToken) | `0xC011a7E12a19f7B1f670d46F03B03f3342E82DFB` |
| USDC.e | `0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174` |
| CollateralOnramp | `0x93070a847efEf7F70739046A929D47a521F5B8ee` |
| CollateralOfframp | `0x2957922Eb93258b93368531d39fAcCA3B4dC5854` |
| NegRisk Adapter | `0xd91E80cF2E7be2e162c6513ceD06f1dD0dA35296` |

## Watchlist

### Mode explicit

Isi daftar di `config/markets.watchlist.json` dan/atau pakai list
condition ID di YAML/env:

```yaml
watchlist_mode: explicit
watchlist_condition_ids:
  - "0x1234..."
auto_discover: true
```

Jika daftar kosong dan `auto_discover: true`, bot fallback ke discovery.

### Mode auto

```yaml
watchlist_mode: auto
auto_discover_filters:
  neg_risk: false
  min_liquidity: 5000
  min_volume_24h: 1000
  active_only: true
```

Filter: binary standard saja, likuiditas minimum 5000 USDC,
volume 24h minimum 1000, dan market aktif.

### Mode hybrid

Gabungan explicit dan auto: semua daftar manual plus tambahan
market dari discovery yang belum ada di daftar manual.

### Format watchlist JSON

```json
{
  "markets": [
    {
      "condition_id": "0x...",
      "question": "Will X happen?",
      "yes_token_id": "",
      "no_token_id": "",
      "clob_token_ids": []
    }
  ]
}
```

`yes_token_id` dan `no_token_id` boleh dikosongkan; saat runtime akan
di-enrichment dari hasil discovery jika `condition_id` cocok.

## Menjalankan

```bash
python main.py                # mode dari settings/env, default paper
python main.py --verbose      # log debug
python main.py --config config/settings.yaml
```

Mode dikontrol lewat environment/YAML (`MODE=paper` atau `MODE=live`).

## Uji Paper Trading

Dengan `.env` kosong, mode default `paper`:

1. Bot resolve watchlist, fallback auto jika daftar kosong.
2. Ambil orderbook tiap market.
3. Cari opportunity di mana `YES_ask + NO_ask < threshold`.
4. Eksekusi **paper**, tanpa order nyata, settlement disimulasikan.

Semua keputusan, sizing, dan PnL tercatat di state SQLite.

## Live Execution Flow

> **Status keamanan:** live execution saat ini dinonaktifkan secara fail-closed.
> Adapter CLOB dan CTF belum memiliki integrasi signing/ABI yang diverifikasi
> end-to-end, sehingga bot menolak mengirim order atau transaksi nyata daripada
> membuat fill atau signature palsu.

1. Place YES and NO orders via CLOB (FOK or FAK).
2. Wait for both orders to fill.
3. Execute CTF `mergePositions` to convert YES+NO -> pUSD.
4. Handle partial fills and excess tokens based on `excess_mode`.
5. Gas estimation and timeout via `tx_timeout_seconds`.

## Checklist Go-Live

1. Copy `.env.example` ke `.env`, isi credential lengkap.
2. Pastikan wallet EOA sudah deposit dan authorized untuk token USDC.e
   serta kondisi yang ditradingkan.
3. Generate API key CLOB lewat flow `derive_api_key`.
4. Set `MODE=live` dan `RPC_URL` privat, misal Alchemy atau Infura.
5. Mulai dengan `max_size_per_trade` kecil dan `threshold` konservatif.
6. Pantau log dan Telegram, adjust risk sesuai keadaan pasar.

## Notifikasi Telegram

```yaml
telegram:
  bot_token: "123456:ABC-xxx"
  chat_id: "-1001234567890"
  rate_limit_per_min: 20
```

Bisa juga lewat env: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`.

## Roadmap

- Test suite pytest: config, risk, paper executor.
- Test offline notifier dengan mock HTTP.
- Live dry-run terbatas: satu trade, FOK kecil.
- Wrap/unwrap otomatis via Collateral, opsional.

## Disclaimer

Bot disediakan as-is tanpa garansi. Perdagangan di Polymarket mengandung
risiko: slippage, kegagalan order, gas spike, dan bug kontrak.
Mulailah dari paper mode dan gunakan ukuran kecil sebelum live penuh.
Selalu audit ulang parameter risk Anda sendiri.
