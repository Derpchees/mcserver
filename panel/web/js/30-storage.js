// ============================================================
// Almacenamiento (administracion)
// ============================================================

const GIB = 1024 * 1024 * 1024;
const STORAGE_KIND_ORDER = ["newpart", "rebuild", "partition", "lvm", "folder"];

let storageTimer = null;
let storageJobRunning = false;


async function loadStorage() {

    clearTimeout(storageTimer);

    try {
        const data = await (await fetch("/admin/storage?t=" + Date.now())).json();
        const running = !!(data.job && data.job.running);

        // Al terminar una tarea se avisa y se actualiza el aviso general
        if (storageJobRunning && !running) {
            showToast(data.job.error ? t("sto.jobFailed") : t("sto.jobDone"), data.job.error ? "red" : "green");
            refreshAuth();
        }

        storageJobRunning = running;
        renderStorage(data);

        if (running && currentView === "admin") {
            storageTimer = setTimeout(loadStorage, 2000);
        }
    } catch (error) {
        $("admStorage").textContent = t("login.noConnection");
    }
}


function isSystemOwner() {
    return !!(authState && authState.user && authState.user.owner);
}


function gb(bytes) {
    return Math.floor((bytes || 0) / GIB);
}


function renderStorage(data) {

    const list = $("admStorage");
    list.textContent = "";

    const job = data.job || {};

    if (job.running) {
        list.append(storageJobBox(job));
    } else if (job.error) {
        list.append(el("div", "sto-note is-red", t("sto.lastFailed", { msg: job.error })));
    }

    list.append(storageRole(data.data, "data", data), storageRole(data.backups, "backups", data));
}


function storageJobBox(job) {

    const box = el("div", "sto-job");
    box.append(el("div", "sto-job-title", t("sto.working")));
    box.append(el("div", "sto-job-step", t("job." + job.step, job.vars || {}) || job.step || "..."));

    const bar = el("div", "sto-bar");
    const fill = el("span");

    if (job.progress === null || job.progress === undefined) {
        bar.classList.add("busy");
    } else {
        fill.style.width = job.progress + "%";
    }

    bar.append(fill);
    box.append(bar);
    return box;
}


function storageRole(info, role, data) {

    const box = el("div", "sto-role");
    const head = el("div", "sto-head");
    head.append(el("span", "sto-name", t("sto." + role)));
    head.append(el("span", "tag " + (info.available ? "green" : "red"),
        info.available ? t("sto.connected") : t("sto.disconnected")));
    box.append(head);

    box.append(el("div", "sto-path", info.path));

    if (info.available) {
        const kind = t("sto.kind." + info.kind) || info.kind;
        box.append(el("div", "pl-sub", kind + (info.disk ? " · " + info.disk : "")));

        const bar = el("div", "sto-bar");
        const fill = el("span");
        const percent = info.total ? Math.round(info.used / info.total * 100) : 0;
        fill.style.width = percent + "%";
        if (percent >= 90) fill.classList.add("full");
        bar.append(fill);
        box.append(bar);

        box.append(el("div", "pl-sub", t("sto.usage", {
            used: formatBytes(info.used), total: formatBytes(info.total), free: formatBytes(info.free)
        })));

        if (info.kind === "system") {
            box.append(el("div", "sto-note", t("sto.sharedNote")));
        }

        if (role === "backups" && info.same_disk) {
            box.append(el("div", "sto-note is-amber", t("sto.sameDisk")));
        }
    } else {
        box.append(el("div", "sto-note is-red", t("sto.missingDesc." + role, { mount: info.mount || "" })));
    }

    if (role === "backups" && data.backups_state === "missing") {
        box.append(el("div", "sto-note is-amber", t("sto.backupsPaused")));
    }

    if (role === "backups" && data.backups_state === "paused") {
        box.append(el("div", "sto-note", t("sto.backupsDisabled")));
    }

    const actions = el("div", "sto-actions");

    if (isSystemOwner()) {
        const move = el("button", "btn btn-ghost btn-small", t("sto.change"));
        move.disabled = !!(data.job && data.job.running);
        move.onclick = function() { chooseStorage(role); };
        actions.append(move);

        if (info.available && (info.kind === "lvm" || info.kind === "image") && info.can_grow >= GIB) {
            const grow = el("button", "btn btn-ghost btn-small", t("sto.grow"));
            grow.disabled = move.disabled;
            grow.onclick = function() { growStorage(role, info); };
            actions.append(grow);
        }

        if (role === "backups" && data.backups_state === "missing") {
            const pause = el("button", "btn btn-ghost btn-small", t("sto.disableNow"));
            pause.onclick = function() { setBackupsPaused(true); };
            actions.append(pause);
        }

        if (role === "backups" && data.backups_state === "paused") {
            const resume = el("button", "btn btn-ghost btn-small", t("sto.enableAgain"));
            resume.onclick = function() { setBackupsPaused(false); };
            actions.append(resume);
        }
    } else {
        actions.append(el("span", "pl-sub", t("sto.ownerOnly")));
    }

    box.append(actions);
    return box;
}


