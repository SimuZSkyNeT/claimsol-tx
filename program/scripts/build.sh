#!/bin/bash
# Build the program (the first run downloads platform-tools, ~5-10 minutes)
set -e
export PATH="$PATH:$HOME/.local/share/solana/install/active_release/bin:$HOME/.cargo/bin"
cd "$(dirname "$0")/.."
cargo build-sbf
ls -la target/deploy/claimsol_close.so
