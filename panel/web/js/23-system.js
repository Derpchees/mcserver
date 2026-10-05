// ============================================================
// Administracion: actualizaciones y acceso seguro (HTTPS)
// ============================================================

let httpsTimer = null;
let updateTimer = null;


function systemRow(label, value) {
    const row = el("div", "sys-row");
    row.append(el("span", "pl-sub", label), el("b", "", value));
    return row;
}


// ------------------------------------------------------------
// Actualizaciones
// ------------------------------------------------------------

async function loadUpdate(force) {

    const box = $("admUpdate");

    try {
        const data = await api("/admin/update?force=" + (force ? "1" : "0") + "&t=" + Date.now());
        renderUpdate(data);
    } catch (error) {
        if (error.message !== "auth") {
            box.textContent = "";
            box.append(el("div", "list-empty", error.message));
        }
    }
}


function renderUpdate(data) {

    const box = $("admUpdate");
    box.textContent = "";

    box.append(systemRow(t("upd.installed"), "v" + data.installed));

    if (data.latest) box.append(systemRow(t("upd.latest"), "v" + data.latest));
    if (data.error) box.append(el("div", "sto-note is-amber", t("upd.checkFailed")));

    const actions = el("div", "sto-actions");

    if (data.available && data.latest) {
        box.append(el("div", "sto-note is-green", t("upd.available", { v: data.latest })));

        if (data.players) box.append(el("div", "sto-note is-amber", t("upd.players", { n: data.players })));

        if (isSystemOwner()) {
            const go = el("button", "btn btn-start btn-small", t("upd.install", { v: data.latest }));
            go.onclick = function() { startUpdate(data); };
            actions.append(go);
        }
    } else if (data.latest) {
        box.append(el("div", "sto-note", t("upd.upToDate")));
    }

    const check = el("button", "btn btn-ghost btn-small", t("upd.check"));
    check.onclick = function() { loadUpdate(true); };

    const changes = el("a", "btn btn-ghost btn-small", t("upd.changes"));
    changes.href = data.repo + "/commits/main";
    changes.target = "_blank";
    changes.rel = "noopener";

    actions.append(check, changes);
    box.append(actions);
}


async function startUpdate(data) {

    const ok = await confirmDialog(t("upd.confirmTitle", { v: data.latest }),
        t("upd.confirmDesc") + (data.players ? " " + t("upd.players", { n: data.players }) : ""),
        t("upd.install", { v: data.latest }));

    if (!ok) return;

    try {
        await postJson("/admin/update/start", {});
    } catch (error) {
        return showToast(error.message, "red");
    }

    const box = $("admUpdate");
    box.textContent = "";
    box.append(el("div", "sto-note is-amber", t("upd.running")));

    // El panel se reinicia durante la actualizacion: se espera a que vuelva
    let wentDown = false;
    const started = Date.now();

    clearInterval(updateTimer);
    updateTimer = setInterval(async function() {
        try {
            const response = await fetch("/auth/state?t=" + Date.now(), { cache: "no-store" });
            if (response.ok && (wentDown || Date.now() - started > 60000)) {
                clearInterval(updateTimer);
                location.reload();
            }
        } catch (error) {
            wentDown = true;
        }
    }, 3000);
}


// ------------------------------------------------------------
// Acceso seguro (HTTPS)
// ------------------------------------------------------------

async function loadHttps() {

    clearTimeout(httpsTimer);

    try {
        const data = await api("/admin/https?t=" + Date.now());
        renderHttps(data);

        if (data.task && data.task.running) {
            httpsTimer = setTimeout(loadHttps, 2000);
        }
    } catch (error) {
        // Durante el reinicio con HTTPS esta pagina (http) deja de responder
    }
}


