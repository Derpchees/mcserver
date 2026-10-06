// ============================================================
// Respaldos automaticos (ajustes del servidor)
// ============================================================
//
// Una sola serie de respaldos con dos frecuencias: con el servidor
// encendido y con el servidor apagado (que puede ser "nunca", porque
// apagado el mundo no cambia). El servidor guarda horas; aqui se
// muestran en horas o dias.

const BACKUP_KEEP_MAX = 3;


function backupField(label, control) {
    const wrap = el("label", "field");
    wrap.append(el("span", "field-label", label), control);
    return wrap;
}


function intervalField(id, label, hours, allowNever) {

    const row = el("div", "interval-row");
    const number = el("input", "input");
    number.type = "number";
    number.id = id;
    number.min = 1;

    const unit = el("select", "input");
    unit.id = id + "Unit";

    const units = [["hours", t("cfg.unitHours")], ["days", t("cfg.unitDays")]];
    if (allowNever) units.push(["off", t("cfg.unitOff")]);

    units.forEach(function([value, text]) {
        const option = el("option", "", text);
        option.value = value;
        unit.append(option);
    });

    if (!hours) {
        unit.value = "off";
        number.value = 1;
    } else if (hours % 24 === 0) {
        unit.value = "days";
        number.value = hours / 24;
    } else {
        unit.value = "hours";
        number.value = hours;
    }

    // "Nunca" no lleva numero
    const refresh = function() {
        number.hidden = unit.value === "off";
        number.max = unit.value === "days" ? 30 : 720;
    };

    unit.onchange = refresh;
    refresh();

    row.append(number, segmentedFromSelect(unit));
    return backupField(label, row);
}


function readInterval(id) {
    const unit = $(id + "Unit").value;
    if (unit === "off") return 0;

    const n = Math.max(1, Math.round(Number($(id).value) || 0));
    return unit === "days" ? n * 24 : n;
}


function backupSection(info) {

    const grid = el("div", "form-grid");

    const box = toggleInput("cfgBackups", info.backups);
    const enabled = el("div", "set-list");
    enabled.append(settingRow(t("cfg.backups"), t("cfg.backupsDesc"), box));

    const start = el("input", "input");
    start.type = "time";
    start.id = "cfgBackupTime";
    start.value = info.backup_time;

    const keep = el("select", "input");
    keep.id = "cfgBackupKeep";

    for (let n = 1; n <= BACKUP_KEEP_MAX; n++) {
        const option = el("option", "", String(n));
        option.value = n;
        keep.append(option);
    }

    keep.value = Math.min(BACKUP_KEEP_MAX, Math.max(1, info.backup_keep || BACKUP_KEEP_MAX));

    grid.append(
        backupField(t("cfg.backupTime"), start),
        intervalField("cfgBackupEvery", t("cfg.everyOn"), info.backup_every_hours || 24, false),
        intervalField("cfgBackupEveryOff", t("cfg.everyOff"),
            info.backup_every_hours_off === undefined ? 24 : info.backup_every_hours_off, true),
        backupField(t("cfg.backupKeep"), segmentedFromSelect(keep))
    );

    // Las opciones no aplican si los respaldos estan desactivados
    const refresh = function() {
        grid.querySelectorAll("input, select").forEach(function(node) {
            if (node !== box) node.disabled = !box.checked;
        });
    };

    box.onchange = refresh;
    refresh();

    return [enabled, grid, el("div", "field-hint", t("cfg.backupHint"))];
}


function readBackupSchedule() {
    return {
        backups: $("cfgBackups").checked,
        backup_time: $("cfgBackupTime").value,
        backup_keep: Number($("cfgBackupKeep").value),
        backup_every_hours: readInterval("cfgBackupEvery"),
        backup_every_hours_off: readInterval("cfgBackupEveryOff")
    };
}
