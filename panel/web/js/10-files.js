// ============================================================
// Gestor de archivos
// ============================================================

const TEXT_EXT = [
    "txt", "properties", "json", "json5", "toml", "yml", "yaml", "cfg",
    "conf", "ini", "log", "md", "sh", "bat", "ps1", "mcmeta", "js",
    "snbt", "csv", "xml", "env", "list"
];


function isText(name) {
    const ext = name.toLowerCase().split(".").pop();
    return name.startsWith(".") && !name.slice(1).includes(".") || TEXT_EXT.includes(ext);
}


function joinPath(folder, name) {
    return folder ? folder + "/" + name : name;
}


function formatStamp(ts) {
    return new Date(ts * 1000).toLocaleString(locale(), {
        day: "2-digit",
        month: "short",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit"
    });
}


function renderBreadcrumb(path) {

    const box = $("breadcrumb");
    box.textContent = "";

    const parts = path ? path.split("/") : [];
    const crumbs = [["minecraft-server", ""]];

    parts.forEach(function(part, i) {
        crumbs.push([part, parts.slice(0, i + 1).join("/")]);
    });

    crumbs.forEach(function([label, target], i) {
        if (i) box.append(el("span", "sep", "/"));
        const link = el("a", "", label);
        link.onclick = function() { loadFolder(target); };
        makeDropTarget(link, target);
        box.append(link);
    });
}


let fmEntries = [];
let fmSelected = new Set();
let fmSort = { key: "name", dir: 1 };
let fmClipboard = null;
let fmLastClicked = null;

const DRAG_TYPE = "application/x-mc-paths";


function parentPath(path) {
    return path.split("/").slice(0, -1).join("/");
}


function goUp() {
    if (currentPath) loadFolder(parentPath(currentPath));
}


async function loadFolder(path) {

    try {

        const data = await api("/files/list?path=" + encodeURIComponent(path));

        if (data.path !== currentPath) {
            fmSelected.clear();
            fmLastClicked = null;
            $("fmFilter").value = "";
        }

        currentPath = data.path;
        fmEntries = data.entries;

        // Quita de la seleccion lo que ya no existe
        const names = new Set(fmEntries.map(function(e) { return e.name; }));
        fmSelected.forEach(function(name) {
            if (!names.has(name)) fmSelected.delete(name);
        });

        renderBreadcrumb(currentPath);
        renderFiles();

    } catch (error) {
        if (error.message !== "auth") {
            showToast(error.message, "red");
            if (path) loadFolder("");
        }
    }
}


function visibleEntries() {

    const filter = $("fmFilter").value.trim().toLowerCase();
    const key = fmSort.key;

    return fmEntries
        .filter(function(e) {
            return !filter || e.name.toLowerCase().includes(filter);
        })
        .sort(function(a, b) {
            // Las carpetas siempre van primero
            if (a.dir !== b.dir) return a.dir ? -1 : 1;

            const x = key === "name" ? a.name.toLowerCase() : a[key];
            const y = key === "name" ? b.name.toLowerCase() : b[key];

            if (x < y) return -fmSort.dir;
            if (x > y) return fmSort.dir;
            return a.name.toLowerCase() < b.name.toLowerCase() ? -1 : 1;
        });
}


function setSort(key) {
    fmSort = {
        key: key,
        dir: fmSort.key === key ? -fmSort.dir : 1
    };
    renderFiles();
}


function renderFiles() {

    const list = $("fileList");
    const entries = visibleEntries();

    list.textContent = "";

    $("fmUp").disabled = !currentPath;

    ["name", "size", "mtime"].forEach(function(key) {
        $("sort-" + key).textContent =
            fmSort.key === key ? (fmSort.dir === 1 ? " ↑" : " ↓") : "";
    });

    if (!entries.length) {
        list.append(el("div", "list-empty",
            fmEntries.length ? t("fm.noMatch") : t("fm.empty")));
    }

    entries.forEach(function(entry) {
        list.append(fileRow(entry));
    });

    renderSelection();
}


