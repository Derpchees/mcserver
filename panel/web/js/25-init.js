// ============================================================
// Arranque
// ============================================================

async function initApp() {
    await refreshAuth();

    // Solo al abrir el panel sin ruta: el boton Servidores (#/) sigue mostrando la lista
    // Primero el favorito de la persona (cuenta o navegador), luego el del admin
    const startServer = personalDefault() || authState.default_server;
    const canSee = loggedIn() || authState.public_access;

    if ((!location.hash || location.hash === "#") && startServer && canSee && !authState.setup) {
        history.replaceState(null, "", "#/s/" + startServer);
    }
    startNotifications();
    window.addEventListener("hashchange", route);
    await route();
    setInterval(loadServers, 5000);
}