function renderHttps(data) {

    const box = $("admHttps");
    box.textContent = "";
    const task = data.task || {};

    if (task.running) {
        box.append(el("div", "sto-job-title", t("https.working")));
        box.append(el("div", "pl-sub", t("https.step." + task.step, task.vars || {}) || task.step));
        const bar = el("div", "sto-bar busy");
        bar.append(el("span"));
        box.append(bar);
        return;
    }

    if (task.error) box.append(el("div", "sto-note is-red", t("https.failed", { msg: task.error })));

    if (data.enabled && data.domain) {
        const url = "https://" + data.domain + ":" + data.port + "/";
        const link = el("a", "", url);
        link.href = url;
        const row = el("div", "sys-row");
        row.append(el("span", "pl-sub", t("https.address")), link);
        box.append(row);

        if (data.expires) {
            box.append(systemRow(t("https.expires"),
                new Date(data.expires * 1000).toLocaleDateString(locale(), { dateStyle: "medium" })));
        }

        box.append(el("div", "sto-note", t("https.renews")));

        // Recien activado: si esta pagina sigue en http, se pasa a la direccion segura
        if (location.protocol === "http:" && task.finished && Date.now() / 1000 - task.finished < 120) {
            box.append(el("div", "sto-note is-green", t("https.opening")));
            setTimeout(function() { location.href = url; }, 6000);
        }

        if (isSystemOwner()) {
            const off = el("button", "btn btn-ghost btn-small", t("https.disable"));
            off.onclick = disableHttps;
            const actions = el("div", "sto-actions");
            actions.append(off);
            box.append(actions);
        }
        return;
    }

    box.append(el("div", "sto-note", t("https.why")));

    if (!isSystemOwner()) {
        box.append(el("div", "pl-sub", t("sto.ownerOnly")));
        return;
    }

    const help = el("div", "sto-note");
    help.append(document.createTextNode(t("https.how") + " "));
    const duck = el("a", "", "duckdns.org");
    duck.href = "https://www.duckdns.org";
    duck.target = "_blank";
    duck.rel = "noopener";
    help.append(duck);
    box.append(help);

    const form = el("form", "form-grid");

    const subWrap = el("label", "field");
    const subRow = el("div", "https-row");
    const sub = el("input", "input");
    sub.placeholder = t("https.subPh");
    sub.autocomplete = "off";
    subRow.append(sub, el("span", "https-suffix", ".duckdns.org"));
    subWrap.append(el("span", "field-label", t("https.subdomain")), subRow);

    const tokWrap = el("label", "field");
    const tok = el("input", "input");
    tok.type = "password";
    tok.autocomplete = "off";
    tok.placeholder = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx";
    tokWrap.append(el("span", "field-label", t("https.token")), tok,
        el("span", "field-hint", t("https.tokenHint")));

    const gameWrap = el("label", "un-check");
    const game = el("input");
    game.type = "checkbox";
    game.checked = true;
    gameWrap.append(game, document.createTextNode(" " + t("https.game")));

    const submit = el("button", "btn btn-start btn-small", t("https.enable"));
    submit.type = "submit";

    const actions = el("div", "sto-actions");
    actions.append(submit);
    form.append(subWrap, tokWrap, gameWrap, actions);
    form.onsubmit = async function(event) {
        event.preventDefault();
        submit.disabled = true;

        try {
            await postJson("/admin/https/enable", {
                subdomain: sub.value.trim(), token: tok.value.trim(), game_address: game.checked
            });
            tok.value = "";
            loadHttps();
        } catch (error) {
            showToast(error.message, "red");
            submit.disabled = false;
        }
    };

    box.append(form);
}


async function disableHttps() {

    const ok = await confirmDialog(t("https.disable"), t("https.disableDesc"), t("https.disable"));
    if (!ok) return;

    try {
        await postJson("/admin/https/disable", {});
        showToast(t("https.disabled"), "amber");
        const url = "http://" + location.hostname + ":" + location.port + "/";
        setTimeout(function() { location.href = url; }, 5000);
    } catch (error) {
        showToast(error.message, "red");
    }
}
