"""CTF merge/redeem adapter (Polymarket CTF Exchange on Polygon)."""
from __future__ import annotations

import logging
from typing import Optional

from src.config import Settings
from src.utils.number import to_wei, from_wei

logger = logging.getLogger(__name__)

# --- Official ABIs ---
# mergePositions(bytes32 conditionId, bytes32 yesToken, bytes32 noToken, uint256 amount)
CTF_MERGE_ABI = [
    {"inputs": [
        {"name": "conditionId", "type": "bytes32"},
        {"name": "yesToken", "type": "bytes32"},
        {"name": "noToken", "type": "bytes32"},
        {"name": "amount", "type": "uint256"}
    ], "name": "mergePositions", "outputs": [], "type": "function"},
    {"inputs": [
        {"name": "conditionId", "type": "bytes32"},
        {"name": "yesToken", "type": "bytes32"},
        {"name": "amount", "type": "uint256"}
    ], "name": "mergePositions", "outputs": [], "type": "function"},  # Simplified for standard binary
]


class CtfAdapter:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._w3 = None
        self._exchange = None

    def _web3(self):
        if self._w3 is None:
            from web3 import Web3
            url = self.settings.rpc_url
            self._w3 = Web3(Web3.HTTPProvider(url))
        return self._w3

    def _get_exchange(self):
        w3 = self._web3()
        if self._exchange is None:
            addr = self.settings.ctf_exchange_address
            if not addr:
                raise RuntimeError("ctf_exchange_address not configured")
            self._exchange = w3.eth.contract(address=addr, abi=CTF_MERGE_ABI)
        return self._exchange

    def merge(self, condition_id: str, amount: float, yes_token_id: str | None = None, no_token_id: str | None = None) -> str:
        """
        Merge YES + NO conditional tokens into pUSD.
        Locally signs the transaction and sends via send_raw_transaction.
        
        condition_id: the condition ID of the market
        amount: number of token pairs to merge (each side)
        yes_token_id: YES token ID
        no_token_id: NO token ID
        
        Returns transaction hash.
        """
        raise NotImplementedError(
            "Live CTF merge is disabled until this adapter uses the verified Conditional Tokens ABI and contract address"
        )

    def redeem(self, condition_id: str, amount: float, pUSD_token_id: str | None = None) -> str:
        """
        Redeem pUSD back to USDC.e (used after market resolution).
        
        condition_id: the condition ID of the market (for reference)
        amount: amount of pUSD to redeem
        pUSD_token_id: pUSD token ID (optional)
        
        Returns transaction hash.
        """
        w3 = self._web3()
        
        # Note: CTF framework may have a separate redeem function or you might need to unwrap pUSD
        # This is a placeholder for implementing redeem if needed
        logger.warning("CTF redeem not fully implemented yet; consider unwrap pUSD via CollateralOfframp")
        
        # For now, raise NotImplementedError as this may not be needed for the main arbitrage strategy
        raise NotImplementedError("CTF redeem not yet implemented - use CollateralOfframp for pUSD to USDC.e unwrap")

    @staticmethod
    def _to_bytes32(value: str) -> str:
        """Convert a hex string to bytes32 format."""
        # Remove 0x prefix if present
        value = value.lower().replace("0x", "")
        
        # Pad with zeros to 64 characters (32 bytes)
        if len(value) > 64:
            raise ValueError(f"Value too long for bytes32: {value}")
        
        padded = value.zfill(64)
        return "0x" + padded

    def get_pUSD_balance(self, wallet_address: str | None = None) -> float:
        """
        Get pUSD balance for the wallet.
        
        Returns balance in pUSD units (6 decimals).
        """
        w3 = self._web3()
        addr = wallet_address or self.settings.wallet_address
        if not addr:
            raise ValueError("wallet_address required to check balance")
        
        # pUSD token contract
        if not self.settings.pusd_address:
            raise RuntimeError("pusd_address not configured")
        pusd = w3.eth.contract(address=self.settings.pusd_address, abi=[
            {"name": "balanceOf", "type": "function",
             "inputs": [{"name": "owner", "type": "address"}],
             "outputs": [{"name": "", "type": "uint256"}]}
        ])
        
        balance_wei = pusd.functions.balanceOf(addr).call()
        return from_wei(balance_wei, 6)  # pUSD has 6 decimals

    def get_USDC_balance(self, wallet_address: str | None = None) -> float:
        """
        Get USDC.e balance for the wallet.
        
        Returns balance in USDC.e units (6 decimals).
        """
        w3 = self._web3()
        addr = wallet_address or self.settings.wallet_address
        if not addr:
            raise ValueError("wallet_address required to check balance")
        
        # USDC.e token contract
        usdc = w3.eth.contract(address=self.settings.usdce_address, abi=[
            {"name": "balanceOf", "type": "function",
             "inputs": [{"name": "owner", "type": "address"}],
             "outputs": [{"name": "", "type": "uint256"}]}
        ])
        
        balance_wei = usdc.functions.balanceOf(addr).call()
        return from_wei(balance_wei, 6)  # USDC.e has 6 decimals
