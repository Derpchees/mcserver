// ============================================================
// Administracion: actualizaciones y acceso seguro (HTTPS)
// ============================================================

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

    // Punto en la pestana Actualizaciones cuando hay version nueva
    $("admUpdateDot").hidden = !(data.available && data.latest);

    if (data.available && data.latest) {
        box.append(el("div", "sto-note is-green", t("upd.available", { v: data.latest })));

        if (data.players) box.append(el("div", "sto-note is-amber", tn("upd.players", data.players)));

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
        t("upd.confirmDesc") + (data.players ? " " + tn("upd.players", data.players) : ""),
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

    // El panel se reinicia durante la actualizacion. Cada arranque tiene su
    // identificador: en cuanto cambia, el panel ya es la version nueva. (Un
    // reinicio dura menos de un segundo y no siempre se alcanza a ver caido.)
    const before = authState && authState.boot;
    const started = Date.now();

    clearInterval(updateTimer);
    updateTimer = setInterval(async function() {
        try {
            const state = await (await fetch("/auth/state?t=" + Date.now(), { cache: "no-store" })).json();

            if ((before && state.boot && state.boot !== before) || Date.now() - started > 120000) {
                clearInterval(updateTimer);
                location.reload();
            }
        } catch (error) {
            // Reiniciando: se vuelve a intentar
        }
    }, 1500);
}


// ------------------------------------------------------------
// Acceso seguro (HTTPS)
// ------------------------------------------------------------
//
// Dos modos: dominio gratis de DuckDNS con certificado de Let's Encrypt
// (recomendado: nadie instala nada) o CA propia del servidor (sin servicios
// externos, pero cada dispositivo instala el certificado una vez).

let httpsTimer = null;

// Direccion segura que devolvio el panel al empezar a activar el dominio:
// si el panel se reinicia y esta pagina (http) pierde la conexion, se va ahi
let httpsTarget = null;


async function loadHttps() {

    clearTimeout(httpsTimer);

    try {
        const data = await api("/admin/https?t=" + Date.now());
        renderHttps(data);

        if (data.duckdns.task && data.duckdns.task.running) {
            httpsTimer = setTimeout(loadHttps, 2000);
        }
    } catch (error) {
        // El panel se reinicio con HTTPS: esta pagina ya no lo alcanza por http
        if (httpsTarget) {
            setTimeout(function() { location.href = httpsTarget + location.hash; }, 3000);
        }
    }
}


function linkRow(label, url) {
    const row = el("div", "sys-row");
    const link = el("a", "", url);
    link.href = url;
    row.append(el("span", "pl-sub", label), link);
    return row;
}


function expiryRow(label, epoch) {
    return systemRow(label, new Date(epoch * 1000).toLocaleDateString(locale(), { dateStyle: "medium" }));
}


function httpsGuide() {
    // Como instalar la CA propia en cada sistema (una sola vez por dispositivo)
    const guide = el("details", "https-guide");
    guide.append(el("summary", "", t("https.howInstall")));

    ["windows", "android", "ios", "mac", "linux"].forEach(function(os) {
        const item = el("div", "https-os");
        item.append(el("b", "", t("https.os." + os)), el("div", "pl-sub", t("https.guide." + os)));
        guide.append(item);
    });

    return guide;
}


function duckdnsForm(port) {

    const wrap = el("div", "https-option");
    wrap.append(el("div", "https-option-title", t("https.dd.title")),
                el("div", "pl-sub", t("https.dd.desc")));

    const steps = el("ol", "https-steps");

    const first = el("li");
    const duck = el("a", "", "duckdns.org");
    duck.href = "https://www.duckdns.org";
    duck.target = "_blank";
    duck.rel = "noopener";
    first.append(document.createTextNode(t("https.dd.step1a") + " "), duck,
                 document.createTextNode(" " + t("https.dd.step1b")));
    steps.append(first);

    [2, 3, 4].forEach(function(n) {
        steps.append(el("li", "", t("https.dd.step" + n, { port: port })));
    });
    wrap.append(steps);

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
    tokWrap.append(el("span", "field-label", t("https.token")), tok, el("span", "field-hint", t("https.tokenHint")));

    const gameWrap = el("label", "un-check");
    const game = el("input");
    game.type = "checkbox";
    game.checked = true;
    gameWrap.append(game, document.createTextNode(" " + t("https.game")));

    const submit = el("button", "btn btn-start btn-small", t("https.dd.enable"));
    submit.type = "submit";
    const actions = el("div", "sto-actions");
    actions.append(submit);

    form.append(subWrap, tokWrap, gameWrap, actions);
    form.onsubmit = async function(event) {
        event.preventDefault();
        submit.disabled = true;

        try {
            const result = await postJson("/admin/https/duckdns", {
                subdomain: sub.value.trim(), token: tok.value.trim(), game_address: game.checked
            });
            httpsTarget = result.url;
            tok.value = "";
            loadHttps();
        } catch (error) {
            showToast(error.message, "red");
            submit.disabled = false;
        }
    };

    wrap.append(form, el("div", "sto-note", t("https.dd.dnsTip")));
    return wrap;
}