function renderSelection() {

    const count = fmSelected.size;
    const visible = visibleEntries();

    document.querySelectorAll("#fileList .row").forEach(function(row) {
        const on = fmSelected.has(row.dataset.name);
        row.classList.toggle("selected", on);
        const box = row.querySelector(".check");
        if (box) box.checked = on;
    });

    const all = $("fmAll");
    const selectedVisible = visible.filter(function(e) { return fmSelected.has(e.name); }).length;
    all.checked = visible.length > 0 && selectedVisible === visible.length;
    all.indeterminate = selectedVisible > 0 && selectedVisible < visible.length;

    $("fmSelection").hidden = count === 0 || !!fmClipboard;
    $("fmSelectionText").textContent = tn("fm.selected", count);
    $("fmRenameBtn").hidden = count !== 1;

    $("fmMove").hidden = !fmClipboard;

    if (fmClipboard) {
        $("fmMoveText").textContent = tn("fm.moving", fmClipboard.paths.length);
    }
}


function toggleSelect(name, on) {
    if (on === undefined ? !fmSelected.has(name) : on) fmSelected.add(name);
    else fmSelected.delete(name);
}


function toggleAll(on) {
    visibleEntries().forEach(function(e) { toggleSelect(e.name, on); });
    renderSelection();
}


function clearSelection() {
    fmSelected.clear();
    fmLastClicked = null;
    renderSelection();
}


function selectedPaths() {
    return Array.from(fmSelected).map(function(name) {
        return joinPath(currentPath, name);
    });
}


function openEntry(entry) {

    const full = joinPath(currentPath, entry.name);

    if (entry.dir) loadFolder(full);
    else if (isText(entry.name)) editFile(full);
    else downloadFile(full);
}


function fileRow(entry) {

    const full = joinPath(currentPath, entry.name);
    const row = el("div", "row");
    row.dataset.name = entry.name;
    row.draggable = true;

    const check = el("input", "check");
    check.type = "checkbox";
    check.onclick = function(event) { event.stopPropagation(); };
    check.onchange = function() {
        toggleSelect(entry.name, check.checked);
        fmLastClicked = entry.name;
        renderSelection();
    };

    const icon = el("span", "row-icon" + (entry.dir ? " folder" : ""));
    icon.innerHTML = entry.dir ? ICONS.folder
        : /\.(zip|jar|gz|tar|7z|rar)$/i.test(entry.name) ? ICONS.archive
        : isText(entry.name) ? ICONS.text
        : ICONS.file;

    const name = el("span", "row-name");
    const link = el("a", "", entry.name);
    link.title = entry.name;
    link.onclick = function(event) {
        event.stopPropagation();
        openEntry(entry);
    };
    name.append(link);

    const size = el("span", "row-meta row-size", entry.dir ? "" : formatBytes(entry.size));
    const date = el("span", "row-meta row-date", formatStamp(entry.mtime));

    const actions = el("span", "row-actions");

    if (!entry.dir && isText(entry.name)) {
        actions.append(iconButton("edit", t("fm.edit"), function() { editFile(full); }));
    }

    actions.append(iconButton("download", entry.dir ? t("fm.downloadZip") : t("fm.download"), function() {
        if (entry.dir) downloadZip([full]);
        else downloadFile(full);
    }));
    actions.append(iconButton("rename", t("fm.rename"), function() { renameItem(full, entry.name); }));
    actions.append(iconButton("trash", t("fm.delete"), function() { deleteItem(full, entry); }, true));

    row.append(check, icon, name, size, date, actions);

    // Clic en la fila: seleccionar. Con Shift selecciona el rango.
    row.onclick = function(event) {

        if (event.shiftKey && fmLastClicked) {
            const names = visibleEntries().map(function(e) { return e.name; });
            const a = names.indexOf(fmLastClicked);
            const b = names.indexOf(entry.name);

            if (a !== -1 && b !== -1) {
                names.slice(Math.min(a, b), Math.max(a, b) + 1).forEach(function(n) {
                    toggleSelect(n, true);
                });
            }
        } else {
            toggleSelect(entry.name);
            fmLastClicked = entry.name;
        }

        renderSelection();
    };

    row.ondblclick = function() {
        openEntry(entry);
    };

    // Arrastrar filas para moverlas a otra carpeta
    row.addEventListener("dragstart", function(event) {

        if (!fmSelected.has(entry.name)) {
            fmSelected.clear();
            fmSelected.add(entry.name);
            renderSelection();
        }

        event.dataTransfer.setData(DRAG_TYPE, JSON.stringify(selectedPaths()));
        event.dataTransfer.effectAllowed = "move";
    });

    if (entry.dir) {
        makeDropTarget(row, full);
    }

    return row;
}


function isInternalDrag(event) {
    return Array.from(event.dataTransfer.types || []).includes(DRAG_TYPE);
}


