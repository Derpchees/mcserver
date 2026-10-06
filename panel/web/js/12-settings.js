// ============================================================
// Ajustes del servidor
// ============================================================

// Debe coincidir con SETTINGS del servidor, que vuelve a validar todo
const SETTINGS_GROUPS = [
    {
        id: "game",
        keys: ["difficulty", "gamemode", "force-gamemode", "hardcore", "pvp",
            "allow-flight", "enable-command-block", "spawn-protection", "player-idle-timeout"]
    },
    {
        id: "world",
        keys: ["spawn-monsters", "spawn-animals", "spawn-npcs", "allow-nether",
            "view-distance", "simulation-distance"]
    },
    {
        id: "players",
        keys: ["max-players", "white-list", "enforce-whitelist", "online-mode",
            "hide-online-players"]
    },
    {
        // Como se genera el mundo (pestana Mundo): cuenta al crearlo o regenerarlo
        id: "worldgen",
        keys: ["level-seed", "level-type", "generate-structures"]
    }
];

const SETTINGS_TYPES = {
    "difficulty": { type: "enum", options: ["peaceful", "easy", "normal", "hard"] },
    "gamemode": { type: "enum", options: ["survival", "creative", "adventure", "spectator"] },
    "spawn-protection": { type: "int", min: 0, max: 256 },
    "player-idle-timeout": { type: "int", min: 0, max: 1440 },
    "view-distance": { type: "int", min: 3, max: 32 },
    "simulation-distance": { type: "int", min: 3, max: 32 },
    "max-players": { type: "int", min: 1, max: 200 },
    "motd": { type: "text", max: 59 },
    "level-seed": { type: "text", max: 64 },
    "level-type": { type: "enum", options: ["minecraft:normal", "minecraft:flat", "minecraft:large_biomes", "minecraft:amplified"] }
};

// Bedrock tiene otras claves (BEDROCK_SETTINGS del servidor)
const BEDROCK_SETTINGS_GROUPS = [
    {
        id: "game",
        keys: ["difficulty", "gamemode", "force-gamemode", "allow-cheats", "player-idle-timeout"]
    },
    {
        id: "world",
        keys: ["view-distance", "tick-distance"]
    },
    {
        id: "players",
        keys: ["max-players", "allow-list", "online-mode", "default-player-permission-level",
            "texturepack-required"]
    },
    {
        id: "worldgen",
        keys: ["level-seed"]
    }
];

const BEDROCK_SETTINGS_TYPES = {
    "gamemode": { type: "enum", options: ["survival", "creative", "adventure"] },
    "view-distance": { type: "int", min: 5, max: 96 },
    "tick-distance": { type: "int", min: 4, max: 12 },
    "default-player-permission-level": { type: "enum", options: ["visitor", "member", "operator"] }
};

// Iconos de las tarjetas de reglas del juego
const SETTINGS_GROUP_ICONS = {
    game: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="6" width="20" height="12" rx="4"/><path d="M6 12h4M8 10v4M15 11h.01M18 13h.01"/></svg>',
    world: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18"/></svg>',
    worldgen: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m8 3 4 8 5-5 5 15H2L8 3z"/></svg>',
    players: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/></svg>'
};

let settingsSaved = null;
let settingsEdition = "java";
let settingsDraft = {};
let settingsLive = [];
let settingsRunning = false;
let settingsRestart = false;


function settingType(key) {
    if (settingsEdition === "bedrock" && BEDROCK_SETTINGS_TYPES[key]) return BEDROCK_SETTINGS_TYPES[key];
    return SETTINGS_TYPES[key] || { type: "bool" };
}


function settingsChanges() {

    const changes = {};

    Object.keys(settingsDraft).forEach(function(key) {
        if (settingsSaved && settingsDraft[key] !== settingsSaved[key]) {
            changes[key] = settingsDraft[key];
        }
    });

    return changes;
}


async function loadSettings() {

    try {
        const data = await api("/settings?t=" + Date.now());

        settingsSaved = data.values;
        settingsDraft = Object.assign({}, data.values);
        settingsLive = data.live || [];
        settingsRunning = data.running;
        settingsEdition = data.edition || "java";

        renderSettings();

    } catch (error) {
        if (error.message !== "auth") showToast(error.message, "red");
    }
}


