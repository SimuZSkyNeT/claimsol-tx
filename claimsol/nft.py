"""Burning junk NFTs (only the ones the user explicitly ticks): Metaplex Token Metadata BurnV1.

A standard NFT (classic Token program, decimals 0, amount 1, with a master edition) locks rent
in 3 accounts: token, metadata and master edition. Burning it returns that rent to the owner.
pNFTs (ProgrammableNonFungible) have a FROZEN token account by design: they are recognised
from the metadata and also need the token record. Printed editions need 4 more accounts and
are left alone. Every transaction is simulated before signing: if Metaplex refuses, nothing
is shown to the user.
"""
import base64
import struct

from solders.instruction import AccountMeta, Instruction
from solders.pubkey import Pubkey

TM = Pubkey.from_string("metaqbxxUerdq28cj1RbAWkYQm3ybzjb6a8bt518x1s")
TOKEN = Pubkey.from_string("TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA")
SYS = Pubkey.from_string("11111111111111111111111111111111")
SYSVAR_IX = Pubkey.from_string("Sysvar1nstructions1111111111111111111111111")
MASTER_V1, MASTER_V2 = 2, 6          # Metaplex keys of master edition accounts
NFT_STD, PNFT_STD = 0, 4


def pda_metadata(mint):
    return Pubkey.find_program_address([b"metadata", bytes(TM), bytes(mint)], TM)[0]


def pda_edition(mint):
    return Pubkey.find_program_address([b"metadata", bytes(TM), bytes(mint), b"edition"], TM)[0]


def pda_record(mint, token):
    return Pubkey.find_program_address([b"metadata", bytes(TM), bytes(mint), b"token_record", bytes(token)], TM)[0]


def leggi_metadata(d):
    """Metaplex metadata (borsh): name, symbol, token standard, collection."""
    o = 1 + 32 + 32

    def stringa():
        nonlocal o
        n = struct.unpack_from("<I", d, o)[0]
        o += 4
        v = d[o:o + n].decode("utf-8", "ignore").rstrip("\x00").strip()
        o += n
        return v
    nome, simbolo, _uri = stringa(), stringa(), stringa()
    o += 2                                     # seller_fee_basis_points
    if d[o]:                                   # creators: Option<Vec<Creator>>
        n = struct.unpack_from("<I", d, o + 1)[0]
        o += 1 + 4 + n * 34
    else:
        o += 1
    o += 2                                     # primary_sale_happened, is_mutable
    o += 2 if d[o] else 1                      # edition_nonce: Option<u8>
    std = None
    if d[o]:
        std = d[o + 1]
        o += 2
    else:
        o += 1
    coll = None
    if o < len(d) and d[o]:
        coll = {"verified": bool(d[o + 1]), "key": str(Pubkey.from_bytes(d[o + 2:o + 34]))}
    return {"name": nome, "symbol": simbolo, "standard": std, "collection": coll}


async def enrich(rpc, accs):
    """Mark burnable NFTs and add the metadata + edition rent to their 'rent'."""
    cand = [a for a in accs if a["program"] == "token" and a["decimals"] == 0 and a["amount"] == "1"
            and a["kind"] in ("nft", "blocked")]
    for i in range(0, len(cand), 50):
        gruppo = cand[i:i + 50]
        chiavi = []
        for a in gruppo:
            m = Pubkey.from_string(a["mint"])
            chiavi += [str(pda_metadata(m)), str(pda_edition(m))]
        j = await rpc("getMultipleAccounts", [chiavi, {"encoding": "base64", "commitment": "confirmed"}])
        vals = (j.get("result") or {}).get("value") or []
        for k, a in enumerate(gruppo):
            md, ed = (vals[2 * k], vals[2 * k + 1]) if len(vals) > 2 * k + 1 else (None, None)
            if not md or not ed:
                continue
            try:
                info = leggi_metadata(base64.b64decode(md["data"][0]))
                chiave_ed = base64.b64decode(ed["data"][0])[0]
            except Exception:
                continue
            if chiave_ed not in (MASTER_V1, MASTER_V2):
                continue                                     # printed edition: left alone
            pnft = info["standard"] == PNFT_STD
            if a["kind"] == "blocked" and not (pnft and a["blocked"] == "frozen"):
                continue                                     # frozen by someone else: no
            a.update({"kind": "nft", "nft_burnable": True, "pnft": pnft,
                      "nft_name": info["name"], "nft_symbol": info["symbol"],
                      "collection": info["collection"]["key"] if info["collection"] and info["collection"]["verified"] else None,
                      "rent": a["lamports"] + int(md["lamports"]) + int(ed["lamports"]), "blocked": None})
    return accs


def ix_burn(owner, a):
    mint, token = Pubkey.from_string(a["mint"]), Pubkey.from_string(a["pubkey"])
    ph = AccountMeta(TM, False, False)                       # absent optional account = program id
    coll = AccountMeta(pda_metadata(Pubkey.from_string(a["collection"])), False, True) if a.get("collection") else ph
    rec = AccountMeta(pda_record(mint, token), False, True) if a.get("pnft") else ph
    accounts = [AccountMeta(owner, True, True), coll,
             AccountMeta(pda_metadata(mint), False, True), AccountMeta(pda_edition(mint), False, True),
             AccountMeta(mint, False, True), AccountMeta(token, False, True),
             ph, ph, ph, ph, rec,
             AccountMeta(SYS, False, False), AccountMeta(SYSVAR_IX, False, False), AccountMeta(TOKEN, False, False)]
    return Instruction(TM, bytes([41, 0]) + (1).to_bytes(8, "little"), accounts)
