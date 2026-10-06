let lastConsole = "";
let clearedAfter = null;
let autoScroll = true;
let toastTimer = null;
let cmdHistory = [];
let cmdHistoryIndex = -1;




function $(id) {
    return document.getElementById(id);
}


function formatTime(seconds) {

    seconds = Math.max(0, Number(seconds) || 0);

    const minutes = Math.floor(seconds / 60);
    const secs = seconds % 60;

    return String(minutes).padStart(2, "0")
        + ":"
        + String(secs).padStart(2, "0");
}


function setTone(el, tone) {
    el.classList.remove("is-green", "is-amber", "is-red");
    if (tone) {
        el.classList.add("is-" + tone);
    }
}


function showToast(text, tone) {

    $("toastText").textContent = text;

    const dot = $("toastDot");
    dot.className = "dot";
    if (tone) {
        dot.classList.add("is-" + tone);
    }

    $("toast").classList.add("show");

    clearTimeout(toastTimer);
    toastTimer = setTimeout(function() {
        $("toast").classList.remove("show");
    }, 3000);
}


async function update() {

    if (!currentServer) return;

    // Si mientras llega la respuesta se volvio a la lista (u a otro
    // servidor), no se pinta: antes dejaba el encabezado del servidor y sus
    // botones de editar encima de la lista de servidores
    const id = currentServer;
    const stale = function() { return currentServer !== id || currentView !== "server"; };

    try {

        const response = await fetch("/api?t=" + Date.now());
        if (stale()) return;

        if (response.status === 404) {
            currentServerInfo = null;
            return;
        }

        const data = await response.json();
        if (stale()) return;

        const wasManage = canManageCurrent;
        currentServerInfo = data.server;
        canManageCurrent = !!data.can_manage;
        authorized = canManageCurrent;
        applyManageUI();

        currentMotd = data.motd || "";
        renderServerHeader();

        if (wasManage && !canManageCurrent && activeTab !== "panel") showTab("panel");

        let label, tone;

        if (data.server && data.server.state === "creating") {
            label = t("srv.creating");
            tone = "amber";
        } else if (data.server && data.server.state === "error") {
            label = t("srv.error") + (data.server.state_detail ? ": " + data.server.state_detail : "");
            tone = "red";
        } else if (!data.running) {
            label = t("status.off");
            tone = "red";
        } else if (data.health !== "healthy") {
            label = t("status.starting");
            tone = "amber";
        } else {
            label = t("status.online");
            tone = "green";
        }

        // Solo suena en la transicion a "en linea" vista en esta sesion,
        // no al abrir la pagina con el servidor ya encendido
        if (lastStatusTone !== null && lastStatusTone !== "green" && tone === "green") {
            playChime();
        }

        lastStatusTone = tone;

        currentPlayers =
            data.running && Array.isArray(data.autostop.names) ? data.autostop.names : [];

        $("statusText").textContent = label;
        setTone($("status"), tone);

        setConnection(true);

        // Cuantos hay, junto a "En linea" (las caras de cada uno van al lado)
        $("players").textContent = data.running && data.autostop.players ? " · " + data.autostop.players : "";

        $("start").disabled = data.running || (data.server && data.server.state !== "ready");
        $("stop").disabled = !data.running;
        $("restart").disabled = !data.running;

        updateAutostop(data.autostop);
        updateOnline(data.running, data.autostop);
        updateEvents(data.events || []);

    } catch (error) {

        if (stale()) return;
        $("statusText").textContent = t("status.disconnected");
        setTone($("status"), "red");

        setConnection(false);
    }
}


// Contador de apagado: el servidor solo actualiza el estado
// cada 10s, asi que aqui se calcula la hora exacta de apagado
// y se anima localmente
let countdown = {
    mode: "off",
    end: 0,
    total: 600
};


