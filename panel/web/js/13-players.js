// ============================================================
// Jugadores
// ============================================================

let playersData = null;
let playerFilter = "all";
let openPlayerName = null;
let skinViewer = null;
let skinLibPromise = null;
let playerPanelDirty = false;

const TIMEOUT_OPTIONS = [5, 15, 60, 360, 1440, 10080];


function loadSkinLib() {

    if (window.skinview3d) return Promise.resolve();

    if (!skinLibPromise) {
        skinLibPromise = new Promise(function(resolve, reject) {
            const script = document.createElement("script");
            script.src = "https://cdn.jsdelivr.net/npm/skinview3d@3.1.0/bundles/skinview3d.bundle.js";
            script.onload = resolve;
            script.onerror = function() {
                skinLibPromise = null;
                reject(new Error("skinview3d"));
            };
            document.head.append(script);
        });
    }

    return skinLibPromise;
}


function timeAgo(ts) {

    if (!ts) return t("pl.never");

    const seconds = Math.round(ts - Date.now() / 1000);
    const abs = Math.abs(seconds);
    const rtf = new Intl.RelativeTimeFormat(locale(), { numeric: "auto" });

    if (abs < 60) return rtf.format(Math.round(seconds), "second");
    if (abs < 3600) return rtf.format(Math.round(seconds / 60), "minute");
    if (abs < 86400) return rtf.format(Math.round(seconds / 3600), "hour");
    return rtf.format(Math.round(seconds / 86400), "day");
}


function formatMinutes(minutes) {
    if (minutes < 60) return t("pl.dur.min", { n: minutes });
    if (minutes < 1440) return t("pl.dur.hour", { n: minutes / 60 });
    return t("pl.dur.day", { n: minutes / 1440 });
}


async function loadPlayers() {

    try {
        playersData = await api("/players?t=" + Date.now());

        // Bedrock no tiene baneos
        const bedrock = playersData.edition === "bedrock";
        document.querySelector('.pl-filters [data-filter="banned"]').hidden = bedrock;
        if (bedrock && playerFilter === "banned") setPlayerFilter("all");

        renderPlayers();

        if (openPlayerName) {
            const player = findPlayer(openPlayerName);
            if (player && !$("modal").hidden) {
                // Tras una accion se redibuja todo; en la recarga periodica solo
                // el estado, para no borrar lo que se este escribiendo
                if (playerPanelDirty) renderPlayerPanel(player);
                else renderPlayerSide(player);
                playerPanelDirty = false;
            }
        }

    } catch (error) {
        if (error.message !== "auth") showToast(error.message, "red");
    }
}


function findPlayer(name) {
    return playersData && playersData.players.find(function(p) {
        return p.name.toLowerCase() === name.toLowerCase();
    });
}


function setPlayerFilter(filter) {
    playerFilter = filter;
    document.querySelectorAll(".pl-filters .tab-btn").forEach(function(btn) {
        btn.classList.toggle("active", btn.dataset.filter === filter);
    });
    renderPlayers();
}


function playerBadges(player) {

    const box = el("span", "pl-badges");

    if (player.op) box.append(el("span", "tag amber", t("pl.badge.op")));
    if (player.whitelisted) box.append(el("span", "tag blue", t("pl.badge.whitelist")));

    if (player.ban) {
        box.append(el("span", "tag red",
            player.ban.until ? t("pl.badge.timeout") : t("pl.badge.banned")));
    }

    return box;
}


function playerStatus(player) {
    if (player.online) return t("pl.onlineNow");
    if (player.ban && player.ban.until) {
        return t("pl.timeoutUntil", { d: new Date(player.ban.until * 1000).toLocaleString(locale(), {
            day: "numeric", month: "short", hour: "2-digit", minute: "2-digit"
        }) });
    }
    return player.last_seen ? t("pl.lastSeen", { d: timeAgo(player.last_seen) }) : t("pl.neverJoined");
}


