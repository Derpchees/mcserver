// ============================================================
// Notificaciones del navegador
// ============================================================

let notifyLast = -1;
let notifyTimer = null;

function notifyEnabled() {
    try {
        return localStorage.getItem("mc-notify") === "on" && "Notification" in window
            && Notification.permission === "granted";
    } catch (error) {
        return false;
    }
}


// El boton es la campana del encabezado (24-alerts.js)
function renderNotifySwitch() {
    renderAlertsButton();
}


function faviconUrl() {
    const link = document.querySelector('link[rel="icon"]');
    return link ? link.href : undefined;
}


// Icono del servidor como PNG: las notificaciones del sistema no siempre
// muestran SVG. Se guarda para no dibujarlo en cada aviso.
const notifyIcons = {};

function notifyIcon(slug) {

    if (!slug) return SYSTEM_FAVICON || faviconUrl();
    if (notifyIcons[slug]) return notifyIcons[slug];

    try {
        const size = 96;
        const cell = size / ICON_GRID;
        const canvas = document.createElement("canvas");
        canvas.width = canvas.height = size;
        const ctx = canvas.getContext("2d");

        serverIconPixels(slug).forEach(function(rgb, i) {
            ctx.fillStyle = "rgb(" + rgb.join(",") + ")";
            ctx.fillRect((i % ICON_GRID) * cell, Math.floor(i / ICON_GRID) * cell, cell, cell);
        });

        notifyIcons[slug] = canvas.toDataURL("image/png");
    } catch (error) {
        notifyIcons[slug] = serverIconUrl(slug);
    }

    return notifyIcons[slug];
}


function eventText(event) {
    const vars = { server: event.server || "", msg: event.message || "" };
    const key = event.kind.split(":")[0];
    return t("ev2." + key, vars) || event.kind;
}


async function pollNotifications() {

    if (!loggedIn()) return;

    try {
        const data = await (await fetch("/events?since=" + notifyLast)).json();
        const first = notifyLast < 0;
        notifyLast = data.last;

        if (first) return;

        (data.events || []).forEach(function(event) {
            const text = eventText(event);
            const title = event.server || authState.system_name;

            if (notifyEnabled() && document.visibilityState !== "visible") {
                new Notification(title, { body: text, icon: notifyIcon(event.server_slug), tag: "mc-" + event.id });
            } else {
                showToast(title + ": " + text,
                    event.level === "error" ? "red" : event.level === "warning" ? "amber" : "green");
            }
        });
    } catch (error) {
    }
}


function startNotifications() {
    notifyLast = -1;
    pollNotifications();

    if (!notifyTimer) {
        notifyTimer = setInterval(pollNotifications, 10000);
    }
}
