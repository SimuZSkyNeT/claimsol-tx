"""Prova end-to-end di close_many: crea N token account e li chiude con UNA istruzione.

Uso: python3 test_close_many.py <program_id> <wallet.json> [n_accounts] [rpc_url]

La CLI `spl-token create-account` v4 crea l'ATA del payer per default (5 chiamate = 5 volte
lo stesso indirizzo), quindi il setup dei N account distinti è fatto qui con solders.
"""
import asyncio, base64, sys

import aiohttp
from solders.compute_budget import set_compute_unit_limit, set_compute_unit_price
from solders.hash import Hash
from solders.instruction import AccountMeta, Instruction
from solders.keypair import Keypair
from solders.message import Message
from solders.pubkey import Pubkey
from solders.system_program import CreateAccountParams, create_account
from solders.transaction import Transaction

RPC = sys.argv[4] if len(sys.argv) > 4 else "https://api.devnet.solana.com"
N = int(sys.argv[3]) if len(sys.argv) > 3 else 5
KEG = Pubkey.from_string("TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA")
T22 = Pubkey.from_string("TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb")
RENT = Pubkey.from_string("SysvarRent111111111111111111111111111111111")

MINT_RENT = 1_461_600   # rent-exempt 82 byte
ACC_RENT = 2_039_280    # rent-exempt 165 byte


async def rpc(session, method, params):
    async with session.post(RPC, json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params}) as r:
        return await r.json()


async def send_and_confirm(session, tx):
    raw = base64.b64encode(bytes(tx)).decode()
    # il preflight del solana-test-validator fallisce su account airdroppati ("no record of a
    # prior credit" pur avendo saldo): saltalo SOLO contro il validator locale.
    skip = RPC.startswith("http://127.0.0.1")
    res = await rpc(session, "sendTransaction", [raw, {"encoding": "base64", "skipPreflight": skip, "maxRetries": 0}])
    if "result" not in res:
        raise SystemExit(f"sendTransaction rifiutata: {res}")
    sig = res["result"]
    for _ in range(40):
        st = await rpc(session, "getSignatureStatuses", [[sig]])
        v = (st.get("result") or {}).get("value") or [None]
        if v[0] and v[0].get("confirmationStatus") in ("confirmed", "finalized"):
            assert not v[0].get("err"), f"tx fallita: {v[0]['err']}"
            return sig
        await asyncio.sleep(1)
    raise SystemExit(f"tx non confermata: {sig}")


