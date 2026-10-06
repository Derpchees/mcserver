// ============================================================
// Ajustes del servidor: pestanas
// ============================================================
//
// Como en Administracion: cada tarjeta lleva data-settab con su pestana y
// solo se ven las de la elegida. La pestana va en la direccion
// (#/s/1/settings/game) para poder abrirla directo. Los cambios sin
// guardar de todas las pestanas se guardan juntos (barra de abajo).

const SETTINGS_TABS = ["server", "auto", "game", "players", "danger"];
let settingsTab = "server";


function settingsTabFromHash() {
    const name = location.hash.replace(/^#\/?/, "").split("/")[3];
    return SETTINGS_TABS.indexOf(name) >= 0 ? name : settingsTab;
}


function showSettingsTab(name) {

    if (SETTINGS_TABS.indexOf(name) < 0) name = "server";
    settingsTab = name;

    document.querySelectorAll("#settingsTabs .tab-btn").forEach(function(btn) {
        btn.classList.toggle("active", btn.dataset.settab === name);
    });

    renderSettingsIntro(name);
    applySettingsTab();

    if (currentServer && activeTab === "settings") {
        try {
            history.replaceState(null, "", "#/s/" + currentServer + "/settings" + (name === "server" ? "" : "/" + name));
        } catch (error) {
        }
    }
}


function renderSettingsIntro(name) {

    const box = $("settingsIntro");
    const button = document.querySelector('#settingsTabs [data-settab="' + name + '"]');
    box.textContent = "";
    box.classList.toggle("is-danger", name === "danger");

    const icon = el("div", "set-intro-icon");
    const svg = button && button.querySelector("svg");
    if (svg) icon.append(svg.cloneNode(true));

    const text = el("div", "set-intro-text");
    text.append(el("div", "set-intro-title", t("settab." + name)),
        el("div", "set-intro-desc", t("settab.desc." + name)));

    box.append(icon, text);
}


// Las tarjetas se rehacen al cargar: se vuelve a aplicar la pestana
function applySettingsTab() {
    document.querySelectorAll("#tab-settings .card[data-settab]").forEach(function(card) {
        card.classList.toggle("adm-off", card.dataset.settab !== settingsTab);
    });

    // El aviso de "servidor apagado" es de las reglas del juego
    const note = $("settingsNote");
    if (note) note.classList.toggle("adm-off", settingsTab !== "game" && settingsTab !== "players");
}
