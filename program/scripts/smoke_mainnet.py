"""MAINNET smoke test of close_many: create ONE empty token account (WSOL mint, owner = your
wallet) and close it with ONE instruction of the deployed program. Cost: network fees only
(~0.00001 SOL), the rent comes back.

Usage: SOLANA_RPC=<mainnet rpc url> python3 smoke_mainnet.py <wallet.json>
"""
import asyncio
import base64
import json
import os
import sys

import aiohttp
from solders.compute_budget import set_compute_unit_limit, set_compute_unit_price
from solders.hash import Hash
from solders.instruction import AccountMeta, Instruction
from solders.keypair import Keypair
from solders.message import MessageV0
from solders.pubkey import Pubkey
from solders.system_program import CreateAccountParams, create_account
from solders.transaction import VersionedTransaction

RPC = os.environ.get("SOLANA_RPC", "https://api.mainnet-beta.solana.com")
KP = Keypair.from_bytes(bytes(json.load(open(sys.argv[1]))))
PROG = Pubkey.from_string("J9CwiaxYkQPtr2UDtEsD5EtEePmKxwPWczuH4oAeb4HR")
KEG = Pubkey.from_string("TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA")
T22 = Pubkey.from_string("TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb")
WSOL = Pubkey.from_string("So11111111111111111111111111111111111111112")
RENT_SYS = Pubkey.from_string("SysvarRent111111111111111111111111111111111")
ACC_RENT = 2_039_280


async def rpc(s, method, params):
    async with s.post(RPC, json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params}) as r:
        return await r.json()


async def send(s, ixs, signers):
    bh = (await rpc(s, "getLatestBlockhash", [{"commitment": "confirmed"}]))["result"]["value"]["blockhash"]
    tx = VersionedTransaction(MessageV0.try_compile(KP.pubkey(), ixs, [], Hash.from_string(bh)),
                              [KP] + signers)
    raw = base64.b64encode(bytes(tx)).decode()
    # a lagging RPC may not know the blockhash yet: skipPreflight and resend the SAME tx until
    # it lands
    sig = str(tx.signatures[0])
    for _ in range(25):
        await rpc(s, "sendTransaction", [raw, {"encoding": "base64", "skipPreflight": True,
                                               "maxRetries": 0}])
        await asyncio.sleep(1.2)
        st = await rpc(s, "getSignatureStatuses", [[sig]])
        v = (st.get("result") or {}).get("value") or [None]
        if v[0] and v[0].get("confirmationStatus") in ("confirmed", "finalized"):
            assert not v[0].get("err"), f"tx failed: {v[0]['err']}"
            return sig
    raise SystemExit(f"tx not confirmed: {sig}")


async def main():
    async with aiohttp.ClientSession() as s:
        acc_kp = Keypair()
        # 1) empty token account (WSOL, owner = your wallet): MODERN 4-account form
        await send(s, [
            create_account(CreateAccountParams(from_pubkey=KP.pubkey(), to_pubkey=acc_kp.pubkey(),
                                               lamports=ACC_RENT, space=165, owner=KEG)),
            Instruction(KEG, bytes([1]) + bytes(WSOL) + bytes(KP.pubkey()) + (0).to_bytes(8, "little"),
                        [AccountMeta(acc_kp.pubkey(), False, True),
                         AccountMeta(WSOL, False, False),
                         AccountMeta(KP.pubkey(), False, False),
                         AccountMeta(RENT_SYS, False, False)]),
        ], [acc_kp])
        print(f"setup ok: empty account {acc_kp.pubkey()}")

        balance0 = (await rpc(s, "getBalance", [str(KP.pubkey()), {"commitment": "confirmed"}]))["result"]["value"]
        # 2) close_many: ONE instruction closes the account and returns the rent to the wallet
        sig = await send(s, [
            set_compute_unit_limit(400_000),
            set_compute_unit_price(20_000),
            Instruction(PROG, b"",
                        [AccountMeta(KP.pubkey(), True, True),
                         AccountMeta(KEG, False, False), AccountMeta(T22, False, False),
                         AccountMeta(acc_kp.pubkey(), False, True)]),
        ], [])
        info = await rpc(s, "getAccountInfo", [str(acc_kp.pubkey()), {"commitment": "confirmed"}])
        balance1 = (await rpc(s, "getBalance", [str(KP.pubkey()), {"commitment": "confirmed"}]))["result"]["value"]
        closed = info.get("result", {}).get("value") is None
        print(f"tx: {sig}")
        print(f"account closed: {closed}, rent returned: +{(balance1 - balance0) / 1e9:.6f} SOL")
        assert closed and balance1 > balance0, "smoke test failed!"
        print("✅ close_many works on mainnet")


asyncio.run(main())
