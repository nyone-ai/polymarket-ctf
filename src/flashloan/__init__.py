"""Morpho Blue flash-loan module (Polygon mainnet.

Morpho Blue exposes native flash loans through the canonical singleton.
The raw interface used here is::

    function flashLoan(address token, uint256 assets, bytes calldata data) external;

``flashFee`` is zero on Morpho Blue, soothe loan must be returned in full
(principal is pulled back by the singleton before callback returns).

Because Morpho only calls back approved flash-loan receivers, a dedicated
``morpho_flashloan_caller`` contract must be deployed(see solidity/samples)
that installs itself as an authorized receiver and implements
``executeFlashLoan``(``onMorphoFlashLoan`` callback that performs the arb
and repays by approving the Morpho singleton.


This module is read-mostly by design: sending a flash loan requires an
already-authorized caller contractand a live bot key.

"""

from __future__ import annotations

import logging
from typing import Optional

from src.config import Settings
from src.utils.constants import PUSD_ADDRESS
from src.utils.number import from_wei, to_wei

logger = logging.getLogger(__name__)


# --- Verified Morpho Blue singleton(MORPHO) on Polygon mainnet ---
# code-length checked on-chain: 2026-09-08.. This is the correct address for chain 137.
# NOTE: 0xBBBBBbbBBb9cC55e2eE6b2A352c4Cd4d54 has NO code on Polygon --that
# address documents the protocol but was deployed as an ERC-1967 proxy on
# other chains only.. We use the concrete singleton verified on Polygon instead..
MORPHO_BLUE_POLYGON = "0x1bF0c2541F820E775182832f06c0B7Fc27A25f67"

# Minimal ABIs (full interface lives in solidity/lib interfaces)
FLASH_LOAN_ABI = [
    {
        "inputs": [
            {"name": "token", "type": "address"},
            {"name": "assets", "type": "uint256"},
            {"name": "data", "type": "bytes"},
        ],
        "name": "flashLoan",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [{"name": "token", "type": "address"}],
        "name": "maxFlashLoan",
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
]

# Caller contract interface for the bot's own flash-loan receiver..
CALLER_ABI = [
    {
        "inputs": [
            {"name": "token", "type": "address"},
            {"name": "assets", "type": "uint256"},
            {"name": "data", "type": "bytes"},
        ],
        "name": "executeFlashLoan",
        "outputs": [{"name": "", "type": "bool"}],
        "stateMutability": "nonpayable",
        "type": "function",
    },
]


class FlashLoanError(RuntimeError):
    """Raised when a flash-loan cannot be configured or executed."""


class MorphoFlashLoan:
    """Read + execute wrappers around the Morpho Blue singleton on Polygon."""

    def __init__(self, settings: Settings):
        if not settings.flashloan_enabled:
            raise FlashLoanError("flash loan is disabled (set FLASHLOAN_ENABLED=true)")
        self.settings = settings
        self._w3 = None
        self._blue = None
        self._caller = None
        self.token_address = settings.morpho_loan_token or PUSD_ADDRESS
        if not self.token_address:
            raise FlashLoanError("no flash-loan token configured (morpho_loan_token/PUSD_ADDRESS)")

    def _web3(self):
        if self._w3 is None:
            from web3 import Web3
            url = self.settings.rpc_url
            self._w3 = Web3(Web3.HTTPProvider(url))
        return self._w3

    def _blue_contract(self):
        w3 = self._web3()
        if self._blue is None:
            blue_addr = self.settings.morpho_blue_address or MORPHO_BLUE_POLYGON
            if not blue_addr:
                raise FlashLoanError("morpho_blue_address not configured")
            self._blue = w3.eth.contract(address=blue_addr, abi=FLASH_LOAN_ABI)
        return self._blue

    def _caller_contract(self):
        w3 = self._web3()
        if self._caller is None:
            caller_addr = self.settings.morpho_flashloan_caller
            if not caller_addr:
                raise FlashLoanError(
                    "morpho_flashloan_caller not configured; a deployed Morpho FlashLoanReceiver "
                    "is required to receive the callback from the singleton"
                )
            self._caller = w3.eth.contract(address=caller_addr, abi=CALLER_ABI)
        return self._caller

    @property
    def loan_token(self) -> str:
        return self.token_address

    def repay_amount(self, amount: float) -> float:
        """Morpho flash loans charge no fee; principal must be repaid in full."""
        return amount

    def max_flash_loan(self, token: Optional[str] = None) -> float:
        """Maximum flash-loanable amount (in token base units) for the token.


        Falls back to reading the singleton's balance when the optional view is
        not available on this deployment..

        """
        w3 = self._web3()
        token_addr = token or self.token_address
        try:
            wei = self._blue_contract().functions.maxFlashLoan(token_addr).call()
        except Exception as exc:
            logger.debug("maxFlashLoan unavailable (%s); reading token balance", exc)
            erc20 = w3.eth.contract(address=token_addr, abi=[
                {
                    "inputs": [{"name": "account", "type": "address"}],
                    "name": "balanceOf",
                    "outputs": [{"name": "", "type": "uint256"}],
                    "stateMutability": "view",
                    "type": "function",
                }
            ])
            wei = erc20.functions.balanceOf(self._blue_contract().address).call()
        return from_wei(wei, 6)

    def execute(self, amount: float, data: bytes = b"", token: Optional[str] = None) -> str:
        """Trigger a flash loan via the deployed caller contract.



        amount: loan size in token units (6 dp.. must be an integer number of
                base unitsand must not exceed the singleton's available balance..

        data: callback payload for the remote arb(e.g.. packed condition-id/token-id pairs..


        Returns the caller-tx hash; the actual arb runs inside the Morpho callback
        and can fail independently of the referral tx returning mined successfully..

        """
        if not self.settings.private_key:
            raise FlashLoanError("private_key required to trigger flash loan")
        if amount <= 0:
            raise ValueError("amount must be > 0")
        w3 = self._web3()
        from eth_account import Account
        acct = Account.from_key(self.settings.private_key.strip().removeprefix("0x"))
        caller = self._caller_contract()
        token_addr = token or self.token_address
        amount_wei = to_wei(self.repay_amount(amount), 6)
        try:
            tx = caller.functions.executeFlashLoan(token_addr, amount_wei, data).build_transaction({
                "from": acct.address,
                "nonce": w3.eth.get_transaction_count(acct.address, "pending"),
                "chainId": self.settings.chain_id,
                "gas": 1000000,
                "gasPrice": w3.eth.gas_price,
            })
        except Exception as exc:
            raise FlashLoanError(f"cannot build executeFlashLoan tx: {exc}") from exc
        signed = acct.sign_transaction(tx)
        raw_tx = getattr(signed, "raw_transaction", None) or signed.rawTransaction
        tx_hash = w3.eth.send_raw_transaction(raw_tx)
        logger.info(
            "Morpho flash loan submitted: token=%s assets=%s caller=%s tx=%s",
            token_addr, amount_wei, caller.address, tx_hash.hex(),
        )
        return tx_hash.hex()