function renderHttps(data) {

    const box = $("admHttps");
    box.textContent = "";

    const dd = data.duckdns;
    const local = data.local;
    const task = dd.task || {};

    box.append(el("div", "sto-note", t("https.why")));

    if (task.running) {
        box.append(el("div", "sto-job-title", t("https.working")));
        box.append(el("div", "pl-sub", t("https.step." + task.step, task.vars || {}) || task.step));
        const bar = el("div", "sto-bar busy");
        bar.append(el("span"));
        box.append(bar);
        return;
    }

    if (task.error) box.append(el("div", "sto-note is-red", t("https.failed", { msg: task.error })));

    // Dominio gratis activo
    if (data.mode === "duckdns" && dd.domain) {
        const url = "https://" + dd.domain + ":" + dd.port + "/";
        box.append(systemRow(t("https.state"), t("https.onDomain")));
        box.append(linkRow(t("https.address"), url));
        if (dd.expires) box.append(expiryRow(t("https.expires"), dd.expires));
        box.append(el("div", "sto-note is-green", t("https.dd.share")));

        // Si esta pagina no se abrio con el dominio, se ofrece la direccion segura
        // (y recien activado se abre sola)
        if (location.hostname !== dd.domain) {
            const open = el("a", "btn btn-start btn-small", t("https.openSecure"));
            open.href = url + location.hash;
            const actions = el("div", "sto-actions");
            actions.append(open);
            box.append(actions);

            if (httpsTarget || (task.finished && Date.now() / 1000 - task.finished < 120)) {
                box.append(el("div", "sto-note", t("https.opening")));
                setTimeout(function() { location.href = url + location.hash; }, 6000);
            }
        }

        if (isSystemOwner()) box.append(httpsOffButton());
        return;
    }

    // Certificado propio activo
    if (data.mode === "local") {
        box.append(systemRow(t("https.state"), t("https.onLocal")));
        local.ips.filter(function(ip) { return ip !== "127.0.0.1"; }).forEach(function(ip) {
            box.append(linkRow(t("https.address"), "https://" + ip + ":" + local.port + "/"));
        });
        if (local.expires) box.append(expiryRow(t("https.expires"), local.expires));
        box.append(el("div", "sto-note", t("https.renews")));

        const ca = el("div", "sto-note https-ca");
        ca.append(el("b", "", t("https.caTitle")), el("div", "", t("https.caDesc")));
        box.append(ca);

        const actions = el("div", "sto-actions");
        const download = el("a", "btn btn-start btn-small", t("https.download"));
        download.href = "/ca.crt";
        download.setAttribute("download", "mcserver-ca.crt");
        actions.append(download);
        if (isSystemOwner()) actions.append(httpsOffButton(true));
        box.append(actions, httpsGuide());

        if (isSystemOwner()) {
            const change = el("details", "https-guide");
            change.append(el("summary", "", t("https.switchDomain")), duckdnsForm(local.port));
            box.append(change);
        }
        return;
    }

    // Desactivado: las dos opciones
    box.append(el("div", "sto-note", t("https.offDesc")));

    if (!isSystemOwner()) {
        box.append(el("div", "pl-sub", t("sto.ownerOnly")));
        return;
    }

    box.append(duckdnsForm(local.port));

    const other = el("div", "https-option");
    other.append(el("div", "https-option-title", t("https.local.title")), el("div", "pl-sub", t("https.local.desc")));
    const localBtn = el("button", "btn btn-ghost btn-small", t("https.local.enable"));
    localBtn.onclick = enableLocalHttps;
    const actions = el("div", "sto-actions");
    actions.append(localBtn);
    other.append(actions);
    box.append(other);
}


function httpsOffButton(bare) {
    const off = el("button", "btn btn-ghost btn-small", t("https.disable"));
    off.onclick = disableHttps;
    if (bare) return off;
    const actions = el("div", "sto-actions");
    actions.append(off);
    return actions;
}


async function enableLocalHttps() {
    try {
        await postJson("/admin/https/local", {});
        showToast(t("https.enabled"), "green");
        // El panel se reinicia con HTTPS: se abre la direccion segura
        setTimeout(function() { location.href = "https://" + location.host + location.pathname + location.hash; }, 6000);
    } catch (error) {
        showToast(error.message, "red");
    }
}


async function disableHttps() {

    const ok = await confirmDialog(t("https.disable"), t("https.disableDesc"), t("https.disable"));
    if (!ok) return;

    try {
        await postJson("/admin/https/disable", {});
        showToast(t("https.disabled"), "amber");
        setTimeout(function() { location.href = "http://" + location.hostname + ":" + location.port + location.pathname + location.hash; }, 6000);
    } catch (error) {
        showToast(error.message, "red");
    }
}
