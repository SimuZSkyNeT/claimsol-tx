"""Offline check: build a claim, sign it as the user, co-sign it as the project, and show
that a tampered transaction is refused. No network needed.

    pip install solders
    python -m examples.test_build_and_cosign
"""
from solders.keypair import Keypair
from solders.message import MessageV0, to_bytes_versioned
from solders.hash import Hash
from solders.signature import Signature
from solders.system_program import TransferParams, transfer
from solders.transaction import VersionedTransaction

from claimsol import builder, cosign

user, project, fee_wallet = Keypair(), Keypair(), Keypair().pubkey()
empty = [{"pubkey": str(Keypair().pubkey()), "mint": str(Keypair().pubkey()), "program": "token",
          "rent": 2_039_280, "amount": "0", "decimals": 0} for _ in range(13)]
bh = Hash.default()

# normal claim: the user is the only signer
txs = builder.build(user.pubkey(), empty, [], [], 20, fee_wallet, bh)
for kind, n, rec, fee, extra, raw, msg in txs:
    tx = VersionedTransaction.from_bytes(raw)
    print(f"{kind}: {n} accounts, {len(raw)} bytes, signers={len(tx.signatures)}, "
          f"recovered={rec} fee={fee} ({fee / rec:.0%})")

# small claim with both: 2 empty accounts + 2 tokens to burn go into ONE transaction
dust = [{"pubkey": str(Keypair().pubkey()), "mint": str(Keypair().pubkey()), "program": "token",
         "rent": 2_039_280, "amount": "1000", "decimals": 0} for _ in range(2)]
txs = builder.build(user.pubkey(), empty[:2], dust, [], 20, fee_wallet, bh)
print(f"2 closes + 2 burns: {len(txs)} transaction, {len(txs[0][5])} bytes")

# gas-free claim: project wallet pays the network fee, the user signs first
txs = builder.build(user.pubkey(), empty, [], [], 20, fee_wallet, bh, sponsor=project.pubkey())
built = {t[6] for t in txs}
for *_, raw, msg in txs:
    tx = VersionedTransaction.from_bytes(raw)
    signed = VersionedTransaction.populate(tx.message, [tx.signatures[0], user.sign_message(msg)])
    out = VersionedTransaction.from_bytes(cosign.cosign(bytes(signed), built, project))
    print("gas-free co-signed, both signatures valid:",
          out.signatures[0].verify(project.pubkey(), msg), out.signatures[1].verify(user.pubkey(), msg))

# a wallet that adds Lighthouse guards (like Phantom) is still accepted
from solders.instruction import Instruction, AccountMeta
from solders.pubkey import Pubkey
from claimsol.cosign import LIGHTHOUSE
*_, raw, msg = txs[0]
m = VersionedTransaction.from_bytes(raw).message
keys = list(m.account_keys)
ixs = [Instruction(keys[ix.program_id_index], bytes(ix.data),
                   [AccountMeta(keys[i], m.is_signer(i), m.is_maybe_writable(i)) for i in ix.accounts]) for ix in m.instructions]
guard = Instruction(Pubkey.from_string(LIGHTHOUSE), b"\x01", [AccountMeta(Keypair().pubkey(), False, True)])
m2 = MessageV0.try_compile(project.pubkey(), ixs + [guard], [], bh)
signed = VersionedTransaction.populate(m2, [Signature.default(), user.sign_message(to_bytes_versioned(m2))])
cosign.cosign(bytes(signed), built, project)
print("wallet-added Lighthouse guard: accepted")

# attack: a transaction we didn't build (drain the project wallet) is refused
evil = MessageV0.try_compile(project.pubkey(), [transfer(TransferParams(
    from_pubkey=project.pubkey(), to_pubkey=user.pubkey(), lamports=10**9))], [], bh)
try:
    cosign.cosign(bytes(VersionedTransaction.populate(evil, [Signature.default()] * 2)), built, project)
    print("BUG: evil transaction co-signed")
except ValueError as e:
    print("evil transaction refused:", e)
