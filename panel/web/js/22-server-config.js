// ============================================================
// Ajustes del servidor: servidor, recursos, automatizacion y borrar
// ============================================================
//
// Se guardan junto con las reglas del juego desde la barra de "cambios
// sin guardar" (12-settings.js). Cualquier cambio hecho por la persona
// marca la configuracion como pendiente.

let configDirty = false;
let configServer = null;


function settingsCard(title, nodes) {
    const card = el("div", "card");
    const head = el("div", "card-head");
    head.append(el("h3", "card-title", title));
    card.append(head);
    nodes.forEach(function(node) { card.append(node); });
    return card;
}


function renderServerConfig(force) {

    const info = currentServerInfo;
    const box = $("serverConfig");

    if (!info || !box) return;

    // Al volver a la pestana no se pierde lo que no se ha guardado, pero
    // solo si sigue siendo el mismo servidor
    if (configDirty && !force && configServer === info.id) return;

    configDirty = false;
    configServer = info.id;
    box.textContent = "";

    const resources = el("div", "form-grid");
    const main = serverFields("cfg", info, { resources: resources });

    const auto = el("div", "form-grid");

    const check = function(id, label, checked) {
        const wrap = el("label", "un-check");
        const node = el("input");
        node.type = "checkbox";
        node.id = id;
        node.checked = checked;
        wrap.append(node, document.createTextNode(" " + label));
        auto.append(wrap);
        return node;
    };

    const number = function(id, label, value, min, max) {
        const wrap = el("label", "field");
        const node = el("input", "input");
        node.id = id;
        node.type = "number";
        if (min !== undefined) { node.min = min; node.max = max; }
        node.value = value;
        wrap.append(el("span", "field-label", label), node);
        auto.append(wrap);
        return node;
    };

    check("cfgAutostop", t("cfg.autostop"), info.autostop);
    number("cfgIdle", t("cfg.idle"), info.idle_minutes, 1, 1440);

    box.append(
        settingsCard(t("cfg.cardServer"), [main, el("div", "field-hint", t("cfg.rebuildHint"))]),
        settingsCard(t("cfg.cardResources"), [resources]),
        settingsCard(t("cfg.automation"), [auto]),
        settingsCard(t("cfg.backupSection"), backupSection(info))
    );

    // Solo los cambios hechos por la persona (no los que hace el codigo al cargar listas)
    box.oninput = box.onchange = function() {
        if (!configDirty) {
            configDirty = true;
            renderSettingsBar();
        }
    };
}


async function saveServerConfig() {

    const body = Object.assign(readServerFields("cfg"), {
        autostop: $("cfgAutostop").checked,
        idle_minutes: Number($("cfgIdle").value)
    }, readBackupSchedule());

    try {
        const data = await postJson("/server/update", body);
        configDirty = false;
        showToast(data.rebuild ? t("cfg.rebuilding") : serverText(data.message), "green");
        setTimeout(update, 600);
        // El nombre tambien sale en el menu de la cuenta
        refreshAuth();
        return true;
    } catch (error) {
        showToast(error.message, "red");
        return false;
    }
}


async function deleteCurrentServer() {

    const info = currentServerInfo;

    const result = await doubleConfirm({
        title: t("srv.deleteTitle"),
        description: t("srv.deleteDesc", { name: info.name }),
        choices: [["purge_data", t("un.purgeData")], ["purge_backups", t("un.purgeBackups")]],
        word: info.name,
        okText: t("srv.deleteBtn")
    });

    if (!result) return;

    try {
        await postJson("/server/delete", result);
        showToast(t("srv.deleted"), "green");
        await refreshAuth();
        leaveServer();
        go("#/");
    } catch (error) {
        showToast(error.message, "red");
    }
}
