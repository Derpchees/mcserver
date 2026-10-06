// ============================================================
// Archivos: menu contextual
// ============================================================
//
// Clic derecho (o mantener presionado en el celular) sobre un archivo o
// carpeta: acciones de la seleccion. Sobre el espacio vacio: crear,
// subir, mover aqui, seleccionar todo, vista y orden.

function fileEntry(name) {
    return fmEntries.find(function(e) { return e.name === name; });
}


function fileMenuItems() {

    const names = Array.from(fmSelected);
    const single = names.length === 1 ? fileEntry(names[0]) : null;
    const full = single ? joinPath(currentPath, single.name) : "";
    const items = [];

    if (single && single.dir) {
        items.push({ label: t("fm.open"), icon: "open", action: function() { loadFolder(full); } });
    } else if (single && isText(single.name)) {
        items.push({ label: t("fm.edit"), icon: "edit", action: function() { editFile(full); } });
    }

    const zip = names.length > 1 || (single && single.dir);
    items.push({ label: zip ? t("fm.downloadZip") : t("fm.download"), icon: "download", action: bulkDownload });
    items.push("-");

    if (single) {
        items.push({ label: t("fm.rename"), icon: "rename", hint: "F2", action: bulkRename });
    }

    items.push({ label: t("fm.move"), icon: "move", action: bulkMove });

    if (single) {
        items.push({ label: t("fm.copyPath"), icon: "link", action: function() { copyText(full); } });
    }

    items.push("-");
    items.push({
        label: names.length > 1 ? t("fm.deleteN", { n: names.length }) : t("fm.delete"),
        icon: "trash", hint: t("fm.keyDelete"), danger: true, action: bulkDelete
    });

    return items;
}


function folderMenuItems() {

    const items = [
        { label: t("fm.newFolder"), icon: "folderNew", action: newFolder },
        { label: t("fm.upload"), icon: "upload", action: function() { $("uploadInput").click(); } }
    ];

    if (fmClipboard) {
        items.push({ label: tn("fm.moveHereN", fmClipboard.paths.length), icon: "paste", action: moveHere });
    }

    items.push("-");
    items.push({ label: t("fm.selectAll"), icon: "selectAll", hint: "Ctrl+A", action: function() { toggleAll(true); } });
    items.push({
        label: fmView === "grid" ? t("fm.viewList") : t("fm.viewGrid"),
        icon: fmView === "grid" ? "list" : "grid",
        action: function() { setFileView(fmView === "grid" ? "list" : "grid"); }
    });
    items.push({ label: t("fm.refresh"), icon: "refresh", action: function() { loadFolder(currentPath); } });

    return items;
}


(function() {

    $("fmArea").addEventListener("contextmenu", function(event) {

        const item = event.target.closest("[data-name]");

        // La fila de titulos (vista de lista) no lleva menu
        if (event.target.closest("#fmHead")) return;

        event.preventDefault();

        if (item) {
            // Clic derecho fuera de la seleccion: pasa a ser solo ese
            if (!fmSelected.has(item.dataset.name)) {
                fmSelected.clear();
                fmSelected.add(item.dataset.name);
                fmLastClicked = item.dataset.name;
                renderSelection();
            }

            openContextMenu(event.clientX, event.clientY, fileMenuItems());
        } else {
            openContextMenu(event.clientX, event.clientY, folderMenuItems());
        }
    });
})();
