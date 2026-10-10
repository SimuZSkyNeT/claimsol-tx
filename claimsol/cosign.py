"""Gas-free claims: when the server is allowed to add its signature.

On a gas-free claim the project wallet is the fee payer (signature #0) and the user is signer
#1. The user signs first, with signTransaction (as Phantom recommends for multi-signer
transactions); then the server adds its signature ONLY if the transaction is one it built.

Wallets may change the transaction before signing it: Phantom adds Lighthouse guard
instructions and can adjust the compute budget. A changed transaction is accepted only if:

  1. the fee payer is unchanged;
  2. it still contains ALL our instructions, in order (compared by account addresses);
  3. every extra instruction belongs to Lighthouse (read-only assertions, it cannot move
     funds) or to the ComputeBudget program;
  4. the priority fee it would make the project wallet pay stays under MAX_PRIORITY_LAMPORTS;
  5. the user's signature verifies against the exact message being co-signed.

Anything else (an extra transfer, a missing instruction, a different program) is refused, so
the project key can never be used to sign a transaction we did not build.
"""
from solders.message import MessageV0, to_bytes_versioned
from solders.transaction import VersionedTransaction

COMPUTE_BUDGET = "ComputeBudget111111111111111111111111111111"
LIGHTHOUSE = "L2TExMFKdjpN9kozasaurPirfHy9P8sbXoAN1qA3S95"
MAX_PRIORITY_LAMPORTS = 100_000


def _instructions(msg):
    """(program, account addresses, data) for each non-ComputeBudget instruction."""
    keys = [str(k) for k in msg.account_keys]
    return [(keys[ix.program_id_index], tuple(keys[i] for i in ix.accounts), bytes(ix.data))
            for ix in msg.instructions if keys[ix.program_id_index] != COMPUTE_BUDGET]


def _priority_lamports(msg):
    keys = [str(k) for k in msg.account_keys]
    limit, price = 200_000, 0
    for ix in msg.instructions:
        if keys[ix.program_id_index] != COMPUTE_BUDGET:
            continue
        d = bytes(ix.data)
        if d[:1] == b"\x02":
            limit = int.from_bytes(d[1:5], "little")
        elif d[:1] == b"\x03":
            price = int.from_bytes(d[1:9], "little")
        elif d[:1] not in (b"\x01", b"\x04"):
            return None                                   # unknown ComputeBudget instruction
    return limit * price // 1_000_000


def matching_build(msg, built_messages):
    """The message we built that `msg` corresponds to (identical, or changed only in the
    allowed ways), else None."""
    raw = to_bytes_versioned(msg)
    if raw in built_messages:
        return raw
    prio = _priority_lamports(msg)
    if prio is None or prio > MAX_PRIORITY_LAMPORTS:
        return None
    theirs = _instructions(msg)
    for built in built_messages:
        ours_msg = MessageV0.from_bytes(built[1:])
        if ours_msg.account_keys[0] != msg.account_keys[0]:
            continue
        ours, i, ok = _instructions(ours_msg), 0, True
        for x in theirs:
            if i < len(ours) and x == ours[i]:
                i += 1
            elif x[0] != LIGHTHOUSE:
                ok = False
                break
        if ok and i == len(ours):
            return built
    return None


def cosign(tx_bytes, built_messages, project_keypair):
    """-> co-signed transaction bytes, or raises ValueError."""
    tx = VersionedTransaction.from_bytes(tx_bytes)
    keys = tx.message.account_keys
    if len(tx.signatures) != 2 or keys[0] != project_keypair.pubkey():
        raise ValueError("not a gas-free claim")
    if matching_build(tx.message, built_messages) is None:
        raise ValueError("transaction was changed")
    msg = to_bytes_versioned(tx.message)
    if not tx.signatures[1].verify(keys[1], msg):
        raise ValueError("transaction not signed by the wallet")
    return bytes(VersionedTransaction.populate(tx.message, [project_keypair.sign_message(msg), tx.signatures[1]]))
