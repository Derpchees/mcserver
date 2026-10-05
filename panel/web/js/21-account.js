// ============================================================
// Cuenta
// ============================================================

function renderAccount() {

    const user = authState.user;
    $("accountName").textContent = user.username;
    $("accountRole").textContent = user.owner ? t("role.owner") : t("role." + user.role);
    $("pwCurrent").value = "";
    $("pwNew").value = "";
    $("pwNew2").value = "";
    loadSessions();
}


async function savePassword(event) {

    event.preventDefault();

    if ($("pwNew").value !== $("pwNew2").value) {
        showToast(t("auth.mismatch"), "red");
        return;
    }

    try {
        await postJson("/me/password", { current: $("pwCurrent").value, password: $("pwNew").value });
        showToast(t("acc.pwSaved"), "green");
        renderAccount();
    } catch (error) {
        showToast(error.message, "red");
    }
}


async function deleteMyAccount() {

    const result = await doubleConfirm({
        title: t("acc.deleteTitle"),
        description: t("acc.deleteDesc"),
        choices: [["purge_data", t("un.purgeData")], ["purge_backups", t("un.purgeBackups")]],
        word: authState.user.username,
        okText: t("acc.deleteBtn")
    });

    if (!result) return;

    try {
        await postJson("/me/delete", result);
        showToast(t("acc.deleted"), "green");
        await refreshAuth();
        go("#/");
    } catch (error) {
        showToast(error.message, "red");
    }
}
