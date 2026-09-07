"""Collateral adapter: wrap/unwrap USDC.e <-> pUSD via CollateralOnramp/Offramp."""
from __future__ import annotations

import logging
from typing import Optional

from src.config import Settings
from src.utils.number import to_wei, from_wei

logger = logging.getLogger(__name__)

# --- CollateralOnramp / CollateralOfframp ABIs (minimal) ---
# wrap(address _asset, address _to, uint256 _amount)
ONRAMP_WRAP_ABI = [
    {"inputs": [{"name": "_asset", "type": "address"}, {"name": "_to", "type": "address"}, {"name": "_amount", "type": "uint256"}], "name": "wrap", "outputs": [], "type": "function"},
]
# unwrap(address _asset, address _to, uint256 _amount)
OFFRAMP_UNWRAP_ABI = [
    {"inputs": [{"name": "_asset", "type": "address"}, {"name": "_to", "type": "address"}, {"name": "_amount", "type": "uint256"}], "name": "unwrap", "outputs": [], "type": "function"},
]


class Collateral:
    def __init__(self, settings: Settings, address: str | None = None):
        self.settings = settings
        self.address = address or settings.wrapper_usdc_address
        self._w3 = None
        self._onramp = None
        self._offramp = None

    def _web3(self):
        if self._w3 is None:
            from web3 import Web3
            url = self.settings.rpc_url
            self._w3 = Web3(Web3.HTTPProvider(url))
        return self._w3

    def _get_onramp(self):
        w3 = self._web3()
        if self._onramp is None:
            addr = self.settings.ctf_exchange_address  # onramp is same as CTF exchange proxy area, but we use known address
            # Actually CollateralOnramp address is separate
            onramp_addr = self.settings.usdce_address  # fallback; should use settings
            # Use the known Onramp address from config
            onramp_addr = getattr(self.settings, "usdce_address", "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174")  # placeholder; will be overridden
            # Better: read from settings if available
            if hasattr(self.settings, "collateral_onramp_address") and self.settings.collateral_onramp_address:
                onramp_addr = self.settings.collateral_onramp_address
            else:
                # Default to official Polygon mainnet address
                onramp_addr = "0x93070a847efEf7F70739046A929D47a521F5B8ee"
            self._onramp = w3.eth.contract(address=onramp_addr, abi=ONRAMP_WRAP_ABI)
        return self._onramp

    def _get_offramp(self):
        w3 = self._web3()
        if self._offramp is None:
            offramp_addr = "0x2957922Eb93258b93368531d39fAcCA3B4dC5854"  # official Offramp
            self._offramp = w3.eth.contract(address=offramp_addr, abi=OFFRAMP_UNWRAP_ABI)
        return self._offramp

    def wrap(self, amount_usdce: float, to_address: str | None = None) -> str:
        """
        Wrap USDC.e -> pUSD.
        amount_usdce: amount in USD base units (6 decimals).
        Returns transaction hash.
        """
        w3 = self._web3()
        amount_wei = to_wei(amount_usdce, 6)  # 6 decimals for USDC.e
        recipient = to_address or w3.eth.account.from_key(self.settings.private_key).address

        # Step 1: Approve Onramp to spend USDC.e
        onramp = self._get_onramp()
        usdc = w3.eth.contract(address=self.settings.usdce_address, abi=[
            {"name": "approve", "type": "function",
             "inputs": [{"name": "spender", "type": "address"}, {"name": "amount", "type": "uint256"}],
             "outputs": [{"name": "", "type": "bool"}]}
        ])
        approve_tx = usdc.functions.approve(onramp.address, amount_wei).transact({"from": recipient})
        approve_hash = w3.eth.wait_for_transaction_receipt(approve_tx)
        logger.info("Approved Onramp for %s USDC.e (approve tx: %s)", amount_usdce, approve_hash.transactionHash)

        # Step 2: Wrap USDC.e -> pUSD
        wrap_tx = onramp.functions.wrap(self.settings.usdce_address, recipient, amount_wei).transact({"from": recipient})
        wrap_hash = w3.eth.wait_for_transaction_receipt(wrap_tx)
        logger.info("Wrapped %s USDC.e -> pUSD (wrap tx: %s)", amount_usdce, wrap_hash.transactionHash)
        return wrap_hash.transactionHash

    def unwrap(self, amount_pusd: float, to_address: str | None = None) -> str:
        """
        Unwrap pUSD -> USDC.e.
        amount_pusd: amount in pUSD base units (6 decimals).
        Returns transaction hash.
        """
        w3 = self._web3()
        amount_wei = to_wei(amount_pusd, 6)  # 6 decimals for pUSD

        # Step 1: Approve Offramp to spend pUSD
        offramp = self._get_offramp()
        pusd = w3.eth.contract(address=self.settings.pusd_address, abi=[
            {"name": "approve", "type": "function",
             "inputs": [{"name": "spender", "type": "address"}, {"name": "amount", "type": "uint256"}],
             "outputs": [{"name": "", "type": "bool"}]}
        ])
        recipient = to_address or w3.eth.account.from_key(self.settings.private_key).address
        approve_tx = pusd.functions.approve(offramp.address, amount_wei).transact({"from": recipient})
        approve_hash = w3.eth.wait_for_transaction_receipt(approve_tx)
        logger.info("Approved Offramp for %s pUSD (approve tx: %s)", amount_pusd, approve_hash.transactionHash)

        # Step 2: Unwrap pUSD -> USDC.e
        unw_tx = offramp.functions.unwrap(self.settings.usdce_address, recipient, amount_wei).transact({"from": recipient})
        unw_hash = w3.eth.wait_for_transaction_receipt(unw_tx)
        logger.info("Unwrapped %s pUSD -> USDC.e (unw tx: %s)", amount_pusd, unw_hash.transactionHash)
        return unw_hash.transactionHash

    @property
    def pusd_address(self) -> str:
        return self.settings.pusd_address if hasattr(self.settings, "pusd_address") else "0xC011a7E12a19f7B1f670d46F03B03f3342E82DFB"

    @property
    def usdce_address(self) -> str:
        return self.settings.usdce_address if hasattr(self.settings, "usdce_address") else "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"