// ============================================================
// Mods, plugins y modpack (Modrinth)
// ============================================================
//
// Tres pestanas (cada tarjeta lleva data-modtab): Instalados, Buscar y
// Modpack. Las busquedas van por paginas (las da Modrinth) y las listas
// de instalados se filtran y se paginan aqui.

let modsData = null;
const modsPicked = new Map();
const modsRemove = new Set();
const filesRemove = new Set();

const MODS_PAGE = 20;
let modsTab = null;
let modsSearchPage = 0;
let modpackPage = 0;
let modsProjectsPage = 0;
let modsFilesPage = 0;
let modsSearched = false;
let modpackSearched = false;


function typeName(type) {
    return {
        FORGE: "Forge", NEOFORGE: "NeoForge", FABRIC: "Fabric", PAPER: "Paper",
        VANILLA: "Vanilla", BEDROCK: "Bedrock", AUTO_CURSEFORGE: t("type.modpackShort"), MODRINTH: t("type.modpackShort")
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

        $("modsJava").hidden = false;
        $("addonsArea").hidden = true;

        // Otro servidor: se empieza de cero (busquedas, paginas y pestana)
        if (!modsData || modsData.server !== started) {
            modsTab = null;
            modsSearched = modpackSearched = false;
            modsSearchPage = modpackPage = modsProjectsPage = modsFilesPage = 0;
            modsPicked.clear();
            $("modsResults").textContent = "";
            $("modpackResults").textContent = "";
            $("modsPager").hidden = $("modpackPager").hidden = true;
            $("modsResultsInfo").hidden = $("modpackResultsInfo").hidden = true;
            $("modsProjectsFilter").value = $("modsFilesFilter").value = "";
        }

        modsData = data;
        modsData.server = started;
        modsRemove.clear();
        filesRemove.clear();
        renderMods();
    } catch (error) {
        if (error.message !== "auth") showToast(error.message, "red");
    }
}


// ------------------------------------------------------------
// Pestanas

function defaultModsTab(d) {
    if (d.modpack) return "modpack";
    if (!d.kind) return "modpack";
    return d.projects.length || d.files.length ? "installed" : "search";
}


function showModsTab(name) {

    modsTab = name;

    document.querySelectorAll("#modsTabs .tab-btn").forEach(function(btn) {
        btn.classList.toggle("active", btn.dataset.modtab === name);
    });

    document.querySelectorAll("#modsJava .card[data-modtab]").forEach(function(card) {
        card.classList.toggle("adm-off", card.dataset.modtab !== name);
    });

    // Al entrar por primera vez se muestran los mas populares
    if (name === "search" && !modsSearched && modsData && modsData.kind && !modsData.modpack) searchMods(null, 0);
    if (name === "modpack" && !modpackSearched && modsData && !modsData.modpack) searchModpacks(null, 0);
}


function modCheck(checked, onChange) {
    const box = el("input", "check");
    box.type = "checkbox";
    box.checked = checked;
    box.onclick = function(event) { event.stopPropagation(); };
    box.onchange = function() { onChange(box.checked); };
    return box;
}


// Enlace a la pagina del proyecto (se abre aparte)
function modLink(url) {
    const link = el("a", "icon-btn mod-link");
    link.href = url;
    link.target = "_blank";
    link.rel = "noopener";
    link.title = t("mods.openPage");
    link.innerHTML = ICONS.open;
    link.onclick = function(event) { event.stopPropagation(); };
    return link;
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
        img.loading = "lazy";
        img.onerror = function() { img.remove(); };
        icon.append(img);
    } else {
        icon.append(el("span", "mod-icon-letter", (item.name || item.slug || "?").charAt(0).toUpperCase()));
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

    const meta = el("div", "mod-meta");

    if (item.meta) meta.append(el("span", "", item.meta));
    if (item.author) meta.append(el("span", "", t("mods.by", { name: item.author })));

    if (item.downloads) {
        const dl = el("span", "mod-downloads");
        dl.innerHTML = ICONS.download;
        dl.append(document.createTextNode(compactNumber(item.downloads)));
        dl.title = t("mods.downloads", { n: compactNumber(item.downloads) });
        meta.append(dl);
    }

    if (meta.childNodes.length) info.append(meta);

    row.append(icon, info);

    const actions = el("div", "mod-actions");
    if (item.url) actions.append(modLink(item.url));
    if (button) actions.append(button);
    row.append(actions);

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

    // Mods o plugins (con modpack o en Vanilla no hay busqueda)
    $("modsUnsupported").hidden = supported || isModpack;
    $("modsSearchCard").hidden = !supported;
    $("modsBulkCard").hidden = !supported;
    $("modsProjectsCard").hidden = !supported;
    document.querySelector('#modsTabs [data-modtab="search"]').hidden = !supported;

    const plugins = d.kind === "plugins";
    $("modsSearchTabLabel").textContent = plugins ? t("mods.tabSearchPlugins") : t("mods.tabSearch");
    $("modsSearchTitle").textContent = plugins ? t("mods.searchPlugins") : t("mods.searchMods");
    $("modsHint").textContent = plugins
        ? t("mods.hintPlugins", { v: d.version })
        : t("mods.hintMods", { v: d.version, loader: typeName(d.type) });
    $("modsFilesTitle").textContent = t("mods.files", { folder: d.folder });

    const installed = d.files.length;
    $("modsInstalledCount").textContent = installed ? String(installed) : "";

    renderModProjects();
    renderModFiles();
    renderPickedBar();

    const tab = modsTab && !(modsTab === "search" && !supported) ? modsTab : defaultModsTab(d);
    showModsTab(tab);
}