// ------------------------------------------------------------
// Elegir una ubicacion nueva
// ------------------------------------------------------------

function storageOptionTitle(option) {
    const vars = { target: option.target, disk: option.disk || option.target, label: option.label || "" };
    return t("sto.opt." + option.kind, vars);
}


function storageOptionRow(option, role, name) {

    const row = el("label", "sto-opt" + (option.current ? " is-current" : ""));
    const radio = el("input");
    radio.type = "radio";
    radio.name = name;
    radio.disabled = !!option.current;

    const text = el("div", "sto-opt-text");
    text.append(el("div", "sto-opt-title", storageOptionTitle(option)));

    const size = option.kind === "folder"
        ? t("sto.freeOf", { free: formatBytes(option.free), total: formatBytes(option.total) })
        : t("sto.free", { free: formatBytes(option.free) });
    text.append(el("div", "pl-sub", size + " · " + t("sto.optDesc." + option.kind)));

    const tags = el("div", "sto-tags");
    if (option.current) tags.append(el("span", "tag", t("sto.current")));
    if (option.empty_disk) tags.append(el("span", "tag blue", t("sto.emptyDisk")));
    if (option.kind === "rebuild") tags.append(el("span", "tag amber", t("sto.rebuildContent", { size: formatBytes(option.content) })));
    if (option.system_disk) tags.append(el("span", "tag", t("sto.systemDisk")));
    if (option.same_as_other) {
        tags.append(el("span", "tag amber", t(role === "backups" ? "sto.sameAsServers" : "sto.sameAsBackups")));
    }
    if (tags.childNodes.length) text.append(tags);

    row.append(radio, text);
    return { row: row, radio: radio };
}


async function chooseStorage(role) {

    let data;

    try {
        data = await (await fetch("/admin/storage/options?role=" + role + "&t=" + Date.now())).json();
    } catch (error) {
        return showToast(t("login.noConnection"), "red");
    }

    if (!data.options || !data.options.length) {
        return showToast(t("sto.noOptions"), "amber");
    }

    const options = data.options.slice().sort(function(a, b) {
        return STORAGE_KIND_ORDER.indexOf(a.kind) - STORAGE_KIND_ORDER.indexOf(b.kind);
    });

    const list = el("div", "sto-opts");
    const radios = [];

    options.forEach(function(option) {
        const item = storageOptionRow(option, role, "stoOpt");
        radios.push(item.radio);
        list.append(item.row);
    });

    const picked = await openModal({
        title: t("sto.chooseTitle." + role),
        wide: true,
        body: [t("sto.chooseDesc." + role), list],
        okText: t("dc.continue"),
        onOk: function() {
            const index = radios.findIndex(function(r) { return r.checked; });
            return index < 0 ? false : options[index];
        }
    });

    if (picked) configureStorage(role, picked, data.current);
}


function numberField(label, value, min, max) {

    const wrap = el("label", "sto-field");
    wrap.append(el("span", "", label));

    const input = el("input", "input set-input");
    input.type = "number";
    input.min = min;
    input.max = max;
    input.value = value;
    wrap.append(input, el("span", "pl-sub", t("sto.range", { min: min, max: max })));

    return { wrap: wrap, input: input };
}


