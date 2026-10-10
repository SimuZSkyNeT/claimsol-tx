"""Pre-signature simulation (Phantom docs, "Domain and transaction warnings").

Every transaction is simulated with sigVerify: false before the user is asked to sign it.
A transaction whose simulation fails is dropped and never shown to the wallet.
"""
import asyncio
import base64


async def keep_only_passing(rpc, txs_raw):
    """rpc(method, params) -> JSON-RPC response dict. Returns the indexes that pass."""
    sims = await asyncio.gather(*[rpc("simulateTransaction", [base64.b64encode(raw).decode(), {
        "encoding": "base64", "sigVerify": False, "replaceRecentBlockhash": True,
        "commitment": "confirmed"}]) for raw in txs_raw], return_exceptions=True)
    ok = []
    for i, s in enumerate(sims):
        v = (s.get("result") or {}).get("value") if isinstance(s, dict) else None
        if v and v.get("err") is None:
            ok.append(i)
    return ok