function renderPlayers() {

    if (!playersData) return;

    const list = $("playerList");
    const query = $("playerSearch").value.trim().toLowerCase();
    const all = playersData.players;

    $("playersCount").textContent = t("pl.count", {
        online: playersData.online.length,
        total: all.length
    });

    $("playersNote").hidden = playersData.running;
    $("playersNote").textContent = playersData.running ? "" : t("pl.offNote");

    const filtered = all.filter(function(p) {
        if (query && !p.name.toLowerCase().includes(query)) return false;
        if (playerFilter === "online") return p.online;
        if (playerFilter === "op") return p.op;
        if (playerFilter === "banned") return !!p.ban;
        if (playerFilter === "whitelist") return p.whitelisted;
        return true;
    });

    list.textContent = "";

    if (!filtered.length) {
        list.append(el("div", "list-empty", t("pl.none")));
        return;
    }

    filtered.forEach(function(player) {

        const row = el("div", "pl-row" + (player.online ? " online" : ""));

        const avatar = el("span", "avatar pl-avatar", player.name.charAt(0).toUpperCase());
        // La cara de su skin (en Bedrock la de GeyserMC o el personaje clasico)
        const img = document.createElement("img");
        img.alt = "";
        img.src = playerHeadUrl(player.name, 64);
        img.onerror = function() { img.remove(); };
        avatar.append(img);

        avatar.append(el("span", "pl-dot"));

        const info = el("div", "pl-info");
        const top = el("div", "pl-name");
        top.append(el("span", "", player.name), playerBadges(player));
        info.append(top, el("div", "pl-sub", playerStatus(player)));

        const actions = el("div", "pl-actions");

        if (player.online && playersData.running) {
            actions.append(iconButton("message", t("pl.message"), function() {
                openPlayer(player.name, "message");
            }));
        }

        const manage = el("button", "btn btn-ghost btn-small", t("pl.manage"));
        manage.onclick = function(event) {
            event.stopPropagation();
            openPlayer(player.name);
        };
        actions.append(manage);

        row.append(avatar, info, actions);
        row.onclick = function() { openPlayer(player.name); };

        list.append(row);
    });
}


async function playerAction(name, action, extra) {

    try {
        const data = await api("/players/action", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(Object.assign({ name: name, action: action }, extra || {}))
        });

        showToast(t("pl.done." + action, { name: name }) || serverText(data.message), "green");
        playerPanelDirty = true;
        setTimeout(loadPlayers, 600);
        return true;

    } catch (error) {
        if (error.message !== "auth") showToast(error.message, "red");
        return false;
    }
}


// Botones peligrosos: el primer clic pide confirmacion en el mismo boton
function armedButton(label, confirmLabel, className, onConfirm) {

    const btn = el("button", "btn btn-small " + className, label);
    let timer = null;

    btn.onclick = function() {

        if (btn.classList.contains("armed")) {
            clearTimeout(timer);
            btn.classList.remove("armed");
            btn.textContent = label;
            onConfirm();
            return;
        }

        btn.classList.add("armed");
        btn.textContent = confirmLabel;
        timer = setTimeout(function() {
            btn.classList.remove("armed");
            btn.textContent = label;
        }, 4000);
    };

    return btn;
}


function plSection(title) {
    const section = el("div", "pl-section");
    section.append(el("div", "pl-section-title", title));
    return section;
}


function renderPlayerSide(player) {

    if (!$("playerName")) return;

    $("playerName").textContent = player.name;
    $("playerStatus").textContent = playerStatus(player);
    $("playerStatus").className = "pl-sub" + (player.online ? " is-green" : "");

    const badges = $("playerBadges");
    badges.textContent = "";
    badges.append(playerBadges(player));

    const facts = $("playerFacts");
    facts.textContent = "";

    [
        [t("pl.firstSeen"), player.first_seen ? new Date(player.first_seen * 1000).toLocaleDateString(locale(), { day: "numeric", month: "short", year: "numeric" }) : "-"],
        [t("pl.lastSeenLabel"), player.online ? t("pl.onlineNow") : timeAgo(player.last_seen)],
        [t("pl.joins"), String(player.joins)],
        [playersData.edition === "bedrock" ? "XUID" : "UUID", player.uuid || "-"]
    ].forEach(function([label, value]) {
        const row = el("div", "pl-fact");
        row.append(el("span", "", label), el("b", "", value));
        facts.append(row);
    });
}


