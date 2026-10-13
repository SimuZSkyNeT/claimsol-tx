#!/bin/bash
# Prova LOCALE di claim_close_many, senza faucet devnet: solana-test-validator + deploy + 5 chiusure.
set -e
export PATH="$PATH:/root/.local/share/solana/install/active_release/bin:/root/.cargo/bin"
cd "$(dirname "$0")/.."

[ -f target/deploy/claimsol_close.so ] || { echo "so mancante: prima build.sh"; exit 1; }

LEDGER=$(mktemp -d)
solana-test-validator --reset --ledger "$LEDGER" >/tmp/validator.log 2>&1 &
VPID=$!
trap 'kill $VPID 2>/dev/null; rm -rf "$LEDGER"' EXIT
for i in $(seq 1 60); do solana -u http://127.0.0.1:8899 cluster-version >/dev/null 2>&1 && break; sleep 1; done
solana -u http://127.0.0.1:8899 cluster-version

solana config set --url http://127.0.0.1:8899 >/dev/null
solana config set --keypair keys/test-wallet.json >/dev/null
solana airdrop 10 keys/test-wallet.json | tail -1
echo "saldo wallet: $(solana balance)"

PROG=$(solana-keygen pubkey keys/program.json)
echo "program id: $PROG"
solana program deploy target/deploy/claimsol_close.so --program-id keys/program.json
echo "saldo dopo deploy: $(solana balance)"

# mint + N account distinti li crea lo script Python (la CLI v4 crea solo l'ATA del payer).
/root/solhousesignal/solvenv/bin/python3 scripts/test_close_many.py "$PROG" keys/test-wallet.json 5 http://127.0.0.1:8899
