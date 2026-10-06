// ============================================================
// Add-ons de Bedrock (gratis: subidos o de CurseForge)
// ============================================================
//
// Ocupan la pestana de Mods en los servidores Bedrock (#addonsArea).
// Instalar, activar, desactivar o quitar se aplica al reiniciar.

let addonsData = null;
const addonsRemove = new Set();
let addonsDropReady = false;
// Servidores con cambios de add-ons desde el ultimo reinicio desde aqui
const addonsChangedOn = new Set();


async function loadAddons() {

    $("modsJava").hidden = true;
    $("addonsArea").hidden = false;
    setupAddonsDrop();

    try {
        const started = currentServer;
        const data = await api("/addons?t=" + Date.now());

        if (currentServer !== started) return;

        addonsData = data;
        const present = new Set(data.addons.map(function(a) { return a.uuid; }));
        Array.from(addonsRemove).forEach(function(uuid) { if (!present.has(uuid)) addonsRemove.delete(uuid); });
        renderAddons();
    } catch (error) {
        if (error.message !== "auth") showToast(error.message, "red");
    }
}


function addonIconUrl(item) {
    return item.icon ? "/s/" + currentServer + "/addons/icon?uuid=" + encodeURIComponent(item.uuid) : "";
}


function addonSwitch(item) {

    const sw = el("button", "switch" + (item.enabled ? " on" : ""));
    sw.type = "button";
    sw.setAttribute("role", "switch");
    sw.setAttribute("aria-checked", item.enabled ? "true" : "false");
    sw.setAttribute("aria-label", t("addons.toggle"));
    sw.title = t("addons.toggle");
    sw.append(el("span", "switch-knob"));
    sw.onclick = function() { toggleAddon(item, !item.enabled, sw); };
    return sw;
}


function renderAddons() {

    const d = addonsData;
    if (!d) return;

    $("addonsNoKey").hidden = d.cf_enabled;
    $("addonsSearchForm").hidden = !d.cf_enabled;
    $("addonsRestart").hidden = !(d.running && addonsChangedOn.has(currentServer));
    renderAddonOptions(d);

    const box = $("addonsList");
    box.textContent = "";

    if (!d.addons.length) box.append(el("div", "list-empty", t("addons.none")));

    d.addons.forEach(function(item) {

        const check = modCheck(addonsRemove.has(item.uuid), function(on) {
            if (on) addonsRemove.add(item.uuid); else addonsRemove.delete(item.uuid);
            renderAddonsBar();
        });

        const source = item.source.provider === "curseforge" ? "CurseForge"
            : item.source.provider === "upload" ? t("addons.fromUpload") : t("addons.fromFolder");

        const row = modRow({
            name: item.name,
            icon: addonIconUrl(item),
            summary: item.description,
            meta: [t("addons.kind." + item.kind), "v" + item.version_text, source].join(" · ")
        }, addonSwitch(item), check);

        row.classList.toggle("addon-off", !item.enabled);

        if (item.beta) {
            const tag = el("span", "tag amber", t("addons.beta"));
            tag.title = t("addons.betaHint");
            row.querySelector(".mod-name").append(tag);
        }

        box.append(row);
    });

    $("addonsAll").checked = d.addons.length > 0 && addonsRemove.size === d.addons.length;
    renderAddonsBar();
}


// Paquetes de recursos obligatorios: lo decide el dueno del servidor
function renderAddonOptions(d) {

    const box = $("addonsOptions");
    box.textContent = "";

    const toggle = toggleInput("addonsTextures", d.textures_required);
    toggle.disabled = !d.has_properties;
    toggle.onchange = async function() {
        toggle.disabled = true;

        try {
            const data = await postJson("/addons/textures", { required: toggle.checked });
            addonsChanged(data, toggle.checked ? t("addons.texturesOn") : t("addons.texturesOff"));
        } catch (error) {
            toggle.checked = !toggle.checked;
            toggle.disabled = false;
            showToast(error.message, "red");
        }
    };

    box.append(settingRow(t("addons.texturesReq"), t("addons.texturesReqDesc"), toggle));

    const note = el("div", "field-hint addons-note", d.has_properties ? t("addons.behaviorNote") : t("addons.startFirst"));
    box.append(note);
}


function renderAddonsBar() {
    $("addonsRemoveBtn").disabled = addonsRemove.size === 0;
    $("addonsRemoveBtn").textContent = addonsRemove.size
        ? t("mods.removeSelected", { n: addonsRemove.size }) : t("mods.remove");
}


function toggleAllAddons(on) {
    addonsRemove.clear();
    if (on) addonsData.addons.forEach(function(a) { addonsRemove.add(a.uuid); });
    renderAddons();
}


// Despues de un cambio: aviso de reinicio si el servidor esta encendido
function addonsChanged(data, message) {
    if (data.running) addonsChangedOn.add(currentServer);
    showToast(message + " " + (data.running ? t("addons.restartToast") : t("addons.nextStartToast")),
        data.running ? "amber" : "green");
    loadAddons();
}


async function toggleAddon(item, on, sw) {

    sw.disabled = true;

    try {
        const data = await postJson("/addons/toggle", { uuid: item.uuid, enabled: on });
        addonsChanged(data, on ? t("addons.enabledToast") : t("addons.disabledToast"));
    } catch (error) {
        sw.disabled = false;
        showToast(error.message, "red");
    }
}