function renderPlayerPanel(player) {

    const panel = $("playerPanel");
    if (!panel) return;

    const live = playersData.running;
    const online = player.online && live;

    renderPlayerSide(player);

    panel.textContent = "";

    if (!live) {
        panel.append(el("div", "set-note", t("pl.offNote")));
    }

    // Mensaje privado
    const msg = plSection(t("pl.message"));
    const msgRow = el("div", "pl-inline");
    const msgInput = el("input", "input");
    msgInput.id = "playerMessage";
    msgInput.maxLength = 240;
    msgInput.placeholder = online ? t("pl.messagePh", { name: player.name }) : t("pl.needsOnline");
    msgInput.disabled = !online;
    const msgBtn = el("button", "btn btn-send btn-small", t("console.send"));
    msgBtn.disabled = !online;
    const sendMsg = async function() {
        const text = msgInput.value.trim();
        if (!text) return;
        if (await playerAction(player.name, "message", { text: text })) msgInput.value = "";
    };
    msgBtn.onclick = sendMsg;
    msgInput.onkeydown = function(event) { if (event.key === "Enter") sendMsg(); };
    msgRow.append(msgInput, msgBtn);
    msg.append(msgRow);
    panel.append(msg);

    // Modo de juego y teletransporte
    const play = plSection(t("pl.gamemode"));
    const modes = el("div", "pl-modes");

    ["survival", "creative", "adventure", "spectator"].forEach(function(mode) {
        const btn = el("button", "btn btn-ghost btn-small", t("opt." + mode));
        btn.disabled = !online;
        btn.onclick = function() { playerAction(player.name, "gamemode", { mode: mode }); };
        modes.append(btn);
    });

    play.append(modes);

    const others = playersData.online.filter(function(n) {
        return n.toLowerCase() !== player.name.toLowerCase();
    });

    const tpRow = el("div", "pl-inline");
    const tpSelect = el("select", "input");
    tpSelect.disabled = !online || !others.length;

    if (!others.length) {
        tpSelect.append(el("option", "", t("pl.noOthers")));
    }

    others.forEach(function(n) {
        const option = el("option", "", n);
        option.value = n;
        tpSelect.append(option);
    });

    const tpBtn = el("button", "btn btn-ghost btn-small", t("pl.teleport"));
    tpBtn.disabled = tpSelect.disabled;
    tpBtn.onclick = function() { playerAction(player.name, "tp", { target: tpSelect.value }); };
    tpRow.append(el("span", "pl-inline-label", t("pl.teleportTo")), tpSelect, tpBtn);
    play.append(tpRow);
    panel.append(play);

    // Moderacion
    const mod = plSection(t("pl.moderation"));
    const reason = el("input", "input");
    reason.maxLength = 120;
    reason.placeholder = t("pl.reasonPh");
    reason.disabled = !live;
    mod.append(reason);

    const modRow = el("div", "pl-modes");

    const kick = armedButton(t("pl.kick"), t("pl.confirm"), "btn-ghost", function() {
        playerAction(player.name, "kick", { reason: reason.value });
    });
    kick.disabled = !online;

    const timeoutSelect = el("select", "input pl-timeout");
    TIMEOUT_OPTIONS.forEach(function(minutes) {
        const option = el("option", "", formatMinutes(minutes));
        option.value = minutes;
        timeoutSelect.append(option);
    });
    timeoutSelect.value = "60";
    timeoutSelect.disabled = !live;

    const timeoutBtn = armedButton(t("pl.timeout"), t("pl.confirm"), "btn-warn", function() {
        playerAction(player.name, "timeout", { minutes: Number(timeoutSelect.value), reason: reason.value });
    });
    timeoutBtn.disabled = !live;

    const bedrock = playersData.edition === "bedrock";
    modRow.append(kick);

    // Bedrock no tiene baneos ni suspensiones: se usa la lista de permitidos
    if (!bedrock) modRow.append(timeoutSelect, timeoutBtn);

    if (bedrock) {
        mod.append(el("div", "pl-hint", t("pl.bedrockNoBan")));
    } else if (player.ban) {
        const pardon = el("button", "btn btn-start btn-small", t("pl.pardon"));
        pardon.disabled = !live;
        pardon.onclick = function() { playerAction(player.name, "pardon"); };
        modRow.append(pardon);
    } else {
        const ban = armedButton(t("pl.ban"), t("pl.confirm"), "btn-danger", function() {
            playerAction(player.name, "ban", { reason: reason.value });
        });
        ban.disabled = !live;
        modRow.append(ban);
    }

    mod.append(modRow);

    if (player.ban && player.ban.reason) {
        mod.append(el("div", "pl-hint", t("pl.banReason", { r: player.ban.reason })));
    }

    const kill = armedButton(t("pl.kill"), t("pl.confirm"), "btn-ghost", function() {
        playerAction(player.name, "kill");
    });
    kill.disabled = !online;
    kill.title = t("pl.killHint");
    modRow.append(kill);

    panel.append(mod);

    // Rol y acceso
    const role = plSection(t("pl.role"));

    [
        ["op", player.op, "op", "deop", t("pl.operator"), t("pl.operatorHint")],
        ["whitelist", player.whitelisted, "whitelist_add", "whitelist_remove", t("pl.whitelist"), t("pl.whitelistHint")]
    ].forEach(function([id, on, enable, disable, label, hint]) {

        const row = el("div", "set-row pl-role");
        const text = el("div", "set-text");
        text.append(el("div", "set-label", label), el("div", "set-desc", hint));

        const sw = el("button", "switch" + (on ? " on" : ""));
        sw.type = "button";
        sw.setAttribute("role", "switch");
        sw.setAttribute("aria-checked", on ? "true" : "false");
        sw.setAttribute("aria-label", label);
        sw.append(el("span", "switch-knob"));
        sw.disabled = !live;
        sw.onclick = function() { playerAction(player.name, on ? disable : enable); };

        row.append(text, sw);
        role.append(row);
    });

    panel.append(role);
}


