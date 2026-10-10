# Contributing to Claim SOL

Thanks for helping make Claim SOL safer and better. This repository holds the code that
builds every transaction users sign, so every change is reviewed with one question first:
**does it still move only rent back to the owner, plus our visible fee?**

## Good first contributions

- **New wallet support** in [`web/wallet.js`](web/wallet.js): a wallet that does not connect
  or sign correctly. Tell us the wallet, the browser and what happened.
- **Edge cases** in the builders: token accounts that should be closable but are skipped,
  Token-2022 extensions, NFTs with unusual metadata.
- **Tests**: more cases in [`examples/test_build_and_cosign.py`](examples/test_build_and_cosign.py),
  especially transactions that must be refused.
- **Docs and translations** of the README.

## How to propose a change

1. Open an issue describing the problem or idea (a transaction signature helps a lot).
2. Fork, create a branch, keep the change small and focused.
3. Run `python -m examples.test_build_and_cosign` and make sure every line still passes.
4. Open a pull request explaining what changes in the transactions, if anything.

## Rules that never change

- No token approvals, delegations or `SetAuthority`.
- No instruction that moves the user's tokens to anyone.
- One visible fee transfer per transaction, shown in the UI before signing.
- Every transaction is simulated before the user is asked to sign it.

Security issues: please follow [SECURITY.md](SECURITY.md) and report privately.
