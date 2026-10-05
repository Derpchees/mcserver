// ============================================================
// Avisos: boton de la campana en el encabezado
// ============================================================
//
// Un solo boton, en todas las paginas, que activa o desactiva todos los
// avisos de una vez: el sonido al encenderse un servidor (04-sound.js) y
// las notificaciones del navegador (24-notifications.js).

const ALERT_ICONS = {
    on: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9"/><path d="M10.3 21a1.94 1.94 0 0 0 3.4 0"/></svg>',
    off: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M8.7 3A6 6 0 0 1 18 8a21.3 21.3 0 0 0 .6 5"/><path d="M17 17H3s3-2 3-9a4.67 4.67 0 0 1 .3-1.7"/><path d="M10.3 21a1.94 1.94 0 0 0 3.4 0"/><path d="m2 2 20 20"/></svg>'
};


function alertsOn() {
    return soundOn || notifyEnabled();
}


function setNotify(on) {
    try { localStorage.setItem("mc-notify", on ? "on" : "off"); } catch (error) {}
}


// Por que no hay notificaciones aunque los avisos esten activos ("" si si hay)
function notifyProblem() {
    // Los navegadores solo permiten notificaciones en paginas seguras (HTTPS o localhost)
    if (!window.isSecureContext) return t("ntf.insecure");
    // En iPhone y iPad solo hay notificaciones con el panel agregado a la pantalla de inicio
    if (!("Notification" in window)) {
        return /iPhone|iPad|iPod/.test(navigator.userAgent) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1)
            ? t("ntf.ios") : t("ntf.unsupported");
    }
    if (Notification.permission === "denied") return t("ntf.denied");
    if (!loggedIn()) return t("alerts.loginNeeded");
    return "";
}


function renderAlertsButton() {

    const btn = $("alertsBtn");
    if (!btn) return;

    const on = alertsOn();
    btn.innerHTML = on ? ALERT_ICONS.on : ALERT_ICONS.off;
    btn.classList.toggle("is-off", !on);
    btn.setAttribute("aria-pressed", on ? "true" : "false");

    let title = on ? t("alerts.on") : t("alerts.off");
    if (on && !notifyEnabled() && notifyProblem()) title += " · " + notifyProblem();
    btn.title = title;
    btn.setAttribute("aria-label", title);
}


async function toggleAlerts() {

    if (alertsOn()) {
        soundOn = false;
        try { localStorage.setItem("mc-sound", "off"); } catch (error) {}
        setNotify(false);
        pushUnsubscribe();
        renderAlertsButton();
        showToast(t("alerts.turnedOff"), "amber");
        return;
    }

    soundOn = true;
    try { localStorage.setItem("mc-sound", "on"); } catch (error) {}
    getAudio();
    setTimeout(playChime, 60);

    let problem = notifyProblem();

    if (!problem) {
        const permission = Notification.permission === "granted"
            ? "granted"
            : await Notification.requestPermission();

        if (permission === "granted") {
            setNotify(true);
            await registerWorker();
            const push = await pushSubscribe();

            // Notificacion de prueba, con el icono del servidor abierto
            showSystemNotification(authState.system_name, {
                body: t("ntf.test") + " " + t(push ? "ntf.pushOn" : "ntf.pushOff"),
                icon: notifyIcon(currentServerInfo && currentServerInfo.slug)
            });
        } else {
            problem = t("ntf.denied");
        }
    }

    renderAlertsButton();
    showToast(problem ? t("alerts.soundOnly") + " " + problem : t("alerts.turnedOn"), problem ? "amber" : "green");
}


// Se dibuja aqui, cuando ya existen los iconos y el estado de ambos avisos
renderAlertsButton();