function hasFiles(event) {
    return Array.from(event.dataTransfer.types || []).includes("Files");
}


// Una carpeta (fila o miga de pan) acepta filas arrastradas (mover)
// y archivos del equipo (subir a esa carpeta)
function makeDropTarget(node, folder) {

    node.addEventListener("dragover", function(event) {
        if (isInternalDrag(event) || hasFiles(event)) {
            event.preventDefault();
            event.stopPropagation();
            node.classList.add("drop-target");
            $("fmOverlayText").textContent =
                t("fm.dropOverlay", { folder: folder || "minecraft-server" });
        }
    });

    node.addEventListener("dragleave", function() {
        node.classList.remove("drop-target");
    });

    node.addEventListener("drop", function(event) {

        node.classList.remove("drop-target");

        if (isInternalDrag(event)) {
            event.preventDefault();
            event.stopPropagation();

            let paths = [];
            try { paths = JSON.parse(event.dataTransfer.getData(DRAG_TYPE)); } catch (error) {}

            movePaths(paths, folder);

        } else if (hasFiles(event)) {
            event.preventDefault();
            event.stopPropagation();
            endExternalDrag();
            uploadDropped(event.dataTransfer, folder);
        }
    });
}


async function movePaths(paths, dest) {

    if (!paths.length) return;

    try {
        const data = await api("/files/move", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ paths: paths, dest: dest })
        });

        showToast(tn("fm.moved", data.count), "green");
        fmSelected.clear();
        fmClipboard = null;
        loadFolder(currentPath);

    } catch (error) {
        if (error.message !== "auth") showToast(error.message, "red");
    }
}


function bulkMove() {
    if (!fmSelected.size) return;
    fmClipboard = { paths: selectedPaths() };
    fmSelected.clear();
    renderSelection();
}


function moveHere() {
    if (fmClipboard) movePaths(fmClipboard.paths, currentPath);
}


function cancelMove() {
    fmClipboard = null;
    renderSelection();
}


function bulkRename() {
    if (fmSelected.size !== 1) return;
    const name = Array.from(fmSelected)[0];
    renameItem(joinPath(currentPath, name), name);
}


function bulkDownload() {

    const names = Array.from(fmSelected);
    if (!names.length) return;

    const entry = fmEntries.find(function(e) { return e.name === names[0]; });

    if (names.length === 1 && entry && !entry.dir) {
        downloadFile(joinPath(currentPath, names[0]));
    } else {
        downloadZip(selectedPaths());
    }
}


function downloadZip(paths) {
    showToast(t("fm.preparingZip"), "amber");
    const link = document.createElement("a");
    link.href = scoped("/files/zip?paths=" + encodeURIComponent(JSON.stringify(paths)));
    link.download = "";
    document.body.append(link);
    link.click();
    link.remove();
}


async function bulkDelete() {

    const paths = selectedPaths();
    if (!paths.length) return;

    if (paths.length === 1) {
        const name = Array.from(fmSelected)[0];
        const entry = fmEntries.find(function(e) { return e.name === name; });
        if (entry) deleteItem(paths[0], entry);
        return;
    }

    const ok = await confirmDialog(t("modal.delete"), t("fm.deleteMany", { n: paths.length }));
    if (!ok) return;

    try {
        const data = await api("/files/delete-many", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ paths: paths })
        });

        showToast(t("fm.deletedMany", { n: data.count }), "green");
        fmSelected.clear();
        loadFolder(currentPath);

    } catch (error) {
        if (error.message !== "auth") showToast(error.message, "red");
    }
}


// Atajos: Supr borra la seleccion, Esc la quita, Ctrl+A selecciona todo
document.addEventListener("keydown", function(event) {

    if ($("tab-files").hidden || !filesReady || !$("modal").hidden) return;
    if (/^(INPUT|TEXTAREA)$/.test(event.target.tagName)) return;

    if (event.key === "Delete" && fmSelected.size) {
        event.preventDefault();
        bulkDelete();
    } else if (event.key === "F2" && fmSelected.size === 1) {
        event.preventDefault();
        bulkRename();
    } else if (event.key === "Escape") {
        if (fmClipboard) cancelMove();
        else clearSelection();
    } else if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "a") {
        event.preventDefault();
        toggleAll(true);
    }
});


function downloadFile(path) {
    const link = document.createElement("a");
    link.href = scoped("/files/download?path=" + encodeURIComponent(path));
    link.download = "";
    document.body.append(link);
    link.click();
    link.remove();
}


