// ============================================================
// Encabezado: cuenta
// ============================================================

function renderAccountArea() {

    const box = $("accountArea");

    // Al cambiar el idioma desde el menu este se redibuja: sigue abierto
    const wasOpen = !!box.querySelector(".account-dropdown:not([hidden])");

    // Las preferencias vuelven al encabezado antes de rehacer el menu
    const prefs = PREFS_ELEMENT;
    $("livePill").before(prefs);
    prefs.classList.remove("in-menu");
    box.textContent = "";

    if (!loggedIn()) {
        const login = el("button", "btn btn-ghost btn-small", t("auth.login"));
        login.onclick = function() { go("#/login"); };
        box.append(login);

        // Dentro de un servidor el invitado solo ve el boton para entrar
        if (authState && authState.signup && currentView !== "server") {
            const signup = el("button", "btn btn-start btn-small", t("auth.signup"));
            signup.onclick = function() { go("#/signup"); };
            box.append(signup);
        }

        return;
    }

    const user = authState.user;
    const wrap = el("div", "account-menu");
    const button = el("button", "btn btn-ghost btn-small account-btn");
    button.setAttribute("aria-haspopup", "menu");
    button.setAttribute("aria-expanded", "false");
    button.append(el("span", "account-avatar", user.username.charAt(0).toUpperCase()),
                  el("span", "", user.username));
    button.insertAdjacentHTML("beforeend", ACCOUNT_ICONS.chev);

    const menu = el("div", "account-dropdown");
    menu.setAttribute("role", "menu");
    menu.hidden = true;

    // Encabezado: quien eres y tu papel
    const head = el("div", "account-head");
    const who = el("div");
    who.append(el("div", "account-head-name", user.username),
               el("div", "account-head-role", t(user.owner ? "role.owner" : isAdmin() ? "role.admin" : "role.user")));
    head.append(el("span", "account-avatar", user.username.charAt(0).toUpperCase()), who);
    menu.append(head);

    const item = function(icon, label, onClick, danger) {
        const node = el("button", "account-item" + (danger ? " is-danger" : ""));
        node.setAttribute("role", "menuitem");
        node.innerHTML = ACCOUNT_ICONS[icon];
        node.append(el("span", "", label));
        node.onclick = function() { closeAccountMenu(); onClick(); };
        menu.append(node);
    };

    // Mis servidores, cada uno con su icono
    const mine = authState.my_server_list || [];

    if (mine.length) {
        menu.append(el("div", "account-label", t(mine.length === 1 ? "nav.myServer" : "nav.myServers")));

        mine.forEach(function(server) {
            rememberServerIcon(server.slug, server.icon);
            const node = el("button", "account-item account-server");
            node.setAttribute("role", "menuitem");
            node.append(serverIconEl(server.slug, "account-srv-icon"), el("span", "", server.name));
            node.classList.toggle("is-current", currentView === "server" && currentServer === server.id);
            node.onclick = function() { closeAccountMenu(); go("#/s/" + server.id); };
            menu.append(node);
        });

        menu.append(el("div", "account-sep"));
    }

    item("user", t("nav.account"), function() { go("#/account"); });

    if (isAdmin()) item("admin", t("nav.admin"), function() { go("#/admin"); });

    // Idioma, tema y avisos (los mismos botones del encabezado)
    menu.append(el("div", "account-sep"));
    const prefsRow = el("div", "account-prefs");
    prefsRow.append(el("span", "account-label", t("acct.prefs")), prefs);
    prefs.classList.add("in-menu");
    // Cambiar una preferencia no cierra el menu
    prefsRow.onclick = function(event) { event.stopPropagation(); };
    menu.append(prefsRow);

    menu.append(el("div", "account-sep"));
    item("logout", t("auth.logout"), logout, true);

    button.onclick = function(event) {
        event.stopPropagation();
        const open = menu.hidden;
        closeAccountMenu();
        menu.hidden = !open;
        button.setAttribute("aria-expanded", open ? "true" : "false");
    };

    menu.hidden = !wasOpen;
    button.setAttribute("aria-expanded", wasOpen ? "true" : "false");

    wrap.append(button, menu);
    box.append(wrap);
}


// Se guarda al cargar: mientras el menu se rehace, el elemento sale del documento
const PREFS_ELEMENT = document.getElementById("prefsBox");


const ACCOUNT_ICONS = {
    chev: '<svg class="chev" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="m6 9 6 6 6-6"/></svg>',
    server: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="7" rx="2"/><rect x="3" y="13" width="18" height="7" rx="2"/><path d="M7 7.5h.01M7 16.5h.01"/></svg>',
    user: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/></svg>',
    admin: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3 4 6v6c0 5 3.5 8 8 9 4.5-1 8-4 8-9V6z"/><path d="m9 12 2 2 4-4"/></svg>',
    logout: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><path d="m16 17 5-5-5-5M21 12H9"/></svg>'
};


function closeAccountMenu() {
    document.querySelectorAll(".account-dropdown").forEach(function(menu) { menu.hidden = true; });
    document.querySelectorAll(".account-btn").forEach(function(btn) { btn.setAttribute("aria-expanded", "false"); });
}


// Un solo cierre para todo el documento (antes se agregaba uno cada vez que
// se redibujaba el encabezado)
document.addEventListener("click", closeAccountMenu);
document.addEventListener("keydown", function(event) {
    if (event.key === "Escape") closeAccountMenu();
});


async function logout() {
    // Este dispositivo deja de recibir los avisos de la cuenta
    await pushUnsubscribe();
    await fetch("/auth/logout", { method: "POST" }).catch(function() {});
    await refreshAuth();
    leaveServer();
    go("#/");
}
