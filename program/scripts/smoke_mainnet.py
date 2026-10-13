# Smoke test MAINNET di close_many: crea UN account token vuoto (mint WSOL, owner = wallet
# progetto) e lo chiude con UNA istruzione del programma deployato. Prova che il programma
# gira davvero sulla catena prima del test con Phantom vero. Costo: solo fee (~0,00001 SOL).
import asyncio
import base64
import json

import aiohttp
from solders.compute_budget import set_compute_unit_limit, set_compute_unit_price
from solders.hash import Hash
from solders.instruction import AccountMeta, Instruction
from solders.keypair import Keypair
from solders.message import MessageV0
from solders.pubkey import Pubkey
from solders.system_program import CreateAccountParams, create_account
from solders.transaction import VersionedTransaction

ENV = {}
for l in open("/root/tools_site/.env"):
    if "=" in l:
        k, v = l.split("=", 1)
        ENV[k] = v.strip().strip('"')
RPC = ENV["SOL_RPC"]
KP = Keypair.from_bytes(bytes(json.load(open("/root/tools_site/progetto.json"))))
PROG = Pubkey.from_string("J9CwiaxYkQPtr2UDtEsD5EtEePmKxwPWczuH4oAeb4HR")
KEG = Pubkey.from_string("TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA")
T22 = Pubkey.from_string("TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb")
WSOL = Pubkey.from_string("So11111111111111111111111111111111111111112")
RENT_SYS = Pubkey.from_string("SysvarRent111111111111111111111111111111111")
ACC_RENT = 2_039_280


async def rpc(s, method, params):
    async with s.post(RPC, json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params}) as r:
        return await r.json()


async def manda(s, ixs, signers):
    bh = (await rpc(s, "getLatestBlockhash", [{"commitment": "confirmed"}]))["result"]["value"]["blockhash"]
    tx = VersionedTransaction(MessageV0.try_compile(KP.pubkey(), ixs, [], Hash.from_string(bh)),
                              [KP] + signers)
    raw = base64.b64encode(bytes(tx)).decode()
    # RPC laggante (stesso pattern di api.py): skipPreflight + retry della STESSA tx finché non
    # entra; il blockhash diventa visibile appena l'RPC si riallinea.
    sig = str(tx.signatures[0])
    for _ in range(25):
        await rpc(s, "sendTransaction", [raw, {"encoding": "base64", "skipPreflight": True,
                                               "maxRetries": 0}])
        await asyncio.sleep(1.2)
        st = await rpc(s, "getSignatureStatuses", [[sig]])
        v = (st.get("result") or {}).get("value") or [None]
        if v[0] and v[0].get("confirmationStatus") in ("confirmed", "finalized"):
            assert not v[0].get("err"), f"tx fallita: {v[0]['err']}"
            return sig
    raise SystemExit(f"tx non confermata: {sig}")


async def main():
    async with aiohttp.ClientSession() as s:
        acc_kp = Keypair()
        # 1) account token vuoto (WSOL, owner = wallet progetto): forma MODERNA a 4 account
        await manda(s, [
            create_account(CreateAccountParams(from_pubkey=KP.pubkey(), to_pubkey=acc_kp.pubkey(),
                                               lamports=ACC_RENT, space=165, owner=KEG)),
            Instruction(KEG, bytes([1]) + bytes(WSOL) + bytes(KP.pubkey()) + (0).to_bytes(8, "little"),
                        [AccountMeta(acc_kp.pubkey(), False, True),
                         AccountMeta(WSOL, False, False),
                         AccountMeta(KP.pubkey(), False, False),
                         AccountMeta(RENT_SYS, False, False)]),
        ], [acc_kp])
        print(f"setup ok: account vuoto {acc_kp.pubkey()}")

        saldo0 = (await rpc(s, "getBalance", [str(KP.pubkey()), {"commitment": "confirmed"}]))["result"]["value"]
        # 2) close_many: UNA istruzione chiude l'account e rende la rendita al wallet
        sig = await manda(s, [
            set_compute_unit_limit(400_000),
            set_compute_unit_price(20_000),
            Instruction(PROG, b"",
                        [AccountMeta(KP.pubkey(), True, True),
                         AccountMeta(KEG, False, False), AccountMeta(T22, False, False),
                         AccountMeta(acc_kp.pubkey(), False, True)]),
        ], [])
        info = await rpc(s, "getAccountInfo", [str(acc_kp.pubkey()), {"commitment": "confirmed"}])
        saldo1 = (await rpc(s, "getBalance", [str(KP.pubkey()), {"commitment": "confirmed"}]))["result"]["value"]
        chiuso = info.get("result", {}).get("value") is None
        print(f"tx: {sig}")
        print(f"account chiuso: {chiuso} — rendita rientrata: +{(saldo1 - saldo0) / 1e9:.6f} SOL")
        assert chiuso and saldo1 > saldo0, "smoke test fallito!"
        print("✅ close_many FUNZIONA SU MAINNET")


asyncio.run(main())
