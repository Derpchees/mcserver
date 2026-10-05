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


// Icono del servidor como PNG: las notificaciones del sistema no siempre
// muestran SVG. Se guarda para no dibujarlo en cada aviso.
const notifyIcons = {};

function notifyIcon(slug) {

    if (!slug) return "/icons/icon-192.png";

    const key = slug + ":" + (serverIconChoices[slug] || "");
    if (notifyIcons[key]) return notifyIcons[key];

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

        notifyIcons[key] = canvas.toDataURL("image/png");
    } catch (error) {
        notifyIcons[key] = serverIconUrl(slug);
    }

    return notifyIcons[key];
}


function eventText(event) {
    const vars = { server: event.server || "", msg: event.message || "" };
    const key = event.kind.split(":")[0];
    return t("ev2." + key, vars) || event.kind;
}


async function pollNotifications() {

    if (!loggedIn()) return;

    try {
        const response = await fetch("/events?since=" + notifyLast);
        // Sesion vencida: sin esto notifyLast quedaba indefinido
        if (!response.ok) return;

        const data = await response.json();
        const first = notifyLast < 0;
        notifyLast = data.last;

        if (first) return;

        (data.events || []).forEach(function(event) {
            const text = eventText(event);
            const title = event.server || authState.system_name;

            if (document.visibilityState !== "visible") {
                // Con push activo avisa el service worker (24-push.js); asi no se repite
                if (notifyEnabled() && !pushActive) {
                    showSystemNotification(title, {
                        body: text, icon: notifyIcon(event.server_slug), tag: "mc-" + event.id,
                        data: { url: event.server_id ? "/#/s/" + event.server_id : "/" }
                    });
                }
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
    startPush();

    if (!notifyTimer) {
        notifyTimer = setInterval(pollNotifications, 10000);
    }
}
