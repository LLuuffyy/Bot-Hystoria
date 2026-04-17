// ==UserScript==
// @name         Hystoria Auto-Voter
// @namespace    https://github.com/LLuuffyy/Bot-Hystoria
// @version      1.6.0
// @description  Vote automatiquement sur play-hystoria.net toutes les 1h30 pour gagner +50 ogrines
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

    // --- CREDENTIALS ---
    const HYSTORIA_USERNAME = 'Zeliox83';
    const HYSTORIA_PASSWORD = 'Boston83';
    const SERVEUR_PRIVE_PSEUDO = 'Zeliox';

    // --- CONFIG ---
    const VOTE_INTERVAL_MS = 90 * 60 * 1000;
    const RETRY_DELAY_MS = 60 * 1000;
    const POST_VOTE_BUFFER_MS = 30 * 1000;
    const VOTE_IN_PROGRESS_TTL = 180000; // 3 min max pour un vote en cours

    // --- LOG ---
    const LOG_PREFIX = '[Hystoria-Bot]';
    function log(...args) { console.log(LOG_PREFIX, ...args); }
    function warn(...args) { console.warn(LOG_PREFIX, ...args); }
    function err(...args) { console.error(LOG_PREFIX, ...args); }

    // --- UI BADGE ---
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
            max-width: 320px;
            line-height: 1.4;
        `;
        badge.innerHTML = '<b>Hystoria Auto-Voter</b><br><span id="hystoria-bot-status">Initialisation...</span>';
        document.body.appendChild(badge);
    }

    function setStatus(msg) {
        injectBadge();
        const el = document.getElementById('hystoria-bot-status');
        if (el) el.innerHTML = msg;
        log('STATUS:', msg.replace(/<[^>]+>/g, ' '));
    }

    // --- UTILS ---
    function sleep(ms) {
        return new Promise(r => setTimeout(r, ms));
    }

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
        // Format "1h 23m 45s"
        let m = text.match(/(\d+)\s*h\s*(\d+)\s*m\s*(\d+)\s*s/);
        if (m) return parseInt(m[1]) * 3600 + parseInt(m[2]) * 60 + parseInt(m[3]);
        // Format "23m 45s"
        m = text.match(/(\d+)\s*m\s*(\d+)\s*s/);
        if (m) return parseInt(m[1]) * 60 + parseInt(m[2]);
        // Format "1:23:45" (h:m:s)
        m = text.match(/(\d+):(\d{2}):(\d{2})/);
        if (m) return parseInt(m[1]) * 3600 + parseInt(m[2]) * 60 + parseInt(m[3]);
        // Format "11:42" (m:s) - le timer affiché sur la page
        m = text.match(/(\d{1,2}):(\d{2})/);
        if (m) return parseInt(m[1]) * 60 + parseInt(m[2]);
        return null;
    }

    function isOnLoginPage() {
        if (location.pathname.includes('/login')) return true;
        const hasPassword = document.querySelector('input[type="password"]');
        const hasProfile = (document.body.textContent || '').includes('Mon Profil');
        return hasPassword && !hasProfile;
    }

    // ========================================
    // LOGIN PAGE
    // ========================================
    async function handleLoginPage() {
        setStatus('Page de login. Connexion auto...');
        await sleep(1500);

        const userField = document.querySelector('input[name="username"]')
            || document.querySelector('input[name="email"]')
            || document.querySelector('input[type="email"]')
            || document.querySelector('input[name="login"]');
        const passField = document.querySelector('input[type="password"]');

        if (!userField || !passField) {
            setStatus('Champs login non trouvés.');
            return;
        }

        userField.value = HYSTORIA_USERNAME;
        userField.dispatchEvent(new Event('input', { bubbles: true }));
        userField.dispatchEvent(new Event('change', { bubbles: true }));

        passField.value = HYSTORIA_PASSWORD;
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
            return;
        }

        setStatus('Identifiants saisis. Clic sur Connexion...');
        submitBtn.click();

        await sleep(5000);
        setStatus('Login effectué. Redirection vers /vote...');
        await sleep(2000);
        if (!location.pathname.includes('/vote')) {
            location.href = 'https://play-hystoria.net/vote';
        }
    }

    // ========================================
    // EXTERNAL VOTE (serveur-prive.net)
    // ========================================
    async function handleExternalVote() {
        setStatus('Sur serveur-prive.net - chargement...');

        // Attendre que la page soit stable
        await sleep(3000);

        // Remplir le pseudo si le champ est vide
        const inputs = document.querySelectorAll('input[type="text"], input:not([type])');
        for (const input of inputs) {
            if (input.offsetParent === null || input.readOnly || input.disabled) continue;
            if (!input.value || input.value.trim() === '') {
                setStatus(`Remplissage pseudo: "${SERVEUR_PRIVE_PSEUDO}"...`);
                input.value = SERVEUR_PRIVE_PSEUDO;
                input.dispatchEvent(new Event('input', { bubbles: true }));
                input.dispatchEvent(new Event('change', { bubbles: true }));
                log('Pseudo rempli:', SERVEUR_PRIVE_PSEUDO);
                await sleep(800);
                break;
            }
        }

        // Chercher le bouton "Je vote maintenant" avec retry (max 20s)
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
            log(`Bouton non trouvé, retry ${attempt + 1}/10...`);
            await sleep(2000);
        }

        if (voteEl) {
            voteEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
            await sleep(1000);

            setStatus('Clic sur "Je vote maintenant"...');
            voteEl.click();

            // Signaler au tab principal que le vote externe est fait
            GM_setValue('external_vote_done', Date.now());
            log('Signal cross-tab envoyé: external_vote_done');

            await sleep(4000);
            setStatus('Vote externe effectué! Fermeture...');
            try { window.close(); } catch (e) {
                setStatus('Vote fait! Tu peux fermer cet onglet.');
            }
        } else {
            warn('Bouton "Je vote maintenant" introuvable après 10 tentatives');
            setStatus('Bouton non trouvé. Clique manuellement puis ferme l\'onglet.');
            // Signaler quand même pour ne pas bloquer le polling
            GM_setValue('external_vote_done', Date.now());
        }
    }

    // ========================================
    // VOTE PAGE (play-hystoria.net/vote)
    // ========================================
    async function handleHystoriaVote() {
        setStatus('Chargement page de vote...');
        await sleep(2000);

        if (isOnLoginPage()) {
            await handleLoginPage();
            return;
        }

        const statusCard = await waitFor('#voteStatusCard', 20000);
        if (!statusCard) {
            if (isOnLoginPage()) {
                await handleLoginPage();
                return;
            }
            setStatus('Page vote non détectée. Reload dans 1 min.');
            setTimeout(() => location.reload(), RETRY_DELAY_MS);
            return;
        }

        const cardClass = (statusCard.className || '').toLowerCase();
        const titleEl = document.getElementById('voteStatusTitle');
        const statusTitle = (titleEl?.textContent || '').trim();

        log('Status:', { cardClass, statusTitle });

        // --- COOLDOWN ---
        if (cardClass.includes('cooldown') || statusTitle.toLowerCase().includes('cooldown')) {
            // Chercher le timer dans le card seulement (pas tout le body)
            const cardText = statusCard.textContent || '';
            const remaining = parseCooldownText(cardText);
            log('Cooldown card text:', cardText, '→ remaining:', remaining, 's');
            let waitMs = VOTE_INTERVAL_MS;
            if (remaining && remaining > 0) {
                waitMs = remaining * 1000 + POST_VOTE_BUFFER_MS;
            }
            const mins = Math.round(waitMs / 60000);
            const nextTime = new Date(Date.now() + waitMs).toLocaleTimeString('fr-FR');

            // Sauvegarder l'heure du prochain vote pour les autres pages
            GM_setValue('next_vote_at', Date.now() + waitMs);
            GM_setValue('vote_in_progress', 0);

            setStatus(`Cooldown actif. Prochain vote dans <b>${mins} min</b><br>(à ${nextTime})`);
            setTimeout(() => location.reload(), waitMs);
            return;
        }

        // --- VOTE DISPONIBLE ---
        if (cardClass.includes('available') || statusTitle.includes('Disponible')) {

            // Protection contre le double-clic OTP si on rafraîchit la page
            const voteInProgress = GM_getValue('vote_in_progress', 0);
            const now = Date.now();
            if (voteInProgress > 0 && (now - voteInProgress) < VOTE_IN_PROGRESS_TTL) {
                log('Vote déjà en cours depuis', Math.round((now - voteInProgress) / 1000), 's');
                setStatus('Vote en cours (reprise après refresh)...');
                startPolling();
                return;
            }

            setStatus('Vote disponible! Clic sur le bouton...');

            const voteBtn = document.getElementById('btnGenerateOTP');
            if (!voteBtn) {
                setStatus('Bouton #btnGenerateOTP introuvable. Retry 1 min.');
                setTimeout(() => location.reload(), RETRY_DELAY_MS);
                return;
            }

            // Scroll vers le bouton
            voteBtn.scrollIntoView({ behavior: 'smooth', block: 'center' });
            await sleep(800);

            // Reset les flags cross-tab et marquer le vote en cours
            GM_setValue('external_vote_done', 0);
            GM_setValue('vote_in_progress', Date.now());

            voteBtn.click();
            setStatus('OTP généré. Attente du vote externe...');

            // Laisser le temps à l'onglet externe de s'ouvrir
            await sleep(3000);
            startPolling();
            return;
        }

        // --- ÉTAT INCONNU ---
        setStatus(`État inconnu: "${statusTitle}". Reload dans 1 min.`);
        setTimeout(() => location.reload(), RETRY_DELAY_MS);
    }

    // ========================================
    // POLLING (attend la confirmation du vote)
    // ========================================
    function startPolling() {
        let attempts = 0;
        const maxAttempts = 36; // 36 × 5s = 3 min max
        let externalDone = GM_getValue('external_vote_done', 0) > 0;

        // Écouter le signal cross-tab de serveur-prive.net
        const listenerId = GM_addValueChangeListener('external_vote_done', (name, oldVal, newVal, remote) => {
            if (newVal > 0) {
                externalDone = true;
                log('Signal cross-tab reçu: vote externe fait!');
                setStatus('Vote externe détecté! Vérification...');
                // Cliquer immédiatement sur manual check
                const manualBtn = document.getElementById('btnManualCheck');
                if (manualBtn && manualBtn.offsetParent !== null) {
                    manualBtn.click();
                }
            }
        });

        function cleanup() {
            try { GM_removeValueChangeListener(listenerId); } catch (e) {}
            GM_setValue('vote_in_progress', 0);
        }

        const interval = setInterval(() => {
            attempts++;

            // Vérifier si le statut a changé en cooldown
            const nowCard = document.getElementById('voteStatusCard');
            const nowClass = (nowCard?.className || '').toLowerCase();
            const nowTitle = (document.getElementById('voteStatusTitle')?.textContent || '').trim();

            if (nowClass.includes('cooldown') || nowTitle.toLowerCase().includes('cooldown')) {
                clearInterval(interval);
                cleanup();
                setStatus('Vote confirmé! Reload dans 3s...');
                setTimeout(() => location.reload(), 3000);
                return;
            }

            // Re-vérifier le flag cross-tab
            if (!externalDone) {
                const extVal = GM_getValue('external_vote_done', 0);
                if (extVal > 0) {
                    externalDone = true;
                    log('Flag external_vote_done détecté via polling');
                }
            }

            // Si le vote externe est fait, cliquer sur manual check
            if (externalDone) {
                const manualBtn = document.getElementById('btnManualCheck');
                if (manualBtn && manualBtn.offsetParent !== null) {
                    setStatus(`Vérification manuelle (${attempts}/${maxAttempts})...`);
                    manualBtn.click();
                } else {
                    setStatus(`Attente confirmation serveur (${attempts}/${maxAttempts})...`);
                }
            } else {
                setStatus(`Attente vote externe (${attempts}/${maxAttempts})...`);
            }

            if (attempts >= maxAttempts) {
                clearInterval(interval);
                cleanup();
                setStatus('Timeout polling. Reload...');
                location.reload();
            }
        }, 5000);
    }

    // ========================================
    // AUTRES PAGES play-hystoria.net
    // ========================================
    function handleOtherPage() {
        const nextVoteAt = GM_getValue('next_vote_at', 0);
        const voteInProgress = GM_getValue('vote_in_progress', 0);
        const now = Date.now();

        // Si un vote est en cours, rediriger vers /vote
        if (voteInProgress > 0 && (now - voteInProgress) < VOTE_IN_PROGRESS_TTL) {
            setStatus('Vote en cours! Redirection vers /vote...');
            setTimeout(() => {
                location.href = 'https://play-hystoria.net/vote';
            }, 2000);
            return;
        }

        // Si c'est l'heure de voter (dans la minute qui vient)
        if (nextVoteAt > 0 && now >= nextVoteAt - 60000) {
            setStatus('C\'est l\'heure de voter! Redirection...');
            setTimeout(() => {
                location.href = 'https://play-hystoria.net/vote';
            }, 2000);
            return;
        }

        // Sinon, afficher le statut sans rediriger
        if (nextVoteAt > 0 && nextVoteAt > now) {
            const remaining = Math.round((nextVoteAt - now) / 60000);
            setStatus(`Prochain vote dans ~${remaining} min.<br><a href="/vote" style="color:#4ecdc4;text-decoration:underline">Aller à /vote</a>`);
        } else {
            setStatus(`Bot actif.<br><a href="/vote" style="color:#4ecdc4;text-decoration:underline">Aller à /vote</a>`);
        }
    }

    // ========================================
    // ENTRY POINT
    // ========================================
    async function main() {
        injectBadge();
        await sleep(1000);

        const host = location.hostname;
        log('Démarrage sur', host, location.pathname);

        try {
            if (host.includes('serveur-prive.net')) {
                await handleExternalVote();

            } else if (host.includes('play-hystoria.net')) {
                if (location.pathname.includes('/login')) {
                    await handleLoginPage();
                } else if (location.pathname.includes('/vote')) {
                    await handleHystoriaVote();
                } else {
                    handleOtherPage();
                }
            }
        } catch (e) {
            err('Erreur:', e);
            setStatus(`Erreur: ${e.message}. Reload dans 1 min.`);
            setTimeout(() => location.reload(), RETRY_DELAY_MS);
        }
    }

    main();
})();
