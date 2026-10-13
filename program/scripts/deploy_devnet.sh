#!/bin/bash
# Deploy close_many to DEVNET and run a real test: 5 token accounts closed with ONE instruction.
# Nothing of value is touched: keys and SOL are devnet only.
set -e
export PATH="$PATH:$HOME/.local/share/solana/install/active_release/bin:$HOME/.cargo/bin"
cd "$(dirname "$0")/.."
mkdir -p keys

[ -f keys/test-wallet.json ] || solana-keygen new -o keys/test-wallet.json --no-bip39-passphrase --force --silent
[ -f keys/program.json ]    || solana-keygen new -o keys/program.json    --no-bip39-passphrase --force --silent

solana config set --url devnet >/dev/null
solana config set --keypair keys/test-wallet.json >/dev/null

PROG=$(solana-keygen pubkey keys/program.json)
echo "program id: $PROG"

# the devnet faucet is heavily rate-limited: if nothing arrives, use test_local.sh
balance=0
for i in 1 2 3 4 5 6 7 8; do
    solana faucet 2 keys/test-wallet.json >/dev/null 2>&1 || solana airdrop 2 keys/test-wallet.json >/dev/null 2>&1 || true
    balance=$(solana balance 2>/dev/null | awk '{print $1}')
    echo "attempt $i: balance $balance SOL"
    [ "$balance" != "0" ] && break
    sleep 20
done
[ "$balance" != "0" ] || { echo "devnet faucet unreachable: try scripts/test_local.sh"; exit 1; }

echo "── build"
cargo build-sbf 2>&1 | tail -2

echo "── deploy"
solana program deploy target/deploy/claimsol_close.so --program-id keys/program.json

echo "── close_many (one tx, one instruction, 5 closures; the script creates the accounts)"
python3 scripts/test_close_many.py "$PROG" keys/test-wallet.json 5
