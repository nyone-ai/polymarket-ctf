"""CTF merge/redeem adapter (Polymarket CTF Exchange on Polygon)."""
from __future__ import annotations

import logging
from typing import Optional

from src.config import Settings
from src.utils.constants import CTF_CONDITION_TOKENS
from src.utils.number import to_wei, from_wei

logger = logging.getLogger(__name__)

# --- Official ABIs ---
# mergePositions(address collateralToken, bytes32 parentCollectionId, bytes32 conditionId,
#              uint256[] partition, uint256 amount) on CtfCollateralAdapter (V2.
CTF_MERGE_ABI = [
    {
        "inputs": [
            {"name": "collateralToken", "type": "address"},
            {"name": "parentCollectionId", "type": "bytes32"},
            {"name": "conditionId", "type": "bytes32"},
            {"name": "partition", "type": "uint256[]"},
            {"name": "amount", "type": "uint256"},
        ],
        "name": "mergePositions",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
]

# ConditionalTokens (ERC-1155) minimal ABI for approvals.
CTF_CONDITIONAL_TOKENS_ABI = [
    {
        "inputs": [
            {"name": "operator", "type": "address"},
            {"name": "approved", "type": "bool"},
        ],
        "name": "setApprovalForAll",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [
            {"name": "owner", "type": "address"},
            {"name": "operator", "type": "address"},
        ],
        "name": "isApprovedForAll",
        "outputs": [{"name": "", "type": "bool"}],
        "stateMutability": "view",
        "type": "function",
    },
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
            addr = self.settings.ctf_collateral_adapter_address
            if not addr:
                raise RuntimeError("ctf_collateral_adapter_address required for mergePositions; the CTF Exchange has no mergePositions")
            self._exchange = w3.eth.contract(address=addr, abi=CTF_MERGE_ABI)
        return self._exchange

    def merge(self, condition_id: str, amount: float, yes_token_id: str | None = None, no_token_id: str | None = None) -> str:
        """Merge YES + NO conditional tokens into pUSD on the CTF
        CollateralAdapter (V2 collateral layer).

        Signs and sends the mergePositions transaction locally.

        condition_id:the condition ID of the market
        amount: number of token pairs to merge (each side)
        yes_token_id: YES token ID (unused, part of the generic interface)
        no_token_id: NO token ID (unused, part of the generic interface)

        Returns transaction hash.
        """
        w3 = self._web3()
        from eth_account import Account

        if not self.settings.private_key:
            raise RuntimeError("private_key required for live merge")
        if not amount or amount <= 0:
            raise ValueError("amount must be > 0")

        acct = Account.from_key(self.settings.private_key.strip().removeprefix("0x"))
        adapter = self._get_exchange()
        amount_wei = to_wei(amount, 6)
        self._ensure_ctf_approval(w3, acct, adapter.address)
        # Preflight: a revert raises here; a void function returns [] on success.
        try:
            adapter.functions.mergePositions(
                "0x0000000000000000000000000000000000000000",
                "0x" + "0" * 64,
                condition_id,
                [1, 2],
                amount_wei,
            ).call({"from": acct.address})
        except Exception as exc:
            raise RuntimeError(f"CTF adapter mergePositions preflight reverted: {exc}") from exc
        tx = adapter.functions.mergePositions(
            "0x0000000000000000000000000000000000000000",  # collateralToken (ignored by adapter)
            "0x" + "0" * 64,  # parentCollectionId (ignored by adapter)
            condition_id,
            [1, 2],  # partition: YES|NO indexes
            amount_wei,
        ).build_transaction({
            "from": acct.address,
            "nonce": w3.eth.get_transaction_count(acct.address, "pending"),
            "chainId": self.settings.chain_id,
            "gas": 400000,
            "gasPrice": w3.eth.gas_price,
        })

        signed = acct.sign_transaction(tx)
        raw_tx = getattr(signed, "raw_transaction", None) or signed.rawTransaction
        tx_hash = w3.eth.send_raw_transaction(raw_tx)
        logger.info(
            "CTF merge submitted: condition=%s amount=%s tx=%s",
            condition_id, amount, tx_hash.hex(),
        )
        return tx_hash.hex()

    def _ensure_ctf_approval(self, w3, acct, adapter_addr: str):
        """Approve the CTF collateral adapter to spend this wallet's conditional
        tokens (ERC-1155) idempotently -- required before mergePositions unless
        a prior approval already exists.

        Performs a single gasless ``isApprovedForAll`` read; only sends the
        approval transaction when needed.

        ``merge()`` is sync (runs in an executor thread) so we can not use
        ``await`` here; the sign+send flow is intentionally the same as the
        merge transaction itself.

        Adapter merges use the conditionaltokens's ``safeTransferFrom``, which
        requires the adapter to be an approved operator for the caller.

        """
        ctf_tokens_addr = self.settings.ctf_condition_tokens_address or CTF_CONDITION_TOKENS
        ctf_tokens = w3.eth.contract(address=ctf_tokens_addr, abi=CTF_CONDITIONAL_TOKENS_ABI)
        if ctf_tokens is None:
            return  # defensive; signature mismatch should surface in the call
        try:
            approved = ctf_tokens.functions.isApprovedForAll(acct.address, adapter_addr).call()
        except Exception as exc:
            logger.warning("Could not read isApprovedForAll (%s); continuing without pre-check", exc)
            return
        if approved:
            return
        approve_tx = ctf_tokens.functions.setApprovalForAll(adapter_addr, True).build_transaction({
            "from": acct.address,
            "nonce": w3.eth.get_transaction_count(acct.address, "pending"),
            "chainId": self.settings.chain_id,
            "gas": 150000,
            "gasPrice": w3.eth.gas_price,
        })
        signed = acct.sign_transaction(approve_tx)
        raw_tx = getattr(signed, "raw_transaction", None) or signed.rawTransaction
        approve_hash = w3.eth.send_raw_transaction(raw_tx)
        logger.info("Approved CTF adapter %s on %s (tx: %s)", adapter_addr, ctf_tokens_addr, approve_hash.hex())

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