function checkField(label, checked) {
    const wrap = el("label", "un-check sto-check");
    const box = el("input");
    box.type = "checkbox";
    box.checked = !!checked;
    wrap.append(box, document.createTextNode(" " + label));
    return { wrap: wrap, box: box };
}


async function configureStorage(role, option, current) {

    const body = [el("div", "sto-picked", storageOptionTitle(option))];
    const maxGb = Math.max(5, gb(option.free) - (option.kind === "folder" ? 1 : 0));
    let size = null;
    let reserve = null;
    let extra = null;
    let extraName = null;
    let existing = null;

    if (option.kind === "newpart" || option.kind === "rebuild") {
        size = numberField(t("sto.sizeGb"), role === "backups" ? Math.min(maxGb, Math.max(5, Math.floor(maxGb / 2))) : maxGb, 5, maxGb);
        body.push(size.wrap);

        extra = checkField(t("sto.extraPart"), false);
        extraName = el("input", "input");
        extraName.value = "cctv";
        extraName.placeholder = "cctv";
        const left = el("div", "pl-sub");

        const refresh = function() {
            const rest = maxGb - Number(size.input.value || 0);
            extra.wrap.hidden = rest < 5;
            extraName.hidden = !extra.box.checked || rest < 5;
            left.textContent = rest >= 5 ? t("sto.extraLeft", { gb: rest }) : t("sto.extraNone");
        };

        size.input.oninput = refresh;
        extra.box.onchange = refresh;
        body.push(extra.wrap, extraName, left, el("div", "sto-note",
            option.kind === "rebuild" ? t("sto.rebuildNote", { mounts: option.mounts.join(", ") }) : t("sto.newpartNote")));
        refresh();
    }

    if (option.kind === "lvm") {
        size = numberField(t("sto.sizeGb"), maxGb, 5, maxGb);
        body.push(size.wrap, el("div", "sto-note", t("sto.lvmNote")));
    }

    if (option.kind === "folder") {
        reserve = checkField(t("sto.reserve"), false);
        size = numberField(t("sto.sizeGb"), Math.min(maxGb, 100), 5, maxGb);
        const why = el("div", "sto-note", t("sto.folderNote"));
        const refresh = function() {
            size.wrap.hidden = !reserve.box.checked;
            why.textContent = reserve.box.checked ? t("sto.imageNote") : t("sto.folderNote");
        };
        reserve.box.onchange = refresh;
        body.push(reserve.wrap, size.wrap, why);
        refresh();
    }

    if (option.kind === "partition") {
        body.push(el("div", "sto-note", t("sto.partitionNote")));
    }

    if (role === "data") {
        body.push(el("div", "sto-note is-amber", t("sto.dataStop")));
    } else if (option.kind === "rebuild") {
        // Los respaldos del disco se devuelven solos a la particion nueva
    } else if (current && current.available) {
        existing = el("select", "input");
        ["move", "copy", "leave"].forEach(function(key) {
            const opt = el("option", "", t("sto.existing." + key));
            opt.value = key;
            existing.append(opt);
        });
        const wrap = el("label", "sto-field");
        wrap.append(el("span", "", t("sto.existingLabel")), existing);
        body.push(wrap);
    } else {
        body.push(el("div", "sto-note", t("sto.oldMissing")));
    }

    const params = await openModal({
        title: t("sto.chooseTitle." + role),
        wide: true,
        body: body,
        okText: t("dc.continue"),
        onOk: function() {
            const result = {
                role: role,
                kind: option.kind,
                target: option.target,
                start: option.start === undefined ? null : option.start,
                existing: existing ? existing.value : "leave"
            };

            if (option.kind === "folder" && reserve.box.checked) result.kind = "image";

            if (size && (option.kind !== "folder" || reserve.box.checked)) {
                const value = Number(size.input.value);
                if (!(value >= 5 && value <= maxGb)) {
                    size.input.focus();
                    return false;
                }
                result.size_gb = value;
            }

            if (extra && extra.box.checked && !extra.wrap.hidden) {
                result.extra_name = extraName.value.trim() || "cctv";
            }

            return result;
        }
    });

    if (!params) return;

    // Confirmacion: inicializar un disco vacio pide escribir su nombre
    let confirmed;

    if (option.kind === "newpart" && option.empty_disk) {
        confirmed = await doubleConfirm({
            title: t("sto.initTitle"),
            description: t("sto.initDesc", { disk: option.disk, name: option.disk_name }),
            word: option.disk_name,
            okText: t("sto.apply")
        });
    } else if (option.kind === "rebuild") {
        confirmed = await doubleConfirm({
            title: t("sto.rebuildTitle"),
            description: t("sto.rebuildDesc", { disk: option.disk, mounts: option.mounts.join(", "),
                                                 size: formatBytes(option.content), gb: params.size_gb }),
            word: option.disk_name,
            okText: t("sto.apply")
        });
    } else {
        confirmed = await confirmDialog(t("sto.confirmTitle"), storageSummary(role, option, params), t("sto.apply"));
    }

    if (!confirmed) return;

    try {
        await postJson("/admin/storage/relocate", params);
        showToast(t("sto.started"), "green");
        storageJobRunning = true;
        loadStorage();
        refreshAuth();
    } catch (error) {
        showToast(error.message, "red");
    }
}


