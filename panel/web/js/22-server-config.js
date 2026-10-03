// ============================================================
// Ajustes del servidor: recursos, automatizacion y borrar
// ============================================================

function renderServerConfig() {

    const info = currentServerInfo;
    const box = $("serverConfig");

    if (!info || !box) return;

    box.textContent = "";
    box.append(serverFields("cfg", info));

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
        node.type = id === "cfgBackupTime" ? "time" : "number";
        if (min !== undefined) { node.min = min; node.max = max; }
        node.value = value;
        wrap.append(el("span", "field-label", label), node);
        auto.append(wrap);
        return node;
    };

    check("cfgAutostop", t("cfg.autostop"), info.autostop);
    number("cfgIdle", t("cfg.idle"), info.idle_minutes, 1, 1440);
    check("cfgBackups", t("cfg.backups"), info.backups);
    number("cfgBackupTime", t("cfg.backupTime"), info.backup_time);
    number("cfgBackupKeep", t("cfg.backupKeep"), info.backup_keep, 1, 60);

    box.append(el("div", "form-section", t("cfg.automation")), auto);
    box.append(el("div", "field-hint", t("cfg.rebuildHint")));
}


async function saveServerConfig() {

    const body = Object.assign(readServerFields("cfg"), {
        autostop: $("cfgAutostop").checked,
        idle_minutes: Number($("cfgIdle").value),
        backups: $("cfgBackups").checked,
        backup_time: $("cfgBackupTime").value,
        backup_keep: Number($("cfgBackupKeep").value)
    });

    try {
        const data = await postJson("/server/update", body);
        showToast(data.rebuild ? t("cfg.rebuilding") : serverText(data.message), "green");
        setTimeout(update, 600);
    } catch (error) {
        showToast(error.message, "red");
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
