# close_many

A tiny Solana program that closes many empty token accounts of the signer in **one
instruction**. Claim SOL uses it for bigger claims, so a wallet with hundreds of empty accounts
needs far fewer approvals.

| | |
|---|---|
| Program id | [`J9CwiaxYkQPtr2UDtEsD5EtEePmKxwPWczuH4oAeb4HR`](https://solscan.io/account/J9CwiaxYkQPtr2UDtEsD5EtEePmKxwPWczuH4oAeb4HR) |
| Verified build | ✅ [OtterSec verify status](https://verify.osec.io/status/J9CwiaxYkQPtr2UDtEsD5EtEePmKxwPWczuH4oAeb4HR): the on-chain binary matches this source at commit `b904fd5` |
| Source | [`src/lib.rs`](src/lib.rs), about 80 lines, `solana-program` only |
| Upgrade authority | **none**: permanently revoked on 13/10/2026 (`set-upgrade-authority --final`). The deployed binary can never be changed by anyone, us included ([OtterSec](https://verify.osec.io/status/J9CwiaxYkQPtr2UDtEsD5EtEePmKxwPWczuH4oAeb4HR): `is_frozen: true`) |

## What it does, and what it cannot do

One instruction, empty data:

```
accounts: [0]  owner             signer, authority of every account below, receives the rent
          [1]  Token program     TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA (readonly)
          [2]  Token-2022        TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb (readonly)
          [3..] token accounts to close, any mix of Token and Token-2022
```

For every account it makes one CPI: `CloseAccount` (instruction 9) on the official Token or
Token-2022 program, with **destination = authority = the signer**. That is the only code path:

- the signer must sign, so nobody can close someone else's accounts;
- the token programs themselves refuse to close an account that still holds tokens, or whose
  close authority is not the signer;
- an account owned by any other program makes the whole instruction fail;
- there are no transfers, approvals, delegations or authority changes in the code.

The two token programs are passed as accounts because `invoke()` needs the account of the
program it calls.

## Limits

Solana allows 64 accounts per transaction, counting the ones loaded from a lookup table.
Claim SOL puts **at most 56 closures** in one transaction (57 was measured as the exact maximum
with its 7 static accounts, 58 fails with `TooManyAccountLocks`), and keeps each transaction
under 850 bytes so wallets have room for their own guard instructions. Each closure costs about
2,500 compute units.

It is only used when the user pays the network fee (one signer). Gas-free claims keep the
classic path.

## Verify it yourself

```console
$ cargo install solana-verify
$ solana-verify verify-from-repo -u mainnet \
    --program-id J9CwiaxYkQPtr2UDtEsD5EtEePmKxwPWczuH4oAeb4HR \
    https://github.com/SimuZSkyNeT/claimsol-tx \
    --commit-hash b904fd5714a569f0f1bada982ae6004e94e2d7d4 \
    --mount-path program --library-name claimsol_close \
    --base-image solanafoundation/solana-verifiable-build:4.3.0 --arch v3
```

The build runs in Docker and compares the hash of the result with the program on-chain
(`761a26eb…`). The same parameters are stored on-chain in the verification PDA
`4nDZoR1AM8KQi1GYGL5haPFQadojpGZjeUVLPSFYz95E`.

## Files

| File | What |
|---|---|
| `src/lib.rs` | the program |
| `scripts/build.sh` | local build |
| `scripts/test_local.sh`, `scripts/test_close_many.py` | local validator test: deploy, create accounts, close them in one instruction |
| `scripts/smoke_mainnet.py` | mainnet smoke test: create one empty account and close it |
| `SHARE.md` | standalone guide and script to close your own accounts with the program, without the site |
