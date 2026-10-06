// ============================================================
// Pestanas
// ============================================================

let activeTab = "panel";

const TAB_HASH = {
    players: "#jugadores",
    files: "#archivos",
    settings: "#ajustes"
};


function showTab(name) {

    // Sin servidor abierto (por ejemplo desde la lista) no hay pestanas
    if (!currentServer) {
        go("#/");
        return;
    }

    if (!["panel", "players", "mods", "files", "settings"].includes(name)) name = "panel";

    // Las pestanas de administracion son solo del dueno o del admin
    if (name !== "panel" && !canManageCurrent) {
        if (!loggedIn()) showToast(t("auth.needLogin"), "amber");
        name = "panel";
    }

    activeTab = name;

    document.querySelectorAll(".tab-btn[data-tab]").forEach(function(btn) {
        btn.classList.toggle("active", btn.dataset.tab === name);
    });

    ["panel", "players", "mods", "files", "settings"].forEach(function(tab) {
        $("tab-" + tab).hidden = tab !== name;
    });

    try {
        history.replaceState(null, "", "#/s/" + currentServer + (name === "panel" ? "" : "/" + name));
    } catch (error) {
    }

    if (name !== "panel") enterTab();
}


function applyManageUI() {

    const manage = canManageCurrent;
    const info = currentServerInfo;

    ["players", "mods", "files", "settings"].forEach(function(tab) {
        document.querySelector('.tab-btn[data-tab="' + tab + '"]').hidden = !manage;
    });

    // Mods o Plugins segun el tipo; Vanilla no tiene
    const modsTab = document.querySelector('.tab-btn[data-tab="mods"]');
    const type = info ? info.type : "";
    modsTab.hidden = !manage;
    $("modsTabLabel").textContent = type === "BEDROCK" ? t("addons.tab")
        : type === "PAPER" ? t("mods.tabPlugins") : t("mods.tab");

    // Sin permiso solo existiria Panel: no se muestra ninguna pestana
    $("serverNav").hidden = !(manage && info && currentView === "server");
    // Los lapices solo dentro del servidor (nunca en la lista de servidores)
    const editable = manage && currentView === "server";
    $("motdEdit").hidden = !editable;
    $("nameEdit").hidden = !editable;
    $("iconEdit").hidden = !editable;

    $("stop").hidden = !manage;
    $("restart").hidden = !manage;
    $("consoleCard").hidden = false;
    $("address").textContent = info ? info.address : "-";
    renderServerHeader();

    if (consoleLocked === manage) setConsoleLocked(!manage);

    renderDefaultStar();
}


// Bedrock: add-ons en lugar de mods, sin baneos ni skins de Java
function isBedrockServer() {
    return !!currentServerInfo && currentServerInfo.type === "BEDROCK";
}


// Estrella: servidor favorito que se abre al entrar al panel. Con sesion
// se guarda en la cuenta; sin sesion, en la memoria de este navegador.
function localDefault() {
    try {
        const value = Number(localStorage.getItem("mc-default-server"));
        return value > 0 ? value : null;
    } catch (error) {
        return null;
    }
}


function personalDefault() {
    return loggedIn() ? authState.my_default : localDefault();
}


function renderDefaultStar() {

    const star = $("defaultStar");
    const isDefault = !!currentServer && personalDefault() === currentServer;

    star.hidden = !currentServer;
    star.disabled = false;
    star.classList.toggle("on", isDefault);
    star.title = isDefault ? t("star.unset") : t("star.set");
}


async function toggleDefaultServer() {

    if (!currentServer) return;

    const isDefault = personalDefault() === currentServer;

    try {
        if (loggedIn()) {
            await postJson("/me/default", { server: isDefault ? "" : String(currentServer) });
            await refreshAuth();
        } else {
            try {
                if (isDefault) localStorage.removeItem("mc-default-server");
                else localStorage.setItem("mc-default-server", String(currentServer));
            } catch (error) {
                showToast(t("star.noStorage"), "red");
                return;
            }
        }

        renderDefaultStar();
        showToast(isDefault ? t("star.unsetDone")
            : loggedIn() ? t("star.setDoneAccount") : t("star.setDoneBrowser"), "green");
    } catch (error) {
        showToast(error.message, "red");
    }
}
