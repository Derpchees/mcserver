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


function renderNotifySwitch() {

    const sw = $("notifySwitch");
    const on = notifyEnabled();
    sw.classList.toggle("on", on);
    sw.setAttribute("aria-checked", on ? "true" : "false");

    let state = t("ntf.off");

    if (!("Notification" in window)) state = t("ntf.unsupported");
    else if (Notification.permission === "denied") state = t("ntf.denied");
    else if (on) state = t("ntf.on");

    $("notifyState").textContent = state;
}


async function toggleNotifications() {

    if (!("Notification" in window)) return renderNotifySwitch();

    if (notifyEnabled()) {
        try { localStorage.setItem("mc-notify", "off"); } catch (error) {}
        return renderNotifySwitch();
    }

    const permission = Notification.permission === "granted"
        ? "granted"
        : await Notification.requestPermission();

    if (permission === "granted") {
        try { localStorage.setItem("mc-notify", "on"); } catch (error) {}
        new Notification(authState.system_name, { body: t("ntf.test"), icon: faviconUrl() });
    }

    renderNotifySwitch();
}


function faviconUrl() {
    const link = document.querySelector('link[rel="icon"]');
    return link ? link.href : undefined;
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
                new Notification(title, { body: text, icon: faviconUrl(), tag: "mc-" + event.id });
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
