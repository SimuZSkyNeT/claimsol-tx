# close_many — close up to 53 empty token accounts with ONE click

A public Solana program (no fees, no permissions, source available) that closes many empty
token accounts in a **single transaction** — including on wallets where Phantom blocks
multi-instruction/multi-transaction requests.

- **Why**: Phantom 26.x shows "Request blocked" on transactions with more than ~32
  instructions, and on any batched `signAllTransactions`/multi-signer request. This program
  does the same work with **1 instruction**: the ceiling becomes the Solana protocol limit
  of 64 accounts per transaction (~53 token accounts), not Phantom's gate.
- **What it does**: for every token account in the instruction it runs the standard
  `CloseAccount` (ix 9) against **Tokenkeg or Token-2022** (auto-detected per account).
  The rent-exempt lamports of every closed account go to **you** (the signer).
- **What it can't do**: nothing else. There is no transfer, no approval, no delegation,
  no hidden branch. The instruction data is empty and ignored. If any account is not a
  token account owned by the signer, the whole transaction fails atomically.

## On-chain facts

| item | value |
|---|---|
| Program ID | `J9CwiaxYkQPtr2UDtEsD5EtEePmKxwPWczuH4oAeb4HR` |
| ProgramData | `8UujbWy7UqZEB3Gp2GLdb8tMPVLb8QcRF3WD2mEMRyP9` |
| Upgrade authority | the deployer (claimsol.solhousesignal.com project wallet) |
| Source | Rust `solana-program`, no macros, ~22.5 KB — readable in `program/src/lib.rs` of this repo |
| Cost per claim | only the normal network fee (~5,000 lamports + priority) — the program takes nothing |

Verify it yourself in 30 seconds (read-only):

```
solana program show J9CwiaxYkQPtr2UDtEsD5EtEePmKxwPWczuH4oAeb4HR
```

and decompile/read the accounts on any explorer — the whole logic is the CPI
`CloseAccount` loop below, nothing else.

## Instruction format

```
accounts: [0] owner      — writable SIGNER; authority of every token account; receives all rent
          [1] Tokenkeg   — readonly (required for CPI)
          [2] Token-2022 — readonly (required for CPI)
          [3..] token accounts to close (max ~53) — writable
data:     empty (b"") — ignored by the program
```

Per account (Rust, from the source):

```rust
let owner = acc.owner;
if owner == TOKENKEG { /* CPI CloseAccount on Tokenkeg */ }
else if owner == TOKEN22 { /* CPI CloseAccount on Token-2022 */ }
else { return Err(...); }         // whole tx fails, nothing closes
```

CPI layout (both programs): `[source, destination=owner, authority=owner signer]`, data `[9]`.

## Limits (measured on mainnet)

- **57 token accounts max per tx** (verified with a real 57-account tx, 13/10): the 64-account
  protocol cap counts the *expanded* message — static accounts + the ones loaded from the lookup
  table. A typical tx has 7 static accounts (payer, 2 token programs, fee receiver, close_many,
  ComputeBudget, System), so 7 + N ≤ 64 → N ≤ 57. At 58 the bank rejects the tx
  (`TooManyAccountLocks`). Use **≤ 56** to keep 1 account of margin.
- **Transaction size**: ~511 bytes WITH an Address Lookup Table. Without a table the same
  tx is ~2,039 bytes — over the 1,232 protocol cap and rejected — so an ALT is mandatory
  for more than a handful of accounts. The ALT costs ~0.0096 SOL of rent (recoverable).
- **Compute**: ~172,500 CU for 53 closes. Budget: `set_compute_unit_limit(60_000 + 2_500 × n)`,
  `set_compute_unit_price(20_000)`.
- **Only empty accounts**: `CloseAccount` succeeds only when the token balance is 0.
  Accounts with dust must be burned/closed the classic way first.
- **Phantom**: a single-instruction close_many tx passes the Phantom origin gate with a
  normal "Confirm Transaction" popup (verified with real Phantom 26.33 on the
  claimsol.solhousesignal.com origin). The program label shows as "Unknown · Program J9Cwi…"
  until the program gets verified on an explorer — cosmetic only.
- **No second signer**: Phantom blocks 2-signer transactions, so close_many txs must be
  paid by the owner itself (no fee-payer sponsor).
- **ALT lifecycle (Solana 4.x)**: a lookup table can only be closed ~512 slots after its
  deactivation ("fully deactivated"). The script below deactivates the tables at the end;
  recover the rent by closing them ~4 minutes later (the close instruction is included).

## Ready-to-use script (python, solders)

```bash
pip install solders aiohttp
```

`chiudi_conti.py`:

