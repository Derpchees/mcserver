// ============================================================
// Mods, plugins y modpack (Modrinth)
// ============================================================

let modsData = null;
const modsPicked = new Map();
const modsRemove = new Set();
const filesRemove = new Set();


function typeName(type) {
    return {
        FORGE: "Forge", NEOFORGE: "NeoForge", FABRIC: "Fabric", PAPER: "Paper",
        VANILLA: "Vanilla", AUTO_CURSEFORGE: t("type.modpackShort"), MODRINTH: t("type.modpackShort")
    }[type] || type;
}


function compactNumber(n) {
    try {
        return new Intl.NumberFormat(locale(), { notation: "compact" }).format(n || 0);
    } catch (error) {
        return String(n || 0);
    }
}


async function loadMods() {
    try {
        const started = currentServer;
        const data = await api("/mods?t=" + Date.now());

        if (currentServer !== started) return;

        modsData = data;
        modsRemove.clear();
        filesRemove.clear();
        renderMods();
    } catch (error) {
        if (error.message !== "auth") showToast(error.message, "red");
    }
}


function modCheck(checked, onChange) {
    const box = el("input", "check");
    box.type = "checkbox";
    box.checked = checked;
    box.onclick = function(event) { event.stopPropagation(); };
    box.onchange = function() { onChange(box.checked); };
    return box;
}


function modRow(item, button, check) {

    const row = el("div", "mod-row");

    if (check) {
        row.append(check);
        row.classList.add("selectable");
        row.onclick = function(event) {
            if (event.target.closest("button, a, input")) return;
            check.checked = !check.checked;
            check.onchange();
        };
    }

    const icon = el("div", "mod-icon");

    if (item.icon) {
        const img = document.createElement("img");
        img.src = item.icon;
        img.alt = "";
        img.onerror = function() { img.remove(); };
        icon.append(img);
    }

    const info = el("div", "mod-info");
    const name = el("div", "mod-name", item.name || item.slug);

    if (item.env === "unknown") {
        const tag = el("span", "tag amber", t("mods.envUnknown"));
        tag.title = t("mods.envUnknownHint");
        name.append(tag);
    }

    info.append(name);
    if (item.summary) info.append(el("div", "mod-summary", item.summary));

    const meta = [item.author, item.downloads ? t("mods.downloads", { n: compactNumber(item.downloads) }) : ""]
        .filter(Boolean).join(" · ");
    if (meta) info.append(el("div", "pl-sub", meta));

    row.append(icon, info);
    if (button) row.append(button);

    return row;
}


function renderMods() {

    const d = modsData;
    if (!d) return;

    const isModpack = !!d.modpack;
    const supported = !!d.kind && !isModpack;

    $("modsPending").hidden = !(d.pending && d.running);

    // Modpack actual
    $("modpackCurrent").hidden = !isModpack;
    $("modpackPick").hidden = isModpack;

    if (isModpack) {
        const box = $("modpackCurrentRow");
        box.textContent = "";
        const version = versionButton(d.modpack.version, d.modpack.version_name, pickModpackVersion);
        box.append(modRow({ name: d.modpack.name || d.modpack.slug, icon: d.modpack.icon,
                            summary: t("mods.modpackActive") }, version, null));
    }

    // Mods o plugins
    $("modsUnsupported").hidden = supported || isModpack;
    $("modsSearchCard").hidden = !supported;
    $("modsBulkCard").hidden = !supported;
    $("modsProjectsCard").hidden = !supported;

    $("modsSearchTitle").textContent = d.kind === "plugins" ? t("mods.searchPlugins") : t("mods.searchMods");
    $("modsHint").textContent = d.kind === "plugins"
        ? t("mods.hintPlugins", { v: d.version })
        : t("mods.hintMods", { v: d.version, loader: typeName(d.type) });
    $("modsFilesTitle").textContent = t("mods.files", { folder: d.folder });

    renderModProjects();
    renderModFiles();
    renderPickedBar();
}


