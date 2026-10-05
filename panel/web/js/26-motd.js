// ============================================================
// Mensaje del servidor (MOTD) con codigos de color de Minecraft
// ============================================================

const MC_COLORS = {
    "0": "#000000", "1": "#0000AA", "2": "#00AA00", "3": "#00AAAA",
    "4": "#AA0000", "5": "#AA00AA", "6": "#FFAA00", "7": "#AAAAAA",
    "8": "#555555", "9": "#5555FF", "a": "#55FF55", "b": "#55FFFF",
    "c": "#FF5555", "d": "#FF55FF", "e": "#FFFF55", "f": "#FFFFFF"
};

const MC_FORMATS = { l: "b", o: "i", n: "u", m: "s", k: "k" };

let currentMotd = "";


function renderMcText(target, text) {

    target.textContent = "";

    const blank = function() {
        return { color: null, b: false, i: false, u: false, s: false, k: false };
    };

    let state = blank();

    String(text || "").split(/(§[0-9a-fk-or])/i).forEach(function(part) {

        const code = /^§([0-9a-fk-or])$/i.exec(part);

        if (code) {
            const c = code[1].toLowerCase();

            if (MC_COLORS[c]) state = Object.assign(blank(), { color: MC_COLORS[c] });
            else if (c === "r") state = blank();
            else state[MC_FORMATS[c]] = true;

            return;
        }

        part.split("\n").forEach(function(segment, index) {

            if (index > 0) target.append(document.createElement("br"));
            if (!segment) return;

            const span = el("span", state.k ? "mc-obf" : "", segment);
            if (state.color) span.style.color = state.color;
            if (state.b) span.style.fontWeight = "700";
            if (state.i) span.style.fontStyle = "italic";

            const deco = [state.u && "underline", state.s && "line-through"].filter(Boolean).join(" ");
            if (deco) span.style.textDecoration = deco;

            target.append(span);
        });
    });

    if (!target.childNodes.length) {
        target.append(el("span", "motd-empty", t("motd.empty")));
    }
}


// Encabezado y titulo de la pestana: el MOTD del servidor abierto
function plainMotd(text) {
    return String(text || "").replace(/§[0-9a-fk-or]/gi, "")
        .split("\n").map(function(line) { return line.trim(); }).filter(Boolean).join(" · ");
}


function renderServerHeader() {

    const info = currentServerInfo;
    const sub = $("appSubtitle");
    const system = authState ? authState.system_name : "MCServer";

    if (!info || currentView !== "server") return;

    setBrandIcon(info.slug);
    renderServerTitle();

    const plain = plainMotd(currentMotd);

    if (plain) {
        sub.classList.add("motd-inline");
        renderMcText(sub, currentMotd.replace(/\n/g, " "));
        sub.title = plain;
    } else {
        sub.classList.remove("motd-inline");
        sub.textContent = info.name;
        sub.title = "";
    }

    document.title = (plain || info.name) + " · " + system;
}


async function editMotd() {

    const area = el("textarea", "input motd-input");
    area.rows = 2;
    area.maxLength = 200;
    area.spellcheck = false;
    area.value = currentMotd;

    const preview = el("div", "motd motd-preview");
    const title = el("div", "motd-title", currentServerInfo ? currentServerInfo.name : "");
    const lines = el("div");
    preview.append(title, lines);

    const counter = el("span", "field-hint");

    const refresh = function() {
        // El cliente muestra como mucho dos lineas
        const parts = area.value.split("\n");
        if (parts.length > 2) area.value = parts.slice(0, 2).join("\n");

        renderMcText(lines, area.value);
        counter.textContent = area.value.length + " / 200";
    };

    const insert = function(code) {
        area.setRangeText("§" + code, area.selectionStart, area.selectionEnd, "end");
        area.focus();
        refresh();
    };

    const palette = el("div", "motd-palette");

    Object.keys(MC_COLORS).forEach(function(code) {
        const swatch = el("button", "motd-swatch");
        swatch.type = "button";
        swatch.style.background = MC_COLORS[code];
        swatch.title = t("motd.c" + code);
        swatch.onclick = function() { insert(code); };
        palette.append(swatch);
    });

    const formats = el("div", "motd-formats");

    [["l", "B", "motd.bold", "font-weight:800"], ["o", "I", "motd.italic", "font-style:italic"],
     ["n", "U", "motd.underline", "text-decoration:underline"], ["m", "S", "motd.strike", "text-decoration:line-through"],
     ["k", "?", "motd.obf", ""], ["r", t("motd.reset"), "motd.resetHint", ""]].forEach(function([code, label, key, css]) {
        const button = el("button", "btn btn-ghost btn-small motd-fmt", label);
        button.type = "button";
        button.title = t(key);
        if (css) button.style.cssText = css;
        button.onclick = function() { insert(code); };
        formats.append(button);
    });

    area.oninput = refresh;
    refresh();

    const ok = await openModal({
        title: t("motd.title"),
        body: [t("motd.desc"), palette, formats, area, counter, el("div", "field-label", t("motd.preview")), preview],
        okText: t("set.save"),
        onOk: function() { return true; }
    });

    if (!ok) return;

    try {
        const data = await postJson("/server/motd", { motd: area.value });
        showToast(data.running ? t("motd.savedRestart") : t("motd.saved"), data.running ? "amber" : "green");
        update();
    } catch (error) {
        showToast(error.message, "red");
    }
}
