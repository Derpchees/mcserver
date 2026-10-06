// ============================================================
// Ajustes: controles (interruptores, botones de opcion y atajos)
// ============================================================
//
// Envuelven los controles normales (checkbox, select, numero) sin cambiar
// como se leen: el resto del codigo sigue usando .checked y .value, y los
// cambios disparan input/change como si la persona los hubiera hecho.

function fireChange(node) {
    node.dispatchEvent(new Event("input", { bubbles: true }));
    node.dispatchEvent(new Event("change", { bubbles: true }));
}


// Casilla con forma de interruptor
function toggleInput(id, checked) {
    const box = el("input", "toggle");
    box.type = "checkbox";
    box.id = id;
    box.checked = !!checked;
    box.setAttribute("role", "switch");
    return box;
}


// Fila con titulo y descripcion a la izquierda y el control a la derecha.
// Solo con un interruptor es <label> (tocar el texto lo cambia): con
// botones dentro, un <label> haria clic en el primero.
function settingRow(label, desc, control) {
    const toggle = control.tagName === "INPUT" && control.type === "checkbox";
    const row = el(toggle ? "label" : "div", "set-row cfg-row");
    const text = el("div", "set-text");
    text.append(el("div", "set-label", label));
    if (desc) text.append(el("div", "set-desc", desc));
    row.append(text, control);
    return row;
}


// Un select con pocas opciones se ve como botones juntos (el select queda oculto)
function segmentedFromSelect(select, labels) {

    const wrap = el("div", "segmented");
    wrap.setAttribute("role", "radiogroup");
    select.hidden = true;

    const mark = function() {
        wrap.querySelectorAll(".seg-btn").forEach(function(btn) {
            const on = btn.dataset.value === select.value;
            btn.classList.toggle("active", on);
            btn.setAttribute("aria-checked", on ? "true" : "false");
        });
    };

    Array.from(select.options).forEach(function(option) {
        const btn = el("button", "seg-btn", (labels && labels[option.value]) || option.textContent);
        btn.type = "button";
        btn.dataset.value = option.value;
        btn.setAttribute("role", "radio");
        btn.onclick = function(event) {
            event.preventDefault();
            if (select.disabled || select.value === option.value) return;
            select.value = option.value;
            mark();
            fireChange(select);
        };
        wrap.append(btn);
    });

    // Si el codigo cambia el valor o lo desactiva, los botones lo siguen
    select.addEventListener("change", mark);
    new MutationObserver(function() {
        wrap.classList.toggle("disabled", select.disabled);
    }).observe(select, { attributes: true, attributeFilter: ["disabled"] });

    wrap.append(select);
    mark();
    return wrap;
}


// Botones de valores comunes junto a un numero (por ejemplo 5, 10, 15 minutos)
function quickPicks(input, values, format) {

    const row = el("div", "quick-picks");

    const mark = function() {
        row.querySelectorAll(".quick-pick").forEach(function(btn) {
            btn.classList.toggle("active", btn.dataset.value === String(input.value));
        });
    };

    values.forEach(function(value) {
        const btn = el("button", "quick-pick", format(value));
        btn.type = "button";
        btn.dataset.value = String(value);
        btn.onclick = function(event) {
            event.preventDefault();
            if (input.disabled) return;
            input.value = value;
            mark();
            fireChange(input);
        };
        row.append(btn);
    });

    input.addEventListener("input", mark);
    row.append(input);
    mark();
    return row;
}
