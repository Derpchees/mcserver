// ============================================================
// Encabezado: cuenta
// ============================================================

function renderAccountArea() {

    const box = $("accountArea");
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
    button.append(el("span", "account-avatar", user.username.charAt(0).toUpperCase()),
                  el("span", "", user.username));

    const menu = el("div", "account-dropdown");
    menu.hidden = true;

    const item = function(label, onClick) {
        const node = el("button", "account-item", label);
        node.onclick = function() { menu.hidden = true; onClick(); };
        menu.append(node);
    };

    if (authState.my_servers.length) {
        item(t("nav.myServer"), function() { go("#/s/" + authState.my_servers[0]); });
    }

    item(t("nav.account"), function() { go("#/account"); });

    if (isAdmin()) item(t("nav.admin"), function() { go("#/admin"); });

    item(t("auth.logout"), logout);

    button.onclick = function(event) {
        event.stopPropagation();
        menu.hidden = !menu.hidden;
    };

    document.addEventListener("click", function() { menu.hidden = true; });

    wrap.append(button, menu);
    box.append(wrap);
}


async function logout() {
    await fetch("/auth/logout", { method: "POST" }).catch(function() {});
    await refreshAuth();
    leaveServer();
    go("#/");
}