function updateAutostop(data) {

    const text = $("autostopText");

    if (!data.running) {
        countdown.mode = "off";
        text.textContent = t("autostop.off");
    } else if (data.health && data.health !== "healthy" && !data.players) {
        countdown.mode = "waiting";
        text.textContent = t("autostop.starting");
    } else if (data.players > 0) {
        countdown.mode = "players";
        text.textContent = tn("autostop.players", data.players);
    } else {

        const remaining =
            (Number(data.remaining_seconds) || 0) - (Number(data.age) || 0);

        const end = Date.now() + remaining * 1000;

        // Solo se corrige si se desvio; evita saltos pequenos
        if (countdown.mode !== "counting" || Math.abs(end - countdown.end) > 1500) {
            countdown.end = end;
        }

        countdown.mode = "counting";
        countdown.total = Number(data.timeout_seconds) || 600;

        text.textContent =
            t("autostop.empty");
    }

    renderCountdown();
}


function renderCountdown() {

    const timer = $("timer");
    const label = $("timerLabel");
    const progress = $("progress");

    setTone(timer, null);

    if (countdown.mode === "off" || countdown.mode === "waiting") {
        timer.textContent = "--:--";
        label.textContent = countdown.mode === "off" ? t("timer.remaining") : t("timer.waiting");
        progress.style.width = "0%";
        return;
    }

    if (countdown.mode === "players") {
        timer.textContent = t("timer.active");
        setTone(timer, "green");
        label.textContent = t("timer.noShutdown");
        progress.style.width = "100%";
        progress.style.background = "var(--green)";
        return;
    }

    const msLeft = Math.max(0, countdown.end - Date.now());
    const seconds = Math.ceil(msLeft / 1000);
    const percent = Math.min(100, msLeft / (countdown.total * 1000) * 100);

    timer.textContent = formatTime(seconds);
    label.textContent = t("timer.remaining");
    progress.style.width = percent + "%";

    if (msLeft <= 0) {
        timer.textContent = "00:00";
        label.textContent = t("timer.stopping");
        setTone(timer, "red");
        progress.style.background = "var(--red)";
        return;
    }

    const tone = percent < 20 ? "red" : "amber";
    setTone(timer, tone);
    progress.style.background =
        tone === "red" ? "var(--red)" : "var(--amber)";
}


function updateOnline(running, data) {

    const box = $("online");
    const names = (data && Array.isArray(data.names)) ? data.names : [];
    const key = running + "|" + names.join(",");

    if (box.dataset.key === key) {
        return;
    }

    box.dataset.key = key;
    box.textContent = "";

    if (!names.length) {
        const empty = document.createElement("span");
        empty.className = "online-empty";
        empty.textContent =
            !running ? t("online.serverOff")
            : data.players > 0 ? tn("online.count", data.players)
            : t("online.nobody");
        box.append(empty);
        return;
    }

    names.forEach(function(name) {

        const chip = document.createElement("span");
        chip.className = "player";

        const avatar = document.createElement("span");
        avatar.className = "avatar";
        avatar.textContent = name.charAt(0).toUpperCase();

        const img = document.createElement("img");
        img.alt = "";
        img.src = "https://mc-heads.net/avatar/" + encodeURIComponent(name) + "/48";
        img.onerror = function() { img.remove(); };
        avatar.append(img);

        const label = document.createElement("span");
        label.textContent = name;

        chip.append(avatar, label);
        box.append(chip);
    });
}


const EVENT_TYPES = {
    join: ["ev.join", "green"],
    leave: ["ev.leave", "amber"],
    request: ["ev.request", "blue"],
    start: ["ev.start", "green"],
    stop: ["ev.stop", "red"]
};


function formatDate(ts) {

    const d = new Date(ts * 1000);
    const today = new Date();

    const time = d.toLocaleTimeString(locale(), {
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit"
    });

    if (d.toDateString() === today.toDateString()) {
        return t("act.today") + " " + time;
    }

    return d.toLocaleDateString(locale(), {
        day: "2-digit",
        month: "short"
    }) + " " + time;
}


