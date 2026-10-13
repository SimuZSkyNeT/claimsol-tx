#!/bin/bash
# Deploy di claim_close_many su DEVNET + prova reale: 5 token account chiusi con UNA istruzione.
# Non tocca niente di valore: chiavi e SOL solo su devnet.
set -e
export PATH="$PATH:/root/.local/share/solana/install/active_release/bin:/root/.cargo/bin"
cd "$(dirname "$0")/.."
mkdir -p keys

[ -f keys/test-wallet.json ] || solana-keygen new -o keys/test-wallet.json --no-bip39-passphrase --force --silent
[ -f keys/program.json ]    || solana-keygen new -o keys/program.json    --no-bip39-passphrase --force --silent

solana config set --url devnet >/dev/null
solana config set --keypair keys/test-wallet.json >/dev/null

PROG=$(solana-keygen pubkey keys/program.json)
echo "program id: $PROG"

# faucet devnet: molto rate-limitato da questo IP. Se non arriva nulla, usare test_local.sh.
saldo=0
for i in 1 2 3 4 5 6 7 8; do
    solana faucet 2 keys/test-wallet.json >/dev/null 2>&1 || solana airdrop 2 keys/test-wallet.json >/dev/null 2>&1 || true
    saldo=$(solana balance 2>/dev/null | awk '{print $1}')
    echo "tentativo $i → saldo: $saldo SOL"
    [ "$saldo" != "0" ] && break
    sleep 20
done
[ "$saldo" != "0" ] || { echo "faucet devnet irraggiungibile: prova scripts/test_local.sh"; exit 1; }

echo "── build"
cargo build-sbf 2>&1 | tail -2

echo "── deploy"
solana program deploy target/deploy/claimsol_close.so --program-id keys/program.json

echo "── close_many (una tx, una istruzione, 5 chiusure; il setup degli account è dentro lo script)"
/root/solhousesignal/solvenv/bin/python3 scripts/test_close_many.py "$PROG" keys/test-wallet.json 5
