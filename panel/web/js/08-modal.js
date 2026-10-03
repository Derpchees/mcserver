// ============================================================
// Modal
// ============================================================

let modalResolve = null;


function openModal(options) {

    $("modalTitle").textContent = options.title || "";
    $("modalHint").textContent = options.hint || "";
    $("modalBox").classList.toggle("wide", !!options.wide);
    $("modalBox").classList.toggle("player-modal", options.cls === "player-modal");
    $("modalCancel").hidden = !!options.hideCancel;

    const body = $("modalBody");
    body.textContent = "";
    (options.body || []).forEach(function(node) {
        body.append(typeof node === "string" ? el("div", "", node) : node);
    });

    const ok = $("modalOk");
    ok.textContent = options.okText || t("modal.ok");
    ok.className = "btn btn-small " + (options.okClass || (options.danger ? "btn-danger" : "btn-start"));
    ok.onclick = function() {
        const value = options.onOk ? options.onOk() : true;
        if (value === false) return;
        closeModal(value);
    };

    $("modal").hidden = false;

    const focus = body.querySelector("input, textarea");
    setTimeout(function() {
        (focus || ok).focus();
    }, 30);

    return new Promise(function(resolve) {
        modalResolve = resolve;
    });
}


function closeModal(value) {

    if ($("modal").hidden) return;

    $("modal").hidden = true;

    if (modalResolve) {
        const resolve = modalResolve;
        modalResolve = null;
        resolve(value === undefined ? null : value);
    }
}


function askText(title, label, value, okText) {

    const input = el("input", "input");
    input.value = value || "";
    input.onkeydown = function(event) {
        if (event.key === "Enter") $("modalOk").click();
    };

    return openModal({
        title: title,
        body: [label, input],
        okText: okText,
        onOk: function() {
            return input.value.trim() || false;
        }
    });
}


function confirmDialog(title, message, okText) {
    return openModal({
        title: title,
        body: [message],
        okText: okText || t("modal.delete"),
        danger: true
    });
}


document.addEventListener("keydown", function(event) {
    if (event.key === "Escape") closeModal();
});
