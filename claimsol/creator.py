"""pump.fun creator fees (added 10/10/2026).

Creators of pump.fun tokens earn trading fees that often stay unclaimed. Two vaults, both tied
to the creator wallet:

- bonding curve (pump program): system PDA ["creator-vault", creator] -> `collect_creator_fee`
  sends the SOL to the creator and leaves the vault at its rent minimum;
- PumpSwap (graduated tokens): WSOL account of the PDA ["creator_vault", creator] ->
  `collect_coin_creator_fee` moves it to the creator's WSOL account, which we then close so the
  creator gets plain SOL.

Only the creator wallet can sign these instructions: nobody else can collect the fees, and the
SOL always lands in the creator's own wallet. Our fee is a separate, visible System Transfer.
"""
import hashlib

from solders.instruction import AccountMeta, Instruction
from solders.pubkey import Pubkey

PUMP = Pubkey.from_string("6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P")
AMM = Pubkey.from_string("pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA")
TOKEN = Pubkey.from_string("TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA")
ATA = Pubkey.from_string("ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL")
SYS = Pubkey.from_string("11111111111111111111111111111111")
WSOL = Pubkey.from_string("So11111111111111111111111111111111111111112")

D_PUMP = hashlib.sha256(b"global:collect_creator_fee").digest()[:8]
D_AMM = hashlib.sha256(b"global:collect_coin_creator_fee").digest()[:8]
EV_PUMP = Pubkey.find_program_address([b"__event_authority"], PUMP)[0]
EV_AMM = Pubkey.find_program_address([b"__event_authority"], AMM)[0]
# the curve vault keeps its rent minimum: we only show what actually comes out (a safe estimate)
MINIMO_VAULT = 890_880
SOGLIA = 100_000          # below 0.0001 SOL it is not worth a transaction


def _ata(owner, mint=WSOL):
    return Pubkey.find_program_address([bytes(owner), bytes(TOKEN), bytes(mint)], ATA)[0]


def indirizzi(owner: Pubkey):
    vault = Pubkey.find_program_address([b"creator-vault", bytes(owner)], PUMP)[0]
    auth = Pubkey.find_program_address([b"creator_vault", bytes(owner)], AMM)[0]
    return vault, auth, _ata(auth)


async def leggi(rpc, owner: Pubkey):
    """{'pump': lamports claimable from the curve, 'amm': WSOL lamports from PumpSwap, 'totale': sum}."""
    vault, auth, vata = indirizzi(owner)
    j = await rpc("getMultipleAccounts", [[str(vault), str(vata)], {"encoding": "jsonParsed",
                                                                    "commitment": "confirmed"}])
    v, a = (j.get("result") or {}).get("value") or [None, None]
    pump = max(0, int(v["lamports"]) - MINIMO_VAULT) if v else 0
    amm = 0
    if a:
        try:
            amm = int(a["data"]["parsed"]["info"]["tokenAmount"]["amount"])
        except Exception:
            amm = 0
    pump = pump if pump >= SOGLIA else 0
    amm = amm if amm >= SOGLIA else 0
    return {"pump": pump, "amm": amm, "totale": pump + amm}


def ixs(owner: Pubkey, info: dict):
    """The collect instructions. Curve first: it gives the wallet SOL, which pays for the temporary
    WSOL account of the PumpSwap branch even when the wallet starts at 0."""
    out = []
    vault, auth, vata = indirizzi(owner)
    if info.get("pump"):
        out.append(Instruction(PUMP, D_PUMP, [
            AccountMeta(owner, False, True), AccountMeta(vault, False, True),
            AccountMeta(SYS, False, False), AccountMeta(EV_PUMP, False, False),
            AccountMeta(PUMP, False, False)]))
    if info.get("amm"):
        dest = _ata(owner)
        out.append(Instruction(ATA, bytes([1]), [                  # create_idempotent of the user's WSOL account
            AccountMeta(owner, True, True), AccountMeta(dest, False, True), AccountMeta(owner, False, False),
            AccountMeta(WSOL, False, False), AccountMeta(SYS, False, False), AccountMeta(TOKEN, False, False)]))
        out.append(Instruction(AMM, D_AMM, [
            AccountMeta(WSOL, False, False), AccountMeta(TOKEN, False, False),
            AccountMeta(owner, True, False), AccountMeta(auth, False, False),
            AccountMeta(vata, False, True), AccountMeta(dest, False, True),
            AccountMeta(EV_AMM, False, False), AccountMeta(AMM, False, False)]))
        out.append(Instruction(TOKEN, bytes([9]), [                # close the WSOL account: back to plain SOL
            AccountMeta(dest, False, True), AccountMeta(owner, False, True), AccountMeta(owner, True, False)]))
    return out
