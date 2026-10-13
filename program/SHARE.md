# close_many: close up to 53 empty token accounts with ONE click

A public Solana program (no fees, no permissions, source available) that closes many empty
token accounts in a **single transaction**, including on wallets where Phantom blocks
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
| Upgrade authority | **none, permanently revoked** (`set-upgrade-authority --final`, 13/10): the deployed binary can never be changed by anyone, not even by the deployer |
| Source | Rust `solana-program`, no macros, ~22.5 KB, readable in `program/src/lib.rs` of this repo |
| Cost per claim | only the normal network fee (~5,000 lamports + priority), the program takes nothing |

Verify it yourself in 30 seconds (read-only):

```
solana program show J9CwiaxYkQPtr2UDtEsD5EtEePmKxwPWczuH4oAeb4HR
```

and decompile/read the accounts on any explorer, the whole logic is the CPI
`CloseAccount` loop below, nothing else.

## Instruction format

```
accounts: [0] owner     : writable SIGNER; authority of every token account; receives all rent
          [1] Tokenkeg  : readonly (required for CPI)
          [2] Token-2022: readonly (required for CPI)
          [3..] token accounts to close (max ~53): writable
data:     empty (b""): ignored by the program
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
  protocol cap counts the *expanded* message, static accounts + the ones loaded from the lookup
  table. A typical tx has 7 static accounts (payer, 2 token programs, fee receiver, close_many,
  ComputeBudget, System), so 7 + N ≤ 64 → N ≤ 57. At 58 the bank rejects the tx
  (`TooManyAccountLocks`). Use **≤ 56** to keep 1 account of margin.
- **Transaction size**: ~511 bytes WITH an Address Lookup Table. Without a table the same
  tx is ~2,039 bytes, over the 1,232 protocol cap and rejected, so an ALT is mandatory
  for more than a handful of accounts. The ALT costs ~0.0096 SOL of rent (recoverable).
- **Compute**: ~172,500 CU for 53 closes. Budget: `set_compute_unit_limit(60_000 + 2_500 × n)`,
  `set_compute_unit_price(20_000)`.
- **Only empty accounts**: `CloseAccount` succeeds only when the token balance is 0.
  Accounts with dust must be burned/closed the classic way first.
- **Phantom**: a single-instruction close_many tx passes the Phantom origin gate with a
  normal "Confirm Transaction" popup (verified with real Phantom 26.33 on the
  claimsol.solhousesignal.com origin). The program label shows as "Unknown · Program J9Cwi…"
  because wallets keep program names in their own curated database, not on-chain: cosmetic
  only, it does not affect the popup or the transaction.
- **Explorer verification ✅**: the on-chain binary is byte-identical to this repo's source
  build (solana-verify / OtterVerify, verified 13/10/2026, repo pinned at commit `b904fd5`,
  build recipe `solana-verifiable-build:4.3.0`, arch `v3`). Solscan and other explorers that
  index OtterVerify show the "Verified" badge on the program address.
- **No second signer**: Phantom blocks 2-signer transactions, so close_many txs must be
  paid by the owner itself (no fee-payer sponsor).
- **ALT lifecycle (Solana 4.x)**: a lookup table can only be closed ~512 slots after its
  deactivation ("fully deactivated"). The script below deactivates the tables at the end;
  recover the rent by closing them ~4 minutes later (the close instruction is included).

## Ready-to-use script (python, solders)

```bash
pip install solders aiohttp
```

`close_accounts.py`:

```python
# Closes ALL the empty token accounts of the wallet, one instruction per 53 accounts.
# Usage: python3 close_accounts.py wallet.json [--go]     (without --go = simulation)
# Needs ~0.01 SOL for each 53-account lookup table (the rent comes back: see the end).
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

RPC = "https://api.mainnet-beta.solana.com"          # any public RPC
CM = Pubkey.from_string("J9CwiaxYkQPtr2UDtEsD5EtEePmKxwPWczuH4oAeb4HR")
KEG = Pubkey.from_string("TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA")
T22 = Pubkey.from_string("TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb")
ALT_P = Pubkey.from_string("AddressLookupTab1e1111111111111111111111111")
SYS = Pubkey.from_string("11111111111111111111111111111111")
GO = "--go" in sys.argv
KP = Keypair.from_bytes(bytes(json.load(open(sys.argv[1]))))   # standard solana-keygen file


async def rpc(s, m, p):
    async with s.post(RPC, json={"jsonrpc": "2.0", "id": 1, "method": m, "params": p}) as r:
        return await r.json()


async def send(s, ixs, payer=KP):
    """Send a tx paid by the wallet (production pattern: skipPreflight + retry)."""
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
                raise SystemExit(f"tx failed: {v['err']}")
            return sig
    raise SystemExit(f"tx not confirmed: {sig}")


def ix_alt_create(tab, bump, slot, payer_kp):
    return Instruction(ALT_P, struct.pack("<IQB", 0, slot, bump),
                       [AccountMeta(tab, False, True), AccountMeta(KP.pubkey(), True, False),
                        AccountMeta(payer_kp.pubkey(), True, True), AccountMeta(SYS, False, False)])


