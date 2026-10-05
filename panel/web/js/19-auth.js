// ============================================================
// Entrar, registrarse y configuracion inicial
// ============================================================

function renderAuth(mode) {

    const card = $("authCard");
    card.textContent = "";

    const icon = el("div", "login-icon");
    icon.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="4" y="11" width="16" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/></svg>';

    card.append(icon, el("h3", "", t("auth." + mode + "Title")), el("p", "hint", t("auth." + mode + "Desc")));

    const form = el("form", "auth-form");
    const error = el("div", "login-error");

    const input = function(id, type, placeholder, autocomplete) {
        const node = el("input", "input");
        node.id = id;
        node.type = type;
        node.placeholder = placeholder;
        node.autocomplete = autocomplete;
        form.append(node);
        return node;
    };

    const user = input("authUser", "text", t("auth.username"), "username");
    const pass = input("authPass", "password", t("auth.password"), mode === "login" ? "current-password" : "new-password");
    let pass2 = null;

    if (mode !== "login") {
        pass2 = input("authPass2", "password", t("auth.password2"), "new-password");
        form.append(el("div", "field-hint", t("auth.userHint")));
    }

    let withServer = null;
    let publicBox = null;

    if (mode === "signup") {
        form.append(el("div", "form-section", t("form.yourServer")));
        form.append(serverFields("authSrv"));
    }

    if (mode === "setup") {
        const pub = el("label", "un-check");
        publicBox = el("input");
        publicBox.type = "checkbox";
        publicBox.checked = true;
        pub.append(publicBox, document.createTextNode(" " + t("auth.setupPublic")));
        form.append(el("div", "form-section", t("auth.setupAccess")), pub,
                    el("div", "field-hint", t("auth.setupPublicHint")),
                    el("div", "form-section", t("form.yourServer")));

        const label = el("label", "un-check");
        withServer = el("input");
        withServer.type = "checkbox";
        withServer.checked = true;
        label.append(withServer, document.createTextNode(" " + t("auth.setupServer")));
        form.append(label);

        const fields = serverFields("authSrv");
        form.append(fields);
        withServer.onchange = function() { fields.hidden = !withServer.checked; };
    }

    // Con la casilla, la sesion dura 30 dias (y se renueva al usarla);
    // sin ella, hasta cerrar el navegador
    const rememberWrap = el("label", "un-check auth-remember");
    const remember = el("input");
    remember.type = "checkbox";
    remember.checked = mode !== "login";
    rememberWrap.append(remember, document.createTextNode(" " + t("auth.remember")));
    form.append(rememberWrap);

    const submit = el("button", "btn btn-start", t("auth." + mode + "Btn"));
    submit.type = "submit";
    submit.style.width = "100%";
    submit.style.justifyContent = "center";
    form.append(submit, error);

    form.onsubmit = async function(event) {

        event.preventDefault();
        error.textContent = "";

        if (pass2 && pass.value !== pass2.value) {
            error.textContent = t("auth.mismatch");
            return;
        }

        const body = { username: user.value.trim(), password: pass.value, remember: remember.checked };

        if (mode === "setup") body.public_access = publicBox.checked;

        if (mode === "signup" || (mode === "setup" && withServer.checked)) {
            body.server = readServerFields("authSrv");
        }

        submit.disabled = true;

        try {
            await postJson(mode === "login" ? "/auth/login" : mode === "signup" ? "/auth/signup" : "/auth/setup", body);
            await refreshAuth();
            startNotifications();

            if (authState.my_servers.length && mode !== "login") {
                go("#/s/" + authState.my_servers[0]);
            } else {
                go("#/");
            }
        } catch (err) {
            error.textContent = err.message;
            submit.disabled = false;
        }
    };

    card.append(form);

    if (mode === "login" && authState && authState.signup) {
        const link = el("button", "link-btn", t("auth.noAccount"));
        link.onclick = function() { go("#/signup"); };
        card.append(link);
    }

    if (mode === "signup") {
        const link = el("button", "link-btn", t("auth.haveAccount"));
        link.onclick = function() { go("#/login"); };
        card.append(link);
    }

    setTimeout(function() { user.focus(); }, 30);
}
