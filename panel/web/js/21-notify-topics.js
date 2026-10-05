// ============================================================
// Mi cuenta: de que avisa el panel
// ============================================================
//
// Cada tema se puede silenciar; aplica a la campana de la pagina y a los
// avisos push de todos los dispositivos (push/kinds.py).

const NOTIFY_TOPICS = ["online", "offline", "problems", "backups", "system"];


function renderNotifyTopics() {

    const box = $("notifyTopics");
    const muted = (authState.user && authState.user.notify_mute) || [];
    box.textContent = "";

    NOTIFY_TOPICS.forEach(function(topic) {

        // Las alertas del equipo solo le llegan al administrador
        if (topic === "system" && !isAdmin()) return;

        const row = el("div", "set-row");
        const text = el("div", "set-text");
        text.append(el("div", "set-label", t("ntp." + topic)), el("div", "set-desc", t("ntp." + topic + ".d")));

        const label = el("label", "switch-check");
        const input = el("input");
        input.type = "checkbox";
        input.dataset.topic = topic;
        input.checked = muted.indexOf(topic) < 0;
        input.onchange = saveNotifyTopics;
        label.append(input);

        row.append(text, label);
        box.append(row);
    });
}


async function saveNotifyTopics() {

    const mute = Array.from($("notifyTopics").querySelectorAll("input")).filter(function(input) {
        return !input.checked;
    }).map(function(input) { return input.dataset.topic; });

    // Lo que un usuario normal no ve se conserva como estaba
    if (!isAdmin() && authState.user.notify_mute.indexOf("system") >= 0) mute.push("system");

    try {
        const data = await postJson("/me/notify", { mute: mute });
        authState.user.notify_mute = mute;
        showToast(serverText(data.message), "green");
    } catch (error) {
        showToast(error.message, "red");
        renderNotifyTopics();
    }
}
