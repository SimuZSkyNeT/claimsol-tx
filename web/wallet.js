/* SolHouse Signal Tools — connettore universale per i wallet Solana.
 *
 * 1) Wallet Standard (Phantom, Solflare, Backpack, Glow, OKX, Coinbase, Trust, Bitget,
 *    Exodus, Magic Eden, …): scoperti con l'evento standard, firmano byte grezzi.
 * 2) Provider "vecchi" iniettati (window.phantom.solana, window.solflare, …): firmano
 *    oggetti web3.js → si usa la copia locale di @solana/web3.js solo per loro.
 * 3) Su telefono senza wallet nel browser: link per aprire la pagina DENTRO l'app.
 * Nessuna chiave privata passa mai di qui: il wallet firma e basta.
 */
(function () {
    const CHAIN = "solana:mainnet";
    const std = [];                       // wallet standard registrati
    function registra(...ws) {
        for (const w of ws) {
            if (!w || std.includes(w)) continue;
            const ok = (w.chains || []).some(c => c.startsWith("solana:")) &&
                w.features && w.features["standard:connect"] &&
                (w.features["solana:signTransaction"] || w.features["solana:signAndSendTransaction"]);
            if (ok) std.push(w);
        }
        document.dispatchEvent(new CustomEvent("sh-wallets-changed"));
        return () => {};
    }
    window.addEventListener("wallet-standard:register-wallet", e => {
        try { e.detail({ register: registra }); } catch (_) {}
    });
    try {
        window.dispatchEvent(new CustomEvent("wallet-standard:app-ready", { detail: { register: registra } }));
    } catch (_) {}

    // provider vecchi: [nome, funzione che lo trova, icona]
    const LEGACY = [
        ["Phantom", () => window.phantom && window.phantom.solana && window.phantom.solana.isPhantom && window.phantom.solana],
        ["Solflare", () => window.solflare && window.solflare.isSolflare && window.solflare],
        ["Backpack", () => window.backpack && window.backpack.isBackpack && window.backpack],
        ["Glow", () => window.glowSolana],
        ["OKX Wallet", () => window.okxwallet && window.okxwallet.solana],
        ["Coinbase Wallet", () => window.coinbaseSolana],
        ["Trust Wallet", () => window.trustwallet && window.trustwallet.solana],
        ["Bitget Wallet", () => window.bitkeep && window.bitkeep.solana],
        ["Exodus", () => window.exodus && window.exodus.solana],
        ["Coin98", () => window.coin98 && window.coin98.sol],
        ["Magic Eden", () => window.magicEden && window.magicEden.solana],
        ["Brave Wallet", () => window.braveSolana],
    ];

    function elenco() {
        const out = [];
        const nomi = new Set();
        for (const w of std) {
            out.push({ name: w.name, icon: w.icon, kind: "standard", ref: w });
            nomi.add(w.name.toLowerCase());
        }
        for (const [name, trova] of LEGACY) {
            let p = null;
            try { p = trova(); } catch (_) {}
            if (p && !nomi.has(name.toLowerCase())) out.push({ name, icon: null, kind: "legacy", ref: p });
        }
        return out;
    }

    const isMobile = /Android|iPhone|iPad|iPod/i.test(navigator.userAgent);
    /* 10/10/2026 (mobile): aprire la pagina DENTRO l'app del wallet la faceva ripartire da zero
     * (wallet da riscansionare, ref perso, Connect da ripremere). Il link ora porta con sé il wallet
     * scansionato (?wallet= è già nell'indirizzo), il ref e connect=1: dentro l'app si collega subito. */
    function urlPerApp() {
        const u = new URL(location.href);
        u.searchParams.set("connect", "1");
        try {
            const r = localStorage.getItem("sh_ref");
            if (r && !u.searchParams.get("ref")) u.searchParams.set("ref", r);
        } catch (_) {}
        return u.toString();
    }
    function deepLinks() {
        const url = encodeURIComponent(urlPerApp()), ref = encodeURIComponent(location.origin);
        return [
            ["Phantom", `https://phantom.app/ul/browse/${url}?ref=${ref}`],
            ["Solflare", `https://solflare.com/ul/v1/browse/${url}?ref=${ref}`],
            ["Backpack", `https://backpack.app/ul/v1/browse/${url}?ref=${ref}`],
            ["OKX Wallet", `okx://wallet/dapp/url?dappUrl=${url}`],
            ["Trust Wallet", `https://link.trustwallet.com/open_url?coin_id=501&url=${url}`],
            ["Bitget Wallet", `https://bkcode.vip?action=dapp&url=${url}`],
        ];
    }

    const W = { conn: null };   // {name, kind, ref, account, address}

    async function connetti(w, silenzioso) {
        if (w.kind === "standard") {
            const res = await w.ref.features["standard:connect"].connect(silenzioso ? { silent: true } : undefined);
            const accs = (res && res.accounts) || w.ref.accounts || [];
            const acc = accs.find(a => (a.chains || [CHAIN]).some(c => c.startsWith("solana:"))) || accs[0];
            if (!acc) throw new Error("No Solana account in this wallet");
            W.conn = { name: w.name, icon: w.icon, kind: "standard", ref: w.ref, account: acc, address: acc.address };
            // cambio di account dentro il wallet → la pagina si aggiorna da sola
            try {
                const ev = w.ref.features["standard:events"];
                if (ev && !w.ref.__shAscolto) {
                    w.ref.__shAscolto = true;
                    ev.on("change", ({ accounts }) => {
                        if (!W.conn || W.conn.ref !== w.ref) return;
                        const a2 = (accounts || []).find(a => (a.chains || [CHAIN]).some(c => c.startsWith("solana:")));
                        if (a2) { W.conn.account = a2; W.conn.address = a2.address; }
                        else W.conn = null;
                        document.dispatchEvent(new CustomEvent("sh-account-changed"));
                    });
                }
            } catch (_) {}
        } else {
            const r = await w.ref.connect(silenzioso ? { onlyIfTrusted: true } : undefined);
            const pk = (r && r.publicKey) || w.ref.publicKey;
            if (!pk) throw new Error("Wallet did not return an address");
            W.conn = { name: w.name, icon: null, kind: "legacy", ref: w.ref, address: pk.toString() };
            try {
                if (w.ref.on && !w.ref.__shAscolto) {
                    w.ref.__shAscolto = true;
                    w.ref.on("accountChanged", pk2 => {
                        if (!W.conn || W.conn.ref !== w.ref) return;
                        if (pk2) W.conn.address = pk2.toString(); else W.conn = null;
                        document.dispatchEvent(new CustomEvent("sh-account-changed"));
                    });
                }
            } catch (_) {}
        }
        try { localStorage.setItem("sh_wallet", w.name); } catch (_) {}
        // collegamento scelto dall'utente → account.js fa il login (una firma gratuita, una volta sola)
        if (!silenzioso) document.dispatchEvent(new CustomEvent("sh-connected", { detail: { address: W.conn.address } }));
        return W.conn;
    }

    /* 10/10: la connessione sopravvive al cambio pagina. Il wallet scelto si ricorda in
     * localStorage e ad ogni pagina si ricollega in SILENZIO (nessun popup: il wallet risponde
     * solo se il sito è già autorizzato). Le pagine aspettano SHWallet.pronto. */
    async function riprendi() {
        let nome = "";
        try { nome = localStorage.getItem("sh_wallet") || ""; } catch (_) {}
        // arrivati dall'app del wallet con connect=1: si collega subito (una sola approvazione)
        const qs = new URLSearchParams(location.search);
        if (qs.get("connect") === "1") {
            qs.delete("connect");
            try { history.replaceState(null, "", location.pathname + (qs.toString() ? "?" + qs : "") + location.hash); } catch (_) {}
            if (!nome) return collegaDaApp();
        }
        if (!nome) return null;
        for (let i = 0; i < 20; i++) {                  // i wallet standard si registrano con un po' di ritardo
            const w = elenco().find(x => x.name === nome);
            if (w) {
                try {
                    const c = await connetti(w, true);
                    document.dispatchEvent(new CustomEvent("sh-account-changed"));
                    return c;
                } catch (_) { return null; }        // non più autorizzato: si resta scollegati, senza popup
            }
            await new Promise(r => setTimeout(r, 150));
        }
        return null;
    }
    async function collegaDaApp() {
        // prima che la pagina abbia caricato account.js nessuno ascolterebbe «sh-connected» (niente login)
        if (document.readyState === "loading")
            await new Promise(r => document.addEventListener("DOMContentLoaded", r, { once: true }));
        let lista = [];
        for (let i = 0; i < 20 && !lista.length; i++) {        // nell'app il wallet si registra in un attimo
            lista = elenco();
            if (!lista.length) await new Promise(r => setTimeout(r, 150));
        }
        if (lista.length === 1) {
            try { return await connetti(lista[0]); }            // evento sh-connected → login automatico
            catch (_) { /* richiesta automatica rifiutata: si apre la scelta normale */ }
        }
        document.dispatchEvent(new CustomEvent("sh-connect-request"));
        return null;
    }
    const pronto = riprendi();

    async function disconnetti() {
        try {
            if (W.conn && W.conn.kind === "standard" && W.conn.ref.features["standard:disconnect"])
                await W.conn.ref.features["standard:disconnect"].disconnect();
            else if (W.conn && W.conn.ref.disconnect) await W.conn.ref.disconnect();
        } catch (_) {}
        W.conn = null;
        try { localStorage.removeItem("sh_wallet"); } catch (_) {}
        document.dispatchEvent(new CustomEvent("sh-disconnected"));
    }

    const b64ToBytes = b => Uint8Array.from(atob(b), c => c.charCodeAt(0));
    function bytesToB64(u) {
        let s = "";
        for (let i = 0; i < u.length; i += 0x8000) s += String.fromCharCode.apply(null, u.subarray(i, i + 0x8000));
        return btoa(s);
    }

    /** Firma (senza inviare) una lista di transazioni base64. Ritorna base64 firmate. */
    async function firma(txsB64) {
        if (!W.conn) throw new Error("Connect a wallet first");
        const c = W.conn;
        if (c.kind === "standard") {
            const f = c.ref.features["solana:signTransaction"];
            if (!f) throw new Error(`${c.name} can only sign-and-send: please use another wallet`);
            const inputs = txsB64.map(t => ({ transaction: b64ToBytes(t), account: c.account, chain: CHAIN }));
            const out = [];                                        // 11/10: una per richiesta (vedi inviaPhantom)
            for (const i of inputs) out.push(...(await f.signTransaction(i)));
            return out.map(o => bytesToB64(o.signedTransaction));
        }
        if (!window.solanaWeb3) throw new Error("Wallet library not loaded");
        const txs = txsB64.map(t => window.solanaWeb3.VersionedTransaction.deserialize(b64ToBytes(t)));
        let signed;
        signed = []; for (const t of txs) signed.push(await c.ref.signTransaction(t));
        return signed.map(t => bytesToB64(t.serialize()));
    }

    // base58 (le firme Solana si mostrano/inviano così)
    const B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz";
    function b58(bytes) {
        let n = 0n;
        for (const b of bytes) n = n * 256n + BigInt(b);
        let s = "";
        while (n > 0n) { s = B58[Number(n % 58n)] + s; n /= 58n; }
        for (const b of bytes) { if (b === 0) s = "1" + s; else break; }
        return s;
    }

    /** true se il wallet sa firmare SENZA inviare (→ una sola approvazione per tutto il giro e
     *  invio insistente dal nostro server: il percorso più affidabile, scelto il 10/10). */
    function puoFirmare() {
        const c = W.conn;
        if (!c) return false;
        if (c.kind === "standard") return !!c.ref.features["solana:signTransaction"];
        return (typeof c.ref.signAllTransactions === "function" || typeof c.ref.signTransaction === "function")
            && !!window.solanaWeb3;
    }

    /** true se il wallet collegato sa «firmare e inviare» da sé (metodo raccomandato da Phantom). */
    function puoInviare() {
        const c = W.conn;
        if (!c) return false;
        if (c.kind === "standard") return !!c.ref.features["solana:signAndSendTransaction"];
        return typeof c.ref.signAndSendTransaction === "function" && !!window.solanaWeb3;
    }

    /** Fa firmare E INVIARE al wallet una transazione (base64). Ritorna la firma base58. */
    async function firmaEInvia(txB64) {
        const c = W.conn;
        if (c.kind === "standard") {
            const f = c.ref.features["solana:signAndSendTransaction"];
            const [out] = await f.signAndSendTransaction({ transaction: b64ToBytes(txB64), account: c.account,
                                                          chain: CHAIN, options: { preflightCommitment: "confirmed" } });
            return typeof out.signature === "string" ? out.signature : b58(out.signature);
        }
        const tx = window.solanaWeb3.VersionedTransaction.deserialize(b64ToBytes(txB64));
        const r = await c.ref.signAndSendTransaction(tx, { preflightCommitment: "confirmed" });
        return (r && (r.signature || r)).toString();
    }

    /** UNA sola approvazione per tutte le transazioni: si passano insieme al wallet.
     *  Ritorna le firme base58 nell'ordine. Se il wallet ne accetta una per volta, ripiega. */
    async function firmaEInviaTutte(txsB64, avanzamento) {
        const c = W.conn;
        if (txsB64.length > 1 && false) {      // 11/10: richiesta multipla = blocco rosso su Phantom
            try {
                if (c.kind === "standard") {
                    const f = c.ref.features["solana:signAndSendTransaction"];
                    const outs = await f.signAndSendTransaction(...txsB64.map(t => ({
                        transaction: b64ToBytes(t), account: c.account, chain: CHAIN,
                        options: { preflightCommitment: "confirmed" } })));
                    if (outs && outs.length === txsB64.length)
                        return outs.map(o => typeof o.signature === "string" ? o.signature : b58(o.signature));
                } else if (typeof c.ref.signAndSendAllTransactions === "function") {
                    const txs = txsB64.map(t => window.solanaWeb3.VersionedTransaction.deserialize(b64ToBytes(t)));
                    const r = await c.ref.signAndSendAllTransactions(txs, { preflightCommitment: "confirmed" });
                    const sigs = (r && (r.signatures || r)) || [];
                    if (sigs.length === txsB64.length) return sigs.map(x => x.toString());
                }
            } catch (e) {
                // rifiuto esplicito dell'utente: non si insiste con altre richieste
                if (/reject|denied|cancel/i.test(String(e && (e.message || e)))) throw e;
            }
        }
        const out = [];
        for (let i = 0; i < txsB64.length; i++) {
            if (avanzamento) avanzamento(i, txsB64.length);
            try { out.push(await firmaEInvia(txsB64[i])); }
            catch (e) { if (!out.length) throw e; break; }
        }
        return out;
    }

    /** Phantom: «firma e invia tutto» con UNA approvazione (signAndSendAllTransactions del suo
     *  provider). È ciò che Phantom raccomanda: invia lui e aggiunge le protezioni Lighthouse,
     *  quindi niente avviso «dApp could be malicious» (10/10, supporto Phantom). */
    function phantomTutto() {
        const c = W.conn;
        const p = window.phantom && window.phantom.solana;
        return !!(c && /phantom/i.test(c.name) && p && typeof p.signAndSendAllTransactions === "function"
                  && window.solanaWeb3);
    }
    /** 🔴 11/10/2026, provato con Phantom vero (26.32): QUALUNQUE richiesta con più transazioni insieme
     *  (signAndSendAllTransactions, signAllTransactions) mostra «Request blocked · This dApp could be
     *  malicious», anche due trasferimenti banali su example.com. Una transazione per richiesta passa
     *  pulita. Quindi: una alla volta. Rifiuto dell'utente → ci si ferma, le precedenti restano fatte. */
    async function inviaPhantom(txsB64, avanzamento) {
        const p = window.phantom.solana;
        if (!p.isConnected) await p.connect();
        const sigs = [];
        for (let i = 0; i < txsB64.length; i++) {
            if (avanzamento) avanzamento(i, txsB64.length);
            const tx = window.solanaWeb3.VersionedTransaction.deserialize(b64ToBytes(txsB64[i]));
            try {
                const r = await p.signAndSendTransaction(tx, { preflightCommitment: "confirmed" });
                const x = r && (r.signature || r);
                sigs.push(x == null ? null : x.toString());
            } catch (e) {
                if (!sigs.some(Boolean)) throw e;
                break;
            }
        }
        return sigs;
    }

    /** Firma un messaggio di testo (login «Sign in with Solana»). Ritorna la firma in base64. */
    async function firmaMessaggio(testo) {
        const c = W.conn;
        if (!c) throw new Error("Connect a wallet first");
        const bytes = new TextEncoder().encode(testo);
        if (c.kind === "standard") {
            const f = c.ref.features["solana:signMessage"];
            if (!f) throw new Error(`${c.name} can't sign messages`);
            const [out] = await f.signMessage({ account: c.account, message: bytes });
            return bytesToB64(out.signature);
        }
        if (typeof c.ref.signMessage !== "function") throw new Error(`${c.name} can't sign messages`);
        const r = await c.ref.signMessage(bytes, "utf8");
        return bytesToB64(r.signature || r);
    }

    window.SHWallet = { pronto, elenco, connetti, disconnetti, firma, firmaEInvia, firmaEInviaTutte, puoInviare, puoFirmare, phantomTutto, inviaPhantom, firmaMessaggio, deepLinks, isMobile,
                        stato: () => W.conn };
})();
