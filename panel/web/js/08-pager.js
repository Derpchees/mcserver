// ============================================================
// Paginacion (busquedas y listas largas)
// ============================================================
//
// renderPager(caja, pagina, paginas, alCambiar): botones Anterior y
// Siguiente con "Pagina X de Y". Se oculta si todo cabe en una pagina.
// pageSlice(lista, pagina, tamano) recorta una lista que ya se tiene.

function renderPager(box, page, pages, onPage) {

    box.textContent = "";
    box.hidden = pages <= 1;

    if (pages <= 1) return;

    const prev = el("button", "btn btn-ghost btn-small pager-btn", "‹ " + t("pager.prev"));
    prev.type = "button";
    prev.disabled = page <= 0;
    prev.onclick = function() { onPage(page - 1); };

    const next = el("button", "btn btn-ghost btn-small pager-btn", t("pager.next") + " ›");
    next.type = "button";
    next.disabled = page >= pages - 1;
    next.onclick = function() { onPage(page + 1); };

    box.append(prev, el("span", "pager-text", t("pager.page", { n: page + 1, total: pages })), next);
}


function pageSlice(items, page, size) {
    const pages = Math.max(1, Math.ceil(items.length / size));
    const current = Math.min(Math.max(0, page), pages - 1);
    return { items: items.slice(current * size, current * size + size), page: current, pages: pages };
}
