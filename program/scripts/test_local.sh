#!/bin/bash
# LOCAL test of close_many, no devnet faucet needed: solana-test-validator + deploy + 5 closures.
set -e
export PATH="$PATH:$HOME/.local/share/solana/install/active_release/bin:$HOME/.cargo/bin"
cd "$(dirname "$0")/.."

[ -f target/deploy/claimsol_close.so ] || { echo ".so missing: run build.sh first"; exit 1; }

LEDGER=$(mktemp -d)
solana-test-validator --reset --ledger "$LEDGER" >/tmp/validator.log 2>&1 &
VPID=$!
trap 'kill $VPID 2>/dev/null; rm -rf "$LEDGER"' EXIT
for i in $(seq 1 60); do solana -u http://127.0.0.1:8899 cluster-version >/dev/null 2>&1 && break; sleep 1; done
solana -u http://127.0.0.1:8899 cluster-version

mkdir -p keys
[ -f keys/test-wallet.json ] || solana-keygen new -o keys/test-wallet.json --no-bip39-passphrase --force --silent
[ -f keys/program.json ]    || solana-keygen new -o keys/program.json    --no-bip39-passphrase --force --silent
solana config set --url http://127.0.0.1:8899 >/dev/null
solana config set --keypair keys/test-wallet.json >/dev/null
solana airdrop 10 keys/test-wallet.json | tail -1
echo "wallet balance: $(solana balance)"

PROG=$(solana-keygen pubkey keys/program.json)
echo "program id: $PROG"
solana program deploy target/deploy/claimsol_close.so --program-id keys/program.json
echo "balance after deploy: $(solana balance)"

# the Python script creates the mint and N distinct accounts (CLI v4 only creates the payer's ATA)
python3 scripts/test_close_many.py "$PROG" keys/test-wallet.json 5 http://127.0.0.1:8899
