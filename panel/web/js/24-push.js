// ============================================================
// Notificaciones push (llegan con la pagina cerrada)
// ============================================================
//
// El service worker (/sw.js) recibe los avisos del agente y muestra las
// notificaciones. Aqui se registra, se suscribe el dispositivo y se le
// dejan el token, los textos y los iconos en la cache "mcpanel-push".
// Sin service worker (http://, certificado no confiable) quedan las
// notificaciones normales mientras la pagina esta abierta.

let swRegistration = null;
let pushActive = false;


async function registerWorker() {

    if (swRegistration) return swRegistration;
    if (!window.isSecureContext || !("serviceWorker" in navigator)) return null;

    try {
        swRegistration = await navigator.serviceWorker.register("/sw.js");
    } catch (error) {
        swRegistration = null;
    }

    return swRegistration;
}


function pushSupported() {
    return !!swRegistration && "PushManager" in window;
}


// En Android "new Notification" no existe: hay que pasar por el service worker
async function showSystemNotification(title, options) {

    options = Object.assign({ badge: "/icons/badge-96.png", icon: "/icons/icon-192.png" }, options);

    try {
        if (swRegistration) {
            await swRegistration.showNotification(title, options);
        } else {
            new Notification(title, options);
        }
        return true;
    } catch (error) {
        return false;
    }
}


function keyBytes(text) {
    const raw = atob(text.replace(/-/g, "+").replace(/_/g, "/") + "===".slice((text.length + 3) % 4));
    return Uint8Array.from(raw, function(c) { return c.charCodeAt(0); });
}


function pushToken() {
    try { return localStorage.getItem("mc-push-token") || ""; } catch (error) { return ""; }
}


// Lo que el service worker necesita para avisar sin abrir la pagina
async function savePushState() {

    const token = pushToken();
    if (!token || !("caches" in window)) return;

    const texts = {};
    Object.keys(I18N.en).forEach(function(key) {
        if (key.startsWith("ev2.")) texts[key.slice(4)] = I18N[lang][key] || I18N.en[key];
    });

    const icons = {};
    Object.keys(serverIconChoices).forEach(function(slug) { icons[slug] = notifyIcon(slug); });

    try {
        const cache = await caches.open("mcpanel-push");
        await cache.put("/push/state", new Response(JSON.stringify({
            token: token,
            title: (authState && authState.system_name) || "MCServer",
            generic: t("ntf.generic"),
            texts: texts,
            icons: icons
        }), { headers: { "Content-Type": "application/json" } }));
    } catch (error) {
    }
}


async function pushSubscribe() {

    if (!pushSupported() || !loggedIn()) return false;

    try {
        const reg = await navigator.serviceWorker.ready;
        let sub = await reg.pushManager.getSubscription();

        if (!sub) {
            const data = await (await fetch("/push/key")).json();
            sub = await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: keyBytes(data.key) });
        }

        const result = await postJson("/push/subscribe", { endpoint: sub.endpoint });
        if (!result.ok || !result.token) throw new Error(result.message || "push");

        try { localStorage.setItem("mc-push-token", result.token); } catch (error) {}
        pushActive = true;
        await savePushState();
    } catch (error) {
        pushActive = false;
    }

    return pushActive;
}


async function pushUnsubscribe() {

    pushActive = false;
    try { localStorage.removeItem("mc-push-token"); } catch (error) {}

    if (!swRegistration) return;

    try {
        const sub = await swRegistration.pushManager.getSubscription();

        if (sub) {
            await postJson("/push/unsubscribe", { endpoint: sub.endpoint });
            await sub.unsubscribe();
        }

        await caches.delete("mcpanel-push");
    } catch (error) {
    }
}


// Al abrir la pagina (y al entrar): con los avisos activos se renueva la
// suscripcion de este dispositivo a la cuenta actual
async function startPush() {
    await registerWorker();
    if (notifyEnabled()) await pushSubscribe();
    renderAlertsButton();
}