function renderModProjects() {

    const d = modsData;
    const box = $("modsProjects");
    box.textContent = "";

    if (!d.projects.length) {
        box.append(el("div", "list-empty", t("mods.noProjects")));
    }

    d.projects.forEach(function(item) {
        const check = modCheck(modsRemove.has(item.slug), function(on) {
            if (on) modsRemove.add(item.slug); else modsRemove.delete(item.slug);
            renderRemoveBar();
        });
        const version = versionButton(item.version, item.version_name, function() { pickProjectVersion(item); });
        box.append(modRow(item, version, check));
    });

    $("modsAllProjects").checked = d.projects.length > 0 && modsRemove.size === d.projects.length;
    renderRemoveBar();
}


function renderRemoveBar() {
    $("modsRemoveBtn").disabled = modsRemove.size === 0;
    $("modsRemoveBtn").textContent = modsRemove.size
        ? t("mods.removeSelected", { n: modsRemove.size }) : t("mods.remove");
}


function toggleAllProjects(on) {
    modsRemove.clear();
    if (on) modsData.projects.forEach(function(p) { modsRemove.add(p.slug); });
    renderModProjects();
}


function renderModFiles() {

    const d = modsData;
    const box = $("modsFiles");
    box.textContent = "";

    if (!d.files.length) {
        box.append(el("div", "list-empty", t("mods.noFiles")));
    }

    d.files.forEach(function(file) {
        const row = el("div", "row mod-file");
        const check = modCheck(filesRemove.has(file.name), function(on) {
            if (on) filesRemove.add(file.name); else filesRemove.delete(file.name);
            renderFilesBar();
        });
        row.append(check, el("span", "row-name", file.name), el("span", "row-meta row-size", formatBytes(file.size)));
        box.append(row);
    });

    $("modsAllFiles").checked = d.files.length > 0 && filesRemove.size === d.files.length;
    renderFilesBar();
}


function renderFilesBar() {
    $("modsDeleteFilesBtn").disabled = filesRemove.size === 0;
    $("modsDeleteFilesBtn").textContent = filesRemove.size
        ? t("mods.deleteFiles", { n: filesRemove.size }) : t("fm.delete");
}


function toggleAllFiles(on) {
    filesRemove.clear();
    if (on) modsData.files.forEach(function(f) { filesRemove.add(f.name); });
    renderModFiles();
}


function renderPickedBar() {
    $("modsPickedBar").hidden = modsPicked.size === 0;
    $("modsPickedText").textContent = tn("mods.picked", modsPicked.size);
}


async function searchMods(event) {

    if (event) event.preventDefault();

    const box = $("modsResults");
    box.textContent = "";
    box.append(el("div", "list-empty", t("form.loading")));

    try {
        const started = currentServer;
        const data = await api("/mods/search?q=" + encodeURIComponent($("modsQuery").value.trim()));

        // Si se cambio de servidor mientras buscaba, se descarta
        if (currentServer !== started) return;
        const added = new Set((modsData.projects || []).map(function(p) { return p.slug; }));

        box.textContent = "";

        if (!data.results.length) {
            box.append(el("div", "list-empty", t("mods.noResults")));
        }

        data.results.forEach(function(item) {

            if (added.has(item.slug)) {
                box.append(modRow(item, el("span", "tag green", t("mods.added")), null));
                return;
            }

            const check = modCheck(modsPicked.has(item.slug), function(on) {
                if (on) modsPicked.set(item.slug, item); else modsPicked.delete(item.slug);
                renderPickedBar();
            });

            box.append(modRow(item, null, check));
        });
    } catch (error) {
        box.textContent = "";
        box.append(el("div", "list-empty", error.message === "auth" ? "" : error.message));
    }
}


function appliedToast(data, message) {
    // "none": el servidor ya tenia esa configuracion (ej. se deshizo un cambio)
    if (data.applied === "none") return showToast(message, "green");
    showToast(message + " " + (data.applied === "pending" ? t("mods.pendingToast") : t("mods.appliedToast")),
        data.applied === "pending" ? "amber" : "green");
}


async function addPicked() {
    await addMods({ items: Array.from(modsPicked.values()) });
    modsPicked.clear();
    renderPickedBar();
    searchMods();
}


async function addPasted() {
    const text = $("modsPaste").value.trim();
    if (!text) return;

    const data = await addMods({ text: text });
    if (data && !data.skipped.length) $("modsPaste").value = "";
}


