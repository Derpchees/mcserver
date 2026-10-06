// ============================================================
// Formulario de servidor (registro, configuracion inicial, crear)
// ============================================================

// Tipos para elegir con tarjetas al crear un servidor (color de su insignia)
const SERVER_TYPE_CARDS = [
    ["PAPER", "#3b82f6"], ["FORGE", "#d97706"], ["NEOFORGE", "#ea580c"],
    ["FABRIC", "#a8956b"], ["VANILLA", "#16a34a"], ["BEDROCK", "#64748b"]
];


// options.resources: otro contenedor para RAM y CPU (en Ajustes van en su tarjeta)
// options.picker: formulario de crear (tipo en tarjetas, secciones y barras)
function serverFields(prefix, values, options) {

    const limits = (authState && authState.limits) || { max_ram_gb: 4, max_cpu: 1, cores: 1 };
    const v = values || {};
    const box = el("div", "form-grid");
    const resources = (options && options.resources) || box;
    const picker = !!(options && options.picker);

    // Titulo numerado de cada parte del formulario de crear
    const section = function(n, key) {
        if (picker) box.append(el("div", "form-section create-step", n + ". " + t(key)));
    };

    section(1, "create.stepName");

    const field = function(label, input, hint, target) {
        const wrap = el("label", "field");
        const labelEl = el("span", "field-label", label);
        wrap.append(labelEl, input);
        if (hint) wrap.append(el("span", "field-hint", hint));
        (target || box).append(wrap);
        return wrap;
    };

    const option = function(select, value, label) {
        const node = el("option", "", label);
        node.value = value;
        select.append(node);
    };

    const name = el("input", "input");
    name.id = prefix + "Name";
    name.maxLength = 40;
    name.value = v.name || "";
    name.placeholder = t("form.serverNamePh");
    field(t("form.serverName"), name, prefix === "cfg" ? t("srv.nameHint") : "");

    const type = el("select", "input");
    type.id = prefix + "Type";

    // Java y Bedrock no se mezclan: un servidor existente no cambia de edicion
    const editing = !!v.type;
    const bedrockServer = v.type === "BEDROCK";

    if (!bedrockServer) {
        [["PAPER", "type.paper"], ["FORGE", "type.forge"], ["NEOFORGE", "type.neoforge"], ["FABRIC", "type.fabric"], ["VANILLA", "type.vanilla"]]
            .forEach(function([value, key]) { option(type, value, t(key)); });
    }

    if (!editing || bedrockServer) option(type, "BEDROCK", t("type.bedrock"));
    if (bedrockServer) type.disabled = true;

    // Los modpacks se eligen y se cambian en la pestana Mods; aqui solo se
    // muestra el actual, sin poder cambiarlo
    const isModpackServer = v.type === "MODRINTH" || v.type === "AUTO_CURSEFORGE";

    if (isModpackServer) {
        option(type, v.type, t("type.modpackShort"));
        type.disabled = true;
    }

    type.value = v.type || "PAPER";
    section(2, "create.stepType");
    const typeWrap = field(t("form.type"), type, isModpackServer ? t("cfg.modpackHint") : "");

    // Al crear: una tarjeta por tipo (el select sigue guardando el valor)
    const typeCards = el("div", "type-picker");

    const markType = function() {
        typeCards.querySelectorAll(".type-card").forEach(function(card) {
            const on = card.dataset.value === type.value;
            card.classList.toggle("active", on);
            card.setAttribute("aria-pressed", on ? "true" : "false");
        });
    };

    if (picker) {
        typeWrap.classList.add("type-field");
        typeWrap.querySelector(".field-label").hidden = true;
        type.hidden = true;

        SERVER_TYPE_CARDS.forEach(function([value, color]) {
            const card = el("button", "type-card");
            card.type = "button";
            card.dataset.value = value;

            const badge = el("span", "type-badge", t("create.type." + value).charAt(0));
            badge.style.background = color;

            const text = el("span", "type-text");
            text.append(el("span", "type-title", t("create.type." + value)),
                el("span", "type-desc", t("create.typeDesc." + value)));

            card.append(badge, text);
            card.onclick = function(event) {
                event.preventDefault();
                type.value = value;
                type.onchange();
                markType();
            };
            typeCards.append(card);
        });

        typeWrap.insertBefore(typeCards, type);
    }

    // Que es Bedrock (solo al elegirlo)
    const bedrockHint = el("span", "field-hint", t("form.bedrockHint"));
    typeWrap.append(bedrockHint);

    if (isModpackServer) {
        const goMods = el("button", "btn btn-ghost btn-small", t("cfg.goMods"));
        goMods.type = "button";
        goMods.onclick = function(event) {
            event.preventDefault();
            showTab("mods");
        };
        typeWrap.append(goMods);
    }

    section(3, "create.stepVersion");

    // Version de Minecraft: lista oficial del tipo elegido
    const version = el("select", "input");
    version.id = prefix + "Version";
    const versionWrap = field(t("form.version"), version);

    // Version del cargador (Forge, Fabric) o build (Paper)
    const loader = el("select", "input");
    loader.id = prefix + "Loader";
    const loaderWrap = field(t("form.loader"), loader);

    const java = el("select", "input");
    java.id = prefix + "Java";
    option(java, "", t("form.javaAuto"));
    ["25", "21", "17", "11", "8"].forEach(function(n) { option(java, n, "Java " + n); });
    java.value = v.java || "";
    const javaWrap = field(t("form.java"), java, t("form.javaHint"));

    if (picker) resources.append(el("div", "form-section create-step", "4. " + t("create.stepResources")));

    const ram = el("input", "input");
    ram.id = prefix + "Ram";
    ram.type = "number";
    ram.min = 1;
    ram.max = limits.max_ram_gb;
    ram.value = Math.min(v.max_gb || Math.min(4, limits.max_ram_gb), limits.max_ram_gb);
    field(t("form.ram"), ram, t("form.ramHint", { max: limits.max_ram_gb, total: limits.system_ram_gb }), resources);

    const cpu = el("input", "input");
    cpu.id = prefix + "Cpu";
    cpu.type = "number";
    cpu.min = 0;
    cpu.max = limits.max_cpu;
    cpu.value = v.cpu !== undefined ? v.cpu : (limits.max_cpu < limits.cores ? limits.max_cpu : 0);
    field(t("form.cpu"), cpu, limits.max_cpu < limits.cores
        ? t("form.cpuHintMax", { max: limits.max_cpu })
        : t("form.cpuHint", { cores: limits.cores }), resources);

    // Al crear, una barra junto a cada numero para elegir mas rapido
    if (picker) {
        [ram, cpu].forEach(function(input) {
            const range = el("input", "range-input");
            range.type = "range";
            range.min = input.min;
            range.max = input.max;
            range.step = 1;
            range.value = input.value;
            range.oninput = function() { input.value = range.value; };
            input.addEventListener("input", function() { range.value = input.value; });

            const row = el("div", "range-row");
            input.replaceWith(row);
            row.append(range, input);
        });
    }

    let wantedVersion = v.version || "LATEST";
    let wantedLoader = v.loader || "";

    // Si no se pueden consultar las versiones, se escribe a mano
    const manualVersion = function() {
        const input = el("input", "input");
        input.id = prefix + "Version";
        input.value = wantedVersion;
        input.placeholder = type.value === "BEDROCK" ? "LATEST, 1.26.52.3..." : "LATEST, 1.20.1, 26.1...";
        versionWrap.replaceChild(input, versionWrap.querySelector("#" + prefix + "Version"));
        versionWrap.append(el("span", "field-hint", t("form.versionManual")));
    };

    const loadLoaders = async function() {

        const typeValue = type.value;
        const mc = $(prefix + "Version").value;
        const label = { FORGE: "form.loaderForge", NEOFORGE: "form.loaderNeoforge", FABRIC: "form.loaderFabric", PAPER: "form.loaderPaper" }[typeValue];

        loaderWrap.hidden = !label;
        if (!label) return;

        loaderWrap.querySelector(".field-label").textContent = t(label);
        loader.textContent = "";
        option(loader, "", t("form.loading"));
        loader.disabled = true;

        if (!mc || mc === "LATEST") {
            loader.textContent = "";
            option(loader, "", t("form.loaderAuto"));
            loader.disabled = false;
            return;
        }

        try {
            const data = await (await fetch("/versions?type=" + typeValue + "&mc=" + encodeURIComponent(mc))).json();
            loader.textContent = "";
            option(loader, "", data.recommended ? t("form.loaderRecommended", { v: data.recommended }) : t("form.loaderAuto"));
            (data.loaders || []).forEach(function(item) { option(loader, item, item); });

            if (wantedLoader && (data.loaders || []).includes(wantedLoader)) loader.value = wantedLoader;
            else if (wantedLoader) { option(loader, wantedLoader, wantedLoader); loader.value = wantedLoader; }
        } catch (error) {
            loader.textContent = "";
            option(loader, "", t("form.loaderAuto"));
        }

        loader.disabled = false;
    };

    const loadVersions = async function() {

        // Bedrock no usa Java ni cargador; la RAM es un limite del contenedor
        const isBedrock = type.value === "BEDROCK";
        javaWrap.hidden = isBedrock;
        bedrockHint.hidden = !isBedrock;

        // Un modpack trae su propia version de Minecraft y cargador
        const isModpack = type.value === "AUTO_CURSEFORGE" || type.value === "MODRINTH";
        versionWrap.hidden = isModpack;

        if (isModpack) {
            loaderWrap.hidden = true;
            return;
        }

        const select = $(prefix + "Version");

        if (!select || select.tagName !== "SELECT") return loadLoaders();

        select.textContent = "";
        option(select, "", t("form.loading"));
        select.disabled = true;

        try {
            const data = await (await fetch("/versions?type=" + type.value)).json();

            if (!data.versions || !data.versions.length) {
                manualVersion();
                return loadLoaders();
            }

            select.textContent = "";
            option(select, "LATEST", t("form.latest", { v: data.versions[0] }));
            data.versions.forEach(function(item) { option(select, item, item); });

            if (wantedVersion !== "LATEST" && !data.versions.includes(wantedVersion)) {
                option(select, wantedVersion, wantedVersion);
            }

            select.value = wantedVersion;
            select.disabled = false;
        } catch (error) {
            manualVersion();
        }

        loadLoaders();
    };

    type.onchange = function() {
        wantedLoader = "";
        loadVersions();
    };

    version.onchange = function() {
        wantedVersion = version.value;
        wantedLoader = "";
        loadLoaders();
    };

    loader.onchange = function() {
        wantedLoader = loader.value;
    };

    // El formulario se agrega al documento despues de crearse
    setTimeout(function() {
        markType();
        loadVersions();
    }, 0);

    return box;
}


