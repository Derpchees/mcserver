// ============================================================
// Sesion
// ============================================================

let filesReady = false;
let currentPath = "";


async function api(url, options) {

    const response = await fetch(url, options);

    if (response.status === 401) {
        showLogin();
        throw new Error("auth");
    }

    const data = await response.json().catch(function() {
        return { ok: false, message: t("fm.badResponse") };
    });

    if (!response.ok || data.ok === false) {
        throw new Error(serverText(data.message) || "Error");
    }

    return data;
}


// La consola comparte la sesion del area de archivos
let consoleLocked = true;
let consolePane = "chat";


// En pantallas angostas los paneles se alternan con pestanas
function isNarrow() {
    return window.matchMedia("(max-width: 899px)").matches;
}


function setConsoleLocked(locked) {
    consoleLocked = locked;
    renderConsoleBars();

}


function renderConsoleBars() {

    // Solo la consola pide contrasena; el chat esta abierto
    $("commandBar").hidden = consoleLocked;
    $("commandLock").hidden = !consoleLocked;

    // Invitado: entrar. Con sesion pero sin permiso: solo el dueno o un admin
    const guest = !loggedIn();
    $("commandLockText").textContent = guest ? t("console.needLogin") : t("console.needOwner");
    $("commandLockBtn").hidden = !guest;
}


async function checkConsoleSession() {
    setConsoleLocked(!canManageCurrent);
}


async function unlockConsole(event) {
    event.preventDefault();
    go("#/login");
}


let authorized = false;


function showLogin() {
    // Sin permiso: se vuelve al panel publico del servidor
    authorized = false;
    filesReady = false;
    setConsoleLocked(true);

    if (currentServer) showTab("panel");
    else go("#/login");
}


function enterTab() {

    authorized = canManageCurrent;
    setConsoleLocked(!authorized);
    $("loginCard").hidden = true;

    if (!authorized) return;

    if (activeTab === "mods") {
        loadMods();
    } else if (activeTab === "files") {
        filesReady = true;
        $("filesArea").hidden = false;
        loadFolder(currentPath);
        loadBackups();
    } else if (activeTab === "players") {
        $("playersArea").hidden = false;
        loadPlayers();
    } else if (activeTab === "settings") {
        $("settingsArea").hidden = false;
        renderServerConfig();

        // No se pisan los cambios sin guardar al volver a la pestana
        if (settingsSaved && Object.keys(settingsChanges()).length) renderSettings();
        else loadSettings();
    }
}


async function openProtected() {
    enterTab();
}


async function login(event) {
    event.preventDefault();
    go("#/login");
}