def ix_alt_extend(tab, payer_kp, addresses):
    return Instruction(ALT_P, struct.pack("<IQ", 2, len(addresses)) + b"".join(bytes(a) for a in addresses),
                       [AccountMeta(tab, False, True), AccountMeta(KP.pubkey(), True, False),
                        AccountMeta(payer_kp.pubkey(), True, True), AccountMeta(SYS, False, False)])


def ix_alt_deactivate(tab):
    return Instruction(ALT_P, struct.pack("<I", 3), [AccountMeta(tab, False, True),
                                                     AccountMeta(KP.pubkey(), True, False)])


async def lookup_table(s, addresses):
    """Create + extend a lookup table with these addresses (authority and payer = the wallet)."""
    slot = int((await rpc(s, "getSlot", [{"commitment": "finalized"}]))["result"])
    tab, bump = derive_lookup_table_address(KP.pubkey(), slot)
    chunks = [addresses[i:i + 27] for i in range(0, len(addresses), 27)]
    await send(s, [ix_alt_create(tab, bump, slot, KP), ix_alt_extend(tab, KP, chunks[0])])
    for p in chunks[1:]:
        await send(s, [ix_alt_extend(tab, KP, p)])
    for _ in range(30):
        info = ((await rpc(s, "getAccountInfo", [str(tab), {"encoding": "jsonParsed", "commitment": "confirmed"}]))
                .get("result") or {}).get("value") or {}
        d = (((info.get("data") or {}).get("parsed") or {}).get("info") or {})
        now = int((await rpc(s, "getSlot", [{"commitment": "confirmed"}]))["result"])
        if len(d.get("addresses") or []) == len(addresses) and now > int(d.get("lastExtendedSlot") or 0):
            return AddressLookupTableAccount(tab, [Pubkey.from_string(a) for a in d["addresses"]])
        await asyncio.sleep(0.6)
    raise SystemExit("lookup table not ready")


async def main():
    async with aiohttp.ClientSession() as s:
        # 1) find the empty token accounts (Tokenkeg + Token-2022)
        empty = []
        for prog in (KEG, T22):
            r = await rpc(s, "getTokenAccountsByOwner",
                          [str(KP.pubkey()), {"programId": str(prog)}, {"encoding": "jsonParsed"}])
            for a in (r.get("result") or {}).get("value") or []:
                i = a["account"]["data"]["parsed"]["info"]["tokenAmount"]
                if int(i["amount"] or 0) == 0:
                    empty.append(Pubkey.from_string(a["pubkey"]))
        print(f"empty accounts found: {len(empty)} (rent ~{len(empty) * 0.002039:.4f} SOL)")
        if not empty:
            return
        tables = []
        # 2) one tx every 53 accounts, each with its own lookup table
        for i in range(0, len(empty), 53):
            gr = empty[i:i + 53]
            bh = (await rpc(s, "getLatestBlockhash", [{"commitment": "confirmed"}]))["result"]["value"]["blockhash"]
            alt = await lookup_table(s, gr)
            tables.append(alt)
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
                print(f"tx {i // 53 + 1}: {len(gr)} accounts, {len(raw)} bytes, sim err={err}")
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
                    print(f"tx {i // 53 + 1}: {sig}, err={v.get('err')}")
                    break
        # 3) deactivate the tables: their rent comes back by closing them ~4 minutes later
        #    (Solana 4.x: close is allowed only after full deactivation, ~512 slots).
        #    To close them: wait ~4 min after ix_alt_deactivate, then send the close ix
        #    (Instruction(ALT_P, struct.pack("<I", 4), [table w, authority signer, recipient w])).
        for alt in tables:
            await send(s, [ix_alt_deactivate(alt.address)])
            print(f"table {alt.address} deactivated, can be closed in ~4 minutes to get its rent back")
        print("done. The rent of the accounts is already in the wallet.")


asyncio.run(main())
```

Wallet file: a standard `solana-keygen` keypair file (JSON array of 64 numbers) works as-is.

**Always run it once without `--go`** (simulation only, costs nothing but the table rent)
and check every simulated tx prints `sim err=None`, then re-run with `--go`.

## Zero-code alternative

If your wallet has lots of empty accounts and you prefer a UI: **claimsol.solhousesignal.com**
does exactly this (it was built around this program). Connect, it scans the wallet, and a
claim closes up to **3,000 accounts in one round**, 54 transactions, each with one
confirm popup on Phantom. It charges a commission on the recovered rent.

## License / attribution

The program source is in this repository (`program/src/lib.rs`); it was deployed and is
maintained by the Claim SOL project. You are free to use the program from any dApp or
script, attribution appreciated, not required. The program is **immutable**: its upgrade
authority has been permanently revoked (`set-upgrade-authority --final`), so the deployed
binary can never change. If a new version is ever needed it will live at a different
address. Pin this Program ID (never trust a different address that claims to be
"close_many").
