// ============================================================
// Respaldos
// ============================================================

let backupWasRunning = false;


async function loadBackups() {

    if (!filesReady || $("tab-files").hidden) return;

    try {

        const data = await api("/backups?t=" + Date.now());

        const btn = $("backupBtn");
        btn.disabled = data.running;
        btn.innerHTML = data.running
            ? '<span class="spinner"></span> ' + t("bk.running")
            : '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" style="width:13px;height:13px"><path d="M12 5v14M5 12h14"/></svg> ' + t("bk.now");

        if (backupWasRunning && !data.running) {
            const failed = /ERROR|cancelado/i.test(data.last_log);
            showToast(failed ? t("bk.failed") : t("bk.done"), failed ? "red" : "green");
        }

        backupWasRunning = data.running;

        const info = $("backupInfo");
        info.textContent = "";

        const next = el("span");
        next.append(t("bk.nextAuto"));
        next.append(el("b", "", data.next_auto ? formatStamp(data.next_auto) : t("bk.notScheduled")));

        const keep = el("span", "", t("bk.keep"));

        info.append(next, keep);

        const list = $("backups");
        list.textContent = "";

        if (!data.backups.length) {
            list.append(el("div", "list-empty", data.running ? t("bk.creatingFirst") : t("bk.none")));
            return;
        }

        data.backups.forEach(function(backup) {

            const row = el("div", "row backup-row");

            const icon = el("span", "row-icon");
            icon.innerHTML = ICONS.archive;

            const name = el("span", "row-name");
            const tag = el("span", "tag " + (backup.type === "auto" ? "blue" : "green"),
                backup.type === "auto" ? t("bk.auto") : t("bk.manual"));
            tag.style.marginRight = "10px";
            name.append(tag, document.createTextNode(formatStamp(backup.mtime)));
            name.title = backup.name;

            const actions = el("span", "row-actions");
            actions.append(
                iconButton("download", t("fm.download"), function() {
                    const link = document.createElement("a");
                    link.href = scoped("/backups/download?name=" + encodeURIComponent(backup.name));
                    link.download = backup.name;
                    document.body.append(link);
                    link.click();
                    link.remove();
                }),
                iconButton("trash", t("fm.delete"), function() { deleteBackup(backup); }, true)
            );

            row.append(
                icon,
                name,
                el("span", "row-meta row-size", formatBytes(backup.size, 1)),
                el("span", "row-meta row-date", backup.name.replace(/\.tar\.gz$/, "")),
                actions
            );

            list.append(row);
        });

    } catch (error) {
        if (error.message !== "auth") showToast(error.message, "red");
    }
}


async function createBackup() {

    try {
        await api("/backups/create", { method: "POST" });
        backupWasRunning = true;
        showToast(t("bk.started"), "amber");
        setTimeout(loadBackups, 800);
    } catch (error) {
        if (error.message !== "auth") showToast(error.message, "red");
    }
}


async function deleteBackup(backup) {

    const ok = await confirmDialog(
        t("bk.deleteTitle"),
        t("bk.deleteBody", { d: formatStamp(backup.mtime), s: formatBytes(backup.size, 1) })
    );

    if (!ok) return;

    try {
        await api("/backups/delete?name=" + encodeURIComponent(backup.name), { method: "POST" });
        showToast(t("bk.deleted"), "green");
        loadBackups();
    } catch (error) {
        if (error.message !== "auth") showToast(error.message, "red");
    }
}