function updateEvents(events) {

    const box = $("events");

    const starts = events.filter(function(e) { return e.type === "start"; });
    $("lastStart").textContent =
        starts.length
            ? t("act.lastStart", { d: formatDate(starts[starts.length - 1].ts) })
            : "";

    const key = events.map(function(e) { return e.ts + e.type + e.text; }).join("|");

    if (box.dataset.key === key) {
        return;
    }

    box.dataset.key = key;

    if (!events.length) {
        box.textContent = "";
        box.append(el("div", "hint", t("act.none")));
        return;
    }

    box.textContent = "";

    events.slice().reverse().forEach(function(event) {

        const [tagKey, tone] = EVENT_TYPES[event.type] || ["ev.event", ""];
        const tag = t(tagKey);
        const eventText = eventLabel(event);

        const row = document.createElement("div");
        row.className = "event";

        const timeEl = document.createElement("div");
        timeEl.className = "event-time";
        timeEl.textContent = event.ts ? formatDate(event.ts) : "";

        const body = document.createElement("div");
        body.className = "event-body";

        const tagEl = document.createElement("span");
        tagEl.className = "tag " + tone;
        tagEl.textContent = tag;

        const textEl = document.createElement("span");
        textEl.className = "event-text";
        textEl.textContent = eventText;
        textEl.title = eventText;

        if (event.type === "join" || event.type === "leave") {
            textEl.style.color = "var(--text)";
            textEl.style.fontWeight = "600";
        }

        body.append(tagEl, textEl);
        row.append(timeEl, body);
        box.append(row);
    });
}


const LOG_LINE =
    /^\[(\d\d:\d\d:\d\d)\] \[([^\]]*?)\/(INFO|WARN|ERROR|FATAL|DEBUG)\](?: \[([^\]]*)\])?:?\s?(.*)$/;


function renderLine(text) {

    const line = document.createElement("div");
    line.className = "line";

    if (text === "El servidor está apagado.") {
        line.textContent = t("console.off");
        return line;
    }

    const m = LOG_LINE.exec(text);

    if (!m) {
        line.textContent = text;
        return line;
    }

    const [, time, thread, level, source, msg] = m;

    if (level === "WARN") line.classList.add("warn");
    if (level === "ERROR" || level === "FATAL") line.classList.add("error");
    if (/^<[^>]+> /.test(msg)) line.classList.add("chat");

    const parts = [
        ["t", time + " "],
        ["lvl lvl-" + level, level.padEnd(5) + " "],
        ["src", (source ? source.replace(/\/$/, "") : thread) + " "],
        ["msg", msg]
    ];

    parts.forEach(function([cls, value]) {
        const span = document.createElement("span");
        span.className = cls;
        span.textContent = value;
        line.append(span);
    });

    return line;
}


async function updateConsole() {

    try {

        const response = await fetch("/console?t=" + Date.now());
        const text = await response.text();

        if (text === lastConsole) {
            return;
        }

        lastConsole = text;

        let lines = text.split("\n").filter(function(x) {
            return x.trim();
        });

        if (clearedAfter !== null) {
            const index = lines.lastIndexOf(clearedAfter);
            if (index !== -1) {
                lines = lines.slice(index + 1);
            }
        }

        const box = $("console");

        const atBottom =
            box.scrollHeight - box.scrollTop - box.clientHeight < 60;

        box.textContent = "";

        if (!lines.length) {
            const empty = document.createElement("div");
            empty.className = "console-empty";
            empty.textContent =
                clearedAfter !== null
                    ? t("console.cleared")
                    : t("console.empty");
            box.append(empty);
        } else {
            const frag = document.createDocumentFragment();
            lines.forEach(function(x) {
                frag.append(renderLine(x));
            });
            box.append(frag);
        }

        if (autoScroll || atBottom) {
            box.scrollTop = box.scrollHeight;
        }

    } catch (error) {
    }
}


