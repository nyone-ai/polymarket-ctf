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
        
        condition_id: the condition ID of the market
        amount: number of token pairs to merge (each side)
        yes_token_id: YES token ID (optional for legacy adapter mode)
        no_token_id: NO token ID (optional for legacy adapter mode)
        
        Returns transaction hash.
        """
        w3 = self._web3()
        exchange = self._get_exchange()
        
        # Convert condition_id to bytes32
        cond_bytes32 = self._to_bytes32(condition_id)
        
        # For mergePositions we need both token IDs for binary markets
        # If not provided, try to get them from settings or raise
        if not yes_token_id or not no_token_id:
            # Try to get from market discovery (legacy)
            logger.warning("yes_token_id or no_token_id not provided, trying to infer from config")
            # This should be handled by the caller with market info
            raise ValueError("yes_token_id and no_token_id required for merge")
        
        # Convert token IDs to bytes32
        yes_bytes32 = self._to_bytes32(yes_token_id)
        no_bytes32 = self._to_bytes32(no_token_id)
        
        # Convert amount to wei (18 decimals for pUSD tokens?)
        # Conditional tokens use 18 decimals for amounts
        amount_wei = to_wei(amount, 18)
        
        # Call mergePositions
        tx_hash = exchange.functions.mergePositions(cond_bytes32, yes_bytes32, no_bytes32, amount_wei).transact({
            "from": self.settings.wallet_address
        })
        
        logger.info("CTF merge submitted: condition=%s, amount=%s, tx=%s", condition_id, amount, tx_hash.hex())
        return tx_hash.hex()

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
        pusd = w3.eth.contract(address=self.settings.wrapper_usdc_address, abi=[
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
