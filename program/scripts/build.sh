#!/bin/bash
# Compila il programma (la prima volta scarica platform-tools, ~5-10 minuti)
set -e
export PATH="$PATH:/root/.local/share/solana/install/active_release/bin:/root/.cargo/bin"
cd "$(dirname "$0")/.."
cargo build-sbf
ls -la target/deploy/claimsol_close.so
