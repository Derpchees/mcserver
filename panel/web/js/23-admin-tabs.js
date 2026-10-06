// ============================================================
// Administracion: pestanas
// ============================================================
//
// Cada tarjeta de la vista lleva data-admtab con su pestana. La pestana va
// en la direccion (#/admin/users) para poder abrirla directo.

const ADMIN_TABS = ["general", "users", "storage", "https", "updates"];

// En Windows no hay discos que administrar ni HTTPS (por ahora)
const LINUX_ONLY_TABS = ["storage", "https"];


function isWindowsHost() {
    return !!authState && authState.platform === "windows";
}


function adminTabs() {
    return ADMIN_TABS.filter(function(name) {
        return !isWindowsHost() || LINUX_ONLY_TABS.indexOf(name) < 0;
    });
}


function adminTabFromHash() {
    const name = location.hash.replace(/^#\/?/, "").split("/")[1];
    return adminTabs().indexOf(name) >= 0 ? name : "general";
}


function showAdminTab(name) {

    if (adminTabs().indexOf(name) < 0) name = "general";

    document.querySelectorAll("#adminTabs .tab-btn").forEach(function(btn) {
        btn.classList.toggle("active", btn.dataset.admtab === name);
        btn.hidden = adminTabs().indexOf(btn.dataset.admtab) < 0;
    });

    // Con una clase (no con hidden): la zona de peligro usa hidden para el dueno
    document.querySelectorAll("#view-admin .card[data-admtab]").forEach(function(card) {
        card.classList.toggle("adm-off", card.dataset.admtab !== name);
    });

    try {
        history.replaceState(null, "", "#/admin" + (name === "general" ? "" : "/" + name));
    } catch (error) {
    }
}
