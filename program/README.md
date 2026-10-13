# claim_close_many — programma on-chain per Claim SOL

## Perché

Phantom blocca le transazioni con più di ~32 istruzioni, quindi il flusso classico di Claim SOL
impacchetta al massimo 25 chiusure per transazione (una approvazione ognuna). Questo programma
fa lo stesso lavoro con **una sola istruzione**: il tetto diventa il limite di protocollo di
64 account per transazione, non i ~32 ix di Phantom. 300 account = ~6 approvazioni invece di 12.

## Cosa fa (e cosa NON può fare)

Una istruzione, dati vuoti:

```
accounts: [0] owner      — firmatario, authority di ogni token account, e destinatario della rendita
          [1] programma Tokenkeg (readonly)   — servono alla CPI: invoke() esige l'account
          [2] programma Token-2022 (readonly)   del programma invocato tra gli account passati
          [3..] token account da chiudere (max ~53: il resto serve a fee transfer e guardie wallet)
```

Per ogni token account esegue una CPI `CloseAccount` (ix 9) su Tokenkeg **o** Token-2022 con
destinazione = authority = il firmatario. Se un account non appartiene ai due programmi token,
l'istruzione fallisce. Non esiste nessun altro ramo di codice: niente trasferimenti, niente
approvazioni, niente deleghe. Il sorgente è pubblicato qui proprio perché gli utenti possano
verificarlo (stesso principio del resto del progetto).

## Costi e limiti

- CU: ~2k per chiusura + overhead → limite 400.000 copre 53+ account.
- CPI verificata sul processore token MODERNO (solana 4.x): `CloseAccount` vuole
  `[source, destination, authority firmatario]` — nessun account extra anche per Token-2022.
  GOTCHA solo per il test locale: `InitializeAccount` moderno vuole 4 account
  `[account, mint, OWNER, rent]` (l'owner come account è una novità rispetto al classico).
- Account: 1 owner + 2 programmi token + 1 programma + 1 fee wallet + 53 token = 58; Lighthouse
  di Phantom ne può aggiungere 2-3 → resta sotto il tetto di 64. NON superare 53 chiusure per tx.
- Con lo sponsor (gas-free, 2 firmatari) NON usare il programma per ora: il percorso classico
  resta quello.

## Stato

| passo | stato |
|---|---|
| sorgente + build (`scripts/build.sh`) | ✅ |
| prova locale (`scripts/test_local.sh`: validator + deploy + 5 chiusure in 1 ix) | ✅ 5/5 chiusi, rendita +0.0102 SOL rientrata al wallet |
| deploy devnet (`scripts/deploy_devnet.sh`) | non necessario (mainnet fatto) |
| deploy mainnet | ✅ 12/10/2026, slot 456.190.497, costo 0,1166 SOL dal wallet progetto |
| smoke test mainnet (`scripts/smoke_mainnet.py`: crea e chiude 1 account vuoto) | ✅ tx `67XTfAXY…`, rendita +0,002026 SOL rientrata |
| probe D nel harness (`/dev/phantom.html`: scan vuoti + tx close_many da firmare) | ✅ costruito e servito |
| test Phantom su mainnet (l'avviso «Unknown program» è il rischio da misurare) | ✅ 12/10 Phantom 26.33.0 reale (server-side, xvfb+playwright): popup «Confirm Transaction» NORMALE, niente «Request blocked»; in Advanced l'istruzione è «Unknown · Program J9Cwi…» = etichetta neutra, nessun banner. **Firmata, inviata e confermata**: tx `PAFmnLBY…`, 2 chiusure, rendita +0,00406556 SOL, 4.669 CU (2 chiusure) → ~53 chiusure ≈ 40k CU |
| integrazione in `/api/reclaim/build` (nuovo ramo: gruppi da 55 via close_many) | ✅ 13/10: flag `USE_CLOSE_MANY=1` in .env, ramo «cm» dietro `len(chiudi) > MAX_CLOSE_TX and not sponsor` con ALT per blocco e fallback classico; API riavviata e verificata |

## Verifica a piena densità (13/10, harness `/root/phantom_test/cm_harness.py`)

Tx cm da **53 account** (4 Tokenkeg + 49 Token-2022 — entrambi i rami CPI in una istruzione), ALT vera
on-chain, compilata e simulata con gli stessi parametri di api.py (CUL 60.000 + 53×2.500, CUP 20k,
fee 15%):

- **byte: 511** (tetto nostro 850) — margine per Lighthouse/aggiunte Phantom
- **simulazione: passa** (err None), **CU consumate: 172.522** contro budget 192.500 — il budget regge
- ramo **Token-2022 verificato on-chain** con account vero (close_many chiude un account T22, rendita
  rientrata; tx `2dJRVMWX…`). Il mint WSOL NON va usato per account T22 (`IncorrectProgramId`):
  serve un mint T22 vero (InitializeMint2, tag 20 — il 22 è InitializeImmutableOwner).
- GOTCHA ALT su solana 4.x: il **close della lookup table richiede ~512 slot dopo la disattivazione**
  («Table cannot be closed until it's fully deactivated»): il custode deve rispettare l'attesa.
- Il wallet progetto deve avere ≥ ~0,025 SOL per creare le tabelle (soglia `_tabella`: rent +
  SPONSOR_FLOOR + 20M); sotto, il ramo cm degrada alla via classica da solo.

## Programma su mainnet

- Program Id: **`J9CwiaxYkQPtr2UDtEsD5EtEePmKxwPWczuH4oAeb4HR`**
- ProgramData: `8UujbWy7UqZEB3Gp2GLdb8tMPVLb8QcRF3WD2mEMRyP9`
- Authority (upgrade) e beneficiario della chiusura: il wallet progetto (stessa chiave che paga le fee)
- Chiave del programma: `program/keys/program_mainnet.json` (gitignored, fuori dal repo)
- 22.576 byte; chiusura = 1 comando `solana program close` e la rendita torna al wallet

## Checklist post-deploy

1. ✅ `solana program deploy` con `--url` RPC progetto + `--keypair` wallet progetto (flag, senza toccare la config globale)
2. ✅ chiave programma dedicata `keys/program_mainnet.json`, `.gitignore` nel program/
3. ✅ deploy slot 456.190.497, ProgramData + Authority verificati con `program show`
4. ⏳ verificare su solscan + richiedere la verifica del programma (Soteria/otter, fonte = questo repo)
5. ✅ test con Phantom vero su tx close_many: gate passato, «Unknown program» neutrale (vedi tabella Stato).
   Resta la verifica a 55 chiusure (stesso formato, solo più conti: nessun motivo tecnico di differenza).

## GOTCHA deploy

- Primo tentativo fallito con **«Error: Custom: Invalid blockhash»** (RPC laggante): il deploy è
  atomico, non lascia buffer né spende nulla; basta ritentare con un blockhash fresco.
