"""Selling "dust" for SOL instead of burning it (only tokens the user explicitly ticks "Sell").

One transaction per token: the Jupiter swap to SOL, then CloseAccount of the now-empty token
account (rent back to the user), then our plain fee transfer:
  SWAP_FEE_PCT% of what the swap guarantees (otherAmountThreshold, the minimum after slippage)
  + the usual % of the rent.
Jupiter's public API. Address lookup tables keep the transaction small; we keep the same 850
byte cap as every other transaction.
"""
import base64

import aiohttp
from solders.address_lookup_table_account import AddressLookupTable, AddressLookupTableAccount
from solders.compute_budget import set_compute_unit_limit, set_compute_unit_price
from solders.instruction import AccountMeta, Instruction
from solders.pubkey import Pubkey

JUP = "https://lite-api.jup.ag/swap/v1"
WSOL = "So11111111111111111111111111111111111111112"
SLIPPAGE_BPS = 300
MIN_OUT_LAMPORTS = 50_000        # below this the network + priority fee would eat it
MAX_PRICE_IMPACT = 0.10         # 10%: above this the sale would dump the token for too little
CU_MARGINE = 60_000              # same headroom as the other transactions (Lighthouse)


def _ix(j):
    return Instruction(Pubkey.from_string(j["programId"]), base64.b64decode(j["data"]),
                       [AccountMeta(Pubkey.from_string(a["pubkey"]), a["isSigner"], a["isWritable"])
                        for a in j["accounts"]])


async def _alts(rpc, indirizzi):
    if not indirizzi:
        return []
    j = await rpc("getMultipleAccounts", [indirizzi, {"encoding": "base64", "commitment": "confirmed"}])
    out = []
    for k, v in zip(indirizzi, (j.get("result") or {}).get("value") or []):
        if v:
            t = AddressLookupTable.deserialize(base64.b64decode(v["data"][0]))
            out.append(AddressLookupTableAccount(Pubkey.from_string(k), list(t.addresses)))
    return out


async def prepare(rpc, owner, acc, max_accounts=28):
    """-> dict(ixs, alts, min_out, out, cu) or dict(error=...)."""
    p = {"inputMint": acc["mint"], "outputMint": WSOL, "amount": acc["amount"],
         "slippageBps": SLIPPAGE_BPS, "restrictIntermediateTokens": "true", "maxAccounts": max_accounts}
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as s:
        async with s.get(JUP + "/quote", params=p) as r:
            q = await r.json(content_type=None)
        if not isinstance(q, dict) or not q.get("outAmount"):
            return {"error": "no route"}
        min_out = int(q["otherAmountThreshold"])
        if min_out < MIN_OUT_LAMPORTS:
            return {"error": "worth too little"}
        # 🛡 anti-mistake: a thin market would sell your tokens far below their value. Above
        # MAX_PRICE_IMPACT the token is NOT sold (it stays in the wallet).
        if float(q.get("priceImpactPct") or 0) > MAX_PRICE_IMPACT:
            return {"error": f"price impact too high ({float(q['priceImpactPct']) * 100:.0f}%): kept in your wallet"}
        body = {"quoteResponse": q, "userPublicKey": str(owner), "wrapAndUnwrapSol": True,
                "dynamicComputeUnitLimit": True}
        async with s.post(JUP + "/swap-instructions", json=body) as r:
            si = await r.json(content_type=None)
    if not isinstance(si, dict) or not si.get("swapInstruction"):
        return {"error": "no route"}
    cu = 300_000
    for c in si.get("computeBudgetInstructions") or []:
        d = base64.b64decode(c["data"])
        if d and d[0] == 2:
            cu = int.from_bytes(d[1:5], "little")
    ixs = [_ix(x) for x in (si.get("setupInstructions") or [])]
    ixs.append(_ix(si["swapInstruction"]))
    if si.get("cleanupInstruction"):
        ixs.append(_ix(si["cleanupInstruction"]))
    ixs += [_ix(x) for x in (si.get("otherInstructions") or [])]
    return {"ixs": ixs, "alts": await _alts(rpc, si.get("addressLookupTableAddresses") or []),
            "min_out": min_out, "out": int(q["outAmount"]), "cu": min(1_400_000, cu + CU_MARGINE)}


def budget(cu, prezzo):
    return [set_compute_unit_limit(cu), set_compute_unit_price(prezzo)]
