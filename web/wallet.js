/* SolHouse Signal Tools: universal connector for Solana wallets.
 *
 * 1) Wallet Standard (Phantom, Solflare, Backpack, Glow, OKX, Coinbase, Trust, Bitget,
 *    Exodus, Magic Eden, …): discovered through the standard event, they sign raw bytes.
 * 2) "Legacy" injected providers (window.phantom.solana, window.solflare, …): they sign
 *    web3.js objects, so the local copy of @solana/web3.js is used only for them.
 * 3) On a phone without a wallet in the browser: links that open the page INSIDE the app.
 * No private key ever passes through here: the wallet just signs.
 */
(function () {
    const CHAIN = "solana:mainnet";
    const std = [];                       // registered standard wallets
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

    // legacy providers: [name, finder function, icon]
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
    /* 10/10/2026 (mobile): opening the page INSIDE the wallet app used to start from scratch
     * (wallet to scan again, ref lost, Connect to press again). The link now carries the scanned
     * wallet (?wallet= is already in the address), the ref and connect=1: inside the app it connects right away. */
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
            // account switched inside the wallet: the page updates by itself
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
        // connection chosen by the user: account.js logs in (one free signature, only once)
        if (!silenzioso) document.dispatchEvent(new CustomEvent("sh-connected", { detail: { address: W.conn.address } }));
        return W.conn;
    }

    /* 10/10: the connection survives page changes. The chosen wallet is remembered in
     * localStorage and every page reconnects SILENTLY (no popup: the wallet only answers if the
     * site is already authorized). Pages wait for SHWallet.pronto. */
    async function riprendi() {
        let nome = "";
        try { nome = localStorage.getItem("sh_wallet") || ""; } catch (_) {}
        // coming from the wallet app with connect=1: connect right away (a single approval)
        const qs = new URLSearchParams(location.search);
        if (qs.get("connect") === "1") {
            qs.delete("connect");
            try { history.replaceState(null, "", location.pathname + (qs.toString() ? "?" + qs : "") + location.hash); } catch (_) {}
            if (!nome) return collegaDaApp();
        }
        if (!nome) return null;
        for (let i = 0; i < 20; i++) {                  // standard wallets register with a small delay
            const w = elenco().find(x => x.name === nome);
            if (w) {
                try {
                    const c = await connetti(w, true);
                    document.dispatchEvent(new CustomEvent("sh-account-changed"));
                    return c;
                } catch (_) { return null; }        // no longer authorized: stay disconnected, no popup
            }
            await new Promise(r => setTimeout(r, 150));
        }
        return null;
    }
    async function collegaDaApp() {
        // before the page has loaded account.js nobody would hear "sh-connected" (no login)
        if (document.readyState === "loading")
            await new Promise(r => document.addEventListener("DOMContentLoaded", r, { once: true }));
        let lista = [];
        for (let i = 0; i < 20 && !lista.length; i++) {        // inside the app the wallet registers almost at once
            lista = elenco();
            if (!lista.length) await new Promise(r => setTimeout(r, 150));
        }
        if (lista.length === 1) {
            try { return await connetti(lista[0]); }            // sh-connected event: automatic login
            catch (_) { /* automatic request refused: open the normal picker */ }
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

    /** Real Phantom (12/10), also for sign-only. It is the only wallet that shows "Request blocked"
     *  on multi-transaction requests, so it is the only one that gets ONE transaction per request. */
    const isPhantom = c => !!(c && /phantom/i.test(c.name));
    /** 13/10: explicit rejection by the user (code 4001 or text): NEVER fall back to one at a
     *  time, that would be N popups in a row after they said no. */
    const rifiutato = e => !!e && (e.code === 4001 || /reject|denied|cancel/i.test(String(e.message || e)));

    /** Sign (without sending) a list of base64 transactions. Returns signed base64.
     *  12/10: wallets that accept several transactions per request sign them with ONE approval
     *  (one signature covering N txs). Not Phantom: its multi-transaction requests are blocked,
     *  so it goes one at a time. If a wallet can't do the batch, fall back to one at a time. */
    async function firma(txsB64) {
        if (!W.conn) throw new Error("Connect a wallet first");
        const c = W.conn;
        if (c.kind === "standard") {
            const f = c.ref.features["solana:signTransaction"];
            if (!f) throw new Error(`${c.name} can only sign-and-send: please use another wallet`);
            const inputs = txsB64.map(t => ({ transaction: b64ToBytes(t), account: c.account, chain: CHAIN }));
            let out;
            if (isPhantom(c)) {                                    // Phantom: multi-transaction requests are blocked
                out = [];
                for (const i of inputs) out.push(...(await f.signTransaction(i)));
            } else {
                try {
                    out = await f.signTransaction(...inputs);      // all of them in one approval
                } catch (e) {
                    if (inputs.length < 2 || rifiutato(e)) throw e;
                    out = [];                                      // wallets that accept only one
                    for (const i of inputs) out.push(...(await f.signTransaction(i)));
                }
            }
            return out.map(o => bytesToB64(o.signedTransaction));
        }
        if (!window.solanaWeb3) throw new Error("Wallet library not loaded");
        const txs = txsB64.map(t => window.solanaWeb3.VersionedTransaction.deserialize(b64ToBytes(t)));
        let signed;
        if (!isPhantom(c) && txs.length > 1 && typeof c.ref.signAllTransactions === "function") {
            try { signed = await c.ref.signAllTransactions(txs); }
            catch (e) { if (rifiutato(e)) throw e; signed = null; }  // batch not supported: one at a time
        }
        if (!signed) { signed = []; for (const t of txs) signed.push(await c.ref.signTransaction(t)); }
        return signed.map(t => bytesToB64(t.serialize()));
    }

    // base58 (how Solana signatures are shown and sent)
    const B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz";
    function b58(bytes) {
        let n = 0n;
        for (const b of bytes) n = n * 256n + BigInt(b);
        let s = "";
        while (n > 0n) { s = B58[Number(n % 58n)] + s; n /= 58n; }
        for (const b of bytes) { if (b === 0) s = "1" + s; else break; }
        return s;
    }

    /** true if the wallet can sign WITHOUT sending (one approval for the whole round and
     *  persistent sending from our server: the most reliable path, chosen on 10/10). */
    function puoFirmare() {
        const c = W.conn;
        if (!c) return false;
        if (c.kind === "standard") return !!c.ref.features["solana:signTransaction"];
        return (typeof c.ref.signAllTransactions === "function" || typeof c.ref.signTransaction === "function")
            && !!window.solanaWeb3;
    }

    /** true if the connected wallet can "sign and send" by itself (the method Phantom recommends). */
    function puoInviare() {
        const c = W.conn;
        if (!c) return false;
        if (c.kind === "standard") return !!c.ref.features["solana:signAndSendTransaction"];
        return typeof c.ref.signAndSendTransaction === "function" && !!window.solanaWeb3;
    }

    /** Has the wallet sign AND SEND one transaction (base64). Returns the base58 signature. */
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

    /** ONE approval for all the transactions: they are passed to the wallet together.
     *  Returns the base58 signatures in order. If the wallet accepts one at a time, falls back. */
    async function firmaEInviaTutte(txsB64, avanzamento) {
        const c = W.conn;
        // 11/10: a multi-transaction request is a red block on Phantom, so batch only for other wallets
        if (txsB64.length > 1 && !isPhantom(c)) {
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
                // explicit rejection by the user: no further requests
                if (rifiutato(e)) throw e;
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

    /** Phantom: "sign and send all" with ONE approval (signAndSendAllTransactions of its
     *  provider). Phantom recommends it: it sends and adds its Lighthouse guards, so no
     *  "dApp could be malicious" warning (10/10, Phantom support). */
    function phantomTutto() {
        const c = W.conn;
        const p = window.phantom && window.phantom.solana;
        return !!(c && /phantom/i.test(c.name) && p && typeof p.signAndSendAllTransactions === "function"
                  && window.solanaWeb3);
    }
    /** 🔴 11/10/2026, tested with real Phantom (26.32): ANY request with several transactions
     *  (signAndSendAllTransactions, signAllTransactions) shows "Request blocked · This dApp could be
     *  malicious", even two trivial transfers on example.com. One transaction per request passes
     *  cleanly. So: one at a time. If the user rejects, stop; the previous ones stay done. */
    async function inviaPhantom(txsB64, avanzamento, rinnova) {
        const p = window.phantom.solana;
        if (!p.isConnected) await p.connect();
        const sigs = [];
        for (let i = 0; i < txsB64.length; i++) {
            if (avanzamento) avanzamento(i, txsB64.length);
            try {
                // 🕐 fresh blockhash right before each approval (the previous ones may have taken minutes)
                let b64 = txsB64[i];
                if (rinnova && i > 0) { try { b64 = (await rinnova(i)) || b64; } catch (_) {} }
                const tx = window.solanaWeb3.VersionedTransaction.deserialize(b64ToBytes(b64));
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

    /** Signs a text message ("Sign in with Solana" login). Returns the signature in base64. */
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
