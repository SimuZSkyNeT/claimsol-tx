"""Gas-free claims: when the server is allowed to add its signature.

On a gas-free claim the project wallet is the fee payer (signature #0) and the user is signer
#1. The user signs first, with signTransaction (as Phantom recommends for multi-signer
transactions); then the server adds its signature ONLY if:

  1. the message is byte-for-byte identical to one the server built for this claim, and
  2. the user's signature verifies against that exact message.

So the project key can never be used to sign anything else, and nobody can get it to pay for
a transaction the user didn't sign.
"""
from solders.message import to_bytes_versioned
from solders.transaction import VersionedTransaction


def cosign(tx_bytes, built_messages, project_keypair):
    """-> co-signed transaction bytes, or raises ValueError."""
    tx = VersionedTransaction.from_bytes(tx_bytes)
    msg = to_bytes_versioned(tx.message)
    if msg not in built_messages:
        raise ValueError("transaction was changed")
    keys = tx.message.account_keys
    if len(tx.signatures) != 2 or keys[0] != project_keypair.pubkey():
        raise ValueError("not a gas-free claim")
    if not tx.signatures[1].verify(keys[1], msg):
        raise ValueError("transaction not signed by the wallet")
    return bytes(VersionedTransaction.populate(tx.message, [project_keypair.sign_message(msg), tx.signatures[1]]))
