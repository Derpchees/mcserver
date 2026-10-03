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
    "motd": { type: "text", max: 59 }
};

let settingsSaved = null;
let settingsDraft = {};
let settingsLive = [];
let settingsRunning = false;
let settingsRestart = false;


function settingType(key) {
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

        return select;
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

    SETTINGS_GROUPS.forEach(function(group) {

        const card = el("div", "card");
        const head = el("div", "card-head");
        head.append(el("h3", "card-title", t("set.group." + group.id)));
        card.append(head);

        const list = el("div", "set-list");

        group.keys.forEach(function(key) {

            const row = el("div", "set-row");
            const text = el("div", "set-text");
            const label = el("div", "set-label", t("set." + key));

            if (settingsLive.includes(key)) {
                label.append(el("span", "tag green set-live", t("set.live")));
            }

            text.append(label, el("div", "set-desc", t("set." + key + ".d")));
            row.append(text, settingControl(key));
            list.append(row);
        });

        card.append(list);
        box.append(card);
    });

    $("settingsNote").textContent = settingsRunning ? "" : t("set.offNote");
    $("settingsNote").hidden = settingsRunning;

    renderSettingsBar();
}


function settingsValid() {
    return !document.querySelector("#settingsGroups .invalid");
}


function renderSettingsBar() {

    const count = Object.keys(settingsChanges()).length;

    $("settingsBar").hidden = count === 0;
    $("settingsBarText").textContent = tn("set.unsaved", count);
    $("settingsSave").disabled = !settingsValid();

    $("settingsRestart").hidden = !settingsRestart || count > 0;
}


function discardSettings() {
    settingsDraft = Object.assign({}, settingsSaved);
    renderSettings();
}


async function saveSettings() {

    const changes = settingsChanges();

    if (!Object.keys(changes).length || !settingsValid()) return;

    $("settingsSave").disabled = true;

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
