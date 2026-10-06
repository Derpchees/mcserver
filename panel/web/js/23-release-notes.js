// ============================================================
// Notas de cada version (dentro del panel, sin ir a GitHub)
// ============================================================
//
// El panel trae las notas de lo instalado (panel/changelog.json) y lee las
// de la version nueva antes de actualizar. Al terminar una actualizacion
// se muestran solas una vez.

function noteEntry(entry) {

    const box = el("div", "note-entry");
    const head = el("div", "note-head");
    head.append(el("span", "note-version", "v" + entry.version));

    if (entry.date) {
        head.append(el("span", "note-date",
            new Date(entry.date + "T12:00:00").toLocaleDateString(locale(), { day: "numeric", month: "long", year: "numeric" })));
    }

    const list = el("ul", "note-list");

    (lang === "es" ? entry.es : entry.en).forEach(function(line) {
        list.append(el("li", "", line));
    });

    box.append(head, list);
    return box;
}


function notesBox(entries) {
    const box = el("div", "notes-box");
    entries.forEach(function(entry) { box.append(noteEntry(entry)); });
    return box;
}


function showReleaseNotes(entries, title) {

    if (!entries || !entries.length) return;

    openModal({
        title: title || t("notes.title"),
        body: [notesBox(entries)],
        okText: t("modal.ok"),
        hideCancel: true,
        cls: "notes-modal"
    });
}


// Antes de recargar tras actualizar se guarda la version de la que se venia
function rememberUpdateFrom(version) {
    try {
        localStorage.setItem("mc-updated-from", version);
    } catch (error) {
    }
}


async function afterUpdateNotes() {

    let from = null;

    try {
        from = localStorage.getItem("mc-updated-from");
        localStorage.removeItem("mc-updated-from");
    } catch (error) {
        return;
    }

    if (!from) return;

    // Espera a saber quien entro (solo los administradores ven Actualizaciones)
    for (let i = 0; i < 40 && !authState; i++) {
        await new Promise(function(resolve) { setTimeout(resolve, 250); });
    }

    if (!isAdmin()) return;

    try {
        const data = await api("/admin/update?t=" + Date.now());
        const fresh = (data.notes || []).filter(function(n) { return versionNewer(n.version, from); });

        showReleaseNotes(fresh, t("notes.updatedTitle", { v: data.installed }));
    } catch (error) {
    }
}


function versionNewer(a, b) {
    const x = String(a).split(".").map(Number);
    const y = String(b).split(".").map(Number);

    for (let i = 0; i < Math.max(x.length, y.length); i++) {
        if ((x[i] || 0) !== (y[i] || 0)) return (x[i] || 0) > (y[i] || 0);
    }

    return false;
}