async function addMods(body) {
    try {
        const data = await api("/mods/add", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body)
        });

        if (data.added.length) appliedToast(data, tn("mods.addedN", data.added.length));
        else if (!data.skipped.length) showToast(t("mods.nothingNew"), "amber");

        if (data.skipped.length) {
            const lines = data.skipped.map(function(s) {
                return s.name + ": " + t({ client: "mods.skipClient", not_plugin: "mods.skipNotPlugin", wrong_loader: "mods.skipLoader" }[s.reason] || "mods.skipMissing");
            });
            openModal({ title: t("mods.skippedTitle"), body: lines, okText: t("modal.ok"), hideCancel: true });
        }

        loadMods();
        return data;
    } catch (error) {
        if (error.message !== "auth") showToast(error.message, "red");
        return null;
    }
}


async function removeSelectedMods() {

    if (!modsRemove.size) return;

    const ok = await confirmDialog(t("mods.remove"), tn("mods.removeDesc", modsRemove.size));
    if (!ok) return;

    try {
        const data = await api("/mods/remove", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ slugs: Array.from(modsRemove) })
        });
        appliedToast(data, tn("mods.removedN", data.removed));
        loadMods();
    } catch (error) {
        if (error.message !== "auth") showToast(error.message, "red");
    }
}


function copyModList() {
    const list = modsData.projects.map(function(p) { return p.slug; }).join("\n");
    if (!list) return;
    copyText(list);
}


async function deleteSelectedFiles() {

    if (!filesRemove.size) return;

    const ok = await confirmDialog(t("fm.delete"), t("fm.deleteMany", { n: filesRemove.size }));
    if (!ok) return;

    try {
        const data = await api("/files/delete-many", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ paths: Array.from(filesRemove).map(function(n) { return modsData.folder + "/" + n; }) })
        });
        showToast(t("fm.deletedMany", { n: data.count }), "green");
        loadMods();
    } catch (error) {
        if (error.message !== "auth") showToast(error.message, "red");
    }
}


async function searchModpacks(event) {

    if (event) event.preventDefault();

    const box = $("modpackResults");
    box.textContent = "";
    box.append(el("div", "list-empty", t("form.loading")));

    try {
        const started = currentServer;
        const response = await fetch("/modpacks?q=" + encodeURIComponent($("modpackQuery").value.trim()));
        const data = await response.json();

        if (currentServer !== started) return;
        box.textContent = "";

        if (data.ok === false) {
            box.append(el("div", "list-empty", serverText(data.message)));
            return;
        }

        if (!data.results.length) box.append(el("div", "list-empty", t("mods.noResults")));

        data.results.forEach(function(item) {
            const use = el("button", "btn btn-start btn-small", t("mods.useModpack"));
            use.onclick = function() { useModpack(item); };
            box.append(modRow(item, use, null));
        });
    } catch (error) {
        box.textContent = "";
        box.append(el("div", "list-empty", t("login.noConnection")));
    }
}


async function useModpack(item) {

    const version = modpackVersionSelect(item.slug);

    const ok = await openModal({
        title: t("mods.useModpack") + ": " + item.name,
        body: [t("mods.useModpackDesc"), version.wrap],
        okText: t("mods.useModpack"),
        okClass: "btn-warn"
    });

    if (!ok) return;

    try {
        const data = await postJson("/server/modpack/set", {
            slug: item.slug, name: item.name, icon: item.icon, version: version.select.value
        });
        appliedToast(data, t("mods.modpackSet"));
        await update();
        loadMods();
    } catch (error) {
        showToast(error.message, "red");
    }
}


async function clearModpack() {

    const ok = await confirmDialog(t("mods.clearModpack"), t("mods.clearModpackDesc"), t("mods.clearModpack"));
    if (!ok) return;

    try {
        const data = await postJson("/server/modpack/clear", {});
        appliedToast(data, t("mods.modpackCleared"));
        await update();
        loadMods();
    } catch (error) {
        showToast(error.message, "red");
    }
}


async function applyMods() {
    try {
        await api("/mods/apply", { method: "POST" });
        showToast(t("mods.applying"), "amber");
        setTimeout(loadMods, 1500);
    } catch (error) {
        if (error.message !== "auth") showToast(error.message, "red");
    }
}
