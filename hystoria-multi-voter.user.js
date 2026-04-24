// ==UserScript==
// @name         Hystoria Multi-Voter
// @namespace    https://github.com/LLuuffyy/Bot-Hystoria
// @version      2.0.0
// @description  Vote automatiquement sur play-hystoria.net avec plusieurs comptes en boucle
// @author       Zeliox83
// @match        https://play-hystoria.net/*
// @match        https://www.serveur-prive.net/*
// @match        https://serveur-prive.net/*
// @grant        GM_setValue
// @grant        GM_getValue
// @grant        GM_addValueChangeListener
// @grant        GM_removeValueChangeListener
// @run-at       document-idle
// ==/UserScript==

(function() {
    'use strict';

    // ================================================================
    //  LISTE DES COMPTES — Remplis ici tous tes comptes
    // ================================================================
    const COMPTES = [
        { username: 'Zeliox83',   password: 'Boston83',      pseudo: 'Zeliox' },
        // { username: 'BotVote01', password: 'MotDePasse01',  pseudo: 'BotVote01' },
        // { username: 'BotVote02', password: 'MotDePasse02',  pseudo: 'BotVote02' },
        // Ajoute autant de comptes que tu veux ici
        // Décommente les lignes (enlève les //) et remplace les valeurs
    ];

    // ================================================================
    //  CONFIG
    // ================================================================
    const VOTE_INTERVAL_MS = 90 * 60 * 1000;       // 1h30 fallback
    const RETRY_DELAY_MS = 60 * 1000;               // 1 min retry
    const POST_VOTE_BUFFER_MS = 30 * 1000;           // +30s après cooldown
    const DELAY_BETWEEN_ACCOUNTS_MS = 15 * 1000;    // 15s entre chaque compte
    const VOTE_IN_PROGRESS_TTL = 180000;             // 3 min max vote en cours

    // ================================================================
    //  STATE (stocké via GM_setValue, persiste entre les pages)
    // ================================================================
    //  current_account_index : index du compte en cours
    //  multi_phase : 'voting' | 'waiting_cooldown' | 'idle'
    //  cycle_start_time : timestamp du début du cycle
    //  vote_in_progress : timestamp quand vote cliqué
    //  external_vote_done : timestamp quand vote externe fait

    // ================================================================
    //  LOG & UI
    // ================================================================
    const LOG_PREFIX = '[Multi-Voter]';
    function log(...args) { console.log(LOG_PREFIX, ...args); }
    function warn(...args) { console.warn(LOG_PREFIX, ...args); }
    function err(...args) { console.error(LOG_PREFIX, ...args); }

    function injectBadge() {
        if (document.getElementById('hystoria-bot-badge')) return;
        const badge = document.createElement('div');
        badge.id = 'hystoria-bot-badge';
        badge.style.cssText = `
            position: fixed;
            bottom: 20px;
            right: 20px;
            background: linear-gradient(135deg, #1a1a2e, #16213e);
            color: #e94560;
            padding: 12px 16px;
            border: 2px solid #e94560;
            border-radius: 8px;
            font-family: monospace;
            font-size: 13px;
            z-index: 999999;
            box-shadow: 0 4px 12px rgba(0,0,0,0.5);
            max-width: 380px;
            line-height: 1.4;
        `;
        badge.innerHTML = '<b>Hystoria Multi-Voter</b><br><span id="hystoria-bot-status">Initialisation...</span>';
        document.body.appendChild(badge);
    }

    function setStatus(msg) {
        injectBadge();
        const el = document.getElementById('hystoria-bot-status');
        if (el) el.innerHTML = msg;
        log('STATUS:', msg.replace(/<[^>]+>/g, ' '));
    }

    // ================================================================
    //  UTILS
    // ================================================================
    function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

    async function waitFor(selector, timeout = 15000) {
        const start = Date.now();
        while (Date.now() - start < timeout) {
            const el = document.querySelector(selector);
            if (el) return el;
            await sleep(300);
        }
        return null;
    }

    function parseCooldownText(text) {
        let m = text.match(/(\d+)\s*h\s*(\d+)\s*m\s*(\d+)\s*s/);
        if (m) return parseInt(m[1]) * 3600 + parseInt(m[2]) * 60 + parseInt(m[3]);
        m = text.match(/(\d+)\s*m\s*(\d+)\s*s/);
        if (m) return parseInt(m[1]) * 60 + parseInt(m[2]);
        m = text.match(/(\d+):(\d{2}):(\d{2})/);
        if (m) return parseInt(m[1]) * 3600 + parseInt(m[2]) * 60 + parseInt(m[3]);
        m = text.match(/(\d{1,2}):(\d{2})/);
        if (m) return parseInt(m[1]) * 60 + parseInt(m[2]);
        return null;
    }

    function getCurrentAccount() {
        const idx = GM_getValue('current_account_index', 0);
        if (idx >= COMPTES.length) return null;
        return { ...COMPTES[idx], index: idx };
    }

    function getAccountLabel(account) {
        if (!account) return '?';
        return `${account.username} (${account.index + 1}/${COMPTES.length})`;
    }

    function isLoggedInAs(username) {
        const body = document.body.textContent || '';
        return body.includes('Mon Profil');
    }

    function isOnLoginPage() {
        if (location.pathname.includes('/login')) return true;
        const hasPassword = document.querySelector('input[type="password"]');
        const hasProfile = (document.body.textContent || '').includes('Mon Profil');
        return hasPassword && !hasProfile;
    }

    // ================================================================
    //  LOGOUT
    // ================================================================
    async function doLogout() {
        log('Déconnexion...');
        setStatus('Déconnexion du compte actuel...');

        // Chercher un lien de déconnexion
        const links = document.querySelectorAll('a[href*="logout"], a[href*="deconnexion"]');
        if (links.length > 0) {
            links[0].click();
            await sleep(3000);
            return true;
        }

        // Fallback : naviguer vers /logout
        location.href = 'https://play-hystoria.net/logout';
        return true;
    }

    // ================================================================
    //  LOGIN
    // ================================================================
    async function doLogin(account) {
        setStatus(`Connexion: <b>${account.username}</b>...`);
        await sleep(1500);

        const userField = document.querySelector('input[name="username"]')
            || document.querySelector('input[name="email"]')
            || document.querySelector('input[type="email"]')
            || document.querySelector('input[name="login"]');
        const passField = document.querySelector('input[type="password"]');

        if (!userField || !passField) {
            setStatus('Champs login non trouvés.');
            return false;
        }

        // Clear les champs d'abord
        userField.value = '';
        userField.dispatchEvent(new Event('input', { bubbles: true }));
        passField.value = '';
        passField.dispatchEvent(new Event('input', { bubbles: true }));

        await sleep(300);

        userField.value = account.username;
        userField.dispatchEvent(new Event('input', { bubbles: true }));
        userField.dispatchEvent(new Event('change', { bubbles: true }));

        passField.value = account.password;
        passField.dispatchEvent(new Event('input', { bubbles: true }));
        passField.dispatchEvent(new Event('change', { bubbles: true }));

        await sleep(500);

        let submitBtn = document.querySelector('button[type="submit"]')
            || document.querySelector('input[type="submit"]');
        if (!submitBtn) {
            for (const b of document.querySelectorAll('button, a')) {
                const txt = (b.textContent || '').trim().toLowerCase();
                if (txt.includes('connexion') || txt.includes('se connecter') || txt === 'login') {
                    submitBtn = b;
                    break;
                }
            }
        }

        if (!submitBtn) {
            setStatus('Bouton submit non trouvé.');
            return false;
        }

        submitBtn.click();
        log('Login soumis pour', account.username);
        await sleep(5000);
        return true;
    }

    // ================================================================
    //  EXTERNAL VOTE (serveur-prive.net)
    // ================================================================
    async function handleExternalVote() {
        const account = getCurrentAccount();
        const label = account ? account.pseudo : '?';
        setStatus(`serveur-prive.net — pseudo: ${label}`);

        await sleep(3000);

        // Remplir le pseudo
        const inputs = document.querySelectorAll('input[type="text"], input:not([type])');
        for (const input of inputs) {
            if (input.offsetParent === null || input.readOnly || input.disabled) continue;
            if (!input.value || input.value.trim() === '') {
                const pseudo = account ? account.pseudo : '';
                if (pseudo) {
                    input.value = pseudo;
                    input.dispatchEvent(new Event('input', { bubbles: true }));
                    input.dispatchEvent(new Event('change', { bubbles: true }));
                    log('Pseudo rempli:', pseudo);
                    await sleep(800);
                }
                break;
            }
        }

        // Chercher le bouton vote (retry 20s)
        let voteEl = null;
        for (let attempt = 0; attempt < 10; attempt++) {
            const candidates = document.querySelectorAll('a, button, input[type="submit"]');
            for (const el of candidates) {
                const txt = (el.textContent || el.value || '').trim().toLowerCase();
                if (txt.includes('je vote maintenant') || txt === 'voter' || txt.includes('voter maintenant')) {
                    voteEl = el;
                    break;
                }
            }
            if (voteEl) break;
            await sleep(2000);
        }

        if (voteEl) {
            voteEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
            await sleep(1000);
            voteEl.click();
            GM_setValue('external_vote_done', Date.now());
            log('Vote externe cliqué, signal envoyé');
            await sleep(4000);
            try { window.close(); } catch (e) {
                setStatus('Vote fait! Ferme cet onglet.');
            }
        } else {
            warn('Bouton vote non trouvé');
            setStatus('Bouton non trouvé. Clique manuellement.');
            GM_setValue('external_vote_done', Date.now());
        }
    }

    // ================================================================
    //  VOTE FLOW (play-hystoria.net/vote)
    // ================================================================
    async function handleVotePage() {
        const account = getCurrentAccount();
        if (!account) {
            setStatus('Tous les comptes ont voté! Attente du cooldown...');
            handleAllVoted();
            return;
        }

        setStatus(`Compte: <b>${getAccountLabel(account)}</b><br>Chargement page vote...`);
        await sleep(2000);

        // Redirigé vers login ?
        if (isOnLoginPage()) {
            await doLogin(account);
            return; // Le login redirigera vers /vote
        }

        // Vérifier si connecté
        if (!isLoggedInAs(account.username)) {
            // Pas connecté ou mauvais compte → logout + login
            setStatus(`Pas connecté. Déconnexion puis login ${account.username}...`);
            await doLogout();
            return; // Après logout on sera redirigé
        }

        const statusCard = await waitFor('#voteStatusCard', 20000);
        if (!statusCard) {
            if (isOnLoginPage()) {
                await doLogin(account);
                return;
            }
            setStatus('Page vote non détectée. Reload 1 min.');
            setTimeout(() => location.reload(), RETRY_DELAY_MS);
            return;
        }

        const cardClass = (statusCard.className || '').toLowerCase();
        const titleEl = document.getElementById('voteStatusTitle');
        const statusTitle = (titleEl?.textContent || '').trim();
        log('Status:', { cardClass, statusTitle, account: account.username });

        // --- COOLDOWN (ce compte a déjà voté) ---
        if (cardClass.includes('cooldown') || statusTitle.toLowerCase().includes('cooldown')) {
            log(`${account.username} en cooldown, passage au suivant`);
            setStatus(`<b>${account.username}</b> déjà voté (cooldown).<br>Passage au compte suivant...`);

            // Si c'est le premier compte, noter le cooldown pour le cycle
            if (account.index === 0) {
                const cardText = statusCard.textContent || '';
                const remaining = parseCooldownText(cardText);
                if (remaining && remaining > 0) {
                    GM_setValue('first_account_cooldown', remaining * 1000 + POST_VOTE_BUFFER_MS);
                }
            }

            await sleep(2000);
            advanceToNextAccount();
            return;
        }

        // --- VOTE DISPONIBLE ---
        if (cardClass.includes('available') || statusTitle.includes('Disponible')) {
            // Protection double-clic
            const voteInProgress = GM_getValue('vote_in_progress', 0);
            const now = Date.now();
            if (voteInProgress > 0 && (now - voteInProgress) < VOTE_IN_PROGRESS_TTL) {
                setStatus(`<b>${account.username}</b> — vote en cours, polling...`);
                startPolling(account);
                return;
            }

            setStatus(`<b>${account.username}</b> — Vote disponible! Clic...`);

            const voteBtn = document.getElementById('btnGenerateOTP');
            if (!voteBtn) {
                setStatus('Bouton #btnGenerateOTP introuvable. Retry 1 min.');
                setTimeout(() => location.reload(), RETRY_DELAY_MS);
                return;
            }

            voteBtn.scrollIntoView({ behavior: 'smooth', block: 'center' });
            await sleep(800);

            GM_setValue('external_vote_done', 0);
            GM_setValue('vote_in_progress', Date.now());

            voteBtn.click();
            setStatus(`<b>${account.username}</b> — OTP généré, attente externe...`);

            await sleep(3000);
            startPolling(account);
            return;
        }

        // --- ÉTAT INCONNU ---
        setStatus(`État inconnu pour ${account.username}: "${statusTitle}". Retry 1 min.`);
        setTimeout(() => location.reload(), RETRY_DELAY_MS);
    }

    // ================================================================
    //  POLLING
    // ================================================================
    function startPolling(account) {
        let attempts = 0;
        const maxAttempts = 36;
        let externalDone = GM_getValue('external_vote_done', 0) > 0;

        const listenerId = GM_addValueChangeListener('external_vote_done', (name, oldVal, newVal, remote) => {
            if (newVal > 0) {
                externalDone = true;
                log('Signal cross-tab reçu pour', account.username);
                const manualBtn = document.getElementById('btnManualCheck');
                if (manualBtn && manualBtn.offsetParent !== null) manualBtn.click();
            }
        });

        function cleanup() {
            try { GM_removeValueChangeListener(listenerId); } catch (e) {}
            GM_setValue('vote_in_progress', 0);
        }

        const interval = setInterval(() => {
            attempts++;

            const nowCard = document.getElementById('voteStatusCard');
            const nowClass = (nowCard?.className || '').toLowerCase();
            const nowTitle = (document.getElementById('voteStatusTitle')?.textContent || '').trim();

            // Vote confirmé → passer au compte suivant
            if (nowClass.includes('cooldown') || nowTitle.toLowerCase().includes('cooldown')) {
                clearInterval(interval);
                cleanup();
                log(`Vote confirmé pour ${account.username}!`);
                setStatus(`<b>${account.username}</b> — Vote confirmé!<br>Passage au suivant dans 5s...`);

                // Sauvegarder le cooldown du premier compte
                if (account.index === 0) {
                    const cardText = nowCard?.textContent || '';
                    const remaining = parseCooldownText(cardText);
                    if (remaining && remaining > 0) {
                        GM_setValue('first_account_cooldown', remaining * 1000 + POST_VOTE_BUFFER_MS);
                    }
                }

                setTimeout(() => advanceToNextAccount(), 5000);
                return;
            }

            if (!externalDone) {
                const extVal = GM_getValue('external_vote_done', 0);
                if (extVal > 0) externalDone = true;
            }

            if (externalDone) {
                const manualBtn = document.getElementById('btnManualCheck');
                if (manualBtn && manualBtn.offsetParent !== null) {
                    setStatus(`<b>${account.username}</b> — Vérif manuelle (${attempts}/${maxAttempts})...`);
                    manualBtn.click();
                } else {
                    setStatus(`<b>${account.username}</b> — Attente serveur (${attempts}/${maxAttempts})...`);
                }
            } else {
                setStatus(`<b>${account.username}</b> — Attente vote externe (${attempts}/${maxAttempts})...`);
            }

            if (attempts >= maxAttempts) {
                clearInterval(interval);
                cleanup();
                setStatus(`<b>${account.username}</b> — Timeout, on assume succès. Suivant...`);
                setTimeout(() => advanceToNextAccount(), 3000);
            }
        }, 5000);
    }

    // ================================================================
    //  NAVIGATION ENTRE COMPTES
    // ================================================================
    function advanceToNextAccount() {
        const currentIdx = GM_getValue('current_account_index', 0);
        const nextIdx = currentIdx + 1;

        if (nextIdx >= COMPTES.length) {
            log('Tous les comptes ont voté!');
            GM_setValue('current_account_index', 0);
            GM_setValue('multi_phase', 'waiting_cooldown');
            handleAllVoted();
            return;
        }

        GM_setValue('current_account_index', nextIdx);
        log(`Passage au compte ${nextIdx + 1}/${COMPTES.length}: ${COMPTES[nextIdx].username}`);

        // Se déconnecter d'abord
        doLogout();
    }

    function handleAllVoted() {
        const cooldownMs = GM_getValue('first_account_cooldown', VOTE_INTERVAL_MS);
        const mins = Math.round(cooldownMs / 60000);
        const nextTime = new Date(Date.now() + cooldownMs).toLocaleTimeString('fr-FR');

        GM_setValue('next_vote_at', Date.now() + cooldownMs);

        setStatus(
            `Tous les <b>${COMPTES.length} comptes</b> ont voté!<br>` +
            `Prochain cycle dans <b>${mins} min</b> (à ${nextTime})`
        );

        setTimeout(() => {
            GM_setValue('current_account_index', 0);
            GM_setValue('multi_phase', 'voting');
            GM_setValue('first_account_cooldown', 0);
            location.reload();
        }, cooldownMs);
    }

    // ================================================================
    //  LOGIN PAGE
    // ================================================================
    async function handleLoginPage() {
        const account = getCurrentAccount();
        if (!account) {
            GM_setValue('current_account_index', 0);
            location.reload();
            return;
        }

        await doLogin(account);
        await sleep(3000);
        if (!location.pathname.includes('/vote')) {
            location.href = 'https://play-hystoria.net/vote';
        }
    }

    // ================================================================
    //  OTHER PAGES → redirect to /vote
    // ================================================================
    function handleOtherPage() {
        const account = getCurrentAccount();
        const label = account ? getAccountLabel(account) : '';
        setStatus(`${label ? label + '<br>' : ''}Redirection vers /vote...`);
        setTimeout(() => {
            location.href = 'https://play-hystoria.net/vote';
        }, 2000);
    }

    // ================================================================
    //  ENTRY POINT
    // ================================================================
    async function main() {
        injectBadge();

        if (COMPTES.length === 0) {
            setStatus('Aucun compte configuré!<br>Ouvre le script et remplis la liste COMPTES.');
            return;
        }

        await sleep(1000);

        const host = location.hostname;
        const account = getCurrentAccount();
        log(`Démarrage — ${host}${location.pathname} — Compte: ${account ? getAccountLabel(account) : 'aucun'}`);
        log(`Total comptes: ${COMPTES.length}`);

        try {
            if (host.includes('serveur-prive.net')) {
                await handleExternalVote();

            } else if (host.includes('play-hystoria.net')) {
                // Vérifier si on est sur /logout (redirigé après déconnexion)
                if (location.pathname.includes('/logout')) {
                    setStatus('Déconnecté. Redirection vers /login...');
                    await sleep(2000);
                    location.href = 'https://play-hystoria.net/login';
                    return;
                }

                if (location.pathname.includes('/login') || isOnLoginPage()) {
                    await handleLoginPage();
                } else if (location.pathname.includes('/vote')) {
                    await handleVotePage();
                } else {
                    handleOtherPage();
                }
            }
        } catch (e) {
            err('Erreur:', e);
            setStatus(`Erreur: ${e.message}. Reload 1 min.`);
            setTimeout(() => location.reload(), RETRY_DELAY_MS);
        }
    }

    main();
})();