```python
# Chiude TUTTI i token account vuoti del wallet, un'istruzione per 53 account.
# Uso:  python3 chiudi_conti.py wallet.json [--go]        (senza --go = simulazione)
# Serve ~0,01 SOL per ogni lookup table da 53 account (l'affitto si recupera: vedi fondo).
import asyncio, base64, json, struct, sys
import aiohttp
from solders.address_lookup_table_account import AddressLookupTableAccount, derive_lookup_table_address
from solders.compute_budget import set_compute_unit_limit, set_compute_unit_price
from solders.hash import Hash
from solders.instruction import AccountMeta, Instruction
from solders.keypair import Keypair
from solders.message import MessageV0
from solders.pubkey import Pubkey
from solders.signature import Signature
from solders.transaction import VersionedTransaction

RPC = "https://api.mainnet-beta.solana.com"          # qualsiasi RPC pubblico
CM = Pubkey.from_string("J9CwiaxYkQPtr2UDtEsD5EtEePmKxwPWczuH4oAeb4HR")
KEG = Pubkey.from_string("TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA")
T22 = Pubkey.from_string("TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb")
ALT_P = Pubkey.from_string("AddressLookupTab1e1111111111111111111111111")
SYS = Pubkey.from_string("11111111111111111111111111111111")
GO = "--go" in sys.argv
KP = Keypair.from_bytes(bytes(json.load(open(sys.argv[1]))))   # file solana-keygen standard


async def rpc(s, m, p):
    async with s.post(RPC, json={"jsonrpc": "2.0", "id": 1, "method": m, "params": p}) as r:
        return await r.json()


async def invia(s, ixs, payer=KP):
    """Invia una tx pagata dal wallet (pattern di produzione: skipPreflight + retry)."""
    bh = (await rpc(s, "getLatestBlockhash", [{"commitment": "confirmed"}]))["result"]["value"]["blockhash"]
    tx = VersionedTransaction(MessageV0.try_compile(payer.pubkey(), ixs, [], Hash.from_string(bh)), [payer])
    raw = base64.b64encode(bytes(tx)).decode()
    sig = str(tx.signatures[0])
    for _ in range(25):
        await rpc(s, "sendTransaction", [raw, {"encoding": "base64", "skipPreflight": True, "maxRetries": 0}])
        await asyncio.sleep(1.2)
        st = await rpc(s, "getSignatureStatuses", [[sig]])
        v = ((st.get("result") or {}).get("value") or [None])[0]
        if v and v.get("confirmationStatus") in ("confirmed", "finalized"):
            if v.get("err"):
                raise SystemExit(f"tx fallita: {v['err']}")
            return sig
    raise SystemExit(f"tx non confermata: {sig}")


def ix_alt_crea(tab, bump, slot, pagatore):
    return Instruction(ALT_P, struct.pack("<IQB", 0, slot, bump),
                       [AccountMeta(tab, False, True), AccountMeta(KP.pubkey(), True, False),
                        AccountMeta(pagatore.pubkey(), True, True), AccountMeta(SYS, False, False)])


def ix_alt_estendi(tab, pagatore, indirizzi):
    return Instruction(ALT_P, struct.pack("<IQ", 2, len(indirizzi)) + b"".join(bytes(a) for a in indirizzi),
                       [AccountMeta(tab, False, True), AccountMeta(KP.pubkey(), True, False),
                        AccountMeta(pagatore.pubkey(), True, True), AccountMeta(SYS, False, False)])


def ix_alt_disattiva(tab):
    return Instruction(ALT_P, struct.pack("<I", 3), [AccountMeta(tab, False, True),
                                                     AccountMeta(KP.pubkey(), True, False)])


async def tabella(s, indirizzi):
    """Crea + estende una lookup table con questi indirizzi (autorità e pagatore = il wallet)."""
    slot = int((await rpc(s, "getSlot", [{"commitment": "finalized"}]))["result"])
    tab, bump = derive_lookup_table_address(KP.pubkey(), slot)
    pezzi = [indirizzi[i:i + 27] for i in range(0, len(indirizzi), 27)]
    await invia(s, [ix_alt_crea(tab, bump, slot, KP), ix_alt_estendi(tab, KP, pezzi[0])])
    for p in pezzi[1:]:
        await invia(s, [ix_alt_estendi(tab, KP, p)])
    for _ in range(30):
        info = ((await rpc(s, "getAccountInfo", [str(tab), {"encoding": "jsonParsed", "commitment": "confirmed"}]))
                .get("result") or {}).get("value") or {}
        d = (((info.get("data") or {}).get("parsed") or {}).get("info") or {})
        ora = int((await rpc(s, "getSlot", [{"commitment": "confirmed"}]))["result"])
        if len(d.get("addresses") or []) == len(indirizzi) and ora > int(d.get("lastExtendedSlot") or 0):
            return AddressLookupTableAccount(tab, [Pubkey.from_string(a) for a in d["addresses"]])
        await asyncio.sleep(0.6)
    raise SystemExit("lookup table non pronta")


async def main():
    async with aiohttp.ClientSession() as s:
        # 1) trova gli account token vuoti (Tokenkeg + Token-2022)
        vuoti = []
        for prog in (KEG, T22):
            r = await rpc(s, "getTokenAccountsByOwner",
                          [str(KP.pubkey()), {"programId": str(prog)}, {"encoding": "jsonParsed"}])
            for a in (r.get("result") or {}).get("value") or []:
                i = a["account"]["data"]["parsed"]["info"]["tokenAmount"]
                if int(i["amount"] or 0) == 0:
                    vuoti.append(Pubkey.from_string(a["pubkey"]))
        print(f"account vuoti trovati: {len(vuoti)} (rendita ~{len(vuoti) * 0.002039:.4f} SOL)")
        if not vuoti:
            return
        tabelle = []
        # 2) una tx ogni 53, ognuna con la sua lookup table
        for i in range(0, len(vuoti), 53):
            gr = vuoti[i:i + 53]
            bh = (await rpc(s, "getLatestBlockhash", [{"commitment": "confirmed"}]))["result"]["value"]["blockhash"]
            alt = await tabella(s, gr)
            tabelle.append(alt)
            cu = 60_000 + 2_500 * len(gr)
            ixs = [set_compute_unit_limit(cu), set_compute_unit_price(20_000),
                   Instruction(CM, b"", [AccountMeta(KP.pubkey(), True, True),
                                         AccountMeta(KEG, False, False), AccountMeta(T22, False, False)]
                               + [AccountMeta(p, False, True) for p in gr])]
            msg = MessageV0.try_compile(KP.pubkey(), ixs, [alt], Hash.from_string(bh))
            if not GO:
                raw = bytes(VersionedTransaction.populate(msg, [Signature.default()]))
                sim = await rpc(s, "simulateTransaction", [base64.b64encode(raw).decode(), {
                                "encoding": "base64", "sigVerify": False, "replaceRecentBlockhash": True}])
                err = sim.get("error") or ((sim.get("result") or {}).get("value") or {}).get("err")
                print(f"tx {i // 53 + 1}: {len(gr)} conti, {len(raw)} byte — sim err={err}")
                continue
            tx = VersionedTransaction(msg, [KP])
            raw = base64.b64encode(bytes(tx)).decode()
            sig = str(tx.signatures[0])
            for _ in range(25):
                await rpc(s, "sendTransaction", [raw, {"encoding": "base64",
                                                       "skipPreflight": True, "maxRetries": 0}])
                await asyncio.sleep(1.2)
                st = await rpc(s, "getSignatureStatuses", [[sig]])
                v = ((st.get("result") or {}).get("value") or [None])[0]
                if v and v.get("confirmationStatus") in ("confirmed", "finalized"):
                    print(f"tx {i // 53 + 1}: {sig} — err={v.get('err')}")
                    break
        # 3) disattiva le tabelle: l'affitto si recupera chiudendole ~4 minuti dopo
        #    (Solana 4.x: il close è permesso solo a deactivation completa, ~512 slot).
        #    Per chiuderle: ripetere ix_alt_disattiva → attendere ~4 min → invia ix close
        #    (Instruction(ALT_P, struct.pack("<I", 4), [tab w, autorità signer, destinatario w])).
        for alt in tabelle:
            await invia(s, [ix_alt_disattiva(alt.address)])
            print(f"tabella {alt.address} disattivata — chiudibile tra ~4 minuti per riavere l'affitto")
        print("fatto. La rendita degli account è già nel wallet.")


asyncio.run(main())
```

Wallet file: a standard `solana-keygen` keypair file (JSON array of 64 numbers) works as-is.

**Always run it once without `--go`** (simulation only — costs nothing but the table rent)
and check every simulated tx prints `sim err=None`, then re-run with `--go`.

## Zero-code alternative

If your wallet has lots of empty accounts and you prefer a UI: **claimsol.solhousesignal.com**
does exactly this (it was built around this program). Connect, it scans the wallet, and a
claim closes up to **3,000 accounts in one round** — 54 transactions, each with one
confirm popup on Phantom. It charges a commission on the recovered rent.

## License / attribution

The program source is in this repository (`program/src/lib.rs`); it was deployed and is
maintained by the Claim SOL project. You are free to use the program from any dApp or
script — attribution appreciated, not required. The program is immutable-by-authority:
upgrades are possible only by the upgrade authority listed above, so pin the Program ID
(never trust a different address that claims to be "close_many").
