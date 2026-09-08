"""Chain / protocol constants used across the bot."""
from __future__ import annotations

# Polygon mainnet
POLYGON_CHAIN_ID = 137
POLYGON_RPC_DEFAULT = "https://polygon-rpc.com"

# --- Tokens (Polygon Mainnet) ---
USDCE_ADDRESS = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"  # USDC.e bridged
USDC_ADDRESS = "0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359"  # Native USDC (Polygon)
PUSD_ADDRESS = "0xC011a7E12a19f7B1f670d46F03B03f3342E82DFB"  # pUSD proxy
WRAPPER_USDC_ADDRESS = PUSD_ADDRESS  # pUSD is the wrapper collateral token

# --- Core Polymarket Contracts (Polygon Mainnet) ---
CTF_EXCHANGE_ADDRESS = "0xE111180000d2663C0091e4f400237545B87B996B"  # CTF Exchange V2
CTF_CONDITION_TOKENS = "0x4D97DCd97eC945f40cF65F87097ACe5EA0476045"  # Legacy CTF (used by CttCollateralAdapter
NEG_RISK_ADAPTER_ADDRESS = "0xd91E80cF2E7be2e162c6513ceD06f1dD0dA35296"  # NegRisk Adapter (deprecated

# --- Collateral contracts ---
COLLATERAL_ONRAMP = "0x93070a847efEf7F70739046A929D47a521F5B8ee"  # USDC.e -> pUSD
COLLATERAL_OFFRAMP = "0x2957922Eb93258b93368531d39fAcCA3B4dC5854"  # pUSD -> USDC.e
CTF_COLLATERAL_ADAPTER = "0xAdA100Db00Ca00073811820692005400218FcE1f"  # CtfCollateralAdapter (merge/split
NEG_RISK_CTF_COLLATERAL_ADAPTER = "0xadA2005600Dec949baf300f4C6120000bDB6eAab"  # NegRiskCtfCollateralAdapter
NEG_RISK_EXCHANGE_ADDRESS = "0xe2222d279d744050d28e00520010520000310F59"  # NegRisk CTF Exchange V2

# --- Nonces / encoded zero ---
ZERO_BYTES32 = "0x" + "0" * 64
ZERO_ADDRESS = "0x" + "0" * 40

# CLOB order sides as sent by API (numeric)
SIDE_BUY = 0
SIDE_SELL = 1

# Price / size decimals
PRICE_SCALE = 2
SIZE_SCALE =  2
USDC_DECIMALS =  6