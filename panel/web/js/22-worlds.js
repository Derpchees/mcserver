// ============================================================
// Ajustes: pestana Mundo
// ============================================================
//
// Los mundos del servidor (el activo y las copias), regenerar, borrar,
// cambiar de mundo, subir uno (.zip o .mcworld), reiniciar el Nether o el
// End (Java) y las funciones experimentales. Ver webpanel/worlds.py.

let worldsData = null;

const WORLD_ICONS = {
    worlds: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18"/></svg>',
    flask: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 3h6M10 3v6L4.5 18.5A2 2 0 0 0 6.2 21h11.6a2 2 0 0 0 1.7-2.5L14 9V3"/><path d="M7 15h10"/></svg>',
    upload: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M17 8l-5-5-5 5M12 3v12"/></svg>'
};


async function loadWorlds() {

    try {
        const started = currentServer;
        const data = await api("/worlds?t=" + Date.now());

        if (currentServer !== started) return;

        worldsData = data;
        renderWorlds();
    } catch (error) {
        if (error.message !== "auth") showToast(error.message, "red");
    }
}


function worldCard(icon, title) {

    const card = el("div", "card");
    card.dataset.settab = "world";
    const head = el("div", "card-head");
    const h = el("h3", "card-title");
    const badge = el("span", "card-title-icon");
    badge.innerHTML = WORLD_ICONS[icon];
    h.append(badge, el("span", "", title));
    head.append(h);
    card.append(head);
    return card;
}


function renderWorlds() {

    const box = $("worldArea");
    box.textContent = "";

    if (!worldsData) return;

    box.append(worldsListCard(worldsData), experimentsCard(worldsData.experiments), worldUploadCard());
    applySettingsTab();
}


function worldsListCard(d) {

    const card = worldCard("worlds", t("world.title"));

    if (!d.exists) {
        card.append(el("div", "set-note", t("world.notCreated")));
    }

    const list = el("div", "world-list");

    d.worlds.forEach(function(world) {

        const row = el("div", "world-row" + (world.active ? " active" : ""));
        const text = el("div", "world-text");
        const name = el("div", "world-name", world.name);

        if (world.active) name.append(el("span", "tag green", t("world.active")));
        else if (world.copy) name.append(el("span", "tag", t("world.copy")));

        text.append(name, el("div", "world-meta", formatBytes(world.size) + " · " + new Date(world.mtime * 1000).toLocaleString()));

        const actions = el("div", "world-actions");

        if (!world.active) {
            const use = el("button", "btn btn-ghost btn-small", t("world.use"));
            use.onclick = function() { activateWorld(world); };

            const del = el("button", "btn btn-stop btn-small", t("world.delete"));
            del.onclick = function() { deleteWorld(world); };

            actions.append(use, del);
        }

        row.append(text, actions);
        list.append(row);
    });

    if (d.worlds.length) card.append(list);

    // Acciones sobre el mundo activo
    const tools = el("div", "world-tools");

    if (d.exists) {
        const regen = el("button", "btn btn-warn btn-small", t("world.regenerate"));
        regen.onclick = regenerateWorld;
        tools.append(regen);

        if (d.edition === "java") {
            ["nether", "end"].forEach(function(dim) {
                const btn = el("button", "btn btn-ghost btn-small", t("world.reset." + dim));
                btn.onclick = function() { resetDimension(dim); };
                tools.append(btn);
            });
        }
    }

    if (tools.childNodes.length) {
        card.append(tools);
        card.append(el("div", "field-hint", d.running ? t("world.stopsNote") : t("world.copyNote")));
    }

    return card;
}


async function worldAction(path, body, message) {

    try {
        const data = await postJson(path, body);
        showToast(data.restart ? t("world.restartToast") : message, data.restart ? "amber" : "green");
        await loadWorlds();
        loadSettings();
        return data;
    } catch (error) {
        showToast(error.message, "red");
        return null;
    }
}


async function regenerateWorld() {

    const seed = el("input", "input");
    seed.placeholder = t("world.seedPh");
    seed.maxLength = 64;
    seed.value = (worldsData && worldsData.seed) || "";

    const keep = toggleInput("worldKeepCopy", true);
    const keepRow = settingRow(t("world.keepCopy"), t("world.keepCopyDesc"), keep);

    const ok = await openModal({
        title: t("world.regenerateTitle"),
        hint: t("world.regenerateHint"),
        body: [el("label", "field-label", t("world.seed")), seed, keepRow],
        okText: t("world.regenerate"),
        okClass: "btn-warn",
        onOk: function() { return { seed: seed.value.trim(), keep: keep.checked }; }
    });

    if (!ok) return;

    await worldAction("/worlds/regenerate", ok, t("world.regenerated"));
}


