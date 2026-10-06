// ============================================================
// Ajustes del servidor: servidor, recursos, automatizacion y borrar
// ============================================================
//
// Se guardan junto con las reglas del juego desde la barra de "cambios
// sin guardar" (12-settings.js). Cualquier cambio hecho por la persona
// marca la configuracion como pendiente.

let configDirty = false;
let configServer = null;


function settingsCard(title, nodes, tab) {
    const card = el("div", "card");
    card.dataset.settab = tab;
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
    const main = serverFields("cfg", info, { resources: resources, cards: true, sliders: true });

    // Encendido y apagado automatico: interruptor y minutos con atajos
    const auto = el("div", "set-list");
    const autostop = toggleInput("cfgAutostop", info.autostop);

    const idle = el("input", "input quick-input");
    idle.id = "cfgIdle";
    idle.type = "number";
    idle.min = 1;
    idle.max = 1440;
    idle.value = info.idle_minutes;

    const idlePicks = quickPicks(idle, [5, 10, 15, 30, 60], function(n) { return t("cfg.minutesShort", { n: n }); });

    auto.append(settingRow(t("cfg.autostop"), t("cfg.autostopDesc"), autostop),
        settingRow(t("cfg.idle"), t("cfg.idleDesc"), idlePicks));

    // Sin apagado automatico los minutos no aplican
    const refreshAuto = function() {
        idle.disabled = !autostop.checked;
        idlePicks.classList.toggle("disabled", !autostop.checked);
    };

    autostop.addEventListener("change", refreshAuto);
    refreshAuto();

    box.append(
        settingsCard(t("cfg.cardServer"), [main, el("div", "field-hint", t("cfg.rebuildHint"))], "server"),
        settingsCard(t("cfg.cardResources"), [resources], "server"),
        settingsCard(t("cfg.automation"), [auto], "auto"),
        settingsCard(t("cfg.backupSection"), backupSection(info), "auto")
    );

    applySettingsTab();

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
