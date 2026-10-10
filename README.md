# Claim SOL — transaction code

This is the code that builds **every transaction** signed on
[claimsol.solhousesignal.com](https://claimsol.solhousesignal.com), published so that anyone
can check exactly what users are asked to sign.

Claim SOL gives back the SOL locked in old token accounts. Every token you trade on Solana
opens an account that holds ~0.002 SOL of rent; when the balance goes to zero the account
stays open and the SOL stays locked. Claim SOL closes those accounts and the rent goes back
to **your** wallet. We keep a service fee, a fixed percentage of what is recovered, sent as a
separate, visible transfer.

## What a transaction can contain — and nothing else

| Instruction | When | Effect |
|---|---|---|
| ComputeBudget limit / price | always | network priority |
| Token `CloseAccount` (9) | every empty account you select | rent goes to **your** wallet; you are the authority |
| Token `BurnChecked` (15) + `CloseAccount` | only tokens you tick to burn | burns **your own** leftover balance of that token |
| Metaplex `BurnV1` | only NFTs you tick to burn | rent of token + metadata + edition back to you |
| Jupiter swap → SOL + `CloseAccount` | only tokens you tick "Sell" | you get the SOL |
| System `Transfer` user → fee wallet | once per transaction | our service fee, shown before signing |
| System `Transfer` user → project wallet | gas-free claims only | refunds the network fee we paid for you |

There are **no** token approvals, delegations, `SetAuthority`, or transfers of your tokens to
anyone. The server re-reads every account from the chain: the browser only says which of your
own accounts to include.

## Safety properties

- **One signer** (you). Gas-free claims have two signers: you sign first, then the server
  co-signs **only** a message byte-for-byte identical to one it built for you, and only after
  verifying your signature on it — see [`claimsol/cosign.py`](claimsol/cosign.py).
- **Small transactions**: at most 850 bytes (Solana's limit is 1232), with compute-unit
  headroom, so wallets can add their own guard instructions (Phantom Lighthouse).
- **Simulated before you sign**: every transaction is simulated with `sigVerify: false`; one
  that would fail is dropped and never shown to your wallet —
  [`claimsol/simulate.py`](claimsol/simulate.py).
- **Phantom sends it itself** with `signAndSendAllTransactions` (one approval), so Phantom's
  own protections apply — [`web/wallet.js`](web/wallet.js) is the exact file served by the site.
- **Public record**: every claim is listed with its on-chain signature in the
  [live explorer](https://claimsol.solhousesignal.com/explorer/).

## Files

| File | What |
|---|---|
| [`claimsol/builder.py`](claimsol/builder.py) | builds the close / burn / NFT transactions and the fee transfer |
| [`claimsol/swap.py`](claimsol/swap.py) | "Sell" option: Jupiter swap + close + fee |
| [`claimsol/nft.py`](claimsol/nft.py) | Metaplex `BurnV1` for junk NFTs |
| [`claimsol/simulate.py`](claimsol/simulate.py) | pre-signature simulation |
| [`claimsol/cosign.py`](claimsol/cosign.py) | when the server may co-sign a gas-free claim |
| [`web/wallet.js`](web/wallet.js) | browser side: wallet connection and signing, as served |
| [`examples/test_build_and_cosign.py`](examples/test_build_and_cosign.py) | offline check, including a refused tampered transaction |

```
pip install solders
python -m examples.test_build_and_cosign
```

## Check a transaction yourself

Open any signature from the explorer on [Solscan](https://solscan.io): you will see only the
instructions listed above, the rent landing in the user's own wallet, and one fee transfer.

## Contact

SolHouse Signal · Telegram [@SimuZT](https://t.me/SimuZT) ·
[solhousesignal.com](https://solhousesignal.com)

## License

MIT
