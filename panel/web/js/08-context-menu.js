// ============================================================
// Menu contextual (clic derecho o mantener presionado)
// ============================================================
//
// openContextMenu(x, y, items): cada item es { label, icon, action,
// danger, disabled } o "-" para una linea. Se cierra al elegir, con Esc,
// al hacer clic fuera, al desplazar la pagina o al cambiar de tamano.

let contextMenuNode = null;


function closeContextMenu() {
    // Primero se suelta: quitarlo del documento puede volver a llamar aqui
    const node = contextMenuNode;
    contextMenuNode = null;
    if (node) node.remove();
}


function openContextMenu(x, y, items) {

    closeContextMenu();

    const menu = el("div", "ctx-menu");
    menu.setAttribute("role", "menu");

    items.forEach(function(item) {

        if (item === "-") {
            if (menu.lastChild && !menu.lastChild.classList.contains("ctx-sep")) menu.append(el("div", "ctx-sep"));
            return;
        }

        const btn = el("button", "ctx-item" + (item.danger ? " danger" : ""));
        btn.type = "button";
        btn.setAttribute("role", "menuitem");
        btn.disabled = !!item.disabled;

        const icon = el("span", "ctx-icon");
        if (item.icon && ICONS[item.icon]) icon.innerHTML = ICONS[item.icon];

        btn.append(icon, el("span", "ctx-label", item.label));
        if (item.hint) btn.append(el("span", "ctx-hint", item.hint));

        btn.onclick = function(event) {
            event.stopPropagation();
            closeContextMenu();
            item.action();
        };

        menu.append(btn);
    });

    if (menu.lastChild && menu.lastChild.classList.contains("ctx-sep")) menu.lastChild.remove();

    document.body.append(menu);
    contextMenuNode = menu;

    // Dentro de la ventana aunque se abra cerca del borde
    const box = menu.getBoundingClientRect();
    const left = Math.max(8, Math.min(x, window.innerWidth - box.width - 8));
    const top = Math.max(8, y + box.height > window.innerHeight - 8 ? y - box.height : y);

    menu.style.left = left + "px";
    menu.style.top = Math.min(top, window.innerHeight - box.height - 8) + "px";

    const first = menu.querySelector(".ctx-item:not(:disabled)");
    if (first) first.focus({ preventScroll: true });
}


(function() {
    document.addEventListener("mousedown", function(event) {
        if (contextMenuNode && !contextMenuNode.contains(event.target)) closeContextMenu();
    }, true);

    document.addEventListener("keydown", function(event) {
        if (!contextMenuNode) return;

        if (event.key === "Escape") {
            event.preventDefault();
            event.stopPropagation();
            closeContextMenu();
            return;
        }

        // Flechas para moverse por el menu
        if (event.key === "ArrowDown" || event.key === "ArrowUp") {
            event.preventDefault();
            const buttons = Array.from(contextMenuNode.querySelectorAll(".ctx-item:not(:disabled)"));
            const i = buttons.indexOf(document.activeElement);
            const next = buttons[(i + (event.key === "ArrowDown" ? 1 : -1) + buttons.length) % buttons.length];
            if (next) next.focus();
        }
    }, true);

    // Desplazar cualquier parte de la pagina, cambiar el tamano o salir de la ventana
    window.addEventListener("scroll", closeContextMenu, true);
    window.addEventListener("resize", closeContextMenu);
    window.addEventListener("blur", closeContextMenu);
})();