async function deleteWorld(world) {

    if (!(await confirmDialog(t("world.deleteTitle"), t("world.deleteText", { name: world.name })))) return;
    await worldAction("/worlds/delete", { id: world.id }, t("world.deleted"));
}


async function activateWorld(world) {
    await worldAction("/worlds/activate", { id: world.id }, t("world.activated", { name: world.name }));
}


async function resetDimension(dim) {

    if (!(await confirmDialog(t("world.reset." + dim), t("world.resetText." + dim), t("world.resetBtn")))) return;
    await worldAction("/worlds/reset", { dim: dim }, t("world.resetDone"));
}


// ------------------------------------------------------------
// Funciones experimentales

function experimentsCard(info) {

    const card = worldCard("flask", t("exp.title"));

    if (!info || !info.items.length) {
        card.append(el("div", "field-hint", t("exp.none")));
        return card;
    }

    card.append(el("p", "hint", t(info.edition === "bedrock" ? "exp.descBedrock" : "exp.descJava")));

    if (!info.editable) card.append(el("div", "set-note", t("exp.locked")));

    const list = el("div", "set-list");

    info.items.forEach(function(item) {

        const toggle = toggleInput("exp-" + item.id, item.on);
        toggle.disabled = !info.editable;
        toggle.onchange = async function() {
            toggle.disabled = true;
            const values = {};
            values[item.id] = toggle.checked;

            try {
                const data = await postJson("/worlds/experiments", { values: values });
                showToast(data.restart ? t("exp.savedRestart") : t("exp.saved"), data.restart ? "amber" : "green");
            } catch (error) {
                toggle.checked = !toggle.checked;
                showToast(error.message, "red");
            }

            toggle.disabled = false;
        };

        list.append(settingRow(t("exp." + item.id), t("exp." + item.id + ".d"), toggle));
    });

    card.append(list);

    if (info.pending) card.append(el("div", "field-hint", t("exp.pending")));

    return card;
}


// ------------------------------------------------------------
// Subir un mundo

function worldUploadCard() {

    const card = worldCard("upload", t("world.uploadTitle"));
    const bedrock = worldsData && worldsData.edition === "bedrock";
    card.append(el("p", "hint", t(bedrock ? "world.uploadDescBedrock" : "world.uploadDescJava")));

    const input = el("input");
    input.type = "file";
    input.accept = bedrock ? ".mcworld,.zip" : ".zip";
    input.hidden = true;
    input.onchange = function() {
        if (input.files[0]) uploadWorld(input.files[0], card);
        input.value = "";
    };

    const button = el("button", "btn btn-ghost btn-small", t("world.uploadBtn"));
    button.onclick = function() { input.click(); };

    card.append(input, button);
    return card;
}


function uploadWorld(file, card) {

    const item = el("div", "upload");
    const label = el("div", "", t("fm.uploading", { name: file.name }));
    const meter = el("div", "meter");
    const bar = el("span");
    bar.style.width = "0%";
    bar.style.background = "var(--blue)";
    meter.append(bar);
    item.append(label, meter);
    card.append(item);

    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/s/" + currentServer + "/worlds/upload?name=" + encodeURIComponent(file.name));

    xhr.upload.onprogress = function(event) {
        if (!event.lengthComputable) return;
        bar.style.width = (event.loaded / event.total * 100) + "%";
        label.textContent = t("fm.uploadProgress", { name: file.name, done: formatBytes(event.loaded), total: formatBytes(event.total) });
    };

    xhr.onload = function() {
        item.remove();

        let data = {};
        try { data = JSON.parse(xhr.responseText); } catch (error) {}

        if (xhr.status === 200 && data.ok) {
            showToast(t("world.uploaded", { name: data.id }), "green");
            loadWorlds();
        } else {
            showToast(serverText(data.message) || t("fm.uploadError", { name: file.name }), "red");
        }
    };

    xhr.onerror = function() {
        item.remove();
        showToast(t("fm.uploadError", { name: file.name }), "red");
    };

    xhr.send(file);
}