function storageSummary(role, option, params) {

    const lines = [t("sto.sum." + params.kind, {
        target: option.target, disk: option.disk || option.target, gb: params.size_gb || ""
    })];

    if (params.extra_name) lines.push(t("sto.sumExtra", { name: params.extra_name }));
    if (role === "data") lines.push(t("sto.dataStop"));
    else lines.push(t("sto.existing." + params.existing));

    return lines.join(" ");
}


async function growStorage(role, info) {

    const current = gb(info.total);
    const max = gb(info.total + info.can_grow);
    const field = numberField(t("sto.sizeGb"), Math.min(max, current + 50), current + 1, max);

    const value = await openModal({
        title: t("sto.growTitle." + role),
        body: [t("sto.growDesc", { current: current }), field.wrap],
        okText: t("sto.grow"),
        onOk: function() {
            const n = Number(field.input.value);
            return n > current && n <= max ? n : false;
        }
    });

    if (!value) return;

    try {
        await postJson("/admin/storage/grow", { role: role, size_gb: value });
        showToast(t("sto.started"), "green");
        storageJobRunning = true;
        loadStorage();
    } catch (error) {
        showToast(error.message, "red");
    }
}


async function setBackupsPaused(paused) {
    try {
        await postJson("/admin/storage/backups", { paused: paused });
        await refreshAuth();
        if (currentView === "admin") loadStorage();
    } catch (error) {
        showToast(error.message, "red");
    }
}


// ------------------------------------------------------------
// Aviso para administradores en todo el panel
// ------------------------------------------------------------

function renderStorageBanner() {

    const banner = $("storageBanner");
    const alert = authState && authState.storage_alert;
    banner.textContent = "";

    if (!alert) {
        banner.hidden = true;
        return;
    }

    let tone = "amber";
    let text = "";
    const buttons = [];

    if (alert.busy) {
        text = t("sto.bannerBusy");
    } else if (!alert.data) {
        tone = "red";
        text = t("sto.bannerData");
    } else if (alert.backups === "missing") {
        text = t("sto.bannerBackups");

        if (isSystemOwner()) {
            buttons.push([t("sto.useOther"), function() { chooseStorage("backups"); }]);
            buttons.push([t("sto.disableNow"), function() { setBackupsPaused(true); }]);
        }
    } else {
        banner.hidden = true;
        return;
    }

    buttons.push([t("sto.open"), function() { go("#/admin/storage"); }]);

    banner.className = "sto-banner " + tone;
    banner.append(el("span", "sto-banner-text", text));

    const actions = el("div", "sto-actions");
    buttons.forEach(function([label, onClick]) {
        const btn = el("button", "btn btn-ghost btn-small", label);
        btn.onclick = onClick;
        actions.append(btn);
    });

    banner.append(actions);
    banner.hidden = false;
}


// El estado del disco puede cambiar sin que nadie haga nada
setInterval(function() {
    if (isAdmin()) refreshAuth();
}, 20000);