function readServerFields(prefix) {
    return {
        name: $(prefix + "Name").value.trim(),
        type: $(prefix + "Type").value,
        version: ($(prefix + "Version").value || "").trim() || "LATEST",
        loader: $(prefix + "Loader") && !$(prefix + "Loader").closest(".field").hidden ? $(prefix + "Loader").value : "",
        java: $(prefix + "Type").value === "BEDROCK" ? "" : $(prefix + "Java").value,
        max_gb: Number($(prefix + "Ram").value),
        cpu: Number($(prefix + "Cpu").value)
    };
}


async function postJson(url, body) {
    const response = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body)
    });

    const data = await response.json().catch(function() { return { ok: false, message: t("fm.badResponse") }; });

    if (!response.ok || data.ok === false) {
        throw new Error(serverText(data.message) || "Error");
    }

    return data;
}


async function openCreateServer() {

    const fields = serverFields("newSrv", { name: authState.user.username }, { picker: true });

    const ok = await openModal({
        title: t("srv.create"),
        body: [el("p", "hint create-intro", t("create.intro")), fields],
        okText: t("srv.createBtn"),
        cls: "create-modal",
        onOk: function() { return true; }
    });

    if (!ok) return;

    try {
        const data = await postJson("/servers/create", readServerFields("newSrv"));
        showToast(t("srv.created"), "green");
        await refreshAuth();
        go("#/s/" + data.id);
    } catch (error) {
        showToast(error.message, "red");
    }
}