function filterByName(items, input, key) {
    const text = $(input).value.trim().toLowerCase();
    if (!text) return items;
    return items.filter(function(item) { return String(item[key] || "").toLowerCase().includes(text); });
}


function renderModProjects() {

    const d = modsData;
    const box = $("modsProjects");
    box.textContent = "";

    const filtered = filterByName(d.projects.map(function(p) {
        return Object.assign({ label: (p.name || "") + " " + p.slug }, p);
    }), "modsProjectsFilter", "label");
    const page = pageSlice(filtered, modsProjectsPage, MODS_PAGE);
    modsProjectsPage = page.page;

    $("modsProjectsCount").textContent = d.projects.length ? "(" + d.projects.length + ")" : "";
    $("modsProjectsFilter").hidden = d.projects.length <= MODS_PAGE / 2;

    if (!filtered.length) {
        box.append(el("div", "list-empty", d.projects.length ? t("fm.noMatch") : t("mods.noProjects")));
    }

    page.items.forEach(function(item) {
        const check = modCheck(modsRemove.has(item.slug), function(on) {
            if (on) modsRemove.add(item.slug); else modsRemove.delete(item.slug);
            renderRemoveBar();
        });
        const version = versionButton(item.version, item.version_name, function() { pickProjectVersion(item); });
        box.append(modRow(Object.assign({ url: "https://modrinth.com/project/" + item.slug }, item), version, check));
    });

    renderPager($("modsProjectsPager"), page.page, page.pages, function(n) {
        modsProjectsPage = n;
        renderModProjects();
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

    const filtered = filterByName(d.files, "modsFilesFilter", "name");
    const page = pageSlice(filtered, modsFilesPage, MODS_PAGE);
    modsFilesPage = page.page;

    $("modsFilesCount").textContent = d.files.length ? "(" + d.files.length + ")" : "";
    $("modsFilesFilter").hidden = d.files.length <= MODS_PAGE / 2;

    if (!filtered.length) {
        box.append(el("div", "list-empty", d.files.length ? t("fm.noMatch") : t("mods.noFiles")));
    }

    page.items.forEach(function(file) {
        const row = el("div", "row mod-file");
        const check = modCheck(filesRemove.has(file.name), function(on) {
            if (on) filesRemove.add(file.name); else filesRemove.delete(file.name);
            renderFilesBar();
        });
        row.append(check, el("span", "row-name", file.name), el("span", "row-meta row-size", formatBytes(file.size)));
        row.onclick = function(event) {
            if (event.target.closest("input")) return;
            check.checked = !check.checked;
            check.onchange();
        };
        box.append(row);
    });

    renderPager($("modsFilesPager"), page.page, page.pages, function(n) {
        modsFilesPage = n;
        renderModFiles();
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


// "123 resultados" arriba de la lista
function renderResultsInfo(node, data) {
    node.hidden = !data.total;
    node.textContent = data.total ? tn("mods.resultsCount", data.total, { n: compactNumber(data.total) }) : "";
}


function loadingList(box) {
    box.textContent = "";
    for (let i = 0; i < 4; i++) box.append(el("div", "mod-row mod-skeleton"));
}


async function searchMods(event, page) {

    if (event) event.preventDefault();
    if (page === undefined) page = 0;

    const box = $("modsResults");
    loadingList(box);
    modsSearched = true;

    try {
        const started = currentServer;
        const data = await api("/mods/search?q=" + encodeURIComponent($("modsQuery").value.trim())
            + "&sort=" + $("modsSort").value + "&page=" + page);

        // Si se cambio de servidor mientras buscaba, se descarta
        if (currentServer !== started) return;
        const added = new Set((modsData.projects || []).map(function(p) { return p.slug; }));

        box.textContent = "";
        modsSearchPage = data.page || 0;
        renderResultsInfo($("modsResultsInfo"), data);

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

            const add = el("button", "btn btn-start btn-small", t("mods.addOne"));
            add.onclick = async function(event) {
                event.stopPropagation();
                add.disabled = true;
                const result = await addMods({ items: [item] });
                if (result && result.added.length) {
                    modsPicked.delete(item.slug);
                    renderPickedBar();
                    add.replaceWith(el("span", "tag green", t("mods.added")));
                } else {
                    add.disabled = false;
                }
            };

            box.append(modRow(item, add, check));
        });

        renderPager($("modsPager"), modsSearchPage, data.pages || 1, function(n) {
            searchMods(null, n);
            $("modsSearchCard").scrollIntoView({ behavior: "smooth", block: "start" });
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
    searchMods(null, modsSearchPage);
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


async function searchModpacks(event, page) {

    if (event) event.preventDefault();
    if (page === undefined) page = 0;

    const box = $("modpackResults");
    loadingList(box);
    modpackSearched = true;

    try {
        const started = currentServer;
        const response = await fetch("/modpacks?q=" + encodeURIComponent($("modpackQuery").value.trim())
            + "&sort=" + $("modpackSort").value + "&page=" + page);
        const data = await response.json();

        if (currentServer !== started) return;
        box.textContent = "";

        if (data.ok === false) {
            box.append(el("div", "list-empty", serverText(data.message)));
            return;
        }

        modpackPage = data.page || 0;
        renderResultsInfo($("modpackResultsInfo"), data);

        if (!data.results.length) box.append(el("div", "list-empty", t("mods.noResults")));

        data.results.forEach(function(item) {
            const use = el("button", "btn btn-start btn-small", t("mods.useModpack"));
            use.onclick = function() { useModpack(item); };
            box.append(modRow(item, use, null));
        });

        renderPager($("modpackPager"), modpackPage, data.pages || 1, function(n) {
            searchModpacks(null, n);
            $("modpackPick").scrollIntoView({ behavior: "smooth", block: "start" });
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
