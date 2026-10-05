// ============================================================
// Enrutador
// ============================================================

function go(hash) {
    if (location.hash === hash) route();
    else location.hash = hash;
}


function parseHash() {
    const parts = location.hash.replace(/^#\/?/, "").split("/").filter(Boolean);

    if (parts[0] === "s" && /^\d+$/.test(parts[1] || "")) {
        return { view: "server", id: Number(parts[1]), tab: parts[2] || "panel" };
    }

    return { view: parts[0] || "home" };
}


async function route() {

    const target = parseHash();

    if (authState && authState.setup && target.view !== "setup") {
        return go("#/setup");
    }

    if (target.view === "setup" && authState && !authState.setup) {
        return go("#/");
    }

    if (!loggedIn() && authState && !authState.public_access && !authState.setup
            && (target.view === "home" || target.view === "server")) {
        return go("#/login");
    }

    if ((target.view === "account" || target.view === "admin") && !loggedIn()) {
        return go("#/login");
    }

    if (target.view === "admin" && !isAdmin()) {
        return go("#/");
    }

    if ((target.view === "login" || target.view === "signup") && loggedIn()) {
        return go("#/");
    }

    if (target.view === "server") {
        await enterServer(target.id, target.tab);
        return;
    }

    leaveServer();

    const views = { home: "view-home", login: "view-auth", signup: "view-auth", setup: "view-auth",
                    account: "view-account", admin: "view-admin" };

    showView(views[target.view] ? target.view : "home");
}


function showView(name) {

    currentView = name;
    const section = { home: "view-home", login: "view-auth", signup: "view-auth", setup: "view-auth",
                      account: "view-account", admin: "view-admin" }[name];

    ["view-home", "view-auth", "view-account", "view-admin"].forEach(function(id) {
        $(id).hidden = id !== section;
    });

    ["panel", "players", "mods", "files", "settings"].forEach(function(tab) {
        $("tab-" + tab).hidden = true;
    });

    $("serverNav").hidden = true;
    $("homeBtn").hidden = name === "home";
    renderAccountArea();
    $("homeBtn").classList.toggle("active", false);
    $("appSubtitle").classList.remove("motd-inline");
    $("motdEdit").hidden = true;
    setBrandIcon(null);
    renderServerTitle();
    $("appSubtitle").textContent = t("nav." + (name === "signup" || name === "setup" ? name : name));
    document.title = authState ? authState.system_name : document.title;

    if (name === "home") loadServers();
    if (name === "login" || name === "signup" || name === "setup") renderAuth(name);
    if (name === "account") renderAccount();
    if (name === "admin") loadAdmin();

    window.scrollTo(0, 0);
}


function leaveServer() {
    currentServer = null;
    currentServerInfo = null;
    canManageCurrent = false;
    authorized = false;
    filesReady = false;
}


function resetServerCaches() {
    lastConsole = "";
    clearedAfter = null;
    chatKey = "";
    chatTotal = null;
    chatUnread = 0;
    playersData = null;
    settingsSaved = null;
    settingsDraft = {};
    settingsRestart = false;
    configDirty = false;
    currentPath = "";
    fmEntries = [];
    fmSelected.clear();
    fmClipboard = null;
    lastStatusTone = null;
    $("events").dataset.key = "";
    $("online").dataset.key = "";
    $("console").textContent = "";
    $("chat").textContent = "";

    // Mods: cada servidor tiene su tipo, version y lista
    modsData = null;
    modsPicked.clear();
    modsRemove.clear();
    filesRemove.clear();
    ["modsResults", "modpackResults", "modsProjects", "modsFiles"].forEach(function(id) { $(id).textContent = ""; });
    ["modsQuery", "modpackQuery", "modsPaste"].forEach(function(id) { $(id).value = ""; });
    $("modsPickedBar").hidden = true;
}


async function enterServer(id, tab) {

    if (currentServer !== id) {
        currentServer = id;
        canManageCurrent = false;
        currentServerInfo = null;
        resetServerCaches();

        // La barra se muestra cuando se sabe el tipo y los permisos
        $("serverNav").hidden = true;
    }

    ["view-home", "view-auth", "view-account", "view-admin"].forEach(function(view) {
        $(view).hidden = true;
    });

    currentView = "server";
    $("homeBtn").hidden = !loggedIn();
    renderAccountArea();

    await update();

    if (!currentServerInfo) {
        showToast(t("srv.notFound"), "red");
        return go("#/");
    }

    showTab(tab);
    updateConsole();
    updateStats();
    loadChat();
}
