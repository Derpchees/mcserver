// ============================================================
// Nombre del servidor (encabezado, junto al icono y el mensaje)
// ============================================================
//
// Es el nombre en este panel: lista de servidores, encabezado de la pestana
// y notificaciones. No cambia nada en el juego: en Minecraft cada jugador ve
// el nombre que el mismo le puso al agregar el servidor; lo que el servidor
// controla ahi es el mensaje (MOTD) y el icono. Cambiarlo no reinicia nada.


// Dentro de un servidor el encabezado muestra su nombre; fuera, el del sistema
function renderServerTitle() {
    const info = currentServerInfo;
    const inServer = info && currentView === "server";
    $("brandTitle").textContent = inServer ? info.name : (authState ? authState.system_name : $("brandTitle").textContent);
    $("nameEdit").hidden = !(inServer && canManageCurrent);
    $("iconEdit").hidden = !(inServer && canManageCurrent);
}


async function renameServer() {

    const info = currentServerInfo;
    if (!info) return;

    const input = el("input", "input");
    input.maxLength = 40;
    input.value = info.name;
    input.onkeydown = function(event) {
        if (event.key === "Enter") $("modalOk").click();
    };

    const name = await openModal({
        title: t("srv.renameTitle"),
        body: [input, el("div", "field-hint", t("srv.nameHint"))],
        okText: t("set.save"),
        onOk: function() {
            return input.value.trim() || false;
        }
    });

    if (!name || name === info.name) return;

    try {
        await postJson("/server/update", { name: name });
        showToast(t("srv.renamed"), "green");
        await update();
        renderServerTitle();
        loadServers();
        refreshAuth();
    } catch (error) {
        showToast(error.message, "red");
    }
}
