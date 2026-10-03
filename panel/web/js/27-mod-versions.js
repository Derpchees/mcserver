// ============================================================
// Version de mods, plugins y modpacks
// ============================================================
//
// Por defecto se usa la version mas reciente compatible; aqui se elige
// una concreta. El servidor devuelve las versiones ya filtradas por el
// cargador y la version de Minecraft.


function versionLabel(pinned, name) {
    return pinned ? (name || pinned) : t("ver.latest");
}


function versionButton(pinned, name, onClick) {
    const btn = el("button", "btn btn-ghost btn-small ver-btn" + (pinned ? " pinned" : ""),
        t("ver.button", { v: versionLabel(pinned, name) }));
    btn.title = pinned ? t("ver.pinnedHint") : t("ver.latestDesc");
    btn.onclick = function(event) {
        event.stopPropagation();
        onClick();
    };
    return btn;
}


function versionMeta(version) {
    const parts = [];
    if (version.game_versions && version.game_versions.length) {
        parts.push(t("ver.mc", { v: version.game_versions.join(", ") }));
    }
    if (version.date) parts.push(new Date(version.date + "T12:00:00").toLocaleDateString(locale()));
    if (version.downloads) parts.push(t("mods.downloads", { n: compactNumber(version.downloads) }));
    return parts.join(" · ");
}


function versionRow(version, current, name) {

    const row = el("label", "ver-opt");
    const radio = el("input");
    radio.type = "radio";
    radio.name = name;
    radio.checked = version.id === current;

    const text = el("div", "ver-text");
    const title = el("div", "ver-title", version.number || t("ver.latest"));

    if (version.type === "beta" || version.type === "alpha") {
        title.append(el("span", "tag amber", t("ver." + version.type)));
    }

    if (version.id === current) title.append(el("span", "tag green", t("ver.current")));

    text.append(title, el("div", "pl-sub", version.id ? versionMeta(version) : t("ver.latestDesc")));
    row.append(radio, text);
    return { row: row, radio: radio };
}


// Lista para elegir: la primera opcion es "la mas reciente"
async function pickVersion(title, url, emptyText) {

    const list = el("div", "ver-list");
    list.append(el("div", "list-empty", t("form.loading")));

    let choices = [];

    const promise = openModal({
        title: title,
        wide: true,
        body: [list],
        okText: t("ver.pick"),
        onOk: function() {
            const picked = choices.find(function(c) { return c.radio.checked; });
            return picked ? { version: picked.id } : false;
        }
    });

    try {
        const data = await api(url);
        const current = data.current || "";
        list.textContent = "";

        const latest = versionRow({ id: "", number: t("ver.latest") }, current, "verPick");
        if (!current) latest.radio.checked = true;
        choices.push({ id: "", radio: latest.radio });
        list.append(latest.row);

        if (!data.versions.length) {
            list.append(el("div", "list-empty", emptyText(data)));
        }

        data.versions.forEach(function(version) {
            const item = versionRow(version, current, "verPick");
            choices.push({ id: version.id, radio: item.radio });
            list.append(item.row);
        });
    } catch (error) {
        list.textContent = "";
        if (error.message !== "auth") list.append(el("div", "list-empty", error.message));
    }

    return promise;
}


async function pickProjectVersion(item) {

    const picked = await pickVersion(
        t("ver.title", { name: item.name || item.slug }),
        "/mods/versions?slug=" + encodeURIComponent(item.slug),
        function(data) { return t("ver.none", { v: data.game_version }); }
    );

    if (!picked || picked.version === (item.version || "")) return;

    try {
        const data = await postJson("/mods/version", { slug: item.slug, version: picked.version });
        appliedToast(data, t("ver.changed"));
        loadMods();
    } catch (error) {
        showToast(error.message, "red");
    }
}


async function pickModpackVersion() {

    const pack = modsData && modsData.modpack;
    if (!pack) return;

    const picked = await pickVersion(
        t("ver.titleModpack", { name: pack.name || pack.slug }),
        "/server/modpack/versions",
        function() { return t("ver.noneModpack"); }
    );

    if (!picked || picked.version === (pack.version || "")) return;

    try {
        const data = await postJson("/server/modpack/version", { version: picked.version });
        appliedToast(data, t("ver.changed"));
        await update();
        loadMods();
    } catch (error) {
        showToast(error.message, "red");
    }
}


// Selector de version para un modpack de Modrinth que se esta por elegir
function modpackVersionSelect(slug) {

    const wrap = el("label", "ver-field");
    wrap.append(el("span", "", t("ver.modpackLabel")));

    const select = el("select", "input");
    const latest = el("option", "", t("ver.latest"));
    latest.value = "";
    select.append(latest);
    wrap.append(select);

    api("/server/modpack/versions?slug=" + encodeURIComponent(slug)).then(function(data) {
        data.versions.forEach(function(version) {
            const mc = version.game_versions.length ? " (" + t("ver.mc", { v: version.game_versions.join(", ") }) + ")" : "";
            const option = el("option", "", version.number + mc + (version.type !== "release" ? " · " + t("ver." + version.type) : ""));
            option.value = version.id;
            option.dataset.name = version.number;
            select.append(option);
        });
    }).catch(function() {});

    return { wrap: wrap, select: select };
}
