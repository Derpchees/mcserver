// ============================================================
// Aplicacion: cuentas, servidores, vistas y enrutador
// ============================================================

let authState = null;
let currentServer = null;
let currentServerInfo = null;
let canManageCurrent = false;
let currentView = "home";

// Rutas que dependen del servidor abierto: se les antepone /s/<id>
const SERVER_SCOPED = /^\/(api|stats|console|chat|files\/|backups|settings|players|mods\b|addons\b|command|action\/|server\/)/;

// Rutas que cualquiera puede consultar sin ser dueno
const SERVER_PUBLIC = /^\/(api|stats|action\/start|console|chat)/;


function scoped(url) {
    if (typeof url !== "string" || !SERVER_SCOPED.test(url)) return url;
    return "/s/" + currentServer + url;
}


function blockedRequest(url) {
    if (typeof url !== "string" || !SERVER_SCOPED.test(url)) return false;
    if (!currentServer) return true;
    return !canManageCurrent && !SERVER_PUBLIC.test(url);
}


(function() {
    const nativeFetch = window.fetch.bind(window);

    window.fetch = function(url, options) {
        // Sin servidor abierto o sin permiso no se pregunta: evita errores 401 en bucle
        if (blockedRequest(url)) {
            return Promise.reject(new Error("blocked"));
        }

        return nativeFetch(scoped(url), options);
    };

    const nativeOpen = XMLHttpRequest.prototype.open;

    XMLHttpRequest.prototype.open = function(method, url) {
        const args = Array.prototype.slice.call(arguments);
        args[1] = scoped(url);
        return nativeOpen.apply(this, args);
    };
})();


function isAdmin() {
    return !!(authState && authState.user && authState.user.role === "admin");
}


function loggedIn() {
    return !!(authState && authState.user);
}


async function refreshAuth() {
    try {
        const response = await fetch("/auth/state?t=" + Date.now());
        authState = await response.json();
    } catch (error) {
        authState = authState || { user: null, setup: false, signup: false, limits: {}, types: [], my_servers: [] };
    }

    renderAccountArea();
    renderStorageBanner();
    renderAlertsButton();
    return authState;
}
