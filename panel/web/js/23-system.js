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
// Acceso seguro (HTTPS) con la CA propia del servidor
// ------------------------------------------------------------

async function loadHttps() {
    try {
        renderHttps(await api("/admin/https?t=" + Date.now()));
    } catch (error) {
        // Durante el reinicio del panel la pagina deja de responder un momento
    }
}


function httpsGuide() {
    // Como instalar la CA en cada sistema (una sola vez por dispositivo)
    const guide = el("details", "https-guide");
    guide.append(el("summary", "", t("https.howInstall")));

    ["windows", "android", "ios", "mac", "linux"].forEach(function(os) {
        const item = el("div", "https-os");
        item.append(el("b", "", t("https.os." + os)), el("div", "pl-sub", t("https.guide." + os)));
        guide.append(item);
    });

    return guide;
}


function renderHttps(data) {

    const box = $("admHttps");
    box.textContent = "";

    box.append(el("div", "sto-note", t("https.why")));

    if (data.enabled) {
        box.append(systemRow(t("https.state"), t(data.running ? "https.on" : "https.starting")));

        data.ips.filter(function(ip) { return ip !== "127.0.0.1"; }).forEach(function(ip) {
            const url = "https://" + ip + ":" + data.port + "/";
            const link = el("a", "", url);
            link.href = url;
            const row = el("div", "sys-row");
            row.append(el("span", "pl-sub", t("https.address")), link);
            box.append(row);
        });

        if (data.expires) {
            box.append(systemRow(t("https.expires"),
                new Date(data.expires * 1000).toLocaleDateString(locale(), { dateStyle: "medium" })));
        }

        box.append(el("div", "sto-note", t("https.renews")));
    } else {
        box.append(el("div", "sto-note", t("https.offDesc")));
    }

    // Instalar la CA: se puede siempre que exista, aunque HTTPS este apagado
    if (data.ca_available) {
        const ca = el("div", "sto-note https-ca");
        ca.append(el("b", "", t("https.caTitle")), el("div", "", t("https.caDesc")));
        box.append(ca);
    }

    const actions = el("div", "sto-actions");

    if (data.ca_available) {
        const download = el("a", "btn btn-start btn-small", t("https.download"));
        download.href = "/ca.crt";
        download.setAttribute("download", "mcserver-ca.crt");
        actions.append(download);
    }

    if (isSystemOwner()) {
        const toggle = el("button", "btn btn-ghost btn-small", t(data.enabled ? "https.disable" : "https.enable"));
        toggle.onclick = data.enabled ? disableHttps : enableHttps;
        if (!data.enabled) toggle.className = "btn btn-start btn-small";
        actions.append(toggle);
    } else if (!data.enabled) {
        box.append(el("div", "pl-sub", t("sto.ownerOnly")));
    }

    box.append(actions);

    if (data.ca_available) box.append(httpsGuide());
}


async function enableHttps() {
    try {
        await postJson("/admin/https/enable", {});
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
        setTimeout(function() { location.href = "http://" + location.host + location.pathname + location.hash; }, 6000);
    } catch (error) {
        showToast(error.message, "red");
    }
}
