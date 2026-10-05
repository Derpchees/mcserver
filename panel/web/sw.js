// ============================================================
// MCServer by Derpchees - Service worker
// ============================================================
//
// Muestra las notificaciones aunque la pagina este cerrada o el celular
// bloqueado. El aviso push llega vacio; aqui se piden los eventos al panel
// con el token del dispositivo. La pagina guarda ese token, los textos en
// su idioma y los iconos de los servidores en la cache "mcpanel-push"
// (24-push.js).

const STATE_CACHE = "mcpanel-push";
const STATE_URL = "/push/state";


self.addEventListener("install", function() {
    self.skipWaiting();
});

self.addEventListener("activate", function(event) {
    event.waitUntil(self.clients.claim());
});


async function readState() {
    try {
        const cache = await caches.open(STATE_CACHE);
        const response = await cache.match(STATE_URL);
        return response ? await response.json() : {};
    } catch (error) {
        return {};
    }
}


function eventText(state, event) {
    const template = (state.texts || {})[event.kind.split(":")[0]];
    if (!template) return event.message || event.kind;

    return template.replace(/\{server\}/g, event.server || "").replace(/\{msg\}/g, event.message || "");
}


async function showEvents() {

    const state = await readState();
    let events = null;

    try {
        const response = await fetch("/push/events", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ token: state.token || "" })
        });

        if (response.ok) events = (await response.json()).events || [];
    } catch (error) {
    }

    // Con la pagina a la vista ella misma avisa (con su mensaje flotante)
    const windows = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
    if (windows.some(function(client) { return client.visibilityState === "visible"; })) return;

    const icons = state.icons || {};
    const common = { badge: "/icons/badge-96.png", icon: "/icons/icon-192.png" };

    // Sin conexion al panel (fuera de la VPN, por ejemplo): un aviso general
    if (!events || !events.length) {
        return self.registration.showNotification(state.title || "MCServer", Object.assign({
            body: state.generic || "", tag: "mc-generic", data: { url: "/" }
        }, common));
    }

    return Promise.all(events.slice(-5).map(function(event) {
        return self.registration.showNotification(event.server || state.title || "MCServer", Object.assign({}, common, {
            body: eventText(state, event),
            icon: (event.server_slug && icons[event.server_slug]) || common.icon,
            tag: "mc-" + event.id,
            data: { url: event.server_id ? "/#/s/" + event.server_id : "/" }
        }));
    }));
}


self.addEventListener("push", function(event) {
    event.waitUntil(showEvents());
});


// Al tocar la notificacion se abre el panel (o se enfoca si ya estaba abierto)
self.addEventListener("notificationclick", function(event) {
    event.notification.close();
    const url = new URL((event.notification.data && event.notification.data.url) || "/", self.location.origin).href;

    event.waitUntil(self.clients.matchAll({ type: "window", includeUncontrolled: true }).then(function(windows) {
        for (const client of windows) {
            if ("focus" in client) {
                return client.focus().then(function(focused) {
                    return focused && focused.navigate ? focused.navigate(url).catch(function() {}) : null;
                });
            }
        }
        return self.clients.openWindow(url);
    }));
});