async function editFile(path) {

    let data;

    try {
        data = await api("/files/read?path=" + encodeURIComponent(path));
    } catch (error) {
        if (error.message !== "auth") showToast(error.message, "red");
        return;
    }

    const editor = el("textarea", "editor");
    editor.value = data.content;
    editor.spellcheck = false;

    editor.addEventListener("keydown", function(event) {

        if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "s") {
            event.preventDefault();
            $("modalOk").click();
        }

        if (event.key === "Tab") {
            event.preventDefault();
            const start = editor.selectionStart;
            editor.setRangeText("    ", start, editor.selectionEnd, "end");
        }
    });

    const original = data.content;

    await openModal({
        title: path,
        body: [editor],
        wide: true,
        okText: t("fm.save"),
        hint: t("fm.editorHint"),
        onOk: function() {
            if (editor.value === original) return true;
            saveFile(path, editor.value);
            return true;
        }
    });
}


async function saveFile(path, content) {

    try {
        await api("/files/write?path=" + encodeURIComponent(path), {
            method: "POST",
            headers: { "Content-Type": "text/plain; charset=utf-8" },
            body: content
        });

        showToast(t("fm.saved"), "green");
        loadFolder(currentPath);

    } catch (error) {
        if (error.message !== "auth") showToast(error.message, "red");
    }
}


async function newFolder() {

    const name = await askText(t("fm.newFolder"), t("fm.folderName"), "", t("fm.create"));
    if (!name) return;

    try {
        await api(
            "/files/mkdir?path=" + encodeURIComponent(currentPath)
            + "&name=" + encodeURIComponent(name),
            { method: "POST" }
        );
        showToast(t("fm.created"), "green");
        loadFolder(currentPath);
    } catch (error) {
        if (error.message !== "auth") showToast(error.message, "red");
    }
}


async function renameItem(path, current) {

    const name = await askText(t("fm.rename"), t("fm.newName"), current, t("fm.rename"));
    if (!name || name === current) return;

    try {
        await api(
            "/files/rename?path=" + encodeURIComponent(path)
            + "&name=" + encodeURIComponent(name),
            { method: "POST" }
        );
        showToast(t("fm.renamed"), "green");
        loadFolder(currentPath);
    } catch (error) {
        if (error.message !== "auth") showToast(error.message, "red");
    }
}


async function deleteItem(path, entry) {

    const message = entry.dir
        ? t("fm.deleteFolder", { name: entry.name })
        : t("fm.deleteFile", { name: entry.name });

    const ok = await confirmDialog(t("modal.delete"), message);
    if (!ok) return;

    try {
        await api("/files/delete?path=" + encodeURIComponent(path), { method: "POST" });
        showToast(t("fm.deleted"), "green");
        loadFolder(currentPath);
    } catch (error) {
        if (error.message !== "auth") showToast(error.message, "red");
    }
}


// Cola de subidas: como mucho 3 a la vez
const uploadQueue = [];
let uploadsActive = 0;
let uploadsDone = 0;
let uploadsFailed = 0;


function uploadFiles(files, folder) {

    const target = folder === undefined ? currentPath : folder;

    Array.from(files).forEach(function(file) {
        uploadQueue.push({ file: file, folder: target });
    });

    pumpUploads();
}


function pumpUploads() {

    while (uploadsActive < 3 && uploadQueue.length) {
        const job = uploadQueue.shift();
        uploadsActive++;
        uploadOne(job.file, job.folder, function(ok) {
            uploadsActive--;
            if (ok) uploadsDone++;
            else uploadsFailed++;
            pumpUploads();
        });
    }

    // Al terminar toda la tanda se avisa una sola vez
    if (!uploadsActive && !uploadQueue.length && (uploadsDone || uploadsFailed)) {

        if (uploadsDone) {
            showToast(tn("fm.uploadedCount", uploadsDone), uploadsFailed ? "amber" : "green");
        }

        uploadsDone = 0;
        uploadsFailed = 0;

        if (filesReady) loadFolder(currentPath);
    }
}


