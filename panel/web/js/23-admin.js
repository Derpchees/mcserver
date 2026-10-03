// ============================================================
// Administracion
// ============================================================

async function loadAdmin() {

    try {
        const [users, settings] = await Promise.all([
            fetch("/admin/users?t=" + Date.now()).then(function(r) { return r.json(); }),
            fetch("/admin/settings?t=" + Date.now()).then(function(r) { return r.json(); })
        ]);

        renderAdminSettings(settings);
        renderAdminUsers(users.users || []);
    } catch (error) {
        showToast(t("login.noConnection"), "red");
    }
}


function renderAdminSettings(settings) {

    $("admSignup").checked = settings.signup === "yes";
    $("admPublic").checked = settings.public_access !== "no";
    $("admCf").value = "";
    $("admCf").placeholder = settings.cf_api_key_set ? t("adm.cfKeep") : t("adm.cfPh");
    $("admCfState").textContent = settings.cf_api_key_set ? t("adm.cfSet") : t("adm.cfMissing");
    $("admDanger").hidden = !(authState.user && authState.user.owner);
    $("admRam").value = settings.max_ram_gb;
    $("admRam").max = settings.limits.system_ram_gb;
    $("admRamHint").textContent = t("adm.ramHint", { total: settings.limits.system_ram_gb });
    $("admCpu").value = settings.max_cpu;
    $("admCpu").max = settings.limits.cores;
    $("admCpuHint").textContent = t("adm.cpuHint", { cores: settings.limits.cores });
    $("admServers").value = settings.max_servers_per_user;
    $("admHost").value = settings.public_host || "";

    const select = $("admDefault");
    select.textContent = "";
    const none = el("option", "", t("adm.defaultNone"));
    none.value = "";
    select.append(none);

    fetch("/servers?t=" + Date.now()).then(function(r) { return r.json(); }).then(function(data) {
        (data.servers || []).forEach(function(server) {
            const option = el("option", "", server.name + (server.owner ? " (" + server.owner + ")" : ""));
            option.value = String(server.id);
            select.append(option);
        });
        select.value = settings.default_server || "";
    }).catch(function() {});
}


async function saveAdminSettings() {
    const settingsBody = {};
    if ($("admCf").value.trim()) settingsBody.cf_api_key = $("admCf").value.trim();

    try {
        await postJson("/admin/settings", Object.assign(settingsBody, {
            signup: $("admSignup").checked,
            max_ram_gb: Number($("admRam").value),
            max_cpu: Number($("admCpu").value),
            max_servers_per_user: Number($("admServers").value),
            public_host: $("admHost").value.trim(),
            public_access: $("admPublic").checked,
            default_server: $("admDefault").value
        }));
        showToast(t("set.saved"), "green");
        await refreshAuth();
    } catch (error) {
        showToast(error.message, "red");
    }
}


function renderAdminUsers(users) {

    const list = $("admUsers");
    list.textContent = "";

    users.forEach(function(user) {

        const row = el("div", "adm-row");
        const who = el("div", "adm-user");
        who.append(el("span", "account-avatar", user.username.charAt(0).toUpperCase()));

        const text = el("div");
        const name = el("div", "adm-name", user.username);
        if (user.owner) name.append(el("span", "tag amber", t("role.owner")));
        else if (user.role === "admin") name.append(el("span", "tag amber", t("role.admin")));
        text.append(name, el("div", "pl-sub",
            (user.servers.length ? user.servers.map(function(s) { return s.name; }).join(", ") : t("adm.noServer"))
            + " · " + new Date(user.created * 1000).toLocaleDateString(locale())));
        who.append(text);

        const actions = el("div", "pl-actions");
        const self = authState.user && authState.user.id === user.id;

        if (!self && !user.owner && authState.user.owner) {
            const role = el("button", "btn btn-ghost btn-small",
                user.role === "admin" ? t("adm.makeUser") : t("adm.makeAdmin"));
            role.onclick = async function() {
                try {
                    await postJson("/admin/users/update", { id: user.id, role: user.role === "admin" ? "user" : "admin" });
                    loadAdmin();
                } catch (error) { showToast(error.message, "red"); }
            };
            actions.append(role);
        }

        const reset = el("button", "btn btn-ghost btn-small", t("adm.resetPw"));
        reset.onclick = async function() {
            const pw = await askText(t("adm.resetPw") + ": " + user.username, t("acc.newPw"), "", t("set.save"));
            if (!pw) return;
            try {
                await postJson("/admin/users/update", { id: user.id, password: pw });
                showToast(t("acc.pwSaved"), "green");
            } catch (error) { showToast(error.message, "red"); }
        };
        if (!user.owner || self) actions.append(reset);

        if (!self && !user.owner) {
            const del = el("button", "btn btn-stop btn-small", t("fm.delete"));
            del.onclick = async function() {
                const result = await doubleConfirm({
                    title: t("adm.deleteTitle"),
                    description: t("adm.deleteDesc", { name: user.username }),
                    choices: [["purge_data", t("un.purgeData")], ["purge_backups", t("un.purgeBackups")]],
                    word: user.username,
                    okText: t("acc.deleteBtn")
                });
                if (!result) return;
                try {
                    await postJson("/admin/users/delete", Object.assign({ id: user.id }, result));
                    showToast(t("adm.deleted"), "green");
                    loadAdmin();
                } catch (error) { showToast(error.message, "red"); }
            };
            actions.append(del);
        }

        row.append(who, actions);
        list.append(row);
    });
}


async function uninstallSystem() {

    const result = await doubleConfirm({
        title: t("un.label"),
        description: t("un.modalDesc"),
        choices: [["purge_data", t("un.purgeAllData")], ["purge_backups", t("un.purgeAllBackups")]],
        word: authState.system_name,
        okText: t("un.button")
    });

    if (!result) return;

    try {
        await postJson("/admin/uninstall", result);
        document.body.innerHTML = "";
        const done = el("div", "un-done");
        done.append(el("h2", "", t("un.doneTitle")), el("p", "", t("un.doneDesc")));
        document.body.append(done);
    } catch (error) {
        showToast(error.message, "red");
    }
}