async function removeSelectedAddons() {

    if (!addonsRemove.size) return;

    const ok = await confirmDialog(t("addons.removeTitle"), tn("addons.removeDesc", addonsRemove.size), t("mods.remove"));
    if (!ok) return;

    try {
        const data = await postJson("/addons/remove", { uuids: Array.from(addonsRemove) });
        addonsRemove.clear();
        addonsChanged(data, tn("addons.removedN", data.removed));
    } catch (error) {
        showToast(error.message, "red");
    }
}


// ------------------------------------------------------------
// Subir archivos (.mcaddon, .mcpack, .zip)

function setupAddonsDrop() {

    if (addonsDropReady) return;
    addonsDropReady = true;

    const drop = $("addonsDrop");

    drop.addEventListener("dragover", function(event) {
        event.preventDefault();
        drop.classList.add("over");
    });

    drop.addEventListener("dragleave", function() {
        drop.classList.remove("over");
    });

    drop.addEventListener("drop", function(event) {
        event.preventDefault();
        drop.classList.remove("over");
        uploadAddons(event.dataTransfer.files);
    });
}


async function uploadAddons(fileList) {

    const files = Array.from(fileList || []);

    // Uno por uno: cada archivo se instala al terminar de subir
    for (const file of files) {
        if (!/\.(mcaddon|mcpack|zip)$/i.test(file.name)) {
            showToast(file.name + ": " + t("addons.badFile"), "red");
            continue;
        }

        const data = await uploadAddon(file);
        if (data) addonsChanged(data, t("addons.installedToast", { names: installedNames(data) }));
    }
}


function installedNames(data) {
    return (data.installed || []).map(function(p) { return p.name; }).join(", ");
}


function uploadAddon(file) {

    return new Promise(function(resolve) {

        const item = el("div", "upload");
        const label = el("div", "", t("fm.uploading", { name: file.name }));
        const meter = el("div", "meter");
        const bar = el("span");
        bar.style.width = "0%";
        bar.style.background = "var(--blue)";
        meter.append(bar);
        item.append(label, meter);
        $("addonsUploads").append(item);

        const xhr = new XMLHttpRequest();
        xhr.open("POST", "/addons/upload?name=" + encodeURIComponent(file.name));

        xhr.upload.onprogress = function(event) {
            if (!event.lengthComputable) return;
            bar.style.width = (event.loaded / event.total * 100) + "%";
            label.textContent = event.loaded >= event.total
                ? t("addons.installing", { name: file.name })
                : t("fm.uploadProgress", { name: file.name, done: formatBytes(event.loaded), total: formatBytes(event.total) });
        };

        xhr.onload = function() {
            item.remove();

            let data = {};
            try { data = JSON.parse(xhr.responseText); } catch (error) {}

            if (xhr.status === 401) {
                showLogin();
                return resolve(null);
            }

            if (xhr.status === 200 && data.ok) return resolve(data);

            showToast(file.name + ": " + (serverText(data.message) || t("fm.uploadError", { name: file.name })), "red");
            resolve(null);
        };

        xhr.onerror = function() {
            item.remove();
            showToast(t("fm.uploadError", { name: file.name }), "red");
            resolve(null);
        };

        xhr.send(file);
    });
}


// ------------------------------------------------------------
// CurseForge (todo es gratis)

async function searchAddons(event, page) {

    if (event) event.preventDefault();
    if (page === undefined) page = 0;

    const box = $("addonsResults");
    loadingList(box);

    try {
        const started = currentServer;
        const data = await api("/addons/search?kind=" + $("addonsKind").value
            + "&q=" + encodeURIComponent($("addonsQuery").value.trim())
            + "&sort=" + $("addonsSort").value + "&page=" + page);

        if (currentServer !== started) return;

        box.textContent = "";
        renderResultsInfo($("addonsResultsInfo"), data);
        if (!data.results.length) box.append(el("div", "list-empty", t("mods.noResults")));

        const installed = new Set((addonsData && addonsData.installed_cf) || []);

        data.results.forEach(function(item) {
            box.append(modRow(item, addonResultAction(item, installed.has(String(item.id))), null));
        });

        renderPager($("addonsPager"), data.page || 0, data.pages || 1, function(n) {
            searchAddons(null, n);
            $("addonsSearchForm").scrollIntoView({ behavior: "smooth", block: "start" });
        });
    } catch (error) {
        box.textContent = "";
        box.append(el("div", "list-empty", error.message === "auth" ? "" : error.message));
    }
}


function addonResultAction(item, installed) {

    // Algunos autores solo permiten bajarlo desde su pagina
    if (!item.downloadable) {
        const link = el("a", "btn btn-ghost btn-small", t("addons.openPage"));
        link.href = item.url;
        link.target = "_blank";
        link.rel = "noopener";
        link.title = t("addons.onlyWebsite");
        return link;
    }

    const wrap = el("div", "addon-actions");

    if (installed) wrap.append(el("span", "tag green", t("mods.added")));

    const button = el("button", "btn btn-small " + (installed ? "btn-ghost" : "btn-start"),
        installed ? t("addons.reinstall") : t("addons.install"));
    button.title = installed ? t("addons.reinstallHint") : "";
    button.onclick = function() { installAddon(item, button); };
    wrap.append(button);

    return wrap;
}


async function installAddon(item, button) {

    const text = button.textContent;
    button.disabled = true;
    button.textContent = t("addons.installingShort");

    try {
        const data = await postJson("/addons/install", { id: item.id });
        addonsChanged(data, t("addons.installedToast", { names: installedNames(data) || item.name }));
        button.textContent = t("addons.reinstall");
        button.className = "btn btn-small btn-ghost";
    } catch (error) {
        button.textContent = text;
        showToast(error.message, "red");
    }

    button.disabled = false;
}
