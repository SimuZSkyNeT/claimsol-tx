"""Transaction builder used in production by Claim SOL (https://claimsol.solhousesignal.com).

What a Claim SOL transaction can contain, and nothing else:

  1. ComputeBudget: set_compute_unit_limit / set_compute_unit_price
  2. SPL Token / Token-2022 `CloseAccount` (ix 9) on the user's EMPTY token accounts.
     destination = the user's own wallet, authority = the user's own wallet.
  3. (only if the user ticks a token to burn) `BurnChecked` (ix 15) of the user's remaining
     balance of THAT token, then `CloseAccount` of the same account.
  4. (only if the user ticks a junk NFT) Metaplex Token Metadata `BurnV1` (see nft.py).
  5. (only if the user ticks "Sell") a Jupiter swap of that token to SOL (see swap.py).
  6. ONE System Program `Transfer` from the user to our fee wallet: the service fee, a fixed
     percentage of the SOL recovered, shown in the UI before signing.
  7. (gas-free claims only) one more `Transfer` from the user to the project wallet that paid
     the network fee for them.

There are no token approvals, no delegations, no `SetAuthority`, and no transfer of the
user's tokens to anyone. Every account and amount is re-read from the chain on the server:
the client only says WHICH of its own accounts to include.
"""
from solders.compute_budget import set_compute_unit_limit, set_compute_unit_price
from solders.hash import Hash
from solders.instruction import AccountMeta, Instruction
from solders.message import MessageV0, to_bytes_versioned
from solders.pubkey import Pubkey
from solders.signature import Signature
from solders.system_program import TransferParams, transfer
from solders.transaction import VersionedTransaction

from . import nft as NFT

TOKEN = Pubkey.from_string("TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA")
TOKEN22 = Pubkey.from_string("TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb")

MAX_CLOSE_TX = 10          # close-account per transaction (leaves room for wallet-side guards)
MAX_BURN_TX = 5            # burn+close per transaction
NFT_PER_TX = 2
CU_PRICE = 20_000          # micro-lamports per CU: modest priority
MAX_BYTE_TX = 850          # our own cap, well below Solana's 1232: room for Phantom Lighthouse
MAX_BYTE_TX_SPONSOR = 1_168  # two signers: 1232 − 64 for the extra signature
RENT_MIN = 890_880         # a system account below this can't exist (rent-exempt minimum)
SPONSOR_MIN_EXTRA = 15_000  # gas-free claims: covers 2 signatures + priority fee


def ix_close(program, account, owner):
    """SPL CloseAccount (9): the rent goes back to `owner`, who must sign."""
    return Instruction(program, bytes([9]), [AccountMeta(account, False, True),
                                             AccountMeta(owner, False, True),
                                             AccountMeta(owner, True, False)])


def ix_burn(program, account, mint, owner, amount, decimals):
    """SPL BurnChecked (15) of the user's own remaining balance (only when the user asks)."""
    data = bytes([15]) + int(amount).to_bytes(8, "little") + bytes([decimals])
    return Instruction(program, data, [AccountMeta(account, False, True),
                                       AccountMeta(Pubkey.from_string(mint), False, True),
                                       AccountMeta(owner, True, False)])


def build(owner, empty, dust_to_burn, nfts, fee_pct, fee_wallet, blockhash,
          sponsor=None, sponsor_extra_pct=5.0):
    """Build the unsigned transactions for one claim.

    owner         Pubkey of the user (the only signer, plus `sponsor` on gas-free claims)
    empty         token accounts with zero balance, as read from the chain
    dust_to_burn  token accounts the user explicitly chose to burn
    nfts          NFTs the user explicitly chose to burn (nft.enrich() output)
    fee_pct       our service fee, % of the rent recovered
    sponsor       Pubkey of the project wallet when it pays the network fee (gas-free claim)

    Returns a list of (kind, n_accounts, lamports_recovered, fee, extra, base64_tx, message_bytes).
    Every transaction is then simulated (simulate.py) and dropped if it would fail, BEFORE the
    user is asked to sign anything.
    """
    groups = [("close", empty[i:i + MAX_CLOSE_TX]) for i in range(0, len(empty), MAX_CLOSE_TX)]
    groups += [("burn", dust_to_burn[i:i + MAX_BURN_TX]) for i in range(0, len(dust_to_burn), MAX_BURN_TX)]
    groups += [("nft", nfts[i:i + NFT_PER_TX]) for i in range(0, len(nfts), NFT_PER_TX)]
    out = []
    for kind, group in groups:
        per_acc = {"burn": 12_000, "nft": 120_000}.get(kind, 4_000)
        # +60k CU of headroom for the guard instructions wallets may add (Lighthouse)
        ixs = [set_compute_unit_limit(60_000 + len(group) * per_acc), set_compute_unit_price(CU_PRICE)]
        recovered = 0
        for a in group:
            program = TOKEN22 if a["program"] == "token2022" else TOKEN
            acc = Pubkey.from_string(a["pubkey"])
            if kind == "nft":
                ixs.append(NFT.ix_burn(owner, a))
            else:
                if kind == "burn":
                    ixs.append(ix_burn(program, acc, a["mint"], owner, a["amount"], a["decimals"]))
                ixs.append(ix_close(program, acc, owner))
            recovered += a["rent"]
        fee = int(recovered * fee_pct / 100)
        if fee > 0:
            ixs.append(transfer(TransferParams(from_pubkey=owner, to_pubkey=fee_wallet, lamports=fee)))
        extra = 0
        if sponsor:
            extra = max(int(recovered * sponsor_extra_pct / 100), SPONSOR_MIN_EXTRA)
            ixs.append(transfer(TransferParams(from_pubkey=owner, to_pubkey=sponsor, lamports=extra)))
        msg = MessageV0.try_compile(sponsor or owner, ixs, [], Hash.from_string(str(blockhash)))
        tx = VersionedTransaction.populate(msg, [Signature.default()] * (2 if sponsor else 1))
        raw = bytes(tx)
        if len(raw) > (MAX_BYTE_TX_SPONSOR if sponsor else MAX_BYTE_TX):
            if kind == "nft" and len(group) > 1:      # two NFTs from different collections: split
                groups.extend(("nft", [a]) for a in group)
                continue
            raise ValueError("transaction too large")
        out.append((kind, len(group), recovered, fee, extra, raw, to_bytes_versioned(msg)))
    return out