async function openPlayer(name, focus) {

    const player = findPlayer(name);
    if (!player) return;

    openPlayerName = player.name;

    const layout = el("div", "pl-sheet");

    const side = el("div", "pl-side");
    const stage = el("div", "pl-skin");
    const canvas = document.createElement("canvas");
    stage.append(canvas);

    const name1 = el("div", "pl-sheet-name");
    name1.id = "playerName";
    const status = el("div", "pl-sub");
    status.id = "playerStatus";
    const badges = el("div");
    badges.id = "playerBadges";
    const facts = el("div", "pl-facts");
    facts.id = "playerFacts";

    side.append(stage, name1, status, badges, facts);

    const panel = el("div", "pl-panel");
    panel.id = "playerPanel";

    layout.append(side, panel);

    const done = openModal({
        title: t("pl.sheetTitle"),
        body: [layout],
        okText: t("modal.close"),
        hideCancel: true,
        cls: "player-modal"
    });

    renderPlayerPanel(player);

    if (focus === "message") {
        setTimeout(function() {
            const input = $("playerMessage");
            if (input && !input.disabled) input.focus();
        }, 60);
    }

    startSkin(stage, canvas, player.name);

    await done;

    openPlayerName = null;

    if (skinViewer) {
        skinViewer.dispose();
        skinViewer = null;
    }
}


async function startSkin(stage, canvas, name) {

    const skinUrl = playerSkinUrl(name);

    const fallback = function() {
        stage.textContent = "";
        const img = document.createElement("img");
        img.className = "pl-skin-2d";
        img.alt = name;
        img.src = "https://mc-heads.net/body/" + encodeURIComponent(name) + "/220";
        stage.append(img);
    };

    try {
        await loadSkinLib();

        // El modal pudo cerrarse mientras cargaba la libreria
        if (!canvas.isConnected) return;

        skinViewer = new skinview3d.SkinViewer({
            canvas: canvas,
            width: 220,
            height: 300
        });

        skinViewer.background = null;
        skinViewer.zoom = 0.85;
        skinViewer.fov = 40;
        skinViewer.autoRotate = true;
        skinViewer.autoRotateSpeed = 0.6;
        skinViewer.controls.enableZoom = false;
        skinViewer.animation = new skinview3d.WalkingAnimation();
        skinViewer.animation.speed = 0.55;

        await skinViewer.loadSkin(skinUrl);

    } catch (error) {
        if (skinViewer) {
            skinViewer.dispose();
            skinViewer = null;
        }
        fallback();
    }
}


setInterval(function() {
    if (activeTab === "players" && authorized) loadPlayers();
}, 5000);
