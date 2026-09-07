"""Chain / protocol constants used across the bot."""
from __future__ import annotations

# Polygon mainnet
POLYGON_CHAIN_ID = 137
POLYGON_RPC_DEFAULT = "https://polygon-rpc.com"

# --- Tokens ---
USDC_ADDRESS = "0x3c499c542cEF5E3811e1192ee70C3c8c7B9E8B2"  # bridged USDC.e on Polygon
USDCe_ADDRESS = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa8414"
PUSD_ADDRESS = "0x9Ba6E67E3251Eb9fFAc384069B2e0bC24A4f4D9"  # pUSD (CTF yield token; placeholder)
WRAPPER_USDC_ADDRESS = "0x0CE8C5F1C4B1b3B4A1F3d1C1a1B1c1D1e1F1a1B1"  # placeholder WrapperUSDC

# WrapperUSDC needs actual address; auto-detected from CTF factory when possible.
# pUSD address too; these are placeholders to keep imports valid.

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