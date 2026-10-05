// ============================================================
// Sesiones activas (pagina de la cuenta)
// ============================================================

async function loadSessions() {

    const list = $("sessionList");

    try {
        const data = await api("/me/sessions?t=" + Date.now());
        renderSessions(data.sessions || []);
    } catch (error) {
        if (error.message !== "auth") {
            list.textContent = "";
            list.append(el("div", "list-empty", t("login.noConnection")));
        }
    }
}


function renderSessions(sessions) {

    const list = $("sessionList");
    list.textContent = "";

    $("sessionsEndOthers").hidden = !sessions.some(function(s) { return !s.current; });

    sessions.forEach(function(session) {

        const row = el("div", "adm-row");
        const text = el("div");
        const name = el("div", "adm-name", session.device || t("ses.unknownDevice"));

        if (session.current) name.append(el("span", "tag green", t("ses.current")));
        if (session.remember) name.append(el("span", "tag", t("ses.remembered")));

        const when = new Date(session.last_seen * 1000).toLocaleString(locale(), { dateStyle: "medium", timeStyle: "short" });
        text.append(name, el("div", "pl-sub", t("ses.meta", { ip: session.ip || "?", when: when })));

        const actions = el("div", "pl-actions");

        if (!session.current) {
            const end = el("button", "btn btn-ghost btn-small", t("ses.end"));
            end.onclick = async function() {
                try {
                    await postJson("/me/sessions/end", { id: session.id });
                    loadSessions();
                } catch (error) {
                    showToast(error.message, "red");
                }
            };
            actions.append(end);
        }

        row.append(text, actions);
        list.append(row);
    });
}


async function endOtherSessions() {

    const ok = await confirmDialog(t("ses.endOthers"), t("ses.endOthersDesc"), t("ses.endOthers"));
    if (!ok) return;

    try {
        await postJson("/me/sessions/end-others", {});
        showToast(t("ses.endedOthers"), "green");
        loadSessions();
    } catch (error) {
        showToast(error.message, "red");
    }
}
