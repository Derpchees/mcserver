// ============================================================
// Inicio: lista de servidores
// ============================================================

function serverStatus(server) {
    if (server.state === "creating") return ["amber", t("srv.creating")];
    if (server.state === "error") return ["red", t("srv.error")];
    if (!server.running) return ["red", t("status.off")];
    if (server.health !== "healthy") return ["amber", t("status.starting")];
    return ["green", t("status.online")];
}


// Aviso de conexion: solo aparece cuando el panel deja de responder
function setConnection(ok) {
    const pill = $("livePill");
    pill.hidden = ok;

    if (!ok) {
        $("liveText").textContent = t("live.off");
        setTone(pill, "red");
    }
}


async function loadServers() {

    if (currentView !== "home") return;

    try {
        const data = await (await fetch("/servers?t=" + Date.now())).json();
        setConnection(true);
        renderServers(data.servers || []);
    } catch (error) {
        setConnection(false);
    }
}


function renderServers(servers) {

    const grid = $("serverGrid");
    const key = JSON.stringify(servers) + lang + (authState && authState.user ? authState.user.id : "");

    if (grid.dataset.key === key) return;
    grid.dataset.key = key;
    grid.textContent = "";

    $("homeIntro").hidden = servers.length > 0;

    servers.forEach(function(server) {

        const [tone, label] = serverStatus(server);
        const card = el("div", "srv-card");

        const top = el("div", "srv-top");
        const logo = el("div", "logo srv-logo logo-server");
        logo.append(serverIconEl(server.slug, "logo-img"));
        const titles = el("div", "srv-titles");
        const nameEl = el("div", "srv-name", server.name);

        if (personalDefault() === server.id) {
            const mark = el("span", "srv-star");
            mark.innerHTML = '<svg viewBox="0 0 24 24" stroke="currentColor" stroke-width="2" stroke-linejoin="round"><path d="M12 2.8l2.8 5.7 6.3.9-4.6 4.4 1.1 6.2L12 17l-5.6 3 1.1-6.2-4.6-4.4 6.3-.9z"/></svg>';
            mark.title = t("star.isDefault");
            nameEl.prepend(mark);
        }

        titles.append(nameEl,
                      el("div", "srv-meta", t("srv.by", { owner: server.owner || "-" }) + " · " +
                          typeName(server.type) + (["AUTO_CURSEFORGE", "MODRINTH"].includes(server.type) ? " " + server.modpack : " " + server.version)));
        const pill = el("span", "pill srv-pill is-" + tone);
        pill.append(el("span", "dot"), el("span", "", label));
        top.append(logo, titles, pill);

        const middle = el("div", "srv-middle");
        const address = el("div", "address srv-address");
        address.append(el("span", "", server.address));
        const copy = iconButton("copy", t("addr.copy"), function() {
            copyText(server.address);
        });
        address.append(copy);

        const players = el("div", "srv-players");

        if (server.running && server.players > 0) {
            server.names.slice(0, 6).forEach(function(name) {
                const head = document.createElement("img");
                head.src = "https://mc-heads.net/avatar/" + encodeURIComponent(name) + "/24";
                head.alt = name;
                head.title = name;
                players.append(head);
            });
            players.append(el("span", "", tn("srv.players", server.players)));
        } else {
            players.append(el("span", "hint", server.running ? t("online.nobody") : ""));
        }

        middle.append(address, players);

        const actions = el("div", "srv-actions");

        if (server.state === "ready" && !server.running) {
            const start = el("button", "btn btn-start btn-small", t("btn.start"));
            start.onclick = async function(event) {
                event.stopPropagation();
                start.disabled = true;
                currentServer = server.id;
                await action("start");
                currentServer = null;
                setTimeout(loadServers, 800);
            };
            actions.append(start);
        }

        const open = el("button", "btn btn-ghost btn-small", t("srv.open"));
        open.onclick = function() { go("#/s/" + server.id); };
        actions.append(open);

        const motdEl = el("div", "motd srv-motd");
        renderMcText(motdEl, server.motd);

        card.append(top, motdEl, middle, actions);
        card.onclick = function(event) {
            if (event.target.closest("button")) return;
            go("#/s/" + server.id);
        };

        grid.append(card);
    });

    // Boton para crear servidor si el usuario aun puede
    if (loggedIn() && authState.my_servers.length < (authState.limits.max_servers || 1)) {
        const add = el("button", "srv-card srv-add");
        add.append(el("span", "srv-add-plus", "+"), el("span", "", t("srv.create")));
        add.onclick = openCreateServer;
        grid.append(add);
    }
}


function copyText(text) {
    const done = function() { showToast(t("addr.copied"), "green"); };

    if (navigator.clipboard && window.isSecureContext) {
        navigator.clipboard.writeText(text).then(done);
        return;
    }

    const area = document.createElement("textarea");
    area.value = text;
    document.body.append(area);
    area.select();
    try { document.execCommand("copy"); done(); } catch (error) {}
    area.remove();
}