async def main():
    prog = Pubkey.from_string(sys.argv[1])
    kp = Keypair.from_json(open(sys.argv[2]).read())

    async with aiohttp.ClientSession() as s:
        # --- setup: un mint + N token account distinti, owner = wallet.
        # Un tx solo supererebbe i 1232 byte del messaggio → un piccolo tx alla volta.
        # Tx LEGACY: il TPU del solana-test-validator non processa le versioned (quirk locale). ---
        async def nuova_tx(ixs, signers):
            bh = (await rpc(s, "getLatestBlockhash", [{"commitment": "confirmed"}]))["result"]["value"]["blockhash"]
            h = Hash.from_string(bh)
            msg = Message.new_with_blockhash(ixs, kp.pubkey(), h)
            print("── tx compilato, keys:", [str(k) for k in msg.account_keys])
            for i, mi in enumerate(msg.instructions):
                print(f"   ix{i}: prog={msg.account_keys[mi.program_id_index]} "
                      f"metas={[str(msg.account_keys[j]) for j in mi.accounts]}")
            return Transaction([kp] + signers, msg, h)

        mint_kp = Keypair()
        await send_and_confirm(s, await nuova_tx([
            create_account(CreateAccountParams(
                from_pubkey=kp.pubkey(), to_pubkey=mint_kp.pubkey(),
                lamports=MINT_RENT, space=82, owner=KEG)),
            # InitializeMint (ix 0): [0] + decimals + mint_authority(32) + freeze_authority COption nullo;
            # account: mint (w) + sysvar rent (ro)
            Instruction(KEG, bytes([0]) + (9).to_bytes(1, "little") + bytes(kp.pubkey()) + bytes(33),
                        [AccountMeta(mint_kp.pubkey(), False, True), AccountMeta(RENT, False, False)]),
        ], [mint_kp]))
        print(f"setup mint ok: {mint_kp.pubkey()}")

        acc_kps = []
        for _ in range(N):
            ak = Keypair()
            await send_and_confirm(s, await nuova_tx([
                create_account(CreateAccountParams(
                    from_pubkey=kp.pubkey(), to_pubkey=ak.pubkey(),
                    lamports=ACC_RENT, space=165, owner=KEG)),
                # InitializeAccount (ix 1): [1] + mint(32) + owner(32) + amount u64.
                # Il processore MODERNO (solana 4.x) vuole 4 account:
                # [0] token account (w), [1] mint (ro), [2] OWNER (ro), [3] sysvar rent (ro).
                # Senza l'owner tra i conti: NotEnoughAccountKeys (errore vista fin qui).
                Instruction(KEG, bytes([1]) + bytes(mint_kp.pubkey()) + bytes(kp.pubkey()) + (0).to_bytes(8, "little"),
                            [AccountMeta(ak.pubkey(), False, True),
                             AccountMeta(mint_kp.pubkey(), False, False),
                             AccountMeta(kp.pubkey(), False, False),
                             AccountMeta(RENT, False, False)]),
            ], [ak]))
            acc_kps.append(ak)
        print(f"setup ok: {N} token account distinti")

        saldo0 = (await rpc(s, "getBalance", [str(kp.pubkey()), {"commitment": "confirmed"}]))["result"]["value"]
        print(f"wallet: {kp.pubkey()} — saldo prima: {saldo0} lamports")

        # --- close_many: UNA istruzione, N chiusure ---
        bh = (await rpc(s, "getLatestBlockhash", [{"commitment": "confirmed"}]))["result"]["value"]["blockhash"]
        ix = Instruction(
            prog,
            b"",
            [AccountMeta(kp.pubkey(), True, True)]
            + [AccountMeta(KEG, False, False), AccountMeta(T22, False, False)]
            + [AccountMeta(a.pubkey(), False, True) for a in acc_kps],
        )
        ixs = [set_compute_unit_limit(400_000), set_compute_unit_price(20_000), ix]
        h = Hash.from_string(bh)
        msg = Message.new_with_blockhash(ixs, kp.pubkey(), h)
        tx = Transaction([kp], msg, h)
        raw = base64.b64encode(bytes(tx)).decode()

        sim = await rpc(s, "simulateTransaction", [raw, {"encoding": "base64", "sigVerify": False,
                                                         "replaceRecentBlockhash": True, "commitment": "confirmed"}])
        err = (sim.get("result") or {}).get("value", {})
        print("simulazione:", "OK" if err.get("err") is None else err)
        if err.get("err") is not None:
            sys.exit(1)

        await send_and_confirm(s, tx)

        infos = await rpc(s, "getMultipleAccounts", [[str(a.pubkey()) for a in acc_kps], {"commitment": "confirmed"}])
        rimasti = sum(1 for a in infos["result"]["value"] if a)
        saldo1 = (await rpc(s, "getBalance", [str(kp.pubkey()), {"commitment": "confirmed"}]))["result"]["value"]
        print(f"account rimasti: {rimasti}/{N} (attesi 0)")
        print(f"rendita rientrata: +{(saldo1 - saldo0) / 1e9:.6f} SOL")
        assert rimasti == 0, "qualche account non chiuso!"
        assert saldo1 > saldo0, "la rendita non è tornata al wallet!"
        print(f"✅ close_many funziona: {N} chiusure in UNA istruzione")


asyncio.run(main())
