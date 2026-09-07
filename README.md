# Polymarket CTF Merge Arbitrage Bot

Bot arbitrage **Polymarket CTF Merge** berbasis Python 3.11+ (asyncio).

## Strategi

Saat harga gabungan `YES_ask + NO_ask` di bawah ambang (default `0.995`),
bot membeli **YES dan NO secara bersamaan** di CLOB, lalu **merge** pasangan
token menjadi **pUSD** lewat Conditional Tokens Framework(CTF).

Profit per pasang:

```
profit = 1.00 - total_cost
total_cost = YES_ask + NO_ask + fee + gas
```

## Fitur

- **Paper trading dan live trading**
  - Paper = simulasi penuh, tanpa private key.
  - Live = eksekusi nyata di Polymarket CLOB + CTF merge.
 Guard preflight
    otomatis menolak jika `private_key`, `wallet_address`, atau `clob_api_key`
    belum diisi saat mode `live`.
- **Watchlist mode** `explicit` | `auto` | `hybrid`
  - `explicit`: pakai daftar manual.JSON atau `watchlist_condition_ids`.
  - `auto`: filter hasil discovery CLOB berdasarkan likuiditas, volume,
    status aktif, dan binary-only.

  - `hybrid`: gabungan daftar explicit plus tambahan auto.

- **Risk management**: `min_profit_usd`, `max_size_per_trade`, `max_daily_loss`,
  cooldown antar trade, rate-limit per menit, reserve gas pUSD.

- **Notifikasi Telegram** opsional, rate-limited gerak 20/min.

- **State persist**: async SQLite untuk riwayat trade dan daily PnL.


- **Logging**: terstruktur ke file di `logs/`.

## Arsitektur

```
main.py                   entrypoint loop
                          resolve watchlist, orderbook, opportunity, execute
src/config.py             Settings pydantic-settings dari env + YAML
src/models.py             Market, Orderbook, Quote,, Side
src/scanner/clob.py      client publik CLOB: markets, orderbooks
src/scanner/watchlist.py load explicit, filter auto,, merge hybrid
src/risk/                pencari opportunity dan RiskManager
src/executor/           eksekusi paper/live: preflight,, CLOB order,, CTF merge
src/collateral/         wrap/unwrap USDCe dengan pUSD
src/ctf/                adaptor CTF merge
src/flashloan/          interface Morpho flashloan, opsional
src/notifier.py          pengirim Telegram
src/utils/              constants,, number,, retry
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
| `max_daily_loss` | `100` | batas rugi harian,, USD |
| `cooldown_seconds` | `5` | jeda antar trade |
| `max_trades_per_minute` | `10` | rate limit |
| `order_type` | `FOK` | FOK atau IOC |
| `watchlist_mode` | `explicit` | explicit, auto,, hybrid |

Field lain yang bisa di-set: `min_profit_margin_bps`, `reserve_gas_usd`,
`poll_interval`, `excess_mode`, `merge_mode`, `auto_wrap_usdce`,
`tx_timeout_seconds`, `chain_id`, `clob_host`, `clob_ws_url`,
`ctf_exchange_address`, `neg_risk_adapter_address`, `wrapper_usdc_address`,
`fee_rate_bps_override`, `matic_usd_price`, `log_level`.

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
volume 24h minimum 1000, dan market aktif.auto

### Mode hybrid

Gabungan explicit dan auto: semua daftar manual plus tambahan
market dari discovery yang belum ada di daftar manual.auto

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
di-enrichment dari hasil discovery jika `condition_id` cocok.auto

## Menjalankan

```bash
python main.py                # mode dari settings/env, default paper
python main.py --verbose      # log debug
python main.py --config config/settings.yaml
```

Mode dikontrol lewat environment/YAML (`MODE=paper` atau `MODE=live`).

## Uji Paper Trading

Dengan `.env` kosong, mode default `paper`:

1. Bot resolve watchlist, fallback auto jika daftar kosong.auto
2. Ambil orderbook tiap market.auto
3. Cari opportunity di mana `YES_ask + NO_ask < threshold`.auto
4. Eksekusi **paper**, tanpa order nyata, settlement disimulasikan.auto

Semua keputusan, sizing, dan PnL tercatat di state SQLite.



## Checklist Go-Live

1. Copy `.env.example` ke `.env`, isi credential lengkap.auto
2. Pastikan wallet EOA sudah deposit dan authorized untuk token USDCe
   serta kondisi yang ditradingkan.auto
3. Generate API key CLOB lewat flow `derive_api_key`.auto
4. Set `MODE=live` dan `RPC_URL` privat, misal Alchemy atau Infura.auto
5. Mulai dengan `max_size_per_trade` kecil dan `threshold` konservatif.auto
6. Pantau log dan Telegram, adjust risk sesuai keadaan pasar.auto

## Notifikasi Telegram

```yaml
telegram:
  bot_token: "123456:ABC-xxx"
  chat_id: "-1001234567890"
  rate_limit_per_min: 20
```

Bisa juga lewat env: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`.auto

## Roadmap

- Test suite pytest: config,, risk,, paper executor.auto
- Test offline notifier dengan mock HTTP.auto
- Live dry-run terbatas: satu trade, FOK kecil.auto
- Wrap/unwrap otomatis via Collateral, opsional.auto
- Flashloan Morpho sebagai opsi scaling modal, opsional.auto

## Disclaimer

Bot disediakan as-is tanpa garansi. Perdagangan di Polymarket mengandung
risiko: slippage, kegagalan order, gas spike,, dan bug kontrak.auto
Mulailah dari paper mode dan gunakan ukuran kecil sebelum live penuh.auto
Selalu audit ulang parameter risk Anda sendiri.auto