async function action(type) {

    const names = {
        start: t("action.start"),
        stop: t("action.stop"),
        restart: t("action.restart")
    };

    ["start", "stop", "restart"].forEach(function(id) {
        $(id).disabled = true;
    });

    showToast(names[type] || t("action.working"), "amber");

    try {

        const response = await fetch("/action/" + type, { method: "POST" });
        const data = await response.json();

        showToast(serverText(data.message), data.ok ? "green" : "red");

    } catch (error) {
        showToast(t("action.error"), "red");
    }

    setTimeout(update, 300);
    setTimeout(updateConsole, 300);
}


function onCommandKey(event) {

    const input = $("command");

    if (event.key === "Enter") {
        sendCommand();
        return;
    }

    if (event.key === "ArrowUp" && cmdHistory.length) {
        event.preventDefault();
        cmdHistoryIndex = Math.max(0, cmdHistoryIndex === -1 ? cmdHistory.length - 1 : cmdHistoryIndex - 1);
        input.value = cmdHistory[cmdHistoryIndex];
    }

    if (event.key === "ArrowDown" && cmdHistoryIndex !== -1) {
        event.preventDefault();
        cmdHistoryIndex++;
        if (cmdHistoryIndex >= cmdHistory.length) {
            cmdHistoryIndex = -1;
            input.value = "";
        } else {
            input.value = cmdHistory[cmdHistoryIndex];
        }
    }
}


async function sendCommand() {

    const input = $("command");
    const command = input.value.trim().replace(/^\//, "");

    if (!command) {
        return;
    }

    try {

        const response = await fetch("/command", {
            method: "POST",
            headers: {
                "Content-Type": "application/x-www-form-urlencoded"
            },
            body: "command=" + encodeURIComponent(command)
        });

        if (response.status === 401) {
            setConsoleLocked(true);
            showToast(t("console.expired"), "red");
            return;
        }

        const data = await response.json();

        if (data.ok) {
            cmdHistory.push(command);
            cmdHistoryIndex = -1;
            input.value = "";
            showToast(data.output ? data.output : t("console.sent"), "green");
        } else {
            showToast(serverText(data.message), "red");
        }

        autoScroll = true;
        setTimeout(updateConsole, 300);

    } catch (error) {
        showToast(t("console.sendError"), "red");
    }
}


let currentPlayers = [];


function playersWarning() {

    if (!currentPlayers.length) {
        return t("confirm.noPlayers");
    }

    return tn("confirm.players", currentPlayers.length, { names: currentPlayers.join(", ") });
}


async function confirmStop() {

    const ok = await openModal({
        title: t("confirm.stopTitle"),
        body: [
            t("confirm.stopBody"),
            el("div", currentPlayers.length ? "is-amber" : "", playersWarning())
        ],
        okText: t("btn.stop"),
        danger: true
    });

    if (ok) action("stop");
}


async function confirmRestart() {

    const ok = await openModal({
        title: t("confirm.restartTitle"),
        body: [
            t("confirm.restartBody"),
            el("div", currentPlayers.length ? "is-amber" : "", playersWarning())
        ],
        okText: t("btn.restart"),
        okClass: "btn-warn"
    });

    if (ok) {
        action("restart");
        // Los add-ons cambiados ya se aplican con este reinicio
        addonsChangedOn.delete(currentServer);
        $("addonsRestart").hidden = true;
    }

    return ok;
}


function clearConsole() {

    const lines = lastConsole.split("\n").filter(function(x) {
        return x.trim();
    });

    clearedAfter = lines.length ? lines[lines.length - 1] : null;
    lastConsole = "";
    updateConsole();
}


function copyAddress() {

    const text = $("address").textContent.trim();

    const done = function() {
        showToast(t("addr.copied"), "green");
    };

    if (navigator.clipboard && window.isSecureContext) {
        navigator.clipboard.writeText(text).then(done);
        return;
    }

    const area = document.createElement("textarea");
    area.value = text;
    document.body.append(area);
    area.select();
    try {
        document.execCommand("copy");
        done();
    } catch (error) {
    }
    area.remove();
}


$("console").addEventListener("scroll", function() {
    autoScroll =
        this.scrollHeight - this.scrollTop - this.clientHeight < 60;
});
