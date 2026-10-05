// ============================================================
// Cambiar el icono del servidor (encabezado)
// ============================================================
//
// Se elige uno de los bloques de Minecraft o uno al azar. El panel lo
// muestra al instante; en la lista de multijugador de Minecraft se ve
// cuando el servidor vuelve a arrancar (lee server-icon.png al iniciar).

async function editServerIcon() {

    const info = currentServerInfo;
    if (!info) return;

    const current = serverIconBlock(info.slug).name;
    let picked = null;

    const grid = el("div", "icon-grid");

    ICON_BLOCKS.forEach(function(block) {
        const btn = el("button", "icon-choice" + (block.name === current ? " current" : ""));
        btn.type = "button";
        btn.title = block.name;

        const img = el("img");
        img.src = blockIconUrl(block);
        img.alt = "";

        btn.append(img, el("span", "", block.name));
        btn.onclick = function() {
            grid.querySelectorAll(".icon-choice").forEach(function(b) { b.classList.remove("picked"); });
            btn.classList.add("picked");
            picked = block.name;
        };
        grid.append(btn);
    });

    const random = el("button", "btn btn-ghost btn-small", t("icon.random"));
    random.type = "button";
    random.onclick = function() {
        picked = "random";
        $("modalOk").click();
    };

    const actions = el("div", "sto-actions");
    actions.append(random);

    const choice = await openModal({
        title: t("icon.title"),
        wide: true,
        body: [el("div", "field-hint", t("icon.hint")), grid, actions],
        okText: t("set.save"),
        onOk: function() {
            return picked || false;
        }
    });

    if (!choice || choice === current) return;

    try {
        const data = await postJson("/server/icon", { block: choice });
        rememberServerIcon(info.slug, data.icon);
        setBrandIcon(info.slug);
        // Datos frescos: un refresco que ya estaba en camino traeria el icono anterior
        await update();
        showToast(t(data.running ? "icon.changedRunning" : "icon.changed", { name: data.icon }), "green");
        loadServers();
    } catch (error) {
        showToast(error.message, "red");
    }
}
