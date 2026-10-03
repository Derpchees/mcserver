// ============================================================
// Doble confirmacion para borrar
// ============================================================

async function doubleConfirm(options) {

    // Paso 1: que se va a borrar y opciones
    const body1 = [options.description];
    const checks = {};

    (options.choices || []).forEach(function([key, label]) {
        const wrap = el("label", "un-check");
        const box = el("input");
        box.type = "checkbox";
        checks[key] = box;
        wrap.append(box, document.createTextNode(" " + label));
        body1.push(wrap);
    });

    const first = await openModal({
        title: options.title,
        body: body1,
        okText: t("dc.continue"),
        danger: true
    });

    if (!first) return null;

    const picked = {};
    Object.keys(checks).forEach(function(key) { picked[key] = checks[key].checked; });

    // Paso 2: ultima advertencia, casilla y texto exacto
    const understandWrap = el("label", "un-check");
    const understand = el("input");
    understand.type = "checkbox";
    understandWrap.append(understand, document.createTextNode(" " + t("dc.understand")));

    const input = el("input", "input");
    input.placeholder = options.word;
    input.autocomplete = "off";

    const summary = el("div", "dc-summary is-red", t("dc.final"));

    const promise = openModal({
        title: t("dc.finalTitle"),
        body: [summary, understandWrap, t("dc.typeWord", { word: options.word }), input],
        okText: options.okText,
        danger: true,
        onOk: function() {
            return understand.checked && input.value.trim() === options.word ? true : false;
        }
    });

    const ok = $("modalOk");
    const refresh = function() {
        ok.disabled = !(understand.checked && input.value.trim() === options.word);
    };

    understand.onchange = refresh;
    input.oninput = refresh;
    refresh();

    const confirmed = await promise;
    ok.disabled = false;

    if (!confirmed) return null;

    return Object.assign({ understand: true, confirm: input.value.trim() }, picked);
}