function settingControl(key) {

    const info = settingType(key);
    const value = settingsDraft[key];

    if (info.type === "bool") {

        const btn = el("button", "switch" + (value === "true" ? " on" : ""));
        btn.type = "button";
        btn.setAttribute("role", "switch");
        btn.setAttribute("aria-checked", value === "true" ? "true" : "false");
        btn.setAttribute("aria-label", t("set." + key));
        btn.append(el("span", "switch-knob"));

        btn.onclick = function() {
            settingsDraft[key] = settingsDraft[key] === "true" ? "false" : "true";
            const on = settingsDraft[key] === "true";
            btn.classList.toggle("on", on);
            btn.setAttribute("aria-checked", on ? "true" : "false");
            renderSettingsBar();
        };

        return btn;
    }

    if (info.type === "enum") {

        const select = el("select", "input set-input");

        info.options.forEach(function(option) {
            const node = el("option", "", t("opt." + option) || option);
            node.value = option;
            select.append(node);
        });

        select.value = value;
        select.onchange = function() {
            settingsDraft[key] = select.value;
            renderSettingsBar();
        };

        // Pocas opciones: botones juntos en lugar de una lista
        return info.options.length <= 4 ? segmentedFromSelect(select) : select;
    }

    const input = el("input", "input set-input" + (info.type === "text" ? " wide" : ""));

    if (info.type === "int") {
        input.type = "number";
        input.min = info.min;
        input.max = info.max;
        input.step = 1;
    } else {
        input.type = "text";
        input.maxLength = info.max;
    }

    input.value = value;

    input.oninput = function() {

        let next = input.value;
        let valid = true;

        if (info.type === "int") {
            const number = Number(next);
            valid = /^\d+$/.test(next.trim()) && number >= info.min && number <= info.max;
            next = valid ? String(number) : next;
        }

        input.classList.toggle("invalid", !valid);
        settingsDraft[key] = next;
        renderSettingsBar();
    };

    return input;
}


function renderSettings() {

    const box = $("settingsGroups");
    box.textContent = "";

    if (!settingsSaved) return;

    (settingsEdition === "bedrock" ? BEDROCK_SETTINGS_GROUPS : SETTINGS_GROUPS).forEach(function(group) {

        const card = el("div", "card");
        // Juego y Mundo van juntos; Jugadores y la generacion del mundo en su pestana
        card.dataset.settab = { players: "players", worldgen: "world" }[group.id] || "game";
        const head = el("div", "card-head");
        const title = el("h3", "card-title");
        const icon = el("span", "card-title-icon");
        icon.innerHTML = SETTINGS_GROUP_ICONS[group.id] || "";
        title.append(icon, el("span", "", t("set.group." + group.id)));
        head.append(title);
        card.append(head);

        const list = el("div", "set-list");

        group.keys.forEach(function(key) {

            const row = el("div", "set-row");
            const text = el("div", "set-text");
            const label = el("div", "set-label", t("set." + key));

            if (settingsLive.includes(key)) {
                label.append(el("span", "tag green set-live", t("set.live")));
            }

            // Algunas claves de Bedrock tienen su propia descripcion
            const desc = (settingsEdition === "bedrock" && t("set." + key + ".d.bedrock")) || t("set." + key + ".d");
            text.append(label, el("div", "set-desc", desc));
            row.append(text, settingControl(key));
            list.append(row);
        });

        card.append(list);
        box.append(card);
    });

    $("settingsNote").textContent = settingsRunning ? "" : t("set.offNote");
    $("settingsNote").hidden = settingsRunning;
    applySettingsTab();

    renderSettingsBar();
}


function settingsValid() {
    return !document.querySelector("#settingsGroups .invalid");
}


// Una sola barra para toda la pestana: reglas del juego (server.properties)
// y configuracion del servidor (22-server-config.js)
function renderSettingsBar() {

    const count = Object.keys(settingsChanges()).length;
    const pending = count > 0 || configDirty;

    $("settingsBar").hidden = !pending;
    $("settingsBarText").textContent = configDirty ? t("set.unsavedAny") : tn("set.unsaved", count);
    $("settingsSave").disabled = !settingsValid();

    $("settingsRestart").hidden = !settingsRestart || pending;
}


function discardSettings() {
    settingsDraft = Object.assign({}, settingsSaved);
    renderServerConfig(true);
    renderSettings();
}


async function saveSettings() {

    const changes = settingsChanges();

    if ((!Object.keys(changes).length && !configDirty) || !settingsValid()) return;

    $("settingsSave").disabled = true;

    if (configDirty && !(await saveServerConfig())) {
        $("settingsSave").disabled = false;
        return;
    }

    if (!Object.keys(changes).length) {
        renderSettingsBar();
        return;
    }

    try {
        const data = await api("/settings", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ values: changes })
        });

        settingsRestart = settingsRestart || data.restart;

        showToast(
            data.restart ? t("set.savedRestart")
                : data.applied && data.applied.length ? t("set.savedApplied")
                : t("set.saved"),
            data.restart ? "amber" : "green"
        );

        await loadSettings();

    } catch (error) {
        if (error.message !== "auth") showToast(error.message, "red");
        $("settingsSave").disabled = false;
    }
}


async function restartFromSettings() {

    if (await confirmRestart()) {
        settingsRestart = false;
        renderSettingsBar();
    }
}