function uploadOne(file, folder, done) {

    const item = el("div", "upload");
    const label = el("div", "", t("fm.uploading", { name: file.name }));
    const meter = el("div", "meter");
    const bar = el("span");
    bar.style.width = "0%";
    bar.style.background = "var(--blue)";
    meter.append(bar);
    item.append(label, meter);
    $("uploads").append(item);

    const xhr = new XMLHttpRequest();

    xhr.open(
        "POST",
        "/files/upload?path=" + encodeURIComponent(folder)
        + "&name=" + encodeURIComponent(file.name)
    );

    xhr.upload.onprogress = function(event) {
        if (event.lengthComputable) {
            const pct = event.loaded / event.total * 100;
            bar.style.width = pct + "%";
            label.textContent =
                t("fm.uploadProgress", { name: file.name, done: formatBytes(event.loaded), total: formatBytes(event.total) });
        }
    };

    xhr.onload = function() {

        item.remove();

        let data = {};
        try { data = JSON.parse(xhr.responseText); } catch (error) {}

        if (xhr.status === 401) {
            uploadQueue.length = 0;
            showLogin();
            done(false);
            return;
        }

        if (xhr.status === 200 && data.ok) {
            done(true);
        } else {
            showToast(file.name + ": " + (serverText(data.message) || t("fm.uploadError", { name: file.name })), "red");
            done(false);
        }
    };

    xhr.onerror = function() {
        item.remove();
        showToast(t("fm.uploadError", { name: file.name }), "red");
        done(false);
    };

    xhr.send(file);
}


// Recorre una carpeta soltada y devuelve sus archivos con su subcarpeta
function readEntry(entry, folder) {

    return new Promise(function(resolve) {

        if (entry.isFile) {
            entry.file(function(file) {
                resolve([{ file: file, folder: folder }]);
            }, function() {
                resolve([]);
            });
            return;
        }

        if (!entry.isDirectory) {
            resolve([]);
            return;
        }

        const reader = entry.createReader();
        const sub = joinPath(folder, entry.name);
        let all = [];

        // readEntries entrega los resultados por tandas
        (function next() {
            reader.readEntries(function(batch) {

                if (!batch.length) {
                    Promise.all(all.map(function(child) {
                        return readEntry(child, sub);
                    })).then(function(lists) {
                        resolve([].concat.apply([], lists));
                    });
                    return;
                }

                all = all.concat(Array.from(batch));
                next();

            }, function() {
                resolve([]);
            });
        })();
    });
}


async function uploadDropped(dataTransfer, folder) {

    const items = Array.from(dataTransfer.items || []);
    const entries = items
        .map(function(item) {
            return item.webkitGetAsEntry ? item.webkitGetAsEntry() : null;
        })
        .filter(Boolean);

    // Navegadores sin soporte de carpetas: solo archivos sueltos
    if (!entries.length) {
        uploadFiles(dataTransfer.files, folder);
        return;
    }

    const lists = await Promise.all(entries.map(function(entry) {
        return readEntry(entry, folder);
    }));

    [].concat.apply([], lists).forEach(function(job) {
        uploadQueue.push(job);
    });

    pumpUploads();
}


let fmDragDepth = 0;


function endExternalDrag() {
    fmDragDepth = 0;
    $("dropZone").classList.remove("dragging");
}


// Se puede soltar en cualquier parte de la pestana de Archivos: todo
// el explorador es la zona de subida. Soltar sobre una carpeta de la
// lista sube ahi (lo maneja makeDropTarget).
(function() {

    const zone = $("dropZone");

    function active(event) {
        return filesReady && !$("tab-files").hidden && $("modal").hidden
            && hasFiles(event) && !isInternalDrag(event);
    }

    document.addEventListener("dragenter", function(event) {
        if (!active(event)) return;
        event.preventDefault();
        fmDragDepth++;
        zone.classList.add("dragging");
    });

    document.addEventListener("dragleave", function(event) {
        if (!active(event)) return;
        fmDragDepth = Math.max(0, fmDragDepth - 1);
        if (!fmDragDepth) zone.classList.remove("dragging");
    });

    document.addEventListener("dragover", function(event) {
        if (!active(event)) return;
        event.preventDefault();
        event.dataTransfer.dropEffect = "copy";
        $("fmOverlayText").textContent =
            t("fm.dropOverlay", { folder: currentPath || "minecraft-server" });
    });

    document.addEventListener("drop", function(event) {

        const ok = active(event);
        endExternalDrag();

        if (!ok) return;

        event.preventDefault();
        uploadDropped(event.dataTransfer, currentPath);
    });

    // Fuera de la pestana de Archivos el navegador no debe abrir el archivo
    ["dragover", "drop"].forEach(function(type) {
        window.addEventListener(type, function(event) {
            if (hasFiles(event)) event.preventDefault();
        });
    });
})();
