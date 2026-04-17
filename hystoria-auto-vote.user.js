// ==UserScript==
// @name         Hystoria Auto-Voter
// @namespace    https://github.com/LLuuffyy/Bot-Hystoria
// @version      1.1.0
// @description  Vote automatiquement sur play-hystoria.net toutes les 1h30 pour gagner +50 ogrines
// @author       Zeliox83
// @match        https://play-hystoria.net/vote*
// @match        https://play-hystoria.net/vote/*
// @match        https://play-hystoria.net/login*
// @match        https://www.serveur-prive.net/*
// @match        https://serveur-prive.net/*
// @grant        GM_setValue
// @grant        GM_getValue
// @run-at       document-idle
// ==/UserScript==

(function() {
    'use strict';

    // --- CREDENTIALS (modifiables) ---
    const HYSTORIA_USERNAME = 'Zeliox83';
    const HYSTORIA_PASSWORD = 'Boston83';

    // --- CONFIG ---
    const VOTE_INTERVAL_MS = 90 * 60 * 1000;       // 1h30 par défaut si on ne peut pas lire le cooldown
    const RETRY_DELAY_MS = 60 * 1000;              // 1 min en cas d'erreur
    const POST_VOTE_BUFFER_MS = 30 * 1000;         // +30s après la fin du cooldown pour être tranquille
    const EXTERNAL_CLICK_DELAY_MS = 3000;          // attente avant de cliquer "Je vote maintenant"
    const EXTERNAL_CLOSE_DELAY_MS = 5000;          // attente après vote externe avant fermeture
    const LOGIN_REDIRECT_DELAY_MS = 5000;          // attente après login avant retour /vote

    // --- LOG HELPERS ---
    const LOG_PREFIX = '[Hystoria-Bot]';
    function log(...args) {
        console.log(LOG_PREFIX, ...args);
    }
    function warn(...args) {
        console.warn(LOG_PREFIX, ...args);
    }
    function err(...args) {
        console.error(LOG_PREFIX, ...args);
    }

    // --- UI BADGE (affiche le statut sur la page) ---
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
            await sleep(200);
        }
        return null;
    }

    function parseCooldownText(text) {
        // "1h 23m 45s" ou "23m 45s"
        let m = text.match(/(\d+)\s*h\s*(\d+)\s*m\s*(\d+)\s*s/);
        if (m) return parseInt(m[1])*3600 + parseInt(m[2])*60 + parseInt(m[3]);
        m = text.match(/(\d+)\s*m\s*(\d+)\s*s/);
        if (m) return parseInt(m[1])*60 + parseInt(m[2]);
        return null;
    }

    function isOnLoginPage() {
        if (location.pathname.includes('/login')) return true;
        // Détection alternative: présence d'un champ password sans Mon Profil
        const hasPassword = document.querySelector('input[type="password"]');
        const hasProfile = (document.body.textContent || '').includes('Mon Profil');
        return hasPassword && !hasProfile;
    }

    // --- PAGE login ---
    async function handleLoginPage() {
        setStatus('Page de login détectée. Tentative de reconnexion auto...');
        await sleep(1500);

        const userField = document.querySelector('input[name="username"]')
            || document.querySelector('input[name="email"]')
            || document.querySelector('input[type="email"]')
            || document.querySelector('input[name="login"]');

        const passField = document.querySelector('input[type="password"]');

        if (!userField || !passField) {
            setStatus('Champs login non trouvés.<br>Reconnecte-toi manuellement.');
            return;
        }

        userField.value = HYSTORIA_USERNAME;
        userField.dispatchEvent(new Event('input', { bubbles: true }));
        userField.dispatchEvent(new Event('change', { bubbles: true }));

        passField.value = HYSTORIA_PASSWORD;
        passField.dispatchEvent(new Event('input', { bubbles: true }));
        passField.dispatchEvent(new Event('change', { bubbles: true }));

        await sleep(500);

        // Trouver le bouton submit
        let submitBtn = document.querySelector('button[type="submit"]')
            || document.querySelector('input[type="submit"]');
        if (!submitBtn) {
            const buttons = document.querySelectorAll('button, a');
            for (const b of buttons) {
                const txt = (b.textContent || '').trim().toLowerCase();
                if (txt.includes('connexion') || txt.includes('se connecter') || txt === 'login') {
                    submitBtn = b;
                    break;
                }
            }
        }

        if (!submitBtn) {
            setStatus('Bouton submit non trouvé.<br>Reconnecte-toi manuellement.');
            return;
        }

        setStatus('Identifiants saisis. Clic sur Connexion...');
        submitBtn.click();

        // Après login, on attend puis on redirige vers /vote
        await sleep(LOGIN_REDIRECT_DELAY_MS);
        setStatus('Login effectué. Redirection vers /vote...');
        await sleep(2000);
        if (!location.pathname.includes('/vote')) {
            location.href = 'https://play-hystoria.net/vote';
        }
    }

    // --- PAGE externe serveur-prive.net ---
    async function handleExternalVote() {
        setStatus('Sur serveur-prive.net - attente de la page...');
        await sleep(EXTERNAL_CLICK_DELAY_MS);

        // Chercher le bouton/lien "Je vote maintenant"
        const candidates = document.querySelectorAll('a, button, input[type="submit"]');
        let voteEl = null;
        for (const el of candidates) {
            const txt = (el.textContent || el.value || '').trim().toLowerCase();
            if (txt.includes('je vote maintenant') || txt === 'voter' || txt.includes('voter maintenant')) {
                voteEl = el;
                break;
            }
        }

        if (voteEl) {
            setStatus('Clic sur "Je vote maintenant"...');
            voteEl.click();
            await sleep(EXTERNAL_CLOSE_DELAY_MS);
            setStatus('Vote externe effectué. Fermeture de l\'onglet...');
            // window.close() ne fonctionne que sur les onglets ouverts par script
            // Si ça ne ferme pas, pas grave, le script principal a déjà fait son taf
            try { window.close(); } catch(e) {}
        } else {
            warn('Bouton "Je vote maintenant" non trouvé');
            setStatus('Bouton "Je vote maintenant" non trouvé.<br>Tu peux cliquer manuellement.');
        }
    }

    // --- PAGE play-hystoria.net/vote ---
    async function handleHystoriaVote() {
        setStatus('Chargement de la page de vote...');

        // Vérifier d'abord si on a été redirigé sur /login
        await sleep(2000);
        if (isOnLoginPage()) {
            await handleLoginPage();
            return;
        }

        const statusCard = await waitFor('#voteStatusCard', 20000);
        if (!statusCard) {
            // Re-vérifier login au cas où
            if (isOnLoginPage()) {
                await handleLoginPage();
                return;
            }
            setStatus('Page de vote non détectée. Reload dans 1 min.');
            setTimeout(() => location.reload(), RETRY_DELAY_MS);
            return;
        }

        const cardClass = (statusCard.className || '').toLowerCase();
        const titleEl = document.getElementById('voteStatusTitle');
        const statusTitle = (titleEl?.textContent || '').trim();

        log('Status:', { cardClass, statusTitle });

        // --- COOLDOWN ---
        if (cardClass.includes('cooldown') || statusTitle.toLowerCase().includes('cooldown')) {
            const bodyText = document.body.textContent || '';
            const remaining = parseCooldownText(bodyText);
            let waitMs = VOTE_INTERVAL_MS;
            if (remaining && remaining > 0) {
                waitMs = remaining * 1000 + POST_VOTE_BUFFER_MS;
            }
            const mins = Math.round(waitMs / 60000);
            const nextTime = new Date(Date.now() + waitMs).toLocaleTimeString('fr-FR');
            setStatus(`Cooldown actif. Prochain vote dans <b>${mins} min</b><br>(à ${nextTime})`);
            setTimeout(() => location.reload(), waitMs);
            return;
        }

        // --- VOTE DISPONIBLE ---
        if (cardClass.includes('available') || statusTitle.includes('Disponible')) {
            setStatus('Vote disponible! Clic sur le bouton...');

            const voteBtn = document.getElementById('btnGenerateOTP');
            if (!voteBtn) {
                setStatus('Bouton #btnGenerateOTP introuvable. Retry dans 1 min.');
                setTimeout(() => location.reload(), RETRY_DELAY_MS);
                return;
            }

            voteBtn.click();
            setStatus('Clic effectué. Ouverture de l\'onglet externe...');
            await sleep(3000);

            // Polling du statut et du bouton de vérif manuelle
            let attempts = 0;
            const maxAttempts = 30; // 30 × 5s = 2.5 min max
            const interval = setInterval(async () => {
                attempts++;

                const nowClass = (document.getElementById('voteStatusCard')?.className || '').toLowerCase();
                const nowTitle = (document.getElementById('voteStatusTitle')?.textContent || '').trim();

                // Vote validé ?
                if (nowClass.includes('cooldown') || nowTitle.toLowerCase().includes('cooldown')) {
                    clearInterval(interval);
                    setStatus('Vote confirmé! Reload dans 3s...');
                    setTimeout(() => location.reload(), 3000);
                    return;
                }

                // Cliquer sur #btnManualCheck s'il est visible
                const manualBtn = document.getElementById('btnManualCheck');
                if (manualBtn && manualBtn.offsetParent !== null) {
                    setStatus(`Vérification manuelle (tentative ${attempts}/${maxAttempts})...`);
                    manualBtn.click();
                }

                if (attempts >= maxAttempts) {
                    clearInterval(interval);
                    setStatus('Timeout polling. Reload...');
                    location.reload();
                }
            }, 5000);
            return;
        }

        // --- ÉTAT INCONNU ---
        setStatus(`État inconnu: "${statusTitle}". Reload dans 1 min.`);
        setTimeout(() => location.reload(), RETRY_DELAY_MS);
    }

    // --- ENTRY POINT ---
    async function main() {
        injectBadge();
        await sleep(1500); // laisser la page se stabiliser

        const host = location.hostname;
        log('Démarrage sur', host, location.pathname);

        try {
            if (host.includes('serveur-prive.net')) {
                await handleExternalVote();
            } else if (host.includes('play-hystoria.net')) {
                if (location.pathname.includes('/login')) {
                    await handleLoginPage();
                } else {
                    await handleHystoriaVote();
